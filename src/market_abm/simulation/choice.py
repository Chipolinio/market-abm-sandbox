# Назначение файла: выбор оффера покупателем за один шаг симуляции.
# Базовая идея: считаем полезность по beta, softmax и случайный выбор внутри витрины.
from __future__ import annotations

import math
import warnings

import numpy as np
import polars as pl

from market_abm.config.simulation import ChoiceModelConfig
from market_abm.simulation.buyers_baseline import ensure_budget_baseline
from market_abm.domain.constants import (
    BUYERS_CHOICE_INPUT_COLUMNS,
    CHOICES_COLUMNS,
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUYER_ID,
    COL_CHOICE_PROBABILITY,
    COL_DELIVERY_DAYS,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PVD_SEGMENT,
    COL_RATING_VALUE,
    PRODUCTS_CHOICE_FEATURE_COLUMNS,
)


def resolve_outside_utility_bias(
    buyers_batch_df: pl.DataFrame,
    config: ChoiceModelConfig,
) -> np.ndarray:
    """
    Возвращает вектор outside bias длины batch (float32).

    Без mapping — скаляр config.outside_utility_bias на всех.
    С mapping — значение по pvd_segment; неизвестный ключ в строке → скаляр.
    """
    n = buyers_batch_df.height
    if config.outside_utility_bias_by_pvd_segment is None:
        return np.full(n, config.outside_utility_bias, dtype=np.float32)

    if COL_PVD_SEGMENT not in buyers_batch_df.columns:
        raise ValueError(f"buyers_batch_df is missing required column: {COL_PVD_SEGMENT}")

    mapping = config.outside_utility_bias_by_pvd_segment
    scalar = config.outside_utility_bias
    segments = buyers_batch_df[COL_PVD_SEGMENT].to_list()
    result = np.empty(n, dtype=np.float32)
    for i, seg in enumerate(segments):
        key = seg if isinstance(seg, str) else str(seg)
        result[i] = mapping.get(key, scalar)
    return result


def _buyer_seed(base_seed: int, buyer_id: int) -> int:
    """Считает отдельный seed для покупателя из общего seed шага."""
    return int(np.random.SeedSequence([base_seed, buyer_id]).generate_state(1)[0])


def _validate_buyers_batch(buyers_batch_df: pl.DataFrame) -> None:
    missing = [c for c in BUYERS_CHOICE_INPUT_COLUMNS if c not in buyers_batch_df.columns]
    if missing:
        raise ValueError(f"buyers_batch_df is missing required columns: {missing}")
    if buyers_batch_df.height == 0:
        raise ValueError("buyers_batch_df must be non-empty")


def _validate_products(products_df: pl.DataFrame) -> None:
    missing = [c for c in PRODUCTS_CHOICE_FEATURE_COLUMNS if c not in products_df.columns]
    if missing:
        raise ValueError(f"products_df is missing required columns: {missing}")
    if products_df.height == 0:
        raise ValueError("products_df must be non-empty")


def _softmax_row(utilities: np.ndarray) -> np.ndarray:
    """Считает вероятности выбора по одной строке полезностей (-inf → prob 0)."""
    finite = np.isfinite(utilities)
    if not np.any(finite):
        return np.full(utilities.size, 1.0 / utilities.size, dtype=np.float32)
    max_u = np.max(utilities[finite])
    shifted = np.where(finite, utilities - max_u, -np.inf)
    exp_u = np.exp(shifted, dtype=np.float64)
    exp_u = np.where(finite, exp_u, 0.0)
    total = exp_u.sum()
    if total <= 0.0:
        return np.full(utilities.size, 1.0 / utilities.size, dtype=np.float32)
    return (exp_u / total).astype(np.float32)


def _sample_choice_index(probabilities: np.ndarray, rng: np.random.Generator) -> int:
    """Выбирает один индекс по вектору вероятностей."""
    return int(rng.choice(probabilities.size, p=probabilities))


def _compute_utilities_numpy(
    prices: np.ndarray,
    delivery: np.ndarray,
    ratings: np.ndarray,
    beta_price: float,
    beta_delivery: float,
    beta_rating: float,
) -> np.ndarray:
    """Считает полезность офферов для одного покупателя."""
    return (
        beta_price * prices
        + beta_delivery * delivery
        + beta_rating * ratings
    ).astype(np.float32)


def _compute_utilities_choice_learn(
    prices: np.ndarray,
    delivery: np.ndarray,
    ratings: np.ndarray,
    beta_price: float,
    beta_delivery: float,
    beta_rating: float,
) -> np.ndarray:
    """
    Считает полезность в режиме Choice-Learn.
    Сейчас используется та же линейная формула MNL, что и в numpy-пути.
    """
    import choice_learn  # noqa: F401 — проверка, что пакет доступен

    return _compute_utilities_numpy(
        prices, delivery, ratings, beta_price, beta_delivery, beta_rating
    )


def _income_utility_shift(
    budget: float,
    budget_baseline: float,
    gamma: float,
) -> float:
    """Скалярный shift U += γ·log(budget/baseline) для всех SKU (Spec 010 §3.2)."""
    if gamma <= 0.0 or budget_baseline <= 0.0:
        return 0.0
    wealth_ratio = budget / budget_baseline
    if wealth_ratio <= 0.0:
        return float("-inf")
    return float(gamma * math.log(wealth_ratio))


