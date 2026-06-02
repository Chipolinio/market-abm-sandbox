# Назначение файла: RED-тесты слайса 5.4 — векторизованный инференс и anti-stagnation (Spec 005 §4.4, §4.5, §12.5).
# Базовая идея: predict_next_prices ≤2 вызова predict, exp+clip к [p_min, p_max], RatingMaximizer no-op;
# apply_price_exploration — чистый stochastic-трансформер (gaussian_log) с детерминизмом по rng;
# apply_ml_repricing_tick — векторное зеркало apply_repricing_tick (без row-loop, маска repricing_speed, p_min).
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.ml_repricing import (
    CatBoostRepricingConfig,
    ExplorationConfig,
    V1_FEATURE_NAMES,
)
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import (
    COL_CAPITAL,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PLATFORM_DEFAULTS,
)

# --- SUT (ещё не существует → RED на импорте) ---
from market_abm.ml.catboost_repricing import CatBoostModelRegistry
from market_abm.ml.catboost_repricing import predict_next_prices
from market_abm.ml.exploration import apply_price_exploration
from market_abm.simulation.repricing import apply_ml_repricing_tick

pytestmark = pytest.mark.ml

# Совокупная комиссия платформы для расчёта эталонного p_min (см. min_price_from_margin, 002).
_TOTAL_FEES = PLATFORM_DEFAULTS["base_commission"] + PLATFORM_DEFAULTS["logistic_fee"]


# --- Поддельная модель: считает вызовы predict, возвращает константный y_hat (log-delta) ---


class _FakeModel:
    """Заглушка CatBoostRegressor: фиксированный прогноз log-дельты + счётчик вызовов predict."""

    def __init__(self, y_value: float = 0.0) -> None:
        self.y_value = y_value
        self.call_count = 0

    def predict(self, x: np.ndarray) -> np.ndarray:
        self.call_count += 1
        return np.full(np.asarray(x).shape[0], self.y_value, dtype=np.float64)


def _fake_registry(*, y_value: float = 0.0) -> CatBoostModelRegistry:
    return CatBoostModelRegistry(
        models={"MaxProfit": _FakeModel(y_value), "MaxVolume": _FakeModel(y_value)},
        feature_names=V1_FEATURE_NAMES,
        train_config_hash="sha256:test",
    )


def _features_df(
    *,
    n: int,
    seed: int = 0,
    strategy_pool: tuple[str, ...] = ("MaxProfit", "MaxVolume"),
    price_override: np.ndarray | None = None,
) -> pl.DataFrame:
    """Синтетический features_df строго в EXPECTED_COLUMNS (§5.1.3): 3 ключа + 15 фич, sorted listing_id."""
    rng = np.random.default_rng(seed)
    listing_id = np.arange(n, dtype=np.int32)
    seller_id = np.arange(n, dtype=np.int32)
    strategy = np.array([strategy_pool[i % len(strategy_pool)] for i in range(n)])

    if price_override is not None:
        price = np.asarray(price_override, dtype=np.float32)
    else:
        price = (100.0 + rng.normal(0.0, 5.0, n)).astype(np.float32)
    unit_cost = (price * 0.5).astype(np.float32)
    margin_floor = np.full(n, 0.1, dtype=np.float32)
    capital = np.full(n, 1000.0, dtype=np.float32)
    demand_index = np.ones(n, dtype=np.float32)

    # Порядок ключей дублирует §5.1.3; фичи — ровно V1_FEATURE_NAMES.
    data: dict[str, object] = {
        COL_LISTING_ID: listing_id,
        COL_SELLER_ID: seller_id,
        COL_STRATEGY_TYPE: strategy,
        "price": price,
        "unit_cost": unit_cost,
        "demand_index": demand_index,
        "margin_floor": margin_floor,
        "capital": capital,
        "lag_gmv_seller_1": np.zeros(n),
        "lag_tx_count_seller_1": np.zeros(n),
        "roll_mean_price_listing_5": price.astype(np.float64),
        "roll_tx_count_listing_5": np.zeros(n),
        "market_mean_price_lag_1": price.astype(np.float64),
        "competitor_mean_price_lag_1": price.astype(np.float64),
        "competitor_price_gap": np.zeros(n),
        "competitor_price_change_flag": np.zeros(n),
        "ticks_since_own_price_change": np.zeros(n),
        "tick_id": np.zeros(n, dtype=np.int32),
    }
    return (
        pl.DataFrame(data)
        .with_columns(
            pl.col(COL_LISTING_ID).cast(pl.Int32),
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
            pl.col("price").cast(pl.Float32),
            pl.col("unit_cost").cast(pl.Float32),
            pl.col("demand_index").cast(pl.Float32),
            pl.col("margin_floor").cast(pl.Float32),
            pl.col("capital").cast(pl.Float32),
        )
        .sort(COL_LISTING_ID)
    )


