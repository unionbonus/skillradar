from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisResult, utcnow


def upsert_analysis(db: Session, repository_id: int, analysis_type: str, content: dict[str, Any], evidence: dict[str, Any] | None = None) -> AnalysisResult:
    row = db.scalar(
        select(AnalysisResult).where(
            AnalysisResult.repository_id == repository_id,
            AnalysisResult.analysis_type == analysis_type,
        )
    )
    if row is None:
        row = AnalysisResult(repository_id=repository_id, analysis_type=analysis_type)
        db.add(row)
    row.content_json = content
    row.evidence = evidence or content.get("evidence") or {}
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def get_analysis(db: Session, repository_id: int, analysis_type: str) -> AnalysisResult | None:
    return db.scalar(
        select(AnalysisResult).where(
            AnalysisResult.repository_id == repository_id,
            AnalysisResult.analysis_type == analysis_type,
        )
    )
