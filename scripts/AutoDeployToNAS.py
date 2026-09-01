#!/usr/bin/env python3
"""AutoDeployToNAS — 将 SkillRadar 部署到极空间 Docker。

优先读本仓库 .nas-deploy.env；若无则复用兄弟项目 knowledge-graph-go 的账号，
但远程目录固定为 /volume1/skillradar/*，不会覆盖星觅目录。

环境变量（勿把密码提交进 Git）：
  NAS_HOST NAS_PORT NAS_USER NAS_PASS
  REMOTE_DIR REMOTE_DATA HOST_PORT BACKEND_PORT
"""
from __future__ import annotations

import os
import shlex
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"
PKG = ROOT / "dist" / f"skillradar-nas-{VERSION}.tar.gz"

DEFAULT_REMOTE_DIR = "/volume1/skillradar/app"
DEFAULT_REMOTE_DATA = "/volume1/skillradar/data"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def load_settings() -> dict[str, str]:
    cred_files = [
        ROOT / ".nas-deploy.env",
        ROOT.parent / "knowledge-graph-go" / ".nas-deploy.env",
    ]
    merged: dict[str, str] = {}
    own = ROOT / ".nas-deploy.env"
    for path in cred_files:
        parsed = _parse_env_file(path)
        if not parsed:
            continue
        if path == own:
            merged.update(parsed)
        else:
            for key in ("NAS_HOST", "NAS_PORT", "NAS_USER", "NAS_PASS"):
                if key in parsed and key not in merged:
                    merged[key] = parsed[key]
    for key, val in os.environ.items():
        if key.startswith("NAS_") or key in {
            "REMOTE_DIR",
            "REMOTE_DATA",
            "HOST_PORT",
            "BACKEND_PORT",
            "COMPOSE_NAME",
            "SECRET_KEY",
            "CORS_ORIGINS",
        }:
            if val:
                merged[key] = val
    merged.setdefault("NAS_HOST", "192.168.1.9")
    merged.setdefault("NAS_PORT", "10000")
    merged.setdefault("NAS_USER", "18621015693")
    merged.setdefault("NAS_PASS", "")
    if "knowledge-graph" in merged.get("REMOTE_DIR", "") or not merged.get("REMOTE_DIR"):
        merged["REMOTE_DIR"] = DEFAULT_REMOTE_DIR
    if "knowledge-graph" in merged.get("REMOTE_DATA", "") or not merged.get("REMOTE_DATA"):
        merged["REMOTE_DATA"] = DEFAULT_REMOTE_DATA
    merged.setdefault("HOST_PORT", "13000")
    merged.setdefault("BACKEND_PORT", "18000")
    merged.setdefault("COMPOSE_NAME", "skillradar")
    merged.setdefault("SECRET_KEY", "change-me-to-a-32-byte-or-longer-random-string")
    return merged


def package_source() -> Path:
    PKG.parent.mkdir(parents=True, exist_ok=True)
    include = [
        "backend",
        "frontend",
        "deploy",
        "docker-compose.nas.yml",
        ".env.example",
    ]
    skip_parts = {
        "node_modules",
        ".next",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".git",
        "dist",
        "data",
        "htmlcov",
        "tests",
    }
    skip_suffix = {".db", ".sqlite", ".pyc"}
    with tarfile.open(PKG, "w:gz") as tar:
        for name in include:
            src = ROOT / name
            if not src.exists():
                raise SystemExit(f"missing {src}")
            tar.add(
                src,
                arcname=name,
                filter=lambda info: None
                if any(p in skip_parts for p in Path(info.name).parts)
                or Path(info.name).suffix in skip_suffix
                else info,
            )
    print(f"package {PKG} ({PKG.stat().st_size} bytes)")
    return PKG


def connect(cfg: dict[str, str]) -> paramiko.SSHClient:
    if not cfg["NAS_PASS"]:
        raise SystemExit("请设置 NAS_PASS，或在仓库创建 .nas-deploy.env（已 gitignore）")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        cfg["NAS_HOST"],
        port=int(cfg["NAS_PORT"]),
        username=cfg["NAS_USER"],
        password=cfg["NAS_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 1800) -> str:
    preview = cmd if len(cmd) < 220 else cmd[:220] + "..."
    print("$", preview)
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    text = (out + ("\n" + err if err.strip() else "")).rstrip()
    if text:
        print(text)
    if code != 0:
        raise RuntimeError(f"remote exit {code}")
    return out


def main() -> None:
    cfg = load_settings()
    host = cfg["NAS_HOST"]
    print(f"NAS {cfg['NAS_USER']}@{host}:{cfg['NAS_PORT']}")
    print(f"remote app={cfg['REMOTE_DIR']} data={cfg['REMOTE_DATA']}")
    pkg = package_source()
    cors = cfg.get("CORS_ORIGINS") or f"http://{host}:{cfg['HOST_PORT']},http://127.0.0.1:{cfg['HOST_PORT']}"

    client = connect(cfg)
    try:
        app = shlex.quote(cfg["REMOTE_DIR"])
        data = shlex.quote(cfg["REMOTE_DATA"])
        try:
            run(client, f"sudo -n mkdir -p {app} {data} {data}/clones")
            run(client, f"sudo -n chmod -R a+rwx {app} {data}")
        except RuntimeError:
            run(client, f"mkdir -p {app} {data} {data}/clones")
            run(client, f"chmod -R a+rwx {app} {data} || true")

        remote_pkg = f"/tmp/skillradar-nas-{VERSION}.tar.gz"
        print(f"upload {pkg.name}")
        sftp = client.open_sftp()
        sftp.put(str(pkg), remote_pkg)
        sftp.close()

        extract = f"""
set -euo pipefail
APP={app}
DATA={data}
sudo -n rm -rf /tmp/skillradar-extract
mkdir -p /tmp/skillradar-extract
tar -xzf {shlex.quote(remote_pkg)} -C /tmp/skillradar-extract
sudo -n bash -lc 'rm -rf '"$APP"'/*; cp -a /tmp/skillradar-extract/. '"$APP"'/'
chmod +x "$APP/deploy/nas/bootstrap.sh"
export APP_DIR="$APP"
export DATA_DIR="$DATA"
export HOST_PORT={shlex.quote(cfg["HOST_PORT"])}
export BACKEND_PORT={shlex.quote(cfg["BACKEND_PORT"])}
export COMPOSE_NAME={shlex.quote(cfg["COMPOSE_NAME"])}
export SECRET_KEY={shlex.quote(cfg["SECRET_KEY"])}
export CORS_ORIGINS={shlex.quote(cors)}
bash "$APP/deploy/nas/bootstrap.sh"
"""
        run(client, f"bash -lc {shlex.quote(extract)}", timeout=2400)
    finally:
        client.close()

    health = f"http://{host}:{cfg['BACKEND_PORT']}/api/v1/health"
    web = f"http://{host}:{cfg['HOST_PORT']}/"
    last_err = ""
    for i in range(20):
        try:
            with urllib.request.urlopen(health, timeout=5) as resp:
                body = resp.read().decode()
                print(resp.status, body)
                print("DEPLOY_OK", health)
                print("打开前端", web)
                return
        except Exception as exc:
            last_err = str(exc)
            print("retry", i + 1, last_err)
            time.sleep(3)
    print(
        f"WARN: 本机无法访问 {health}（{last_err}）。"
        f"请在 NAS 上执行: curl -s http://127.0.0.1:{cfg['BACKEND_PORT']}/api/v1/health",
        file=sys.stderr,
    )
    raise SystemExit("health probe failed")


if __name__ == "__main__":
    main()
