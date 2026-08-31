#!/usr/bin/env bash
# SkillRadar v0.5 sandbox: unit+coverage then health 200 + API Pass
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" && -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
fi
PYTHON="${PYTHON:-python3}"
PORT="${PORT:-18001}"
export PYTHONUNBUFFERED=1
export SKILLRADAR_DISABLE_SCHEDULER=1
export SKILLRADAR_OFFLINE=1
export SECRET_KEY="${SECRET_KEY:-test-secret-key-please-change-32b}"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-test-encryption-key}"
export APP_VERSION="${APP_VERSION:-0.5.0}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////dev/shm/skillradar-sandbox.db}"
export CLONE_DIR="${CLONE_DIR:-$ROOT/backend/_clones}"
export PYTHONPATH="$ROOT/backend"

echo "==> install deps (user site if needed)"
"$PYTHON" -m pip install -q -r requirements.txt

echo "==> unit tests + coverage"
"$PYTHON" -m pytest

echo "==> start API on :$PORT"
rm -f "$ROOT/backend/_sandbox.db"
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/skillradar-test.log 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; }
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
grep -q '0.5.0' /tmp/sr-health.json
grep -q '"backend"' /tmp/sr-health.json

reg=$(curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa@example.com","password":"password1"}')
echo "$reg" | grep -q access_token
TOKEN=$(python3 -c "import json,sys; print(json.load(open('/dev/stdin'))['data']['access_token'])" <<<"$reg")

FIX="$ROOT/backend/tests/fixtures/sample-skill"
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/repos/decompose" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"repo_url\":\"file://$FIX\",\"local_path\":\"$FIX\"}" >/tmp/sr-dec.json
grep -q task_id /tmp/sr-dec.json
sleep 0.6
curl -fsS "http://127.0.0.1:${PORT}/api/v1/repos" -H "Authorization: Bearer $TOKEN" >/tmp/sr-repos.json
grep -q full_name /tmp/sr-repos.json

REPO_ID=$(python3 -c "import json; print(json.load(open('/tmp/sr-repos.json'))['data']['items'][0]['id'])")
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/plugins/${REPO_ID}/market-research" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}' >/tmp/sr-mr.json
grep -q '市场调研报告' /tmp/sr-mr.json
grep -q 'PEST' /tmp/sr-mr.json
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/repos/${REPO_ID}/commercial-report" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}' >/tmp/sr-cr.json
grep -q '需求调研详细分析' /tmp/sr-cr.json
curl -sS -X POST "http://127.0.0.1:${PORT}/api/v1/configs/llm" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"local","provider":"openai","api_key":"sk-test-aaaa","model_name":"gpt-4o"}' >/tmp/sr-llm.json
grep -q api_key_masked /tmp/sr-llm.json
grep -qv sk-test-aaaa /tmp/sr-llm.json


curl -fsS "http://127.0.0.1:${PORT}/api/v1/radar" -H "Authorization: Bearer $TOKEN" >/tmp/sr-radar.json
grep -q '"keywords"' /tmp/sr-radar.json
grep -q 'mcp server' /tmp/sr-radar.json
grep -q '"graph"' /tmp/sr-radar.json

curl -fsS "http://127.0.0.1:${PORT}/api/v1/scan/keywords" -H "Authorization: Bearer $TOKEN" | grep -q 'claude skill'

test -f "$ROOT/frontend/electron/main.cjs"
grep -q "0.5.0" "$ROOT/frontend/electron/main.cjs"

echo "PASS: health 200 OK + register + decompose + radar + market-research + configs + electron main"
