from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_electron_desktop_assets_exist():
    main = ROOT / "frontend" / "electron" / "main.cjs"
    preload = ROOT / "frontend" / "electron" / "preload.cjs"
    splash = ROOT / "frontend" / "electron" / "splash.html"
    pkg = ROOT / "frontend" / "package.json"
    assert main.is_file()
    text = main.read_text(encoding="utf-8")
    assert "0.5.2" in text
    assert "BrowserWindow" in text
    assert preload.is_file()
    assert "contextBridge" in preload.read_text(encoding="utf-8")
    assert splash.is_file()
    body = pkg.read_text(encoding="utf-8")
    assert '"electron"' in body
    assert '"main": "electron/main.cjs"' in body
    manual = ROOT / "用户手册.md"
    assert "0.5.2" in manual.read_text(encoding="utf-8")
    assert "Electron" in manual.read_text(encoding="utf-8")
