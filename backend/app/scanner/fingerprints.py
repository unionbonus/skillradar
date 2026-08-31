from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FINGERPRINT_RULES: dict[str, dict[str, Any]] = {
    "claude_skill": {
        "files": ["SKILL.md", "skill.yaml"],
        "dirs": [".claude/skills/", "skills/"],
        "parser": "ClaudeSkillParser",
    },
    "mcp_server": {
        "files": ["mcp.json", "server.py", "server.ts"],
        "dirs": ["src/", "tools/"],
        "parser": "MCPServerParser",
        "package_hints": ["@modelcontextprotocol", "mcp"],
    },
    "langchain_tool": {
        "files": ["langchain.json", "agent.yaml"],
        "dirs": ["tools/", "agents/", "chains/"],
        "parser": "LangChainParser",
        "package_hints": ["langchain"],
    },
}


def load_rules(extra_path: str | None = None) -> dict[str, dict[str, Any]]:
    rules = dict(FINGERPRINT_RULES)
    if extra_path:
        path = Path(extra_path)
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid fingerprint config: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError("fingerprint config must be an object")
            rules.update(loaded)
    return rules


def detect_fingerprint(file_tree: list[str], package_text: str = "") -> str | None:
    """Return the first matching fingerprint type for a relative file list."""
    lowered = [p.replace("\\", "/").removeprefix("./") for p in file_tree]
    names = {Path(p).name for p in lowered}
    pkg = package_text.lower()
    for ftype, rule in FINGERPRINT_RULES.items():
        for fname in rule.get("files", []):
            if fname in names or any(p.endswith("/" + fname) for p in lowered):
                return ftype
        for d in rule.get("dirs", []):
            prefix = d.rstrip("/") + "/"
            if any(p.startswith(prefix) or p == d.rstrip("/") for p in lowered):
                if ftype == "claude_skill" or fname_hint_ok(ftype, names, pkg):
                    return ftype
        for hint in rule.get("package_hints", []):
            if hint.lower() in pkg:
                return ftype
    return None


def fname_hint_ok(ftype: str, names: set[str], pkg: str) -> bool:
    if ftype == "mcp_server":
        return "mcp.json" in names or "mcp" in pkg or "server.py" in names or "server.ts" in names
    if ftype == "langchain_tool":
        return "langchain" in pkg or "agent.yaml" in names
    return True


def list_files(root: Path, limit: int = 4000) -> list[str]:
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")
    out: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".git/"):
                continue
            out.append(rel)
            if len(out) >= limit:
                break
    return out
