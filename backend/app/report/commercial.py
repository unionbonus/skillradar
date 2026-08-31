from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CommercialReport, MarketResearchReport, RepoAnalysis, Repository, utcnow


def generate_commercial_report(db: Session, repo: Repository, market: MarketResearchReport | None = None) -> CommercialReport:
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
    structure = (analysis.structure if analysis else {}) or {}
    motivation = (analysis.motivation if analysis else {}) or {}
    market_json = (market.content_json if market else {}) or {}
    payload = {
        "plugin_name": repo.full_name,
        "fingerprint_type": repo.fingerprint_type or structure.get("fingerprint_type"),
        "structure": structure,
        "motivation": motivation,
        "market": market_json,
    }
    md = render_commercial_markdown(repo, structure, motivation, market_json, market.id if market else None)
    row = db.scalar(select(CommercialReport).where(CommercialReport.repository_id == repo.id))
    if row is None:
        row = CommercialReport(repository_id=repo.id)
        db.add(row)
    row.content_json = payload
    row.content_md = md
    row.market_research_id = market.id if market else None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def render_commercial_markdown(
    repo: Repository,
    structure: dict[str, Any],
    motivation: dict[str, Any],
    market: dict[str, Any],
    market_id: Any = None,
) -> str:
    name = repo.full_name
    ftype = repo.fingerprint_type or structure.get("fingerprint_type") or "unknown"
    skills = structure.get("skills") or []
    skill_lines = "\n".join(
        f"- **{s.get('name')}**：{(s.get('description') or '')[:120]}" for s in skills
    ) or "- （尚未拆解到技能条目，可先运行仓库拆解）"
    principles = "；".join(motivation.get("design_principles") or ["结构可扫描", "能力可复用"])
    users = motivation.get("target_users") or []
    user_md = "\n".join(
        f"- {u.get('role')}（{u.get('tech_level', '')}）" for u in users if isinstance(u, dict)
    ) or "- AI 开发者 / 产品经理"
    pains = motivation.get("pain_points") or []
    pain_md = "\n".join(
        f"- {p.get('pain')} → {p.get('solution')}" for p in pains if isinstance(p, dict)
    ) or "- 接入成本高，缺少标准化包装"

    pest = (market.get("pest") or {}) if market else {}
    policy = (market.get("policy") or {}) if market else {}
    competitors = (market.get("competitors") or []) if market else []
    m_pains = (market.get("pain_points") or []) if market else []
    mvp = (market.get("mvp") or {}) if market else {}
    link = f"`/repos/{repo.id}` 市场调研 Tab" if market_id else "（尚未生成市场调研，本章为结构占位）"

    pest_md = "\n".join(
        f"- **{label}**：{(pest.get(key) or {}).get('summary') or '见完整市场调研报告'}"
        for label, key in [("政治", "political"), ("经济", "economic"), ("社会", "social"), ("技术", "technical")]
    )
    policy_md = "\n".join(
        f"- [{i.get('title')}]({i.get('url')})" for i in (policy.get("items") or [])
    ) or "- 见完整市场调研报告"
    comp_rows = "\n".join(
        f"| {c.get('name')} | {c.get('advantage') or '-'} | {c.get('disadvantage') or '-'} | {c.get('price') or '-'} |"
        for c in competitors[:8]
    ) or "| （待市场调研填充） | - | - | - |"
    mp_md = "\n".join(
        f"- **{p.get('title')}**（{p.get('severity')}/5）"
        for p in m_pains
    ) or "- （待市场调研填充）"

    return f"""# {name} 商业拆解报告

## 1. 产品定位
- 仓库：[{name}]({repo.html_url})
- 指纹类型：`{ftype}`
- 一句话：把该 AI 基础插件拆成可理解的商业单元，判断值不值得立项或投资。
- 设计原则：{principles}

## 2. 技术架构拆解
{skill_lines}
- 语言：{repo.language or structure.get('language') or '未知'}
- 星标：{repo.stargazers_count}

## 3. 商业模式推断
- 当前形态：开源插件 / 技能包（默认免费分发）
- 可能收费点：托管连接、企业合规版、垂直模板、用量套餐
- 渠道：GitHub、MCP Registry、IDE 市场、飞书/企微简报触达

## 4. 用户与场景
{user_md}
{pain_md}

## 5. 需求调研详细分析

> 完整报告见 {link}

### 5.1 宏观环境
{pest_md}

### 5.2 产业政策
{policy_md}
- 影响：{policy.get('impact') or '监管抬高企业采购门槛，合规能力可成为溢价来源。'}

### 5.3 竞品分析
| 竞品 | 优势 | 劣势 | 价格 |
|------|------|------|------|
{comp_rows}

- 差异化：{market.get('differentiation') if market else '待调研'}

### 5.4 市场痛点及论证
{mp_md}

### 5.5 MVP 建议
- P0：{'; '.join(mvp.get('p0') or ['核心成功路径', '密钥隔离'])}
- P1：{'; '.join(mvp.get('p1') or ['观测', '计费试点'])}
- 验证：{'; '.join(mvp.get('metrics') or ['激活率', 'D7 留存', 'NPS'])}

## 6. 商业机会
- 垂直场景包装（比通用工具箱更容易转化）
- 企业合规发行版（日志、权限、私有化）
- 与订阅简报联动的持续情报产品

## 7. 风险与建议
- 平台内置同类能力导致功能商品化
- 开源协议与模型 ToS 冲突
- 建议：先用市场调研痛点验证 2 周设计伙伴，再投入完整研发

---
*由 SkillRadar v0.5.0 商业拆解模板生成。第 5 章数据来自市场调研模块 JSON。*
"""
