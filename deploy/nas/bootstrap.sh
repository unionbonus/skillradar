#!/usr/bin/env bash
# 在 NAS 上解压后启动 SkillRadar 轻量栈（SQLite + 内存图）
set -euo pipefail

APP="${APP_DIR:-}"
if [[ -z "$APP" || ! -f "$APP/docker-compose.nas.yml" ]]; then
  APP="$(cd "$(dirname "$0")/../.." && pwd)"
fi
if [[ ! -f "$APP/docker-compose.nas.yml" ]]; then
  APP="$(cd "$(dirname "$0")" && pwd)"
fi
DATA="${DATA_DIR:-$APP/data}"
HOST_PORT="${HOST_PORT:-13000}"
BACKEND_PORT="${BACKEND_PORT:-18000}"
COMPOSE_NAME="${COMPOSE_NAME:-skillradar}"
SECRET_KEY="${SECRET_KEY:-change-me-to-a-32-byte-or-longer-random-string}"
CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:${HOST_PORT}}"

cd "$APP"
mkdir -p "$DATA/clones"

dock() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  elif sudo -n docker info >/dev/null 2>&1; then
    sudo -n docker "$@"
  else
    echo "ERROR: docker 不可用（需要当前用户权限或 sudo -n docker）" >&2
    exit 1
  fi
}

echo "==> docker 构建并启动 SkillRadar（$APP）"
export DATA_DIR="$DATA"
export HOST_PORT BACKEND_PORT SECRET_KEY CORS_ORIGINS COMPOSE_NAME

if dock compose version >/dev/null 2>&1; then
  dock compose -f docker-compose.nas.yml -p "$COMPOSE_NAME" up -d --build
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f docker-compose.nas.yml -p "$COMPOSE_NAME" up -d --build
else
  echo "==> 无 compose，改用 docker build / run"
  dock network create skillradar >/dev/null 2>&1 || true
  dock build -t skillradar-backend:0.5.0 "$APP/backend"
  dock build --build-arg BACKEND_URL=http://backend:8000 -t skillradar-frontend:0.5.0 "$APP/frontend"
  dock rm -f skillradar-backend skillradar-frontend >/dev/null 2>&1 || true
  dock run -d --name skillradar-backend --restart unless-stopped \
    --network skillradar --network-alias backend \
    --memory 512m \
    -p "${BACKEND_PORT}:8000" \
    -v "$DATA:/data" \
    -e DATABASE_URL=sqlite:////data/skillradar.db \
    -e SECRET_KEY="$SECRET_KEY" \
    -e NEO4J_URI= \
    -e CORS_ORIGINS="$CORS_ORIGINS" \
    -e CLONE_DIR=/data/clones \
    -e PYTHONPATH=/app \
    skillradar-backend:0.5.0
  for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:${BACKEND_PORT}/api/v1/health >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  dock run -d --name skillradar-frontend --restart unless-stopped \
    --network skillradar \
    --memory 512m \
    -p "${HOST_PORT}:3000" \
    -e BACKEND_URL=http://backend:8000 \
    skillradar-frontend:0.5.0
fi

echo "==> 等待健康检查"
ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "$ok" != 1 ]]; then
  echo "WARN: 后端健康检查未通过，查看: docker logs skillradar-backend" >&2
  dock ps || true
  exit 1
fi
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" || true
echo
echo "NAS 前端端口 ${HOST_PORT}  后端端口 ${BACKEND_PORT}"
