# Spec 012 §4.1 / §16.2 — per-category ranking configuration.
from __future__ import annotations

from pydantic import BaseModel, Field


class RankingConfig(BaseModel):
    """
    Per-category ranking score weights and consideration-set parameters (Spec 012 §4).

    Score_j = w1·Rating_j + w2·(P_cat_median/P_j) + w3·log(1+SalesVolume_j)

    Consideration set per buyer:
        C_cat = Top-K(Score|cat) ∪ Sample-M(residual|cat)
        C*    = merge-capped to max_n (= ChoiceModelConfig.max_products_per_choice_set)
    """

    model_config = {"frozen": True}

    w1: float = Field(default=0.40, ge=0.0, le=1.0, description="Rating weight")
    w2: float = Field(default=0.35, ge=0.0, le=1.0, description="Price-vs-cat-median weight")
    w3: float = Field(default=0.25, ge=0.0, le=1.0, description="Log-sales-volume weight")

    top_k: int = Field(default=15, ge=1, description="Top-K ranked listings per category")
    organic_m: int = Field(default=3, ge=0, description="Organic Sample-M from residual per category")

    n_categories: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of product categories for listing bootstrap (§16.4)",
    )
