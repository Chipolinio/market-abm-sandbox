# Назначение файла: тесты слайса 6.4 — thread-safety DuckDB и метод query_market_aggregate.
# Базовая идея: _query_pl обязан использовать cursor() для изоляции потоков;
# query_market_aggregate возвращает нативные Python-скаляры для Pydantic-совместимости.
from __future__ import annotations

import threading
from pathlib import Path

import polars as pl
import pytest

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from tests.helpers.reference_snapshots import stub_buyers_df, stub_sellers_df
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
    PRODUCTS_COLUMNS,
    TRANSACTIONS_COLUMNS,
)


# ---------------------------------------------------------------------------
# Python-proxy для отслеживания вызовов cursor() (DuckDB C-extension — read-only атрибуты)
# ---------------------------------------------------------------------------


class _CursorTracker:
    """Python-обёртка над DuckDB-соединением, считающая вызовы cursor().

    DuckDB-соединение — C-extension, его атрибуты read-only → patch.object не работает.
    Решение: заменяем store._con этим объектом после __init__, делегируя все вызовы.
    """

    def __init__(self, real_con: object) -> None:
        self._real = real_con
        self.cursor_call_count = 0

    def cursor(self) -> object:
        self.cursor_call_count += 1
        return self._real.cursor()  # type: ignore[attr-defined]

    def execute(self, sql: str, params: object = None) -> object:
        return self._real.execute(sql, params)  # type: ignore[attr-defined]

    def close(self) -> None:
        self._real.close()  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------


def _run_config(tmp_path: Path, *, run_id: str) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id),
    )


def _tx_row(tick_id: int, price: float = 100.0) -> dict:
    return {
        COL_TICK_ID: tick_id,
        COL_BUYER_ID: 0,
        COL_LISTING_ID: 0,
        COL_SELLER_ID: 0,
        COL_PRICE_PAID: price,
        COL_UNIT_COST: 20.0,
        COL_GROSS_MARGIN: price - 20.0,
    }


def _make_tx(rows: list[dict]) -> pl.DataFrame:
    if not rows:
        schema = {
            COL_TICK_ID: pl.Int32,
            COL_BUYER_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_PRICE_PAID: pl.Float32,
            COL_UNIT_COST: pl.Float32,
            COL_GROSS_MARGIN: pl.Float32,
        }
        return pl.DataFrame({c: [] for c in TRANSACTIONS_COLUMNS}, schema=schema)
    return pl.DataFrame(rows).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )


def _make_products(n: int, *, price: float = 80.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: [price] * n,
            "demand_index": [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col("demand_index").cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


def _build_run(
    tmp_path: Path,
    *,
    run_id: str,
    ticks: list[tuple[pl.DataFrame, pl.DataFrame]],
) -> Path:
    config = _run_config(tmp_path, run_id=run_id)
    buyers = stub_buyers_df([0])
    sellers = stub_sellers_df([0])
    listings = pl.DataFrame({COL_LISTING_ID: [0], COL_SELLER_ID: [0]}).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32), pl.col(COL_SELLER_ID).cast(pl.Int32)
    )
    ctx = init_run_directory(
        config, run_id=run_id, buyers_df=buyers, sellers_df=sellers,
        listings_df=listings, n_ticks=len(ticks),
    )
    con = open_duckdb_connection(config.persistence)
    try:
        for tick_id, (tx, products) in enumerate(ticks):
            persist_tick_artifacts(
                ctx.run_root, tick_id=tick_id, transactions_df=tx,
                products_df=products, config=config.persistence, con=con,
            )
    finally:
        con.close()
    return ctx.run_root


@pytest.fixture()
def store_with_data(tmp_path: Path) -> AnalyticsStore:
    """Store с двумя тиками и реальными Parquet-файлами."""
    run_root = _build_run(
        tmp_path,
        run_id="concurrency-run",
        ticks=[
            (_make_tx([_tx_row(0, 100.0), _tx_row(0, 50.0)]), _make_products(2, price=80.0)),
            (_make_tx([_tx_row(1, 200.0)]), _make_products(2, price=90.0)),
        ],
    )
    store = AnalyticsStore(run_root)
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Блок 1 — Структурные тесты: _query_pl обязан использовать cursor()
# ---------------------------------------------------------------------------


def test_query_pl_uses_cursor_not_raw_execute(store_with_data: AnalyticsStore) -> None:
    """_query_pl должен делегировать выполнение через self._con.cursor(), а не execute()."""
    tracker = _CursorTracker(store_with_data._con)
    store_with_data._con = tracker  # type: ignore[assignment]

    store_with_data.gmv_by_tick()

    assert tracker.cursor_call_count >= 1, (
        "_query_pl must call self._con.cursor() for thread-safe isolation, "
        f"but cursor() was called {tracker.cursor_call_count} times"
    )


def test_each_query_creates_own_cursor(store_with_data: AnalyticsStore) -> None:
    """Два последовательных вызова → минимум два отдельных cursor()."""
    tracker = _CursorTracker(store_with_data._con)
    store_with_data._con = tracker  # type: ignore[assignment]

    store_with_data.gmv_by_tick()
    store_with_data.gmv_by_tick()

    assert tracker.cursor_call_count >= 2, (
        f"Expected cursor() called at least 2 times, got {tracker.cursor_call_count}"
    )