def _sellers_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: [0, 1, 2],
            COL_STRATEGY_TYPE: ["MaxProfit", "MaxVolume", "RatingMaximizer"],
            COL_CAPITAL: [1000.0, 1000.0, 1000.0],
            COL_MARGIN_FLOOR: [0.1, 0.1, 0.1],
            COL_REPRICING_SPEED: [1, 1, 1],
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col(COL_CAPITAL).cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings_df() -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                COL_LISTING_ID: [0, 1, 2],
                COL_SELLER_ID: [0, 1, 2],
                COL_UNIT_COST: [50.0, 50.0, 50.0],
                COL_PRICE: [100.0, 100.0, 100.0],
                COL_DEMAND_INDEX: [1.0, 1.0, 1.0],
            }
        )
        .with_columns(
            pl.col(COL_LISTING_ID).cast(pl.Int32),
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_UNIT_COST).cast(pl.Float32),
            pl.col(COL_PRICE).cast(pl.Float32),
            pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        )
        .sort(COL_LISTING_ID)
    )


def _expected_p_min(unit_cost: float, margin_floor: float) -> float:
    return unit_cost / (1.0 - margin_floor - _TOTAL_FEES)


# --- 5.4-T1 ---


def test_predict_output_shape_and_dtype() -> None:
    n = 20
    features = _features_df(n=n)
    current = features[COL_PRICE].to_numpy().astype(np.float32)
    out = predict_next_prices(
        _fake_registry(y_value=0.0),
        features,
        current_prices=current,
        config=CatBoostRepricingConfig(),
        rng=np.random.default_rng(7),
    )
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.shape == (n,)
    assert np.all(np.isfinite(out))


# --- 5.4-T2 ---


def test_predict_call_count_bounded() -> None:
    features = _features_df(n=30)  # обе стратегии присутствуют
    registry = _fake_registry(y_value=0.01)
    current = features[COL_PRICE].to_numpy().astype(np.float32)

    predict_next_prices(
        registry,
        features,
        current_prices=current,
        config=CatBoostRepricingConfig(),
        rng=np.random.default_rng(1),
    )

    total_calls = sum(model.call_count for model in registry.models.values())
    assert total_calls <= 2  # V1: ≤ S вызовов (S = число активных стратегий)
    for model in registry.models.values():
        assert model.call_count <= 1  # ровно один вызов на стратегию, не на строку


# --- 5.4-T3 ---


def test_rating_maximizer_unchanged_prices() -> None:
    features = _features_df(
        n=30, strategy_pool=("MaxProfit", "MaxVolume", "RatingMaximizer")
    )
    current = features[COL_PRICE].to_numpy().astype(np.float32)
    out = predict_next_prices(
        _fake_registry(y_value=0.5),  # ML-строки заметно сдвинут
        features,
        current_prices=current,
        config=CatBoostRepricingConfig(),
        rng=np.random.default_rng(3),
    )

    strategy = features[COL_STRATEGY_TYPE].cast(pl.String).to_numpy()
    rm_mask = strategy == "RatingMaximizer"

    assert np.array_equal(out[rm_mask], current[rm_mask])  # RM строго no-op
    assert np.any(out[~rm_mask] != current[~rm_mask])  # ML-строки изменены


# --- 5.4-T4 ---


def test_predict_respects_max_price_multiplier() -> None:
    features = _features_df(n=40)
    config = CatBoostRepricingConfig()  # max_price_multiplier = 3.0
    current = features[COL_PRICE].to_numpy().astype(np.float32)
    out = predict_next_prices(
        _fake_registry(y_value=5.0),  # exp(5) улетает вверх → должен сработать верхний клип
        features,
        current_prices=current,
        config=config,
        rng=np.random.default_rng(4),
    )

    upper = config.max_price_multiplier * current
    assert np.all(out <= upper + 1e-3)


