# Назначение файла: выбор оффера покупателем за один шаг симуляции.
# Базовая идея: считаем полезность по beta, softmax и случайный выбор внутри витрины.
from __future__ import annotations

import warnings

import numpy as np
import polars as pl

from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    BUYERS_CHOICE_INPUT_COLUMNS,
    CHOICES_COLUMNS,
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_CHOICE_PROBABILITY,
    COL_DELIVERY_DAYS,
    COL_LISTING_ID,
    COL_PRICE,
    COL_RATING_VALUE,
    PRODUCTS_CHOICE_FEATURE_COLUMNS,
)


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
    """Считает вероятности выбора по одной строке полезностей."""
    shifted = utilities - np.max(utilities)
    exp_u = np.exp(shifted, dtype=np.float64)
    return (exp_u / exp_u.sum()).astype(np.float32)


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


def _choose_one_buyer(
    buyer_row: dict[str, float | int],
    products_df: pl.DataFrame,
    config: ChoiceModelConfig,
    rng: np.random.Generator,
    *,
    use_choice_learn: bool,
) -> tuple[int | None, float]:
    """Выбирает один оффер для покупателя или возвращает отказ от покупки."""
    n_products = products_df.height
    k = min(config.max_products_per_choice_set, n_products)
    product_indices = rng.choice(n_products, size=k, replace=False)

    subset = products_df.gather(product_indices.astype(np.uint32).tolist())
    prices = subset[COL_PRICE].to_numpy()
    budgets = float(buyer_row[COL_BUDGET])
    affordable_mask = prices <= budgets
    if not np.any(affordable_mask):
        return None, 1.0

    prices = prices[affordable_mask]
    delivery = subset[COL_DELIVERY_DAYS].to_numpy()[affordable_mask]
    ratings = subset[COL_RATING_VALUE].to_numpy()[affordable_mask]
    listing_ids = subset[COL_LISTING_ID].to_numpy()[affordable_mask]

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

    utilities = np.concatenate(
        [product_utils, np.array([config.outside_utility_bias], dtype=np.float32)]
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

    buyer_rows = buyers_batch_df.select(list(BUYERS_CHOICE_INPUT_COLUMNS)).to_dicts()
    listing_ids: list[int | None] = []
    buyer_ids: list[int] = []
    probabilities: list[float] = []

    for row in buyer_rows:
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