# ---------------------------------------------------------------------------
# Блок 2 — Threading: конкурентный доступ не бросает исключений
# ---------------------------------------------------------------------------


def test_two_threads_concurrent_reads_no_exception(store_with_data: AnalyticsStore) -> None:
    """Два потока одновременно читают разные методы — ни один не должен бросить."""
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def read_gmv() -> None:
        try:
            barrier.wait()
            for _ in range(8):
                store_with_data.gmv_by_tick()
        except Exception as exc:
            errors.append(exc)

    def read_price() -> None:
        try:
            barrier.wait()
            for _ in range(8):
                store_with_data.price_index_by_tick()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=read_gmv), threading.Thread(target=read_price)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"Concurrent reads raised exceptions: {errors}"


def test_five_threads_all_get_consistent_results(store_with_data: AnalyticsStore) -> None:
    """5 потоков конкурентно вызывают gmv_by_tick() — результаты должны совпадать."""
    results: list[pl.DataFrame | None] = [None] * 5
    errors: list[Exception] = []
    barrier = threading.Barrier(5)

    def read(idx: int) -> None:
        try:
            barrier.wait()
            results[idx] = store_with_data.gmv_by_tick()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=read, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"Concurrent reads raised: {errors}"
    reference = results[0]
    assert reference is not None
    for i, df in enumerate(results[1:], start=1):
        assert df is not None
        assert df.equals(reference), f"Thread {i} got different result"


# ---------------------------------------------------------------------------
# Блок 3 — query_market_aggregate: контракт метода
# ---------------------------------------------------------------------------


def test_query_market_aggregate_method_exists(store_with_data: AnalyticsStore) -> None:
    assert hasattr(store_with_data, "query_market_aggregate"), (
        "AnalyticsStore.query_market_aggregate is missing — needed by broadcaster_loop"
    )


def test_query_market_aggregate_returns_dict(store_with_data: AnalyticsStore) -> None:
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert isinstance(result, dict)


def test_query_market_aggregate_required_keys(store_with_data: AnalyticsStore) -> None:
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert "mean_price" in result
    assert "total_gmv" in result
    assert "total_transactions" in result


def test_query_market_aggregate_correct_values(store_with_data: AnalyticsStore) -> None:
    """tick_id=0 → 2 транзакции на 100.0 и 50.0 → gmv=150.0, transactions=2, mean_price=80.0."""
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert result["total_gmv"] == pytest.approx(150.0)
    assert result["total_transactions"] == 2
    assert result["mean_price"] == pytest.approx(80.0)


def test_query_market_aggregate_missing_tick_returns_zeros(store_with_data: AnalyticsStore) -> None:
    """Несуществующий tick_id → нули, не raise, не None."""
    result = store_with_data.query_market_aggregate(tick_id=9999)
    assert result["total_gmv"] == pytest.approx(0.0)
    assert result["total_transactions"] == 0
    assert result["mean_price"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Блок 4 — Маршаллинг типов: нативные Python-скаляры для Pydantic (§4.3 Spec 006)
# ---------------------------------------------------------------------------


def test_mean_price_is_native_float(store_with_data: AnalyticsStore) -> None:
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert type(result["mean_price"]) is float, (
        f"Expected plain Python float, got {type(result['mean_price'])}"
    )


def test_total_gmv_is_native_float(store_with_data: AnalyticsStore) -> None:
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert type(result["total_gmv"]) is float, (
        f"Expected plain Python float, got {type(result['total_gmv'])}"
    )


def test_total_transactions_is_native_int(store_with_data: AnalyticsStore) -> None:
    result = store_with_data.query_market_aggregate(tick_id=0)
    assert type(result["total_transactions"]) is int, (
        f"Expected plain Python int, got {type(result['total_transactions'])}"
    )


def test_result_is_pydantic_compatible(store_with_data: AnalyticsStore) -> None:
    """Результат должен напрямую создавать MarketAggregateDTO без ValidationError."""
    import datetime

    result = store_with_data.query_market_aggregate(tick_id=0)
    dto = MarketAggregateDTO(**result)
    payload = TickStreamPayload(
        tick_id=0,
        timestamp_utc=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        market_summary=dto,
        active_drift_alerts=[],
    )
    serialized = payload.model_dump_json()
    assert '"mean_price"' in serialized


# ---------------------------------------------------------------------------
# Блок 5 — Конкурентный query_market_aggregate
# ---------------------------------------------------------------------------


def test_three_threads_concurrent_query_market_aggregate(store_with_data: AnalyticsStore) -> None:
    """3 потока одновременно вызывают query_market_aggregate(tick_id=0) — без исключений."""
    errors: list[Exception] = []
    results: list[dict | None] = [None] * 3
    barrier = threading.Barrier(3)

    def query(idx: int) -> None:
        try:
            barrier.wait()
            results[idx] = store_with_data.query_market_aggregate(tick_id=0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=query, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"Concurrent query_market_aggregate raised: {errors}"
    for i, r in enumerate(results):
        assert r is not None, f"Thread {i} returned None"
        assert r["total_gmv"] == pytest.approx(150.0), f"Thread {i} got wrong gmv: {r}"
