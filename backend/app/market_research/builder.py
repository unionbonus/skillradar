from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import resolve_llm_config
from app.market_research.analyzer import analyze
from app.market_research.collectors import collect
from app.models import LLMConfig, MarketResearchReport, Repository, utcnow


def generate_market_research(
    db: Session,
    repo: Repository,
    user_id: UUID | None = None,
    llm_config_id: UUID | None = None,
) -> MarketResearchReport:
    llm_cfg: LLMConfig | None = None
    try:
        llm_cfg = resolve_llm_config(db, user_id, llm_config_id)
    except Exception:
        llm_cfg = None
    collected = collect(db, repo)
    payload = analyze(collected, llm_config=llm_cfg)
    md = render_market_markdown(payload)
    row = db.scalar(select(MarketResearchReport).where(MarketResearchReport.repository_id == repo.id))
    if row is None:
        row = MarketResearchReport(repository_id=repo.id)
        db.add(row)
    row.content_json = payload
    row.content_md = md
    row.evidence = payload.get("evidence") or []
    row.status = "published"
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def render_market_markdown(data: dict[str, Any]) -> str:
    name = data.get("plugin_name") or "插件"
    market = data.get("market") or {}
    pest = data.get("pest") or {}
    policy = data.get("policy") or {}
    competitors = data.get("competitors") or []
    pains = data.get("pain_points") or []
    mvp = data.get("mvp") or {}
    porter = data.get("porter") or {}
    swot = data.get("swot") or {}

    def ev_lines(items: list) -> str:
        if not items:
            return "- （待补充证据）"
        lines = []
        for item in items:
            if isinstance(item, dict):
                claim = item.get("claim") or item.get("title") or "依据"
                url = item.get("url")
                lines.append(f"- {claim}" + (f" — {url}" if url else ""))
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)

    comp_rows = "\n".join(
        f"| {c.get('name')} | {c.get('function') or '-'} | {c.get('performance') or '-'} | {c.get('ease')} | {c.get('community')} | {c.get('price') or '-'} |"
        for c in competitors
    ) or "| （不足 5 个，已用行业参照补齐） | - | - | - | - | - |"
    pain_md = "\n".join(
        f"### {p.get('title')}\n- 严重程度：{p.get('severity')}/5\n{ev_lines(p.get('evidence') or [])}"
        for p in pains
    )
    policy_md = "\n".join(f"- [{i.get('title')}]({i.get('url')})" for i in (policy.get("items") or [])) or "- （无）"
    users = mvp.get("users") or []
    user_md = "\n".join(f"- {u.get('role') if isinstance(u, dict) else u}" for u in users) or "- AI 开发者"

    return f"""# {name} 市场调研报告

## 1. 市场定义与规模
- 细分市场：{market.get('segment')}
- 描述：{market.get('description')}
- 全球/区域规模估算：{market.get('global_size')}
- 增长率与预测（CAGR）：{market.get('cagr')}
{ev_lines(market.get('evidence') or [])}

## 2. 宏观环境分析（PEST）
- 政治（P）：{(pest.get('political') or {}).get('summary')}
{ev_lines((pest.get('political') or {}).get('evidence') or [])}
- 经济（E）：{(pest.get('economic') or {}).get('summary')}
{ev_lines((pest.get('economic') or {}).get('evidence') or [])}
- 社会（S）：{(pest.get('social') or {}).get('summary')}
{ev_lines((pest.get('social') or {}).get('evidence') or [])}
- 技术（T）：{(pest.get('technical') or {}).get('summary')}
{ev_lines((pest.get('technical') or {}).get('evidence') or [])}

## 3. 产业政策分析
{policy_md}
- 影响评估：{policy.get('impact')}

### 3.1 波特五力（摘要）
- 现有竞争：{porter.get('rivalry')}
- 新进入者：{porter.get('new_entrants')}
- 替代品：{porter.get('substitutes')}
- 买方议价：{porter.get('buyer_power')}
- 供方议价：{porter.get('supplier_power')}

### 3.2 SWOT
- 优势：{'; '.join(swot.get('strengths') or [])}
- 劣势：{'; '.join(swot.get('weaknesses') or [])}
- 机会：{'; '.join(swot.get('opportunities') or [])}
- 威胁：{'; '.join(swot.get('threats') or [])}

## 4. 竞品分析
| 竞品 | 功能 | 性能 | 易用性 | 社区 | 价格 |
|------|------|------|--------|------|------|
{comp_rows}

- 差异化机会：{data.get('differentiation')}

## 5. 市场痛点及论证
{pain_md}

## 6. MVP 建议
- 目标用户：
{user_md}
- 场景：{'; '.join(mvp.get('scenarios') or [])}
- P0：{'; '.join(mvp.get('p0') or [])}
- P1：{'; '.join(mvp.get('p1') or [])}
- 验证指标：{'; '.join(mvp.get('metrics') or [])}
- 风险：{'; '.join(mvp.get('risks') or [])}
- 假设：{'; '.join(mvp.get('hypotheses') or [])}

---
*由 SkillRadar v0.5.0 市场调研模块生成，结论均附证据链接或推理依据。可人工编辑后重新发布。*
"""
