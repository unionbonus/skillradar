#!/usr/bin/env bash
# 安装可双击的桌面入口（默认 Electron，无终端）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chmod +x "$ROOT/启动SkillRadar.sh" \
  "$ROOT/scripts/启动SkillRadar.sh" \
  "$ROOT/scripts/AutoDeployToNAS.sh" \
  "$ROOT/scripts/AutoDeployToNAS.py" \
  "$ROOT/deploy/nas/bootstrap.sh" \
  "$ROOT/scripts/install-desktop.sh" \
  "$ROOT/scripts/build-electron.sh" 2>/dev/null || true

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"

write_desktop() {
  local dest="$1"
  cat > "$dest" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SkillRadar 情报雷达
Comment=SkillRadar v0.5.3 Electron 桌面应用
Exec=/bin/bash "$ROOT/启动SkillRadar.sh"
Path=$ROOT
Terminal=false
Categories=Development;Network;
StartupNotify=true
EOF
  chmod +x "$dest"
}

write_desktop "$ROOT/SkillRadar.desktop"
write_desktop "$APP_DIR/skillradar.desktop"

if [[ -d "$HOME/Desktop" ]]; then
  write_desktop "$HOME/Desktop/SkillRadar.desktop"
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
echo "已安装: $APP_DIR/skillradar.desktop"
echo "双击: $ROOT/启动SkillRadar.sh  或  $ROOT/SkillRadar.desktop"
echo "打包 AppImage: $ROOT/scripts/build-electron.sh"
echo "部署 NAS: $ROOT/scripts/AutoDeployToNAS.sh"
