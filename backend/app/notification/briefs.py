from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Repository, Subscription
from app.security import decrypt_secret
import json


def should_run(sub: Subscription, now: datetime | None = None) -> bool:
    if not sub.is_active:
        return False
    now = now or datetime.now(timezone.utc)
    last = sub.last_sent_at
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = now - last
    if sub.frequency == "daily":
        return delta >= timedelta(days=1)
    if sub.frequency == "weekly":
        return delta >= timedelta(weeks=1)
    if sub.frequency == "monthly":
        return delta >= timedelta(days=30)
    raise ValueError(f"unknown frequency: {sub.frequency}")


def match_repos(db: Session, conditions: dict[str, Any], limit: int = 30) -> list[Repository]:
    stmt = select(Repository)
    clauses = []
    keywords = conditions.get("keywords") or []
    for kw in keywords[:8]:
        like = f"%{kw}%"
        clauses.append(Repository.full_name.ilike(like))
        clauses.append(Repository.description.ilike(like))
    authors = conditions.get("authors") or []
    for author in authors[:8]:
        clauses.append(Repository.full_name.ilike(f"{author}/%"))
    orgs = conditions.get("organizations") or []
    for org in orgs[:8]:
        clauses.append(Repository.full_name.ilike(f"{org}/%"))
    repos = conditions.get("specific_repos") or []
    for name in repos[:12]:
        clauses.append(Repository.full_name == name)
    if clauses:
        stmt = stmt.where(or_(*clauses))
    stmt = stmt.order_by(Repository.stargazers_count.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def render_brief(sub: Subscription, repos: list[Repository], range_label: str) -> str:
    cond = sub.conditions or {}
    rows = "\n".join(
        f"| {r.full_name} | {(r.description or '')[:48]} | {r.fingerprint_type or '-'} | {r.stargazers_count} |"
        for r in repos[:12]
    ) or "| （本周期无匹配仓库） | - | - | - |"
    top = "\n".join(
        f"{i}. [{r.full_name}]({r.html_url}) ⭐ {r.stargazers_count}"
        for i, r in enumerate(repos[:5], 1)
    ) or "- 暂无"
    deep = ""
    if repos:
        r = repos[0]
        deep = f"### {r.full_name}\n- 指纹：{r.fingerprint_type or '未识别'}\n- 描述：{r.description or '（无）'}\n"
    return f"""# 【SkillRadar 情报简报】{sub.name}
**周期**：{range_label}
**监控条件**：关键词：{', '.join(cond.get('keywords') or []) or '（空）'}

## 📈 本周趋势
- 匹配仓库：{len(repos)} 个
- 热门仓库 Top 5：
{top}

## 🆕 新项目速览
| 仓库 | 描述 | 指纹类型 | 星标 |
|------|------|---------|------|
{rows}

## 🔍 深度分析
{deep or '（暂无）'}

## 🧠 趋势洞察
- AI Skill 仓库持续向 MCP / Claude Skill 指纹收敛，建议优先跟踪带 SKILL.md 或 mcp.json 的项目。

---
*由 SkillRadar 自动生成，如有打扰可退订*
"""


def load_channel_config(sub: Subscription, db: Session | None = None) -> dict[str, Any]:
    if sub.channel_config_id and db is not None:
        from app.models import ChannelConfig

        row = db.get(ChannelConfig, sub.channel_config_id)
        if row is not None and row.config_encrypted:
            raw = decrypt_secret(row.config_encrypted)
            try:
                named = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                raise ValueError("channel_config is not valid JSON") from exc
            if isinstance(named, dict) and named:
                return named
    raw = decrypt_secret(sub.channel_config_enc)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("channel_config is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("channel_config must be an object")
    return data
