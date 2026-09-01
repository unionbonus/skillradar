from __future__ import annotations

from pathlib import Path
from typing import Any


PLUGIN_HINTS = ("plugins/", "extensions/", "addons/")
LAYER_HINTS = ("api/", "core/", "infra/", "domain/", "adapters/")
EVENT_HINTS = ("queue", "kafka", "rabbit", "pubsub", "event_bus", "events/")
WORKER_HINTS = ("worker", "scheduler", "pipeline", "celery")
MW_HINTS = ("middleware", "decorator", "intercept")


def _files(structure: dict[str, Any]) -> list[str]:
    files = structure.get("files") or []
    if files:
        return [str(f).replace("\\", "/").lower() for f in files]
    skills = structure.get("skills") or []
    out = []
    for s in skills:
        if isinstance(s, dict) and s.get("entry_file"):
            out.append(str(s["entry_file"]).replace("\\", "/").lower())
    return out


def detect_arch_style(files: list[str]) -> dict[str, Any]:
    blob = " ".join(files)
    scores = {
        "plugin_microkernel": sum(1 for h in PLUGIN_HINTS if h in blob),
        "layered": sum(1 for h in LAYER_HINTS if h in blob),
        "event_driven": sum(1 for h in EVENT_HINTS if h in blob),
        "master_worker": sum(1 for h in WORKER_HINTS if h in blob),
        "middleware": sum(1 for h in MW_HINTS if h in blob),
        "functional_pipeline": 1 if any("pipeline" in f or "/fn/" in f for f in files) else 0,
    }
    style = max(scores, key=scores.get) if any(scores.values()) else "modular_monolith"
    if not any(scores.values()) and any("skill.md" in f or "mcp.json" in f for f in files):
        style = "plugin_microkernel"
        scores["plugin_microkernel"] = 1
    labels = {
        "plugin_microkernel": "插件化 / 微内核",
        "layered": "分层架构",
        "event_driven": "事件驱动",
        "master_worker": "主从 / 管道-过滤器",
        "middleware": "中间件模式",
        "functional_pipeline": "函数式管道",
        "modular_monolith": "模块化单体",
    }
    return {"style": style, "label": labels.get(style, style), "signals": scores}


def identify_core_modules(structure: dict[str, Any], files: list[str]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in files:
        parts = Path(rel).parts
        if not parts:
            continue
        top = parts[0] if parts[0] not in {".", "src"} else (parts[1] if len(parts) > 1 else parts[0])
        if top in seen or top.startswith(".") or top in {"node_modules", "dist", "tests", "__pycache__"}:
            continue
        seen.add(top)
        degree = sum(1 for f in files if f.startswith(top) or f"/{top}/" in f)
        modules.append(
            {
                "name": top,
                "path": top,
                "role": _guess_role(top),
                "degree": degree,
            }
        )
        if len(modules) >= 12:
            break
    skills = structure.get("skills") or []
    for skill in skills[:8]:
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("name") or "skill")
        modules.append(
            {
                "name": name,
                "path": skill.get("entry_file") or "",
                "role": "技能入口",
                "degree": len(skill.get("tools") or []) + 1,
            }
        )
    modules.sort(key=lambda m: int(m.get("degree") or 0), reverse=True)
    return modules[:16]


def _guess_role(name: str) -> str:
    n = name.lower()
    if n in {"api", "server", "app"}:
        return "接入层"
    if n in {"core", "engine", "lib"}:
        return "核心逻辑"
    if n in {"tools", "skills", "plugins"}:
        return "扩展点"
    if n in {"infra", "db", "storage"}:
        return "基础设施"
    return "业务模块"


def reconstruct_call_flow(structure: dict[str, Any]) -> dict[str, Any]:
    skills = structure.get("skills") or []
    steps: list[dict[str, str]] = []
    mermaid = ["sequenceDiagram"]
    entry = "Client"
    mermaid.append(f"    {entry}->>Runtime: invoke")
    for skill in skills[:6]:
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("name") or "skill").replace(" ", "_")[:32]
        steps.append({"from": "Runtime", "to": name, "via": skill.get("entry_file") or ""})
        mermaid.append(f"    Runtime->>{name}: {skill.get('entry_file') or 'entry'}")
        for tool in (skill.get("tools") or [])[:4]:
            tname = str(tool.get("name") if isinstance(tool, dict) else tool).replace(" ", "_")[:24]
            mermaid.append(f"    {name}->>{tname}: CALLS")
            steps.append({"from": name, "to": tname, "via": "tool"})
    if len(mermaid) == 1:
        mermaid.append("    Client->>Plugin: start")
    return {"steps": steps, "mermaid": "\n".join(mermaid)}


def find_extension_points(files: list[str], structure: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for rel in files:
        low = rel.lower()
        if any(x in low for x in ("plugin", "extension", "hook", "adapter", "provider")):
            points.append({"path": rel, "kind": "hot_plug", "note": "可插拔目录或适配器"})
        if any(x in low for x in ("config", ".env.example", "settings")):
            points.append({"path": rel, "kind": "config", "note": "配置外置"})
    if any((s.get("tools") if isinstance(s, dict) else None) for s in (structure.get("skills") or [])):
        points.append({"path": "tools", "kind": "tools", "note": "工具清单可扩展"})
    # unique by path
    seen = set()
    uniq = []
    for p in points:
        if p["path"] in seen:
            continue
        seen.add(p["path"])
        uniq.append(p)
    return uniq[:20]


def analyze_data_flow(structure: dict[str, Any]) -> dict[str, Any]:
    sources = ["manifest / SKILL.md / mcp.json"]
    sinks = ["LLM", "外部 API"]
    deps = structure.get("dependencies") or {}
    external = deps.get("external") if isinstance(deps, dict) else []
    if external:
        sinks.extend(str(x) for x in external[:8])
    return {
        "sources": sources,
        "sinks": sinks[:12],
        "transforms": ["解析配置", "调用工具", "组装 Prompt", "返回结果"],
    }


def analyze_deep_dive(structure: dict[str, Any]) -> dict[str, Any]:
    files = _files(structure)
    arch = detect_arch_style(files)
    modules = identify_core_modules(structure, files)
    flow = reconstruct_call_flow(structure)
    extensions = find_extension_points(files, structure)
    data_flow = analyze_data_flow(structure)
    return {
        "architecture": arch,
        "modules": modules,
        "call_flow": flow,
        "extension_points": extensions,
        "data_flow": data_flow,
        "file_count": len(files) or structure.get("file_count") or 0,
        "fingerprint_type": structure.get("fingerprint_type"),
        "source": "heuristic",
    }
