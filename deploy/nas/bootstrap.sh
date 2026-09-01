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

# 旧版 skillradar-go:0.4 占用 13000；v0.5 Next 前端需要同一端口。
echo "==> 释放 ${HOST_PORT}/${BACKEND_PORT}（停掉旧 skillradar-go 与残留容器）"
dock rm -f skillradar-go >/dev/null 2>&1 || true
for port in "$HOST_PORT" "$BACKEND_PORT"; do
  ids="$(dock ps -q --filter "publish=${port}" 2>/dev/null || true)"
  if [[ -n "${ids}" ]]; then
    echo "    停止占用 ${port} 的容器: ${ids}"
    dock rm -f ${ids} || true
  fi
done

if dock compose version >/dev/null 2>&1; then
  dock compose -f docker-compose.nas.yml -p "$COMPOSE_NAME" up -d --build
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f docker-compose.nas.yml -p "$COMPOSE_NAME" up -d --build
else
  echo "==> 无 compose，改用 docker build / run"
  dock network create skillradar >/dev/null 2>&1 || true
  dock build -t skillradar-backend:0.5.2 "$APP/backend"
  dock build --build-arg BACKEND_URL=http://backend:8000 -t skillradar-frontend:0.5.2 "$APP/frontend"
  dock rm -f skillradar-backend skillradar-frontend >/dev/null 2>&1 || true
  dock run -d --name skillradar-backend --restart unless-stopped \
    --network skillradar --network-alias backend \
    --memory 512m \
    -p "${BACKEND_PORT}:8000" \
    -v "$DATA:/data" \
    -e APP_VERSION=0.5.2 \
    -e DATABASE_URL=sqlite:////data/skillradar.db \
    -e SECRET_KEY="$SECRET_KEY" \
    -e NEO4J_URI= \
    -e CORS_ORIGINS="$CORS_ORIGINS" \
    -e CLONE_DIR=/data/clones \
    -e OBJECT_DIR=/data/objects \
    -e PYTHONPATH=/app \
    skillradar-backend:0.5.2
  for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:${BACKEND_PORT}/api/v1/health >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  if ! dock run -d --name skillradar-frontend --restart unless-stopped \
    --network skillradar \
    --memory 512m \
    -p "${HOST_PORT}:3000" \
    -e BACKEND_URL=http://backend:8000 \
    skillradar-frontend:0.5.2; then
    echo "ERROR: frontend 启动失败，inspect:" >&2
    dock inspect skillradar-frontend --format '{{.State.Error}}' >&2 || true
    exit 1
  fi
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
front_ok=0
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/" >/dev/null 2>&1; then
    front_ok=1
    break
  fi
  sleep 2
done
if [[ "$front_ok" != 1 ]]; then
  echo "WARN: 前端 http://127.0.0.1:${HOST_PORT}/ 未响应" >&2
  dock inspect skillradar-frontend --format '{{.State.Status}} {{.State.Error}}' >&2 || true
  dock logs --tail 40 skillradar-frontend >&2 || true
  exit 1
fi
echo "NAS 前端端口 ${HOST_PORT}  后端端口 ${BACKEND_PORT}"
