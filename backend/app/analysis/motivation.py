from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


class AnalysisError(Exception):
    pass


def heuristic_motivation(structure: dict[str, Any], readme: str = "") -> dict[str, Any]:
    ftype = structure.get("fingerprint_type") or "unknown"
    name = structure.get("full_name") or "skill"
    skills = structure.get("skills") or []
    desc = ""
    if skills:
        desc = str(skills[0].get("description") or "")
    text = (readme or desc).lower()
    principles = []
    if "compos" in text or "组合" in text:
        principles.append("可组合性优先")
    if "config" in text or "yaml" in text:
        principles.append("约定优于配置")
    if not principles:
        principles = ["技能可发现、可复用", "接口显式、配置外置"]
    pain = "多工具编排复杂" if ftype in {"mcp_server", "langchain_tool"} else "Skill 结构不统一、难以复用"
    solution = "统一 Skill / MCP 接口并提供可扫描指纹"
    return {
        "design_principles": principles,
        "target_users": [
            {"role": "AI 开发者", "tech_level": "高级", "percentage": 70},
            {"role": "AI 产品经理", "tech_level": "中级", "percentage": 30},
        ],
        "pain_points": [{"pain": pain, "solution": solution, "evidence": "README / skill metadata"}],
        "tradeoffs": [
            {"tradeoff": "牺牲部分灵活性换取开箱即用", "reason": "默认配置覆盖常见场景"}
        ],
        "evolution": [{"version": "v0.1", "change": "核心技能/工具实现", "motivation": "验证可行性"}],
        "competitive_advantages": ["结构可扫描", "可生成架构图与 PRD"],
        "source": "heuristic",
        "fingerprint_type": ftype,
        "subject": name,
    }


def render_prd(structure: dict[str, Any], motivation: dict[str, Any]) -> str:
    name = structure.get("full_name") or "Untitled Skill"
    ftype = structure.get("fingerprint_type") or "generic"
    skills = structure.get("skills") or []
    pains = motivation.get("pain_points") or []
    users = motivation.get("target_users") or []
    principles = motivation.get("design_principles") or []
    skill_lines = "\n".join(
        f"- **{s.get('name')}**：{s.get('description') or ''}（入口 `{s.get('entry_file')}`）" for s in skills
    ) or "- （未识别到技能条目）"
    stories = "\n".join(
        f"- 作为{u.get('role')}，我希望复用 {name}，以便减少重复接入成本。" for u in users
    )
    return f"""# PRD · {name}

## 1. 背景与定位
- 指纹类型：`{ftype}`
- 设计原则：{'；'.join(principles)}
- 产品一句话：把开源 AI Skill 拆成可理解、可订阅、可复用的能力单元。

## 2. 目标用户
{chr(10).join(f"- {u.get('role')}（{u.get('tech_level')}，约 {u.get('percentage')}%）" for u in users)}

## 3. 痛点与方案
{chr(10).join(f"- 痛点：{p.get('pain')} → 方案：{p.get('solution')}（证据：{p.get('evidence')}）" for p in pains)}

## 4. 功能需求
### 4.1 技能清单
{skill_lines}

### 4.2 非功能
- 仅分析公开仓库；克隆 depth=1；密钥不明文出日志。

## 5. 用户故事
{stories}

## 6. 成功指标
- 扫描命中指纹准确率
- 从仓库到 PRD 的端到端时长
- 订阅简报送达成功率

---
*由 SkillRadar v0.1 自动生成，可在工作台编辑后导出。*
"""


def llm_complete(prompt: str) -> str:
    from app.llm import LLMError, complete

    try:
        return complete(prompt)
    except LLMError as exc:
        raise AnalysisError(str(exc)) from exc


def analyze_motivation(structure: dict[str, Any], readme: str = "") -> dict[str, Any]:
    base = heuristic_motivation(structure, readme)
    settings = get_settings()
    if not settings.llm_api_key:
        return base
    prompt = (
        "Infer design motivation JSON with keys design_principles, target_users, "
        "pain_points, tradeoffs, evolution, competitive_advantages.\n"
        f"structure={json.dumps(structure, ensure_ascii=False)[:8000]}\nreadme={readme[:4000]}"
    )
    try:
        raw = llm_complete(prompt)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise AnalysisError("LLM JSON is not an object")
        parsed["source"] = "llm"
        return parsed
    except (json.JSONDecodeError, AnalysisError):
        base["source"] = "heuristic_fallback"
        return base
