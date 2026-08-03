# Limitations & Threats to Validity

Honest scope boundaries for Spec 015 / paper draft.

## Measurement

- **Consumer surplus is a proxy**, not textbook CS. v1 uses \(\sum (Budget_{effective} - Price_{paid})\) (budget residual). It is **not** willingness-to-pay minus price from the MNL inclusive value / logsum. Do not interpret CS proxy as exact social surplus.

## Institutional / agent realism

- No full firm **entry/exit** cycle beyond simplified bankruptcy/capital paths; no multi-SKU WMS complexity beyond Spec 012.1 v1.
- Buyer demand process is **synthetic** (configured distributions), not estimated on Amazon / Ozon panel data.
- Platform fees and promotion mechanics are stylized.

## Learning / ML

- CatBoost models are trained on **simulator history**, not production logs; missing registry / warmup → **rules fallback** (Spec 015 §6.3), which can understate ML effects in early ticks (hence burn-in).

## External validity

- Results are **conditional on calibration** in `parameter-calibration.md`. Without external data fitting, claims are qualitative / comparative across `ml_seller_share`, not absolute welfare estimates for a named marketplace.

## Statistical

- Default \(N=30\) runs uses Student-t CI; still a modest ensemble. Parallel batch (`--jobs`) must preserve isolation (no shared CatBoost registry leakage).
