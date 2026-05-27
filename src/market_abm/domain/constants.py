from __future__ import annotations

from typing import Final

# --- Покупатели (buyers_df) ---

COL_BUYER_ID: Final = "buyer_id"
COL_BUDGET: Final = "budget"
COL_BETA_PRICE: Final = "beta_price"
COL_BETA_DELIVERY: Final = "beta_delivery"
COL_BETA_RATING: Final = "beta_rating"
COL_DEVICE_TYPE: Final = "device_type"
COL_PVD_SEGMENT: Final = "pvd_segment"
COL_ACTIVITY_HOUR: Final = "activity_hour"
COL_IS_IMPULSIVE: Final = "is_impulsive"
COL_PURCHASE_FREQUENCY: Final = "purchase_frequency"

DEVICE_TYPES: Final[tuple[str, ...]] = ("ios", "android", "desktop")
PVD_SEGMENTS: Final[tuple[str, ...]] = ("rich", "standard", "low")

PVD_BUDGET_MULTIPLIERS: Final[dict[str, float]] = {
    "rich": 1.25,
    "standard": 1.0,
    "low": 0.75,
}

BUYERS_COLUMNS: Final[tuple[str, ...]] = (
    COL_BUYER_ID,
    COL_BUDGET,
    COL_BETA_PRICE,
    COL_BETA_DELIVERY,
    COL_BETA_RATING,
    COL_DEVICE_TYPE,
    COL_PVD_SEGMENT,
    COL_ACTIVITY_HOUR,
    COL_IS_IMPULSIVE,
    COL_PURCHASE_FREQUENCY,
)

# Строковые имена Polars dtypes — маппинг в pl.* выполняется в population-слое.
BUYERS_SCHEMA_DTYPES: Final[dict[str, str]] = {
    COL_BUYER_ID: "Int32",
    COL_BUDGET: "Float32",
    COL_BETA_PRICE: "Float32",
    COL_BETA_DELIVERY: "Float32",
    COL_BETA_RATING: "Float32",
    COL_DEVICE_TYPE: "Categorical",
    COL_PVD_SEGMENT: "Categorical",
    COL_ACTIVITY_HOUR: "UInt8",
    COL_IS_IMPULSIVE: "Boolean",
    COL_PURCHASE_FREQUENCY: "Float32",
}

# --- Продавцы (sellers_df) — контракт для будущих слайсов ---

COL_SELLER_ID: Final = "seller_id"
COL_STRATEGY_TYPE: Final = "strategy_type"
COL_CAPITAL: Final = "capital"
COL_MARGIN_FLOOR: Final = "margin_floor"
COL_REPRICING_SPEED: Final = "repricing_speed"

STRATEGY_TYPES: Final[tuple[str, ...]] = (
    "MaxProfit",
    "MaxVolume",
    "RatingMaximizer",
)

SELLERS_COLUMNS: Final[tuple[str, ...]] = (
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_CAPITAL,
    COL_MARGIN_FLOOR,
    COL_REPRICING_SPEED,
)

SELLERS_SCHEMA_DTYPES: Final[dict[str, str]] = {
    COL_SELLER_ID: "Int32",
    COL_STRATEGY_TYPE: "Categorical",
    COL_CAPITAL: "Float32",
    COL_MARGIN_FLOOR: "Float32",
    COL_REPRICING_SPEED: "UInt8",
}

# --- Платформа (глобальные скаляры) ---

COL_BASE_COMMISSION: Final = "base_commission"
COL_LOGISTIC_FEE: Final = "logistic_fee"
COL_PROMO_PRESSURE: Final = "promo_pressure"

PLATFORM_KEYS: Final[tuple[str, ...]] = (
    COL_BASE_COMMISSION,
    COL_LOGISTIC_FEE,
    COL_PROMO_PRESSURE,
)

PLATFORM_DEFAULTS: Final[dict[str, float]] = {
    COL_BASE_COMMISSION: 0.15,
    COL_LOGISTIC_FEE: 0.05,
    COL_PROMO_PRESSURE: 0.10,
}
