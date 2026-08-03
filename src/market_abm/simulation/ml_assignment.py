# Spec 015 §6 — deterministic ML seller share assignment (pure DataFrame transform).
from __future__ import annotations

from typing import Literal

import numpy as np
import polars as pl

from market_abm.domain.constants import COL_SELLER_ID, COL_USES_ML

# Salt for SeedSequence([seed, salt]) — independent of tick/explore salts.
_ML_ASSIGN_SALT: int = 0x4D4C4153  # "MLAS"

AssignOrder = Literal["permutation", "seller_id"]


def assign_ml_sellers(
    sellers_df: pl.DataFrame,
    *,
    share: float,
    seed: int,
    order: AssignOrder = "permutation",
) -> pl.DataFrame:
    """
    Add boolean uses_ml column: first K sellers in a deterministic order.
    K = round(n * share), clipped to [0, n]. Same seed+order → identical mask.

    order:
      - permutation: seeded shuffle (default; Spec 015 random ablation)
      - seller_id: ascending id — nested dose-response (ML(0.25) ⊂ ML(0.5) ⊂ …).
        Prefer for research grids with small n_sellers: random shuffle can leave the
        monopolist listing on rules until share=1.0 → bit-identical mid-share metrics.
    """
    if share < 0.0 or share > 1.0:
        raise ValueError(f"share must be in [0, 1], got {share}")
    if order not in ("permutation", "seller_id"):
        raise ValueError(f"order must be 'permutation' or 'seller_id', got {order!r}")

    n = int(sellers_df.height)
    k = int(round(n * float(share)))
    k = max(0, min(n, k))

    ids = sellers_df[COL_SELLER_ID].to_numpy().astype(np.int64, copy=True)
    if order == "seller_id":
        rank = np.argsort(ids, kind="mergesort")
    else:
        rng = np.random.default_rng(np.random.SeedSequence([int(seed), _ML_ASSIGN_SALT]))
        rank = rng.permutation(n)
    chosen = set(ids[rank[:k]].tolist())
    uses = pl.Series(
        COL_USES_ML,
        [int(sid) in chosen for sid in sellers_df[COL_SELLER_ID].to_list()],
        dtype=pl.Boolean,
    )
    if COL_USES_ML in sellers_df.columns:
        return sellers_df.with_columns(uses)
    return sellers_df.with_columns(uses)