def _choose_one_buyer(
    buyer_row: dict[str, float | int],
    products_df: pl.DataFrame,
    config: ChoiceModelConfig,
    rng: np.random.Generator,
    *,
    use_choice_learn: bool,
    outside_utility_bias: float,
) -> tuple[int | None, float]:
    """Выбирает один оффер для покупателя или возвращает отказ от покупки."""
    budget = float(buyer_row[COL_BUDGET])
    all_prices = products_df[COL_PRICE].to_numpy()
    affordable_indices = np.flatnonzero(all_prices <= budget)
    if affordable_indices.size == 0:
        return None, 1.0

    k = min(config.max_products_per_choice_set, affordable_indices.size)
    product_indices = rng.choice(affordable_indices, size=k, replace=False)

    subset = products_df.gather(product_indices.astype(np.uint32).tolist())
    prices = subset[COL_PRICE].to_numpy()
    delivery = subset[COL_DELIVERY_DAYS].to_numpy()
    ratings = subset[COL_RATING_VALUE].to_numpy()
    listing_ids = subset[COL_LISTING_ID].to_numpy()

    beta_price = float(buyer_row[COL_BETA_PRICE])
    beta_delivery = float(buyer_row[COL_BETA_DELIVERY])
    beta_rating = float(buyer_row[COL_BETA_RATING])

    if use_choice_learn:
        product_utils = _compute_utilities_choice_learn(
            prices, delivery, ratings, beta_price, beta_delivery, beta_rating
        )
    else:
        product_utils = _compute_utilities_numpy(
            prices, delivery, ratings, beta_price, beta_delivery, beta_rating
        )

    # Budget constraint: price > budget → probability strictly 0 (outside option only).
    product_utils = np.where(prices <= budget, product_utils, -np.inf)

    income_shift = _income_utility_shift(
        budget,
        float(buyer_row[COL_BUDGET_BASELINE]),
        config.income_utility_gamma,
    )
    if np.isfinite(income_shift):
        product_utils = product_utils + np.float32(income_shift)

    utilities = np.concatenate(
        [product_utils, np.array([outside_utility_bias], dtype=np.float32)]
    )
    probabilities = _softmax_row(utilities)
    chosen_idx = _sample_choice_index(probabilities, rng)

    if chosen_idx == product_utils.size:
        return None, float(probabilities[chosen_idx])

    return int(listing_ids[chosen_idx]), float(probabilities[chosen_idx])


def choose_listings_for_buyers(
    buyers_batch_df: pl.DataFrame,
    products_df: pl.DataFrame,
    *,
    rng: np.random.Generator,
    config: ChoiceModelConfig,
    base_seed: int | None = None,
    allow_choice_learn_fallback: bool = True,
) -> pl.DataFrame:
    """
    Возвращает choices_df: buyer_id, listing_id (или null), choice_probability.
    Если задан base_seed, seed для каждого покупателя считается отдельно (для батчей).
    """
    buyers_batch_df = ensure_budget_baseline(buyers_batch_df)
    _validate_buyers_batch(buyers_batch_df)
    _validate_products(products_df)

    use_choice_learn = config.engine == "choice_learn"
    if use_choice_learn:
        try:
            import choice_learn  # noqa: F401
        except ImportError:
            if allow_choice_learn_fallback:
                warnings.warn(
                    "choice_learn is not installed; falling back to numpy_softmax",
                    RuntimeWarning,
                    stacklevel=2,
                )
                use_choice_learn = False
            else:
                raise

    bias_vector = resolve_outside_utility_bias(buyers_batch_df, config)
    buyer_rows = buyers_batch_df.select(list(BUYERS_CHOICE_INPUT_COLUMNS)).to_dicts()
    listing_ids: list[int | None] = []
    buyer_ids: list[int] = []
    probabilities: list[float] = []

    for i, row in enumerate(buyer_rows):
        buyer_id = int(row[COL_BUYER_ID])
        if base_seed is not None:
            row_rng = np.random.default_rng(_buyer_seed(base_seed, buyer_id))
        else:
            row_rng = rng

        listing_id, prob = _choose_one_buyer(
            row,
            products_df,
            config,
            row_rng,
            use_choice_learn=use_choice_learn,
            outside_utility_bias=float(bias_vector[i]),
        )
        buyer_ids.append(buyer_id)
        listing_ids.append(listing_id)
        probabilities.append(prob)

    return pl.DataFrame(
        {
            COL_BUYER_ID: buyer_ids,
            COL_LISTING_ID: listing_ids,
            COL_CHOICE_PROBABILITY: probabilities,
        },
        schema={
            COL_BUYER_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_CHOICE_PROBABILITY: pl.Float32,
        },
    )


def choose_listings_for_all_buyers(
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    *,
    seed: int | None,
    config: ChoiceModelConfig,
    allow_choice_learn_fallback: bool = True,
) -> pl.DataFrame:
    """Считает выбор для всех покупателей, разбивая их на батчи по config.buyers_batch_size."""
    if buyers_df.height == 0:
        raise ValueError("buyers_df must be non-empty")

    buyers_df = ensure_budget_baseline(buyers_df)

    chunks: list[pl.DataFrame] = []
    batch_size = config.buyers_batch_size
    for start in range(0, buyers_df.height, batch_size):
        batch = buyers_df.slice(start, batch_size)
        batch_rng = np.random.default_rng(0 if seed is None else seed + start)
        chunks.append(
            choose_listings_for_buyers(
                batch,
                products_df,
                rng=batch_rng,
                config=config,
                base_seed=seed,
                allow_choice_learn_fallback=allow_choice_learn_fallback,
            )
        )
    if len(chunks) == 1:
        return chunks[0]
    return pl.concat(chunks, how="vertical")
