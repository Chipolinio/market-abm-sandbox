#!/usr/bin/env bash
# Smoke-тесты Compose (Spec 007 §10.3). Запуск: tests/docker/test_compose_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/docker"

echo "==> compose config"
docker compose config >/dev/null

echo "==> build"
docker compose build

echo "==> up (detached)"
docker compose up -d

cleanup() {
  docker compose down
}
trap cleanup EXIT

echo "==> wait backend healthy"
for _ in $(seq 1 40); do
  if curl -sf http://localhost:8000/api/v1/health >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf http://localhost:8000/api/v1/health | grep -q '"status":"ok"'

echo "==> frontend index"
curl -sf http://localhost:3000/ | grep -qi html

echo "==> nginx proxies API"
curl -sf http://localhost:3000/api/v1/simulation/status | grep -q '"state"'

echo "==> all smoke checks passed"
