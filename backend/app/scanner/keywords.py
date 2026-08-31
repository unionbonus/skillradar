from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanKeyword, utcnow

DEFAULT_KEYWORDS = [
    ("mcp server", "keyword", 6, 20),
    ("claude skill", "keyword", 6, 20),
    ("langchain", "keyword", 12, 20),
    ("anthropics", "author", 12, 15),
]


def seed_keywords(db: Session) -> int:
    existing = {row.query for row in db.scalars(select(ScanKeyword)).all()}
    added = 0
    for query, stype, hours, limit in DEFAULT_KEYWORDS:
        if query in existing:
            continue
        db.add(
            ScanKeyword(
                query=query,
                search_type=stype,
                enabled=True,
                interval_hours=hours,
                limit=limit,
                last_status="idle",
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def due_keywords(db: Session, now: datetime | None = None) -> list[ScanKeyword]:
    now = now or datetime.now(timezone.utc)
    rows = list(db.scalars(select(ScanKeyword).where(ScanKeyword.enabled.is_(True))).all())
    out: list[ScanKeyword] = []
    for kw in rows:
        if keyword_is_due(kw, now):
            out.append(kw)
    return out


def keyword_is_due(kw: ScanKeyword, now: datetime | None = None) -> bool:
    if not kw.enabled:
        return False
    now = now or utcnow()
    last = kw.last_run_at
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    hours = kw.interval_hours if kw.interval_hours > 0 else 6
    return (now - last) >= timedelta(hours=hours)
