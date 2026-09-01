#!/usr/bin/env bash
# SkillRadar v0.5 — 双击启动 Electron。日志：/tmp/skillradar-start.log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(basename "$ROOT")" == "scripts" ]]; then
  ROOT="$(cd "$ROOT/.." && pwd)"
fi
cd "$ROOT"

LOG="${SKILLRADAR_START_LOG:-/tmp/skillradar-start.log}"
export APP_VERSION="${APP_VERSION:-0.5.0}"
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"

log() {
  printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"
}

die() {
  log "ERROR: $*"
  local msg="SkillRadar 启动失败：$1"$'\n'"详情见 $LOG"
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --error "$msg" >/dev/null 2>&1 || true
  elif command -v zenity >/dev/null 2>&1; then
    zenity --error --text="$msg" >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "SkillRadar" "$msg" || true
  fi
  exit 1
}

: >"$LOG"
log "启动 ROOT=$ROOT DISPLAY=${DISPLAY:-unset} tty=$([[ -t 1 ]] && echo yes || echo no)"

# nvm.sh 与 set -u 不兼容，双击时会静默退出。只把 Node 可执行目录加进 PATH。
NVM_NODE_BIN=""
if [[ -d "$HOME/.nvm/versions/node" ]]; then
  NVM_NODE_BIN="$(ls -d "$HOME/.nvm/versions/node"/v*/bin 2>/dev/null | sort -V | tail -1 || true)"
fi
if [[ -n "$NVM_NODE_BIN" ]]; then
  export PATH="$NVM_NODE_BIN:$PATH"
  log "PATH 加入 $NVM_NODE_BIN"
fi
export PATH="$ROOT/frontend/node_modules/.bin:$PATH"

pick_python() {
  local py
  for py in /usr/bin/python3.12 /usr/bin/python3.11 python3.12 python3.11 /usr/bin/python3 python3; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  echo "python3"
}

electron_bin() {
  local dist="$ROOT/frontend/node_modules/electron/dist/electron"
  local shim="$ROOT/frontend/node_modules/.bin/electron"
  if [[ -x "$dist" ]]; then
    echo "$dist"
    return 0
  fi
  if [[ -x "$shim" ]]; then
    echo "$shim"
    return 0
  fi
  return 1
}

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  log "已生成 .env"
fi
set -a
set +u
# shellcheck disable=SC1091
source "$ROOT/.env"
set -u
set +a
export APP_VERSION=0.5.0
export PYTHONPATH="$ROOT/backend"
mkdir -p "$ROOT/backend/data" "$ROOT/data/clones"

PY="$(pick_python)"
log "Python: $PY ($($PY --version 2>&1))"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  log "创建虚拟环境…"
  "$PY" -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
if ! python -c "import uvicorn, fastapi" 2>/dev/null; then
  log "安装后端依赖…"
  pip install -q -r "$ROOT/backend/requirements.txt" || die "pip 安装失败"
else
  log "后端依赖已就绪"
fi

install_electron() {
  local fe="$ROOT/frontend"
  local dest="$fe/node_modules/electron"
  log "安装 Electron 包（npmmirror，跳过 GitHub 二进制）…"
  rm -rf "$dest" "$fe/node_modules/.electron-"* \
    "$fe/node_modules/.builder-util-"* 2>/dev/null || true
  mkdir -p "$fe/node_modules"
  (
    cd "$fe"
    if ! npm install --ignore-scripts --no-audit --no-fund --no-save \
      --registry=https://registry.npmmirror.com electron@28.3.3 >>"$LOG" 2>&1; then
      log "npm install 失败，改用 npm pack…"
      rm -rf "$dest"
      mkdir -p "$dest"
      tgz="$(npm pack electron@28.3.3 --registry=https://registry.npmmirror.com 2>>"$LOG")"
      tar -xzf "$tgz" -C "$dest" --strip-components=1
      rm -f "$tgz"
    fi
  ) || die "无法获取 electron npm 包"
  [[ -f "$dest/package.json" ]] || die "electron 包不完整"
  local ver zip bindir
  ver="$(node -p "require('$dest/package.json').version")"
  bindir="$dest/dist"
  if [[ -x "$bindir/electron" ]]; then
    log "已有 Electron 二进制 $ver"
    return 0
  fi
  mkdir -p "$bindir"
  zip="/tmp/electron-${ver}-linux-x64.zip"
  log "下载 Electron ${ver} linux-x64…"
  curl -fL --retry 3 --connect-timeout 20 -o "$zip" \
    "https://npmmirror.com/mirrors/electron/v${ver}/electron-v${ver}-linux-x64.zip" \
    || die "下载 Electron 二进制失败"
  python3 - "$zip" "$bindir" <<'PY' || die "解压 Electron 失败"
import sys, zipfile, os
from pathlib import Path
zf, dest = sys.argv[1], Path(sys.argv[2])
with zipfile.ZipFile(zf) as z:
    z.extractall(dest)
binp = dest / "electron"
os.chmod(binp, os.stat(binp).st_mode | 0o111)
print("extracted", binp, "size", binp.stat().st_size)
PY
}

if ! command -v npm >/dev/null 2>&1; then
  die "未找到 npm。请安装 Node.js 18+（nvm 或系统包）"
fi
log "npm: $(command -v npm) ($(npm --version 2>/dev/null || echo unknown))"

# 仅有空目录 node_modules/next 不算安装成功，必须能跑 next 可执行文件。
if [[ ! -f "$ROOT/frontend/node_modules/next/package.json" || ! -e "$ROOT/frontend/node_modules/.bin/next" ]]; then
  log "安装前端依赖（含 Next.js）…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund --registry=https://registry.npmmirror.com) >>"$LOG" 2>&1 \
    || die "npm install 前端依赖失败"
  [[ -f "$ROOT/frontend/node_modules/next/package.json" ]] || die "Next.js 仍未安装成功"
fi

if ! electron_bin >/dev/null; then
  rm -rf "$ROOT/frontend/node_modules/electron/dist"
  install_electron
fi

ELECTRON="$(electron_bin || true)"
if [[ -z "${ELECTRON}" ]]; then
  die "Electron 二进制仍不存在。请在有网络时运行：cd frontend && npm install"
fi
log "Electron: $ELECTRON"

export SKILLRADAR_PYTHON="$ROOT/.venv/bin/python"
export ELECTRON_RUN_AS_DESKTOP=1

if command -v notify-send >/dev/null 2>&1; then
  notify-send "SkillRadar" "正在打开桌面窗口…" >/dev/null 2>&1 || true
fi

cd "$ROOT/frontend"
log "exec $ELECTRON ."
exec env DISPLAY="${DISPLAY:-:0}" SKILLRADAR_PYTHON="$SKILLRADAR_PYTHON" \
  ELECTRON_RUN_AS_DESKTOP=1 "$ELECTRON" .
