# Market ABM

Событийно-управляемый агентный симулятор рынка (Python DOD + React dashboard).

Спецификации: [`specs/`](specs/). Текущий UI/Docker-инкремент: [`specs/007-frontend-and-docker.md`](specs/007-frontend-and-docker.md).

---

## Требования

| Компонент | Версия |
|-----------|--------|
| Python | 3.12+ |
| Node.js | 22+ (frontend) |
| Docker Compose | v2 (опционально, для production-like стека) |

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm ci
```

---

## Локальная разработка (без Docker)

Backend и frontend запускаются отдельно. **CORS нужен только в этом режиме.**

### Backend

```bash
ENABLE_CORS=1 .venv/bin/uvicorn market_abm.main:app --reload --host 0.0.0.0 --port 8000
```

| Переменная | Значение | Назначение |
|------------|----------|------------|
| `ENABLE_CORS=1` | dev only | Разрешает запросы с `http://localhost:5173` (Vite) |
| `SIMULATION_ARTIFACTS_DIR` | `runs/default` (default) | Каталог Parquet-артефактов |

В Docker и production-like Compose **`ENABLE_CORS` не задавайте** — браузер ходит same-origin через Nginx.

### Frontend

```bash
cd frontend && npm run dev
```

Файл `frontend/.env.development` задаёт:

- `VITE_API_BASE_URL=http://localhost:8000`
- `VITE_WS_BASE_URL=ws://localhost:8000`

