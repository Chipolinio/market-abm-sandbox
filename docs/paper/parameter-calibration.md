# Parameter Calibration Table

Draft justification table for key defaults. Replace “source” cells with literature citations before submission.

| Parameter | Default | Source / justification |
|-----------|---------|------------------------|
| MNL price sensitivity (buyer `beta_price` distribution) | population log-scale | Calibrated to produce interior purchase rates in smoke runs; align with discrete-choice intensity (cf. Berry et al. 1995 family) — **needs empiric citation pass** |
| Outside utility bias | `-1.5` | Holds outside option competitive vs top listings |
| Income utility γ | `0.35` | Spec 012; scales log(budget/budget_baseline) |
| Ranking weights w1/w2/w3 | `0.40 / 0.35 / 0.25` | Spec 012 RankingConfig defaults (rating / price / sales) |
| Platform `base_commission` | `0.15` | Stylized marketplace take-rate |
| Logistic fee | `0.05` | Stylized fulfillment share |
| Repricing relative step | `0.02` | Spec 002 — small discrete price moves |
| CatBoost warmup_ticks | `15` | Spec 005 — avoid cold inference |
| Panic stress threshold | `0.40` | Spec 011 stress repricing |
| Stress / expansion caps | `1.2` / `0.8` | Spec 011 MacroDynamicsConfig |
| Batch `n_runs` | `30` | Small-sample Student-t CI (Spec 015) |
| `burn_in_ticks` | `100` | Steady-state filter after cold start / ML warmup |
| `ml_share_grid` | `0, 0.25, 0.5, 0.75, 1.0` | Ablation resolution for phase transition |
| HHI scale | `0–10000` | FTC-style index |
| CS metric | budget residual proxy | Explicitly **not** WTP−P; see limitations.md |

**Note:** Values marked as stylized require literature/empiric anchoring before journal submission.
