from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def read_text(path: Path, limit: int = 200_000) -> str:
    try:
        data = path.read_bytes()[:limit]
        return data.decode("utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def parse_front_matter(md: str) -> tuple[dict[str, Any], str]:
    if not md.startswith("---"):
        return {}, md
    parts = md.split("---", 2)
    if len(parts) < 3:
        return {}, md
    meta: dict[str, Any] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].lstrip("\n")


class ClaudeSkillParser:
    def parse(self, root: Path, files: list[str]) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for rel in files:
            if Path(rel).name not in {"SKILL.md", "skill.yaml"}:
                continue
            path = root / rel
            text = read_text(path)
            meta, body = parse_front_matter(text)
            parent = Path(rel).parent.as_posix()
            prompts = [f for f in files if f.startswith(parent + "/") and f.endswith(".md") and f != rel]
            examples = [f for f in files if "/examples/" in f or f.endswith("example.md")]
            tools = _tools_from_dir(root, files, parent)
            skills.append(
                {
                    "name": meta.get("name") or Path(rel).parent.name or "skill",
                    "description": meta.get("description") or body.strip().split("\n", 1)[0][:240],
                    "entry_file": rel,
                    "config": {k: v for k, v in meta.items() if k not in {"name", "description"}},
                    "prompt_templates": prompts[:12],
                    "tools": tools,
                    "examples": examples[:12],
                }
            )
        if not skills:
            skills.append(_generic_skill(root, files, "claude_skill"))
        return skills


class MCPServerParser:
    def parse(self, root: Path, files: list[str]) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        mcp_rel = next((f for f in files if Path(f).name == "mcp.json"), None)
        config: dict[str, Any] = {}
        if mcp_rel:
            try:
                config = json.loads(read_text(root / mcp_rel))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid mcp.json: {exc}") from exc
            if isinstance(config.get("tools"), list):
                tools = config["tools"]
        pkg = _read_json(root, "package.json")
        name = (config.get("name") if isinstance(config, dict) else None) or pkg.get("name") or root.name
        entry = next((f for f in ("server.py", "server.ts", "src/index.ts", "src/server.py") if f in files), files[0] if files else "")
        return [
            {
                "name": str(name),
                "description": str(config.get("description") or pkg.get("description") or "MCP server"),
                "entry_file": entry,
                "config": config if isinstance(config, dict) else {},
                "prompt_templates": [f for f in files if f.endswith(".md")][:8],
                "tools": tools,
                "examples": [f for f in files if "example" in f.lower()][:8],
            }
        ]


class LangChainParser:
    def parse(self, root: Path, files: list[str]) -> list[dict[str, Any]]:
        return [_generic_skill(root, files, "langchain_tool")]


def _generic_skill(root: Path, files: list[str], kind: str) -> dict[str, Any]:
    readme = next((f for f in files if f.lower() in {"readme.md", "readme"}), None)
    desc = ""
    if readme:
        desc = read_text(root / readme).strip().split("\n", 1)[0][:240]
    entry = next((f for f in files if f.endswith((".py", ".ts", ".js")) and "test" not in f.lower()), files[0] if files else "")
    return {
        "name": root.name,
        "description": desc or kind,
        "entry_file": entry,
        "config": {"fingerprint": kind},
        "prompt_templates": [f for f in files if f.endswith(".md")][:8],
        "tools": _tools_from_dir(root, files, "tools"),
        "examples": [f for f in files if "example" in f.lower()][:8],
    }


def _tools_from_dir(root: Path, files: list[str], parent: str) -> list[dict[str, Any]]:
    tools = []
    for rel in files:
        if not rel.startswith(parent.rstrip("/") + "/"):
            continue
        if not rel.endswith((".py", ".ts", ".js", ".json")):
            continue
        name = Path(rel).stem
        tools.append({"name": name, "input_schema": {"query": "string"}, "output_schema": {"results": "array"}, "file": rel})
    return tools[:20]


def _read_json(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    if not path.is_file():
        return {}
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {name}: {exc}") from exc
    return data if isinstance(data, dict) else {}


IMPORT_RE = {
    "python": re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M),
    "js": re.compile(r"""(?:from\s+['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))"""),
}


def extract_imports(root: Path, files: list[str]) -> dict[str, list[str]]:
    internal: set[str] = set()
    external: set[str] = set()
    local_mods = {Path(f).stem for f in files}
    for rel in files:
        suffix = Path(rel).suffix
        lang = "python" if suffix == ".py" else "js" if suffix in {".ts", ".js", ".tsx"} else None
        if not lang:
            continue
        text = read_text(root / rel, limit=80_000)
        for match in IMPORT_RE[lang].finditer(text):
            mod = next((g for g in match.groups() if g), "")
            name = mod.split(".")[0].lstrip("./")
            if not name or name.startswith("."):
                continue
            if name in local_mods or any(f.startswith(name.replace(".", "/") ) for f in files):
                internal.add(mod)
            else:
                external.add(mod)
    reqs = _manifest_deps(root)
    external.update(reqs)
    return {"internal": sorted(internal)[:80], "external": sorted(external)[:80], "cross_repo": []}


def _manifest_deps(root: Path) -> set[str]:
    deps: set[str] = set()
    req = root / "requirements.txt"
    if req.is_file():
        for line in read_text(req).splitlines():
            pkg = re.split(r"[<>=\[]", line.strip())[0].strip()
            if pkg and not pkg.startswith("#"):
                deps.add(pkg)
    pkg = _read_json(root, "package.json")
    for key in ("dependencies", "devDependencies"):
        block = pkg.get(key) or {}
        if isinstance(block, dict):
            deps.update(str(k) for k in block)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        for line in read_text(pyproject).splitlines():
            m = re.match(r'\s*"([A-Za-z0-9_.-]+)"', line)
            if m:
                deps.add(m.group(1))
    return deps
