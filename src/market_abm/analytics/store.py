# Назначение файла: CQRS query-side — SQL-метрики поверх Parquet-артефактов прогона.
# Базовая идея: DuckDB read_parquet(glob); без pl.read_parquet и без мутации run_root.
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import polars as pl

from market_abm.domain.constants import (
    COL_LISTING_ID,
    COL_PRICE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
)

_TICK_ID_FROM_FILENAME = (
    "CAST(regexp_extract(filename, 'tick_([0-9]+)', 1) AS INTEGER)"
)

# Общий SQL-фрагмент квантилей цен (Spec 007 §4.1): approx_quantile, не MEDIAN.
_PRICE_QUANTILES_AGG = """
    AVG(price)::DOUBLE AS mean_price,
    approx_quantile(price, 0.5)::DOUBLE AS median_price,
    approx_quantile(price, 0.1)::DOUBLE AS p10_price,
    approx_quantile(price, 0.9)::DOUBLE AS p90_price
"""


class AnalyticsStore:
    """
    Тонкая DuckDB-сессия, привязанная к каталогу одного run_id.
    Читает Parquet лениво через SQL.
    """

    def __init__(self, run_root: Path, *, memory_limit: str = "2GB") -> None:
        self._run_root = Path(run_root)
        manifest = self._run_root / "manifest.json"
        has_parquet = any(self._run_root.glob("**/tick_*.parquet")) or self._has_system_events_files()
        if not manifest.is_file() and not has_parquet:
            raise FileNotFoundError(f"Run directory not found or missing manifest: {run_root}")
        self._con = duckdb.connect()
        self._con.execute(f"SET memory_limit='{memory_limit}'")

    def close(self) -> None:
        """Закрывает DuckDB-соединение."""
        self._con.close()

    def drift_alerts(self) -> list[dict[str, object]]:
        """Query-side: reads manifest['drift_alerts'] (Spec 005 §10.4)."""
        manifest_path = self._run_root / "manifest.json"
        if not manifest_path.is_file():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return list(manifest.get("drift_alerts", []))

    def _transactions_glob(self) -> str:
        return str(self._run_root / "transactions" / "tick_*.parquet")

    def _products_glob(self) -> str:
        return str(self._run_root / "products_snapshots" / "tick_*.parquet")

    def _parquet_files(self, subdir: str, pattern: str = "tick_*.parquet") -> list[str]:
        """Список parquet-файлов с диска — без DuckDB glob cache на long-lived connection."""
        directory = self._run_root / subdir
        if not directory.is_dir():
            return []
        return sorted(str(path) for path in directory.glob(pattern))

    def _transactions_files(self) -> list[str]:
        return self._parquet_files("transactions")

    def _products_files(self) -> list[str]:
        return self._parquet_files("products_snapshots")

    def _read_parquet_arg(self, files: list[str]) -> str | list[str]:
        if not files:
            return []
        return files[0] if len(files) == 1 else files

    def _has_parquet_files(self, subdir: str) -> bool:
        return any((self._run_root / subdir).glob("tick_*.parquet"))

    def _has_system_events_files(self) -> bool:
        events_dir = self._run_root / "system_events"
        if not events_dir.is_dir():
            return False
        return (events_dir / "events.parquet").is_file() or any(
            events_dir.glob("evt_*.parquet")
        )

    def _system_events_read_sources(self) -> list[str]:
        """Parquet-источники system_events (legacy monolith + fragment files)."""
        events_dir = self._run_root / "system_events"
        if not events_dir.is_dir():
            return []
        sources: list[str] = []
        legacy = events_dir / "events.parquet"
        if legacy.is_file():
            sources.append(str(legacy))
        sources.extend(str(path) for path in sorted(events_dir.glob("evt_*.parquet")))
        return sources

    def _query_pl(self, sql: str, params: list[object]) -> pl.DataFrame:
        """Выполняет SQL через изолированный cursor() — thread-safe (§1.2 Spec 006)."""
        return self._con.cursor().execute(sql, params).pl()

    def gmv_by_tick(self) -> pl.DataFrame:
        """tick_id, gmv (Float64), transaction_count (Int64)."""
        schema = {
            COL_TICK_ID: pl.Int32,
            "gmv": pl.Float64,
            "transaction_count": pl.Int64,
        }
        if not self._has_parquet_files("transactions"):
            return pl.DataFrame(schema=schema)

        files = self._transactions_files()
        if not files:
            return pl.DataFrame(schema=schema)

        sql = """
            SELECT
                tick_id,
                SUM(price_paid)::DOUBLE AS gmv,
                COUNT(*)::BIGINT AS transaction_count
            FROM read_parquet(?)
            GROUP BY tick_id
            ORDER BY tick_id
        """
        result = self._query_pl(sql, [self._read_parquet_arg(files)])
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result.cast(
            {
                COL_TICK_ID: pl.Int32,
                "gmv": pl.Float64,
                "transaction_count": pl.Int64,
            }
        )

    def gross_margin_by_seller(self) -> pl.DataFrame:
        """seller_id, total_gross_margin, avg_gross_margin, transaction_count."""
        schema = {
            COL_SELLER_ID: pl.Int32,
            "total_gross_margin": pl.Float64,
            "avg_gross_margin": pl.Float64,
            "transaction_count": pl.Int64,
        }
        if not self._has_parquet_files("transactions"):
            return pl.DataFrame(schema=schema)

        sql = """
            SELECT
                seller_id,
                SUM(gross_margin)::DOUBLE AS total_gross_margin,
                AVG(gross_margin)::DOUBLE AS avg_gross_margin,
                COUNT(*)::BIGINT AS transaction_count
            FROM read_parquet(?)
            GROUP BY seller_id
            ORDER BY seller_id
        """
        result = self._query_pl(sql, [self._transactions_glob()])
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result.cast(
            {
                COL_SELLER_ID: pl.Int32,
                "total_gross_margin": pl.Float64,
                "avg_gross_margin": pl.Float64,
                "transaction_count": pl.Int64,
            }
        )

    def avg_price_by_listing_over_time(self) -> pl.DataFrame:
        """tick_id, listing_id, seller_id, price — из products_snapshots."""
        schema = {
            COL_TICK_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_PRICE: pl.Float64,
        }
        if not self._has_parquet_files("products_snapshots"):
            return pl.DataFrame(schema=schema)

        sql = f"""
            SELECT
                {_TICK_ID_FROM_FILENAME} AS tick_id,
                listing_id,
                seller_id,
                price::DOUBLE AS price
            FROM read_parquet(?, filename=true)
            ORDER BY tick_id, listing_id
        """
        result = self._query_pl(sql, [self._products_glob()])
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result.cast(
            {
                COL_TICK_ID: pl.Int32,
                COL_LISTING_ID: pl.Int32,
                COL_SELLER_ID: pl.Int32,
                COL_PRICE: pl.Float64,
            }
        )

    def products_snapshot_at_tick(self, tick_id: int) -> pl.DataFrame:
        """Полный products-срез одного тика (operational listings для bootstrap, §5.2)."""
        schema = {
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_UNIT_COST: pl.Float64,
            COL_PRICE: pl.Float64,
            "demand_index": pl.Float64,
        }
        if not self._has_parquet_files("products_snapshots"):
            return pl.DataFrame(schema=schema)

        sql = f"""
            SELECT listing_id, seller_id, unit_cost, price, demand_index FROM (
                SELECT
                    {_TICK_ID_FROM_FILENAME} AS tick_id,
                    listing_id,
                    seller_id,
                    unit_cost::DOUBLE AS unit_cost,
                    price::DOUBLE AS price,
                    demand_index::DOUBLE AS demand_index
                FROM read_parquet(?, filename=true)
            )
            WHERE tick_id = ?
            ORDER BY listing_id
        """
        result = self._query_pl(sql, [self._products_glob(), tick_id])
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result

    def _run_id_from_manifest(self) -> str:
        manifest_path = self._run_root / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return str(manifest.get("run_id", self._run_root.name))
        return self._run_root.name

    def query_price_quantiles(self, tick_id: int) -> dict[str, float] | None:
        """
        Квантили цен одного тика для WS/REST (approx_quantile).
        None — если snapshot пуст или тик отсутствует.
        """
        if not self._has_parquet_files("products_snapshots"):
            return None

        sql = f"""
            SELECT
                {_PRICE_QUANTILES_AGG}
            FROM (
                SELECT {_TICK_ID_FROM_FILENAME} AS tick_id, price
                FROM read_parquet(?, filename=true)
            )
            WHERE tick_id = ?
        """
        row = self._con.cursor().execute(sql, [self._products_glob(), tick_id]).fetchone()
        if row is None or row[0] is None:
            return None

        p10, p50, p90 = row[2], row[1], row[3]
        if p10 is None or p50 is None or p90 is None:
            return None

        return {"p10": float(p10), "p50": float(p50), "p90": float(p90)}

    def query_market_aggregate(self, tick_id: int) -> dict[str, object]:
        """
        Агрегаты одного тика для WebSocket-стрима (broadcaster_loop, §5.2 Spec 006).

        Использует изолированные cursor() — безопасен при конкурентных вызовах из
        нескольких asyncio-корутин или потоков (§1.2 Spec 006).
        Все значения приводятся к нативным Python float/int для Pydantic (§4.3 Spec 006).
        При отсутствии данных возвращает нули — исключения не бросает.
        """
        total_gmv = 0.0
        total_transactions = 0

        if self._has_parquet_files("transactions"):
            tx_files = self._transactions_files()
            if tx_files:
                sql_tx = """
                    SELECT
                        COALESCE(SUM(price_paid)::DOUBLE, 0.0) AS total_gmv,
                        COALESCE(COUNT(*)::BIGINT, 0)          AS total_transactions
                    FROM read_parquet(?)
                    WHERE tick_id = ?
                """
                row = self._con.cursor().execute(
                    sql_tx,
                    [self._read_parquet_arg(tx_files), tick_id],
                ).fetchone()
                if row is not None:
                    total_gmv = float(row[0])
                    total_transactions = int(row[1])

        mean_price = 0.0

        if self._has_parquet_files("products_snapshots"):
            product_files = self._products_files()
            if product_files:
                sql_price = f"""
                    SELECT COALESCE(AVG(price)::DOUBLE, 0.0) AS mean_price
                    FROM (
                        SELECT {_TICK_ID_FROM_FILENAME} AS tick_id, price
                        FROM read_parquet(?, filename=true)
                    )
                    WHERE tick_id = ?
                """
                row = self._con.cursor().execute(
                    sql_price,
                    [self._read_parquet_arg(product_files), tick_id],
                ).fetchone()
                if row is not None:
                    mean_price = float(row[0])

        price_quantiles = self.query_price_quantiles(tick_id)

        return {
            "mean_price": mean_price,
            "total_gmv": total_gmv,
            "total_transactions": total_transactions,
            "price_quantiles": price_quantiles,
        }

    def top_listings_metrics(self, limit: int = 10) -> pl.DataFrame:
        """
        Топ-N listing_id по суммарному GMV; per-tick price, gmv, volume (Slice 7.7).
        Пустой DataFrame при отсутствии Parquet.
        """
        schema = {
            COL_TICK_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_PRICE: pl.Float64,
            "gmv": pl.Float64,
            "volume": pl.Int64,
        }
        if not self._has_parquet_files("transactions") or not self._has_parquet_files(
            "products_snapshots"
        ):
            return pl.DataFrame(schema=schema)

        sql = f"""
            WITH listing_rank AS (
                SELECT
                    listing_id,
                    MAX(seller_id)::INTEGER AS seller_id,
                    SUM(price_paid)::DOUBLE AS total_gmv
                FROM read_parquet(?)
                GROUP BY listing_id
                ORDER BY total_gmv DESC
                LIMIT ?
            ),
            tx_tick AS (
                SELECT
                    tick_id,
                    listing_id,
                    SUM(price_paid)::DOUBLE AS gmv,
                    COUNT(*)::BIGINT AS volume
                FROM read_parquet(?)
                GROUP BY tick_id, listing_id
            ),
            prices AS (
                SELECT
                    {_TICK_ID_FROM_FILENAME} AS tick_id,
                    listing_id,
                    price::DOUBLE AS price
                FROM read_parquet(?, filename=true)
            )
            SELECT
                p.tick_id,
                lr.listing_id,
                lr.seller_id,
                p.price,
                COALESCE(t.gmv, 0.0) AS gmv,
                COALESCE(t.volume, 0)::BIGINT AS volume
            FROM listing_rank lr
            INNER JOIN prices p ON p.listing_id = lr.listing_id
            LEFT JOIN tx_tick t
                ON t.tick_id = p.tick_id AND t.listing_id = lr.listing_id
            ORDER BY lr.listing_id, p.tick_id
        """
        result = self._query_pl(
            sql,
            [
                self._transactions_glob(),
                limit,
                self._transactions_glob(),
                self._products_glob(),
            ],
        )
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result.cast(
            {
                COL_TICK_ID: pl.Int32,
                COL_LISTING_ID: pl.Int32,
                COL_SELLER_ID: pl.Int32,
                COL_PRICE: pl.Float64,
                "gmv": pl.Float64,
                "volume": pl.Int64,
            }
        )

    def recent_system_events(self, limit: int = 50) -> list[dict[str, object]]:
        """Последние system_events для WS broadcaster и REST backfill."""
        sources = self._system_events_read_sources()
        if not sources:
            return []

        last_error: Exception | None = None
        for attempt in range(5):
            try:
                return self._recent_system_events_from_sources(sources, limit)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < 4:
                    time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            return []
        return []

    def system_events_since(
        self,
        since_tick: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        """События с tick_id >= since_tick (ASC) — инкрементальный poll cyber-log."""
        sources = self._system_events_read_sources()
        if not sources:
            return []

        read_arg = self._read_parquet_arg(sources)
        if not read_arg:
            return []

        df = self._query_pl(
            """
            SELECT *
            FROM read_parquet(?)
            WHERE tick_id >= ?
            ORDER BY tick_id ASC, event_id ASC
            LIMIT ?
            """,
            [read_arg, since_tick, limit],
        )
        return self._rows_from_events_df(df)

    def _rows_from_events_df(self, df: pl.DataFrame) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row in df.iter_rows(named=True):
            raw_payload = row.get("payload_json")
            payload: dict[str, object] = {}
            if raw_payload:
                payload = json.loads(str(raw_payload))
            rows.append(
                {
                    "event_id": str(row["event_id"]),
                    "tick_id": int(row["tick_id"]),
                    "event_type": str(row["event_type"]),
                    "display_code": str(row["display_code"]),
                    "severity": str(row["severity"]),
                    "message": str(row["message"]),
                    "payload": payload,
                }
            )
        return rows

    def _recent_system_events_from_sources(
        self,
        sources: list[str],
        limit: int,
    ) -> list[dict[str, object]]:
        read_arg = self._read_parquet_arg(sources)
        if not read_arg:
            return []
        df = self._query_pl(
            """
            SELECT *
            FROM read_parquet(?)
            ORDER BY tick_id DESC, event_id DESC
            LIMIT ?
            """,
            [read_arg, limit],
        )
        return self._rows_from_events_df(df)

    def price_index_by_tick(self) -> pl.DataFrame:
        """Агрегированные цены по тику; nullable Float64 при пустом snapshot."""
        schema = {
            COL_TICK_ID: pl.Int32,
            "mean_price": pl.Float64,
            "median_price": pl.Float64,
            "p10_price": pl.Float64,
            "p90_price": pl.Float64,
        }
        if not self._has_parquet_files("products_snapshots"):
            return pl.DataFrame(schema=schema)

        product_files = self._products_files()
        if not product_files:
            return pl.DataFrame(schema=schema)

        sql = f"""
            SELECT
                {_TICK_ID_FROM_FILENAME} AS tick_id,
                {_PRICE_QUANTILES_AGG}
            FROM read_parquet(?, filename=true)
            GROUP BY tick_id
            ORDER BY tick_id
        """
        result = self._query_pl(sql, [self._read_parquet_arg(product_files)])
        if result.height == 0:
            return pl.DataFrame(schema=schema)
        return result.cast(
            {
                COL_TICK_ID: pl.Int32,
                "mean_price": pl.Float64,
                "median_price": pl.Float64,
                "p10_price": pl.Float64,
                "p90_price": pl.Float64,
            }
        )
