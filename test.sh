#!/usr/bin/env bash
# SkillRadar v0.5.3 sandbox: unit+coverage then health 200 + API Pass
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"

PYTHON="${PYTHON:-python3}"
PORT="${PORT:-18001}"
export SKILLRADAR_DISABLE_SCHEDULER=1
export SECRET_KEY="${SECRET_KEY:-test-secret-key-please-change-32b}"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-test-encryption-key}"
export APP_VERSION="${APP_VERSION:-0.5.3}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////dev/shm/skillradar-sandbox.db}"
export CLONE_DIR="${CLONE_DIR:-/dev/shm/skillradar-sandbox-clones}"
export OBJECT_DIR="${OBJECT_DIR:-/dev/shm/skillradar-sandbox-objects}"
export VECTOR_STORE_PATH="${VECTOR_STORE_PATH:-/dev/shm/skillradar-sandbox-vectors.json}"
export PYTHONPATH="$ROOT/backend"

echo "==> install deps (user site if needed)"
"$PYTHON" -m pip install -q -r requirements.txt

echo "==> unit tests + coverage"
"$PYTHON" -m pytest

echo "==> start API on :$PORT"
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port ${PORT}" 2>/dev/null || true
sleep 0.3
rm -f "$ROOT/backend/_sandbox.db" /tmp/skillradar-test.log
: > /tmp/skillradar-test.log
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/skillradar-test.log 2>&1 &
UV_PID=$!
cleanup() { kill "$UV_PID" 2>/dev/null || true; }
trap cleanup EXIT

ok=0
for i in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/v1/health" >/tmp/sr-health.json 2>/dev/null; then
    ok=1
    break
  fi
  sleep 0.25
done
if [[ "$ok" != 1 ]]; then
  echo "FAIL: health not ready" >&2
  cat /tmp/skillradar-test.log >&2 || true
  exit 1
fi
code=$(curl -s -o /tmp/sr-health.json -w '%{http_code}' "http://127.0.0.1:${PORT}/api/v1/health")
if [[ "$code" != "200" ]]; then
  echo "FAIL: health HTTP $code" >&2
  exit 1
fi
grep -q '"status":"ok"' /tmp/sr-health.json
grep -q '0.5.3' /tmp/sr-health.json
grep -q '"backend"' /tmp/sr-health.json

reg=$(curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa@example.com","password":"password1"}')
if ! echo "$reg" | grep -q access_token; then
  reg=$(curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"qa@example.com","password":"password1"}')
fi
echo "$reg" | grep -q access_token
TOKEN=$(python3 -c "import json,sys; print(json.load(open('/dev/stdin'))['data']['access_token'])" <<<"$reg")

FIX="$ROOT/backend/tests/fixtures/sample-skill"
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/repos/decompose" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"repo_url\":\"file://$FIX\",\"local_path\":\"$FIX\"}" >/tmp/sr-dec.json
grep -q task_id /tmp/sr-dec.json
sleep 0.6
curl -fsS "http://127.0.0.1:${PORT}/api/v1/repos" -H "Authorization: Bearer $TOKEN" | grep -q full_name

curl -fsS "http://127.0.0.1:${PORT}/api/v1/radar" -H "Authorization: Bearer $TOKEN" >/tmp/sr-radar.json
grep -q '"keywords"' /tmp/sr-radar.json
grep -q 'mcp server' /tmp/sr-radar.json
grep -q '"graph"' /tmp/sr-radar.json

curl -fsS "http://127.0.0.1:${PORT}/api/v1/scan/keywords" -H "Authorization: Bearer $TOKEN" | grep -q 'claude skill'

SEARCH=$(curl -fsS "http://127.0.0.1:${PORT}/api/v1/search?q=web-search" -H "Authorization: Bearer $TOKEN")
echo "$SEARCH" | grep -q '"items"'

REPOS=$(curl -fsS "http://127.0.0.1:${PORT}/api/v1/repos" -H "Authorization: Bearer $TOKEN")
PLUGIN_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['data']['items'][0]['id'])" <<<"$REPOS")
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/reports/generate" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"plugin_id\": $PLUGIN_ID}" | grep -q '"title"'
curl -fsS "http://127.0.0.1:${PORT}/api/v1/reports" -H "Authorization: Bearer $TOKEN" | grep -q 商业拆解

test -f "$ROOT/frontend/electron/main.cjs"
grep -q "0.5.3" "$ROOT/frontend/electron/main.cjs"

echo "PASS: health 200 OK + register + decompose + radar + search + report + electron main"
