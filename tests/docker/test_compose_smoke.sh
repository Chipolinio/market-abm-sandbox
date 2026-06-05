#!/usr/bin/env bash
# Smoke-тесты Compose (Spec 007 §10.3). Запуск: tests/docker/test_compose_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/docker"

PROJECT="market_abm_smoke_$$"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml -p "$PROJECT")
API_BASE="http://localhost:18000"
FRONTEND_BASE="http://localhost:13000"
BACKEND_CTR="market_abm_backend_pytest"

echo "==> compose config"
"${COMPOSE[@]}" config >/dev/null

echo "==> build"
"${COMPOSE[@]}" build

echo "==> up (detached)"
"${COMPOSE[@]}" up -d --wait

MINI_RUN=""
cleanup() {
  if [[ -n "${MINI_RUN}" && -d "${MINI_RUN}" ]]; then
    rm -rf "${MINI_RUN}"
  fi
  "${COMPOSE[@]}" down -v
}
trap cleanup EXIT

echo "==> wait backend healthy"
for _ in $(seq 1 40); do
  if curl -sf "${API_BASE}/api/v1/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "${API_BASE}/api/v1/health" | grep -q '"status":"ok"'

echo "==> frontend index"
curl -sf "${FRONTEND_BASE}/" | grep -qi html

echo "==> nginx proxies API"
curl -sf "${FRONTEND_BASE}/api/v1/simulation/status" | grep -q '"state"'

echo "==> seed mini_run + restart backend (7.3-T6 partial)"
MINI_RUN="$(mktemp -d)"
"$ROOT/.venv/bin/python" -c "
from pathlib import Path
from tests.helpers.mini_run import build_mini_run
build_mini_run(Path('$MINI_RUN'), run_id='default')
"
docker cp "${MINI_RUN}/." "${BACKEND_CTR}:/data/runs/"
"${COMPOSE[@]}" restart market_abm_backend
for _ in $(seq 1 40); do
  if curl -sf "${API_BASE}/api/v1/health" >/dev/null; then
    break
  fi
  sleep 1
done
docker exec "${BACKEND_CTR}" test -f /data/runs/default/transactions/tick_000000.parquet
POINTS="$(curl -sf "${API_BASE}/api/v1/analytics/price-index" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["points"]))')"
test "${POINTS}" -gt 0

echo "==> all smoke checks passed"
