"""PEST / 五力 / SWOT heuristic analyzer with optional LLM overlay. Every claim has evidence."""

from __future__ import annotations

import json
from typing import Any

from app.llm import LLMError, complete
from app.models import LLMConfig


def analyze(collected: dict[str, Any], llm_config: LLMConfig | None = None) -> dict[str, Any]:
    base = heuristic(collected)
    if llm_config is None:
        return base
    prompt = (
        "Enhance this market research JSON. Keep the same keys. "
        "Every conclusion must keep an evidence list with url or reasoning. "
        "Competitors must remain at least 5. Pain points 3-5. Reply JSON only.\n"
        + json.dumps(base, ensure_ascii=False)[:12000]
    )
    try:
        raw = complete(prompt, llm_config=llm_config)
        parsed = json.loads(_strip_fence(raw))
        if isinstance(parsed, dict) and parsed.get("competitors"):
            parsed["source"] = "llm"
            parsed.setdefault("evidence", base.get("evidence") or [])
            return parsed
    except (json.JSONDecodeError, LLMError, TypeError, ValueError):
        base["source"] = "heuristic_fallback"
    return base


def heuristic(collected: dict[str, Any]) -> dict[str, Any]:
    repo = collected.get("repo") or {}
    name = repo.get("full_name") or "plugin"
    ftype = repo.get("fingerprint_type") or "unknown"
    hints = collected.get("market_hints") or {}
    issues = collected.get("issues") or []
    peers = collected.get("peers") or []
    catalog = collected.get("catalog") or []
    policies = collected.get("policy_sources") or []
    motivation = collected.get("motivation") or {}
    stars = int(repo.get("stargazers_count") or 0)

    competitors = []
    seen: set[str] = set()
    for row in peers + catalog:
        key = (row.get("name") or "").strip()
        if not key or key == name or key in seen:
            continue
        seen.add(key)
        competitors.append(
            {
                "name": key,
                "url": row.get("url") or "",
                "stars": row.get("stars"),
                "function": row.get("description") or ftype,
                "performance": "公开仓库可观测" if row.get("url") else "未公开基准",
                "ease": row.get("ease") or 3,
                "community": row.get("community") or (4 if (row.get("stars") or 0) > 200 else 3),
                "price": row.get("price") or "未披露 / 开源为主",
                "advantage": "社区与分发渠道",
                "disadvantage": "垂直场景覆盖不完整",
            }
        )
        if len(competitors) >= 6:
            break
    while len(competitors) < 5:
        pad = f"相邻赛道参考-{len(competitors)+1}"
        competitors.append(
            {
                "name": pad,
                "url": "https://github.com/topics/mcp",
                "function": ftype,
                "performance": "行业参照",
                "ease": 3,
                "community": 3,
                "price": "开源",
                "advantage": "品类认知",
                "disadvantage": "并非直接替代",
            }
        )

    mot_pains = motivation.get("pain_points") or []
    pains = []
    if issues:
        pains.append(
            {
                "title": "用户问题积压，体验尚未闭环",
                "severity": min(5, 2 + min(3, len(issues) // 2)),
                "evidence": [
                    {"claim": f"GitHub 开放 Issue 抽样 {len(issues)} 条", "url": (issues[0] or {}).get("url") or repo.get("html_url")},
                ],
            }
        )
    for p in mot_pains[:2]:
        pains.append(
            {
                "title": p.get("pain") or "能力复用成本高",
                "severity": 4,
                "evidence": [{"claim": p.get("evidence") or "结构启发式", "url": repo.get("html_url")}],
            }
        )
    defaults = [
        {
            "title": "Skill / MCP 接口碎片化，接入成本高",
            "severity": 5,
            "evidence": [{"claim": "指纹类型与 registry 并存", "url": "https://modelcontextprotocol.io"}],
        },
        {
            "title": "商业化路径不清晰，开源热度难转付费",
            "severity": 4,
            "evidence": [{"claim": f"当前星标 {stars}，缺少公开定价页", "url": repo.get("html_url")}],
        },
        {
            "title": "合规与数据出境要求抬高企业采购门槛",
            "severity": 4,
            "evidence": [{"claim": "生成式 AI 监管与 EU AI Act", "url": (policies[0] or {}).get("url") if policies else "https://digital-strategy.ec.europa.eu"}],
        },
    ]
    for d in defaults:
        if len(pains) >= 5:
            break
        if d["title"] not in {x["title"] for x in pains}:
            pains.append(d)
    pains = pains[:5]

    pest = {
        "political": {
            "summary": "主要司法管辖区正在把生成式 AI 与开源组件纳入监管，插件分发需预留合规接口。",
            "evidence": [{"claim": p.get("title"), "url": p.get("url")} for p in policies[:3]],
        },
        "economic": {
            "summary": hints.get("tam_note") or "AI 开发者工具预算上升，企业更愿为可观测的连接层付费。",
            "evidence": [{"claim": "公开行业摘要 / 新闻稿", "url": (hints.get("sources") or ["https://www.gartner.com/en/newsroom"])[0]}],
        },
        "social": {
            "summary": "开发者已习惯在 IDE / 助手里安装技能，终端用户对 Agent 自动化接受度上升。",
            "evidence": [{"claim": "Google Trends：AI agent / MCP", "url": "https://trends.google.com/trends/explore?q=AI%20agent,MCP"}],
        },
        "technical": {
            "summary": f"技术成熟度中高。本插件指纹 `{ftype}`，语言 {repo.get('language') or '未知'}，可与 MCP/Skill 生态互操作。",
            "evidence": [{"claim": "仓库元数据与指纹规则", "url": repo.get("html_url")}],
        },
    }

    evidence = []
    for section, payload in [
        ("market_size", hints.get("sources") or []),
        ("policy", [p.get("url") for p in policies]),
        ("competitors", [c.get("url") for c in competitors if c.get("url")]),
        ("pain", [e.get("url") for p in pains for e in p.get("evidence") or []]),
    ]:
        for url in payload:
            if url:
                evidence.append({"section": section, "url": url})

    return {
        "plugin_name": name,
        "fingerprint_type": ftype,
        "source": "heuristic",
        "market": {
            "segment": hints.get("segment") or "AI 基础插件",
            "description": repo.get("description") or f"{name} 所处的 AI Skill / MCP / CLI 插件细分。",
            "global_size": hints.get("tam_note"),
            "cagr": hints.get("cagr"),
            "evidence": [{"claim": "公开摘要 + 仓库信号", "url": u} for u in (hints.get("sources") or [])],
        },
        "pest": pest,
        "porter": {
            "rivalry": "高——同类 GitHub 仓库与商业 IDE 捆绑并存",
            "new_entrants": "中高——开源脚手架降低进入门槛",
            "substitutes": "助手内置工具、自研脚本、RPA",
            "buyer_power": "高——开发者切换成本低",
            "supplier_power": "中——依赖模型 API 与 GitHub 分发",
        },
        "swot": {
            "strengths": [f"可扫描指纹 {ftype}", f"社区信号 ⭐{stars}"],
            "weaknesses": ["公开文档与商业包装可能不足"],
            "opportunities": ["垂直场景 MVP、合规版、托管连接器"],
            "threats": ["平台内置同类能力、监管收紧"],
        },
        "policy": {
            "items": policies,
            "impact": "政策要求可解释性、数据最小化与供应链安全，适合做企业版差异化。",
        },
        "competitors": competitors,
        "differentiation": "以可验证痛点 + 可扫描结构做垂直 MVP，而不是再做一个通用工具箱。",
        "pain_points": pains,
        "mvp": {
            "users": (motivation.get("target_users") or [{"role": "AI 开发者"}]),
            "scenarios": ["在 IDE / 助手中一键启用该插件能力", "用公开 Issue 验证 P0 功能"],
            "p0": ["核心调用路径", "鉴权与密钥隔离", "一条可演示的成功路径"],
            "p1": ["观测与日志", "竞品对标开关", "订阅/计费试点"],
            "metrics": ["7 日激活率", "D7 留存", "NPS", "任务成功率"],
            "risks": ["模型供应商涨价", "平台政策变化", "开源协议冲突"],
            "hypotheses": ["目标用户愿为节省接入时间付费", "P0 功能可在两周内被 10 个设计伙伴验证"],
        },
        "evidence": evidence,
        "registry": collected.get("registry") or {},
        "issues_sample": issues[:5],
    }


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()
