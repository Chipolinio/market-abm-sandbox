# Назначение файла: CQRS query-side — SQL-метрики поверх Parquet-артефактов прогона.
# Базовая идея: DuckDB read_parquet(glob); без pl.read_parquet и без мутации run_root.
from __future__ import annotations

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

    def _transactions_glob(self) -> str:
        return str(self._run_root / "transactions" / "tick_*.parquet")

    def _products_glob(self) -> str:
        return str(self._run_root / "products_snapshots" / "tick_*.parquet")

    def _has_parquet_files(self, subdir: str) -> bool:
        return any((self._run_root / subdir).glob("tick_*.parquet"))

    def _query_pl(self, sql: str, params: list[object]) -> pl.DataFrame:
        """Выполняет SQL и возвращает Polars через Arrow (не pl.read_parquet)."""
        return self._con.execute(sql, params).pl()

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
                AVG(price)::DOUBLE AS mean_price,
                MEDIAN(price)::DOUBLE AS median_price,
                quantile_cont(price, 0.10)::DOUBLE AS p10_price,
                quantile_cont(price, 0.90)::DOUBLE AS p90_price
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
