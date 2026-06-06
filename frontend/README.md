# Market ABM — Trading Terminal (Spec 009)

React 19 + Vite thin client для событийно-управляемого симулятора рынка.

## Быстрый старт

```bash
# Backend (из корня репозитория)
ENABLE_CORS=1 .venv/bin/uvicorn market_abm.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Vite проксирует `/api` и WebSocket на `http://localhost:8000` (см. `vite.config.ts`).

## Архитектура UI

4-zone Trading Terminal (`TradingTerminalLayout`):

| Zone | Компонент | Транспорт |
|------|-----------|-----------|
| Left sidebar | Environment, Shocks, Start/Pause | REST command |
| Top ribbon | Ticker metrics X/Y, GMV, Index | WS 1 Hz |
| Center tabs | Dynamics / Leaders / Demand Matrix | WS + REST poll |
| Right cyber-log | System events prepend buffer | WS + REST backfill |

**Thin client:** без клиентских расчётов GMV, квантилей, корреляций; leaderboard sort — на backend.

## Скрипты

```bash
npm run dev       # Vite dev server :5173
npm run build     # tsc + production bundle
npm run test      # Vitest (матрица 9.1–9.6)
npm run preview   # preview production build
```

## Smoke checklist (≈10 min)

1. `npm run test` — green
2. `npm run build` — green
3. Start backend + `npm run dev`
4. Start simulation → ticker ribbon обновляется (1 Hz)
5. «Запустить шок спроса» → событие в CYBER-LOG
6. Tab Market Leaders → top-5 table, poll 5 s
7. Tab Demand Matrix → 10×10 grid

## Legacy (Spec 007)

Плоский dashboard (`ControlPanel`, `StatusBar`, flat `charts-grid`) заменён в `App.tsx` на `TradingTerminalLayout`. Компоненты Spec 007 сохранены для unit-тестов и переиспользования в `MarketDynamicsTab`.