UI: [http://localhost:5173](http://localhost:5173)

---

## Docker (production-like)

Из каталога `docker/`:

```bash
cd docker
docker compose up --build
```

### Порты

| URL | Сервис | Назначение |
|-----|--------|------------|
| [http://localhost:3000](http://localhost:3000) | `market_abm_frontend` (Nginx) | React SPA + reverse-proxy `/api/` и WebSocket |
| [http://localhost:8000](http://localhost:8000) | `market_abm_backend` (Uvicorn) | FastAPI напрямую (отладка, healthcheck) |

В браузере используйте **только `:3000`** — same-origin: API на `/api/v1/*`, WS на `/api/v1/stream/ws`.

### Порядок старта

1. Backend поднимается и проходит `GET /api/v1/health`.
2. Frontend стартует после `depends_on: service_healthy` (без гонки 502).
3. Nginx резолвит `market_abm_backend` через Docker DNS (`resolver 127.0.0.11`).

### Dev override (bind-mount `runs/`)

Чтобы инспектировать Parquet на хосте:

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Каталог `../runs` монтируется в `/data/runs`. На хосте он должен быть доступен UID **1000** (`chown 1000:1000 runs/` при ошибках записи).

### Именованный volume и данные прогона

| Параметр | Значение |
|----------|----------|
| Volume | `market_abm_runs` (имя в Docker) |
| Mount в backend | `/data/runs` |
| `SIMULATION_ARTIFACTS_DIR` | `/data/runs/default` |
| Содержимое | `manifest.json`, `transactions/tick_*.parquet`, `products_snapshots/tick_*.parquet` |

**Остановка без удаления данных:**

```bash
docker compose down
```

Volume **сохраняется**. После `docker compose up` история графиков восстанавливается через REST backfill.

**Полное уничтожение данных прогона:**

```bash
docker compose down -v
```

Флаг `-v` удаляет именованный volume `market_abm_runs`. Используйте осознанно — восстановление только из бэкапа.

**Бэкап volume (операционная заметка):**

```bash
docker run --rm -v market_abm_runs:/data alpine tar czf - /data > market_abm_runs_backup.tar.gz
```

### Тестовый override (pytest)

Автотесты используют `docker-compose.test.yml` — порты `18000`/`13000`, volume `market_abm_runs_pytest`, чтобы не конфликтовать с локальным стеком на `:3000`/`:8000`.

---

## Тесты

```bash
# Python (без worker и docker)
.venv/bin/python -m pytest -m "not worker and not docker" -q

# Docker volume smoke (нужен Docker daemon)
.venv/bin/python -m pytest tests/docker/ -m docker -v

# Bash smoke
tests/docker/test_compose_smoke.sh

# Frontend
cd frontend && npm test && npm run build
```

---

## Ручной smoke — чеклист (слайс 7.6)

Проверка через Docker UI на [http://localhost:3000](http://localhost:3000). Ориентир: ~10 минут.

### Подготовка

- [ ] `cd docker && docker compose up --build` — оба контейнера healthy
- [ ] В статус-баре: badge **Connected**, state **IDLE**

### Управление симуляцией

- [ ] **Start** — state → `RUNNING`, `current_tick` растёт
- [ ] Графики квантилей и GMV получают точки (stub-телеметрия в noop-режиме или данные из Parquet)
- [ ] **Pause** — state → `PAUSED`, tick перестаёт расти
- [ ] **Step** (в PAUSED) — tick +1
- [ ] **Reset** — state → `IDLE`, tick → 0 (кнопка Reset disabled при `RUNNING`)

### F5 и персистентность

- [ ] Во время `RUNNING`: F5 — графики восстанавливаются (REST backfill + WS upsert), нет «колбасящихся» дублей
- [ ] `docker compose restart market_abm_backend` — UI на `:3000` снова доступен; при наличии Parquet на volume backfill возвращает историю

### Ошибки и пустые состояния

- [ ] До Start: графики показывают «Waiting for simulation data…» / «Waiting for GMV data…»
- [ ] При `FAILED`: красный баннер с `last_error`, Start disabled до Reset

### Очистка (опционально)

- [ ] `docker compose down` — данные на volume сохранены
- [ ] `docker compose down -v` — графики пустые после следующего `up`

---

## Ручной smoke — demand shock (Spec 010)

Проверка, что **«Запустить шок спроса»** даёт видимый отклик на графиках и в cyber-log. Ориентир: ~5 минут после базового чеклиста 7.6.

Спека: [`specs/010-demand-shock-income-and-engagement.md`](specs/010-demand-shock-income-and-engagement.md).

### Локальный стек (`:5173` + `:8000`)

```bash
ENABLE_CORS=1 .venv/bin/uvicorn market_abm.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```

### Подготовка

- [ ] Configure: `n_buyers` ≥ 300, `n_sellers` ≥ 20 → **Start**
- [ ] State `RUNNING`, `current_tick` растёт
- [ ] Вкладка **Динамика рынка**: график **GMV** уже набирает точки (не пустой)

### Шок спроса

- [ ] Кнопка **«Запустить шок спроса»** (sidebar Zone A)
- [ ] Cyber-log (Zone D): строка `DEMAND_SHOCK` с текстом про **budget** и **active buyer rate**, например:
  - `Buyer budgets cut by 30%; active buyer rate scaled by 30%`
- [ ] В течение **1–3 тиков** после шока:
  - [ ] GMV на графике **снижается** или стабилизируется ниже уровня непосредственно до шока
  - [ ] (опционально) индекс цены может реагировать с лагом — главный сигнал для 010 — **GMV / число сделок**

### Регрессия thin client

- [ ] Квантили цен **не** пересчитываются в браузере (значения = backend DTO)
- [ ] После **Reset** → новый Start графики и cyber-log обновляются без stale данных

### Автоматический smoke (CI / локально)

```bash
.venv/bin/python -m pytest tests/worker/test_demand_shock_smoke.py -q
```

Проверяет `LiveSimulationSession`: тик с `DEMAND_CRASH` → GMV и txn count ниже, чем на тике до шока; cyber-log message содержит frequency channel.

---

## Архитектура (кратко)

- **Симуляция** пишет Parquet; **AnalyticsStore** (DuckDB) — read-only query-side.
- **FastAPI** stateless; состояние воркера — shared memory + IPC.
- **React** — thin client: квантили/GMV не считаются в браузере; merge серий по `tick_id` (anti-race REST ↔ WS).

Подробнее: [`specs/007-frontend-and-docker.md`](specs/007-frontend-and-docker.md).

### Dense-графики (топ-N SKU, слайс 7.7)

Дашборд показывает до **10 listing** по суммарному GMV — три dense-графика (price, GMV, volume):

- REST: `GET /api/v1/analytics/top-listings?limit=10`
- Буфер: `DENSE_SERIES_CAP=600`, рендер: downsample до 600 точек
- Данные появляются после записи Parquet (noop-воркер без runner — секция пустая)
