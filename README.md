# Market ABM

Event-driven agent-based e-commerce market simulator: Python DOD/Polars core, FastAPI transport, React trading-terminal UI, and an offline Research Lab for paper grids.

---

## What is this?

**Market ABM** simulates a marketplace with heterogeneous buyers and sellers:

- Buyers choose products under budget, engagement, and outside-option constraints.
- Sellers reprice with rule strategies and optional CatBoost / hybrid ML policies.
- Macro shocks (demand crash, recession narratives) feed stress, recovery, and segment dynamics.
- The live UI is a **thin client**: charts and control state come from the backend (REST + WebSocket), not browser-side econometrics.
- The **Research Lab** (`#research`) runs offline ML-share ablation batches and renders paper figures F1–F5 — separate from the live worker.

---

## What you can do with it

| Mode | What you get |
|------|----------------|
| **Live terminal** | Start / pause / step / reset a simulation; watch prices, GMV, HHI, segments, sellers, shocks |
| **Demand & crisis shocks** | Inject mild / standard / severe / recession protocols; read macro narratives in the cyber-log |
| **Analytics** | Query Parquet + DuckDB-backed analytics (top listings, welfare, category ranking, …) |
| **ML repricing** | Hybrid CatBoost policies for a share of sellers (optional `[ml]` extra) |
| **Research Lab** | Smoke / paper / custom grids over ML share × seeds; summary table, robust stats, figure gallery |
| **Docker stack** | Production-like Nginx + API with persisted run volume |

---

## Architecture

```
┌─────────────────┐     REST / WS      ┌──────────────────────────┐
│  React SPA      │ ◄────────────────► │  FastAPI (stateless)     │
│  Vite / Nginx   │                    │  + LiveSimulation worker │
└─────────────────┘                    └────────────┬─────────────┘
                                                    │
                       Parquet artifacts            │  IPC / shared memory
                       (runs/, experiments/)        ▼
                                         ┌──────────────────────┐
                                         │ Simulation core      │
                                         │ (Polars DOD tick)    │
                                         └──────────┬───────────┘
                                                    │
                                         ┌──────────▼───────────┐
                                         │ AnalyticsStore       │
                                         │ (DuckDB, read-only)  │
                                         └──────────────────────┘

Offline: experiments/batch_runner → aggregate → figures → output/experiments/<id>/
```

**Principles**

- Simulation **writes** Parquet; analytics is **read-side**.
- FastAPI does not own durable sim state — the worker process does.
- React merges series by `tick_id` (REST backfill ↔ WS) to avoid duplicate points after refresh.
- Research jobs run in a background thread under `/api/v1/experiments/*` (one job at a time).

---

## Requirements

| Component | Version |
|-----------|---------|
| Python | 3.12+ |
| Node.js | 22+ (frontend) |
| Docker Compose | v2 (optional) |

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional CatBoost for ML paths:
# pip install -e ".[dev,ml]"
cd frontend && npm ci
```

---

## Run locally (no Docker)

Backend and frontend are separate processes. **CORS is only for this mode.**

### Backend

```bash
ENABLE_CORS=1 .venv/bin/uvicorn market_abm.main:app --reload --host 0.0.0.0 --port 8000
```

| Variable | Default / value | Role |
|----------|-----------------|------|
| `ENABLE_CORS=1` | unset in Docker | Allow Vite origin `http://localhost:5173` |
| `SIMULATION_ARTIFACTS_DIR` | `runs/default` | Live Parquet run root |
| `EXPERIMENTS_DIR` | `output/experiments` | Research Lab artifacts |
| `MARKET_ABM_ML_REGISTRY` | unset → frozen dir / stub | Path to frozen CatBoost registry for experiments |
| `MARKET_ABM_ML_FROZEN_DIR` | `output/ml_frozen` | Default train/load root (`…/ml/registry.json`) |

### Frontend

```bash
cd frontend && npm run dev
```

`frontend/.env.development` points the SPA at:

- `VITE_API_BASE_URL=http://localhost:8000`
- `VITE_WS_BASE_URL=ws://localhost:8000`

| URL | Purpose |
|-----|---------|
| [http://localhost:5173](http://localhost:5173) | Live trading terminal |
| [http://localhost:5173/#research](http://localhost:5173/#research) | Research Lab |

---

## Run with Docker

From `docker/`:

```bash
cd docker
docker compose up --build
```

| URL | Service | Notes |
|-----|---------|--------|
| [http://localhost:3000](http://localhost:3000) | Nginx frontend | **Use this in the browser** — same-origin `/api/` + WS |
| [http://localhost:8000](http://localhost:8000) | Uvicorn | Direct API / health / debugging |

Do **not** set `ENABLE_CORS` in Compose — the browser talks same-origin through Nginx.

### Dev override (inspect Parquet on the host)

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Host `../runs` mounts to `/data/runs`. If writes fail, ensure UID **1000** can write (`chown 1000:1000 runs/`).

### Data volume

| Item | Value |
|------|--------|
| Volume | `market_abm_runs` |
| Backend mount | `/data/runs` |
| `SIMULATION_ARTIFACTS_DIR` | `/data/runs/default` |
| Volume | `market_abm_experiments` |
| Experiments mount | `/data/experiments` |
| `EXPERIMENTS_DIR` | `/data/experiments` |

```bash
docker compose down          # keep volume
docker compose down -v       # destroy run data
```

Test Compose (`docker-compose.test.yml`) uses ports `18000` / `13000` and volume `market_abm_runs_pytest` so it does not clash with a local stack.

---

## Research Lab

Offline batch experiments — **not** the live worker.

Open from the live terminal via **Research Lab** in the top bar (`#research`), or go back with **← Live terminal**.

1. **Обучить CatBoost** (once) — bootstrap rules runs → fit → `output/ml_frozen/ml/`. Shared job lock with experiment runs. Without this, grids use a deterministic stub and warn.
2. Pick **Smoke** / **Paper** / **Custom** — IDs auto-suggest as `smoke-1`, `paper-1`, `custom-1`, …
3. **Launch** → background job; after **DONE**: summary, warnings, figures F1–F5 under `output/experiments/<id>/`.

Optional overrides: `MARKET_ABM_ML_REGISTRY` (path to registry), `MARKET_ABM_ML_FROZEN_DIR` (default `output/ml_frozen`). Needs `pip install -e ".[ml]"`.

---

## Tests

```bash
# Python (skip process/docker-heavy marks)
.venv/bin/python -m pytest -m "not worker and not docker" -q

# Worker / Docker / slow as needed
.venv/bin/python -m pytest tests/worker/ -m worker -q
.venv/bin/python -m pytest tests/docker/ -m docker -v
.venv/bin/python -m pytest tests/simulation/test_recession_integration.py -m slow -q

# Frontend
cd frontend && npm test && npm run build
```

Demand-shock smoke: `pytest tests/worker/test_demand_shock_smoke.py -q`.

---

## Repository layout

```
src/market_abm/     # simulation, analytics, API, worker, ML
frontend/           # React trading terminal + Research Lab
experiments/        # offline batch, aggregate, figures, job runner
docker/             # Compose + Dockerfiles
tests/              # pytest
output/experiments/ # Research Lab artifacts (generated)
runs/               # live Parquet runs (generated / Docker volume)
```