# --- 5.4-T5 ---


def test_apply_ml_repricing_tick_no_python_row_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = _listings_df()
    sellers = _sellers_df()

    # next_prices выровнены по sorted listing_id:
    #   l0 (MaxProfit) → 110.0 (активно, выше пола)
    #   l1 (MaxVolume) → 0.01  (ниже пола → должен подняться до p_min)
    #   l2 (RatingMaximizer) → 130.0 (но RM no-op → останется 100.0)
    next_prices = np.array([110.0, 0.01, 130.0], dtype=np.float32)

    calls = {"n": 0}
    real_map_elements = pl.Expr.map_elements
    real_map_rows = pl.DataFrame.map_rows

    def _spy_map_elements(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_map_elements(self, *args, **kwargs)

    def _spy_map_rows(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_map_rows(self, *args, **kwargs)

    monkeypatch.setattr(pl.Expr, "map_elements", _spy_map_elements)
    monkeypatch.setattr(pl.DataFrame, "map_rows", _spy_map_rows)

    out = apply_ml_repricing_tick(
        sellers,
        listings,
        next_prices=next_prices,
        tick=1,
        config=RepricingConfig.default_market(),
    )

    assert calls["n"] == 0  # V2: без row-wise цикла
    assert tuple(out.columns) == LISTINGS_COLUMNS
    assert out.height == listings.height

    by_id = {row[COL_LISTING_ID]: row[COL_PRICE] for row in out.iter_rows(named=True)}
    p_min_l1 = _expected_p_min(50.0, 0.1)
    assert by_id[0] == pytest.approx(110.0, abs=1e-3)  # применено
    assert by_id[1] == pytest.approx(p_min_l1, abs=1e-2)  # подтянуто до p_min
    assert by_id[2] == pytest.approx(100.0, abs=1e-3)  # RM no-op


# --- 5.4-T6 ---


def test_exploration_changes_price_under_seed() -> None:
    n = 50
    base = np.full(n, 100.0, dtype=np.float32)
    p_min = np.full(n, 50.0, dtype=np.float32)
    p_max = np.full(n, 300.0, dtype=np.float32)
    config = ExplorationConfig()  # gaussian_log, sigma = 0.02

    out1 = apply_price_exploration(
        base, config, np.random.default_rng(123), p_min, p_max
    )
    assert out1.shape == (n,)
    assert np.any(out1 != base)  # ≥1 цена изменилась
    assert np.all(out1 >= p_min - 1e-6)
    assert np.all(out1 <= p_max + 1e-6)

    # Детерминизм: тот же seed → тот же выход.
    out2 = apply_price_exploration(
        base, config, np.random.default_rng(123), p_min, p_max
    )
    assert np.array_equal(out1, out2)

    # Иной seed → расхождение.
    out3 = apply_price_exploration(
        base, config, np.random.default_rng(999), p_min, p_max
    )
    assert np.any(out1 != out3)

    # Жёсткие рамки клипа соблюдаются даже при узких границах.
    tight_min = base * 0.999
    tight_max = base * 1.001
    out_tight = apply_price_exploration(
        base, config, np.random.default_rng(5), tight_min, tight_max
    )
    assert np.all(out_tight >= tight_min - 1e-6)
    assert np.all(out_tight <= tight_max + 1e-6)


# --- 5.4-T7 ---


def test_no_price_stagnation_over_30_ticks() -> None:
    n = 5
    config = CatBoostRepricingConfig()
    registry = _fake_registry(y_value=0.0)  # «мёртвый ноль»: модель не двигает цену

    current = _features_df(n=n, strategy_pool=("MaxProfit",))[COL_PRICE].to_numpy().astype(
        np.float32
    )
    history = [current.copy()]
    seed = 2026

    for tick in range(30):
        feats = _features_df(
            n=n, strategy_pool=("MaxProfit",), price_override=current
        )
        rng = np.random.default_rng(np.random.SeedSequence([seed, tick, 0xE5910E]))
        current = predict_next_prices(
            registry,
            feats,
            current_prices=current,
            config=config,
            rng=rng,
        )
        history.append(np.asarray(current).copy())

    series = np.stack(history)  # shape (31, n)
    per_listing_std = series.std(axis=0)
    assert np.all(per_listing_std > 1e-3)  # exploration снимает стагнацию даже при y_hat≡0
