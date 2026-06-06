from __future__ import annotations

from typing import Final

# --- Buyers (buyers_df) ---

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

# String Polars dtype names are mapped to pl.* in population layer.
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

# --- Sellers (sellers_df) ---

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

# Top-sellers ribbon mapping (Zone D UI).
ALGORITHM_TYPES: Final[tuple[str, ...]] = ("CB", "REPR", "RULE")
LOGIC_STATUS_BANKRUPT: Final = "bankrupt"
LOGIC_STATUS_ROI: Final = "roi_optimization"
LOGIC_STATUS_DUMPING: Final = "aggressive_dumping"
LOGIC_STATUS_RULE: Final = "rule_based"

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

# --- Sellers runtime state (sellers_state_df), slice 008 ---

COL_WORKING_CAPITAL: Final = "working_capital"
COL_IS_BANKRUPT: Final = "is_bankrupt"

SELLERS_STATE_COLUMNS: Final[tuple[str, ...]] = (
    COL_SELLER_ID,
    COL_WORKING_CAPITAL,
    COL_IS_BANKRUPT,
)

SELLERS_STATE_SCHEMA_DTYPES: Final[dict[str, str]] = {
    COL_SELLER_ID: "Int32",
    COL_WORKING_CAPITAL: "Float32",
    COL_IS_BANKRUPT: "Boolean",
}

# --- Listings (listings_df), slice 002 contract ---

COL_LISTING_ID: Final = "listing_id"
COL_UNIT_COST: Final = "unit_cost"
COL_PRICE: Final = "price"
COL_DEMAND_INDEX: Final = "demand_index"

LISTINGS_COLUMNS: Final[tuple[str, ...]] = (
    COL_LISTING_ID,
    COL_SELLER_ID,
    COL_UNIT_COST,
    COL_PRICE,
    COL_DEMAND_INDEX,
)

LISTINGS_SCHEMA_DTYPES: Final[dict[str, str]] = {
    COL_LISTING_ID: "Int32",
    COL_SELLER_ID: "Int32",
    COL_UNIT_COST: "Float32",
    COL_PRICE: "Float32",
    COL_DEMAND_INDEX: "Float32",
}

# --- Products (products_df), slice 003: listings + card features for choice ---

COL_DELIVERY_DAYS: Final = "delivery_days"
COL_RATING_VALUE: Final = "rating_value"

PRODUCTS_COLUMNS: Final[tuple[str, ...]] = (
    COL_LISTING_ID,
    COL_SELLER_ID,
    COL_UNIT_COST,
    COL_PRICE,
    COL_DEMAND_INDEX,
    COL_DELIVERY_DAYS,
    COL_RATING_VALUE,
)

PRODUCTS_SCHEMA_DTYPES: Final[dict[str, str]] = {
    **LISTINGS_SCHEMA_DTYPES,
    COL_DELIVERY_DAYS: "Float32",
    COL_RATING_VALUE: "Float32",
}

# --- Choice step output (choices_df), slice 003 ---

COL_CHOICE_PROBABILITY: Final = "choice_probability"

CHOICES_COLUMNS: Final[tuple[str, ...]] = (
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_CHOICE_PROBABILITY,
)

BUYERS_CHOICE_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    COL_BUYER_ID,
    COL_BUDGET,
    COL_BETA_PRICE,
    COL_BETA_DELIVERY,
    COL_BETA_RATING,
)

PRODUCTS_CHOICE_FEATURE_COLUMNS: Final[tuple[str, ...]] = (
    COL_LISTING_ID,
    COL_PRICE,
    COL_DELIVERY_DAYS,
    COL_RATING_VALUE,
)

# --- Transactions (transactions_df), slice 003 ---

COL_TICK_ID: Final = "tick_id"
COL_PRICE_PAID: Final = "price_paid"
COL_GROSS_MARGIN: Final = "gross_margin"

TRANSACTIONS_COLUMNS: Final[tuple[str, ...]] = (
    COL_TICK_ID,
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_SELLER_ID,
    COL_PRICE_PAID,
    COL_UNIT_COST,
    COL_GROSS_MARGIN,
)

TRANSACTIONS_SCHEMA_DTYPES: Final[dict[str, str]] = {
    COL_TICK_ID: "Int32",
    COL_BUYER_ID: "Int32",
    COL_LISTING_ID: "Int32",
    COL_SELLER_ID: "Int32",
    COL_PRICE_PAID: "Float32",
    COL_UNIT_COST: "Float32",
    COL_GROSS_MARGIN: "Float32",
}

# --- Platform scalar defaults ---

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

# --- Market guardrails and realistic defaults for slice 002 ---

MARGIN_FLOOR_MIN: Final[float] = 0.01
MARGIN_FLOOR_DEFAULT_MAX: Final[float] = 0.50
MARGIN_FLOOR_HARD_MAX: Final[float] = 0.70

REPRICING_SPEED_MIN: Final[int] = 1
REPRICING_SPEED_MAX: Final[int] = 255
REPRICING_SPEED_DEFAULT_MIN: Final[int] = 1
REPRICING_SPEED_DEFAULT_MAX: Final[int] = 5

DEFAULT_DEMAND_INDEX: Final[float] = 1.0
MAX_PROFIT_DEMAND_HIGH_DEFAULT: Final[float] = 1.10
MAX_PROFIT_DEMAND_LOW_DEFAULT: Final[float] = 0.90
MAX_VOLUME_AGGRESSION_DEFAULT: Final[float] = 1.5
