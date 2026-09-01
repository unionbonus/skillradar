from __future__ import annotations

from typing import Any


DEFAULTS = {
    "claude_skill": "多数 Skill 只放一份 SKILL.md 和脚本，缺少可扫描指纹与订阅面。",
    "mcp_server": "常见 MCP 只暴露工具列表，缺少架构图与动机说明。",
    "langchain_tool": "LangChain 工具往往散落在 examples，难以横向对比。",
}


def mine_highlights(structure: dict[str, Any], motivation: dict[str, Any] | None = None) -> dict[str, Any]:
    ftype = structure.get("fingerprint_type") or "unknown"
    skills = structure.get("skills") or []
    deps = structure.get("dependencies") or {}
    external = (deps.get("external") if isinstance(deps, dict) else []) or []
    highlights: list[dict[str, Any]] = []
    if skills:
        skill = skills[0] if isinstance(skills[0], dict) else {}
        entry = skill.get("entry_file") or "SKILL.md"
        highlights.append(
            {
                "title": "显式技能入口",
                "summary": f"通过 `{entry}` 暴露能力，降低发现成本。",
                "impact": "显著降低接入门槛",
                "generality": "可被其他 Skill 仓库复用",
                "novelty": "中",
                "elegance": "高",
                "evidence": [{"kind": "file", "path": entry, "note": "parser 识别的入口"}],
            }
        )
        if skill.get("tools"):
            highlights.append(
                {
                    "title": "工具清单外置",
                    "summary": "工具/API 在清单中声明，而不是散落在实现里。",
                    "impact": "便于审计与订阅",
                    "generality": "高",
                    "novelty": "中",
                    "elegance": "高",
                    "evidence": [{"kind": "structure", "path": "skills[].tools", "note": str(len(skill.get("tools") or []))}],
                }
            )
    if external:
        highlights.append(
            {
                "title": "依赖边界清晰",
                "summary": "外部包被单独抽出，便于评估供应链风险。",
                "impact": "降低集成不确定性",
                "generality": "高",
                "novelty": "低",
                "elegance": "中",
                "evidence": [{"kind": "deps", "path": "dependencies.external", "note": ", ".join(str(x) for x in external[:6])}],
            }
        )
    if motivation and motivation.get("pain_points"):
        pain = motivation["pain_points"][0]
        highlights.append(
            {
                "title": "针对明确痛点",
                "summary": str(pain.get("pain") or DEFAULTS.get(ftype, "补齐结构可扫描性")),
                "impact": "对目标用户有直接收益",
                "generality": "中",
                "novelty": "中",
                "elegance": "中",
                "evidence": [{"kind": "motivation", "path": "pain_points[0]", "note": pain.get("evidence") or "heuristic"}],
            }
        )
    if not highlights:
        highlights.append(
            {
                "title": "结构可扫描",
                "summary": DEFAULTS.get(ftype, "仓库具备可识别指纹，适合进入情报雷达。"),
                "impact": "可进入统一分析流水线",
                "generality": "高",
                "novelty": "低",
                "elegance": "中",
                "evidence": [{"kind": "fingerprint", "path": ftype, "note": "fingerprint_rules.json"}],
            }
        )
    return {"highlights": highlights, "baseline": DEFAULTS.get(ftype, ""), "source": "heuristic"}
