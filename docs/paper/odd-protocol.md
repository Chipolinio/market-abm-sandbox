# ODD Protocol (Overview, Design concepts, Details)

Draft following Grimm et al. for the `market_abm` marketplace simulator (Spec 015).

## 1. Overview

### 1.1 Purpose

Evaluate how the **share of ML (CatBoost) sellers** interacts with **macro demand shocks** to shape prices, concentration (HHI), and welfare proxies in a synthetic e-commerce market.

### 1.2 Entities

| Entity | Representation |
|--------|----------------|
| Buyers | Rows in `buyers_df` (budget, betas, segment, frequency) |
| Sellers | Rows in `sellers_df` (strategy, capital, margin_floor, optional `uses_ml`) |
| Listings / products | Rows in `listings_df` / `products_df` (price, unit_cost, rating, stock) |
| Platform | Scalar fees (`base_commission`, logistic fee) + shock catalog |
| Macro state | Stress / expansion / episode / active shocks (Spec 011) |

**No OOP agent classes** — Data-Oriented Design: flat Polars tables + pure transforms.

### 1.3 Process overview

Each tick: environment shocks → bankrupt filter → ranking → buyer choice (MNL / softmax) → transactions → inventory → rating update → seller repricing (rules and/or CatBoost by `uses_ml` mask) → analytics metrics (welfare, HHI).

## 2. Design concepts

- **Emergence:** price paths, HHI, Zipf-like rank-size from many micro choices.
- **Adaptation:** rule strategies + CatBoost on features from recent history; exploration noise.
- **Objectives:** MaxProfit / MaxVolume / RatingMaximizer seller heuristics; buyers maximize utility with outside option.
- **Learning:** CatBoost trained offline from persisted history (Spec 005); inference after warmup.
- **Sensing:** sellers observe demand index, competitor prices, ref price, inventory pressure.
- **Interaction:** competition via ranking + MNL choice set; platform fees and promotions.
- **Stochasticity:** seeded `SeedSequence` per tick / batch run (Spec 015); paired seeds across ML shares.
- **Collectives:** segments (rich/standard/low); strategy cohorts.
- **Observation:** tick_metrics parquet; batch aggregate mean±Student-t CI95 after burn-in.

## 3. Details

### 3.1 Initialization

Population configs (`BuyerPopulationConfig`, `SellerPopulationConfig`) sample attributes; listings from unit_cost + markup; optional `assign_ml_sellers(share, seed)`.

### 3.2 Input data

No external Amazon panel required (limitation). All synthetic under fixed seeds.

### 3.3 Submodels (pointers)

| Submodel | Spec |
|----------|------|
| Choice / MNL | 003 / 012 |
| Rule + ML repricing | 002 / 005 / 015.3 |
| Macro stress / demand shocks | 011 |
| Inventory | 012.1 |
| Welfare / HHI | 015.2 |
| Batch reproducibility | 015.1 / 015.4 |

### 3.4 Scheduling

Discrete ticks `0..n_ticks-1`. Extended runtime advances macro then step. Batch runner may use `--jobs N` process pool with isolation reset.
