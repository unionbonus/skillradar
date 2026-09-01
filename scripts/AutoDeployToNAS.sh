#!/usr/bin/env bash
# AutoDeployToNAS — SkillRadar → 极空间 Docker
# 配置：复制 .nas-deploy.env.example 为 .nas-deploy.env 并填写 NAS_PASS
# 也可复用 ../knowledge-graph-go/.nas-deploy.env 里的主机账号（不会覆盖星觅目录）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.nas-deploy.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.nas-deploy.env"
  set +a
fi
exec python3 "$ROOT/scripts/AutoDeployToNAS.py"
