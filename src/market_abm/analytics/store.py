# Назначение файла: CQRS query-side — SQL-метрики поверх Parquet-артефактов прогона.
# Базовая идея: DuckDB read_parquet(glob); без pl.read_parquet и без мутации run_root.
from __future__ import annotations

import json
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
        if not manifest.is_file():
            raise FileNotFoundError(f"Run directory not found or missing manifest: {run_root}")
        self._con = duckdb.connect()
        self._con.execute(f"SET memory_limit='{memory_limit}'")

    def close(self) -> None:
        """Закрывает DuckDB-соединение."""
        self._con.close()

    def drift_alerts(self) -> list[dict[str, object]]:
        """Query-сторона: читает manifest['drift_alerts'] (Spec 005 §10.4)."""
        manifest = json.loads((self._run_root / "manifest.json").read_text(encoding="utf-8"))
        return list(manifest.get("drift_alerts", []))

    def _transactions_glob(self) -> str:
        return str(self._run_root / "transactions" / "tick_*.parquet")

    def _products_glob(self) -> str:
        return str(self._run_root / "products_snapshots" / "tick_*.parquet")

    def _has_parquet_files(self, subdir: str) -> bool:
        return any((self._run_root / subdir).glob("tick_*.parquet"))

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

        sql = """
            SELECT
                tick_id,
                SUM(price_paid)::DOUBLE AS gmv,
                COUNT(*)::BIGINT AS transaction_count
            FROM read_parquet(?)
            GROUP BY tick_id
            ORDER BY tick_id
        """
        result = self._query_pl(sql, [self._transactions_glob()])
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
        manifest = json.loads((self._run_root / "manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("run_id", self._run_root.name))

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
            sql_tx = """
                SELECT
                    COALESCE(SUM(price_paid)::DOUBLE, 0.0) AS total_gmv,
                    COALESCE(COUNT(*)::BIGINT, 0)          AS total_transactions
                FROM read_parquet(?)
                WHERE tick_id = ?
            """
            row = self._con.cursor().execute(sql_tx, [self._transactions_glob(), tick_id]).fetchone()
            if row is not None:
                total_gmv = float(row[0])
                total_transactions = int(row[1])

        mean_price = 0.0

        if self._has_parquet_files("products_snapshots"):
            sql_price = f"""
                SELECT COALESCE(AVG(price)::DOUBLE, 0.0) AS mean_price
                FROM (
                    SELECT {_TICK_ID_FROM_FILENAME} AS tick_id, price
                    FROM read_parquet(?, filename=true)
                )
                WHERE tick_id = ?
            """
            row = self._con.cursor().execute(sql_price, [self._products_glob(), tick_id]).fetchone()
            if row is not None:
                mean_price = float(row[0])

        price_quantiles = self.query_price_quantiles(tick_id)

        return {
            "mean_price": mean_price,
            "total_gmv": total_gmv,
            "total_transactions": total_transactions,
            "price_quantiles": price_quantiles,
        }

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

        sql = f"""
            SELECT
                {_TICK_ID_FROM_FILENAME} AS tick_id,
                {_PRICE_QUANTILES_AGG}
            FROM read_parquet(?, filename=true)
            GROUP BY tick_id
            ORDER BY tick_id
        """
        result = self._query_pl(sql, [self._products_glob()])
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
