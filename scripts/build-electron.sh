#!/usr/bin/env bash
# 构建 Linux AppImage（需要 Node 18+ 与 Python 依赖已可运行）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.nvm/nvm.sh"
fi
cd "$ROOT/frontend"
if [[ ! -d node_modules/electron ]]; then
  npm install --no-audit --no-fund
fi
npm run electron:build
echo "产出目录: $ROOT/frontend/release"
ls -la "$ROOT/frontend/release" || true
