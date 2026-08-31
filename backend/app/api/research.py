from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.market_research.builder import generate_market_research, render_market_markdown
from app.models import CommercialReport, MarketResearchReport, Repository, User
from app.report.commercial import generate_commercial_report

router = APIRouter(prefix="/api/v1", tags=["research"])


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


class ResearchIn(BaseModel):
    llm_config_id: UUID | None = None


class MarketResearchUpdate(BaseModel):
    content_md: str | None = None
    content_json: dict | None = None
    status: str | None = None


def _repo(db: Session, plugin_id: int) -> Repository:
    repo = db.get(Repository, plugin_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return repo


def _market_out(row: MarketResearchReport) -> dict:
    return {
        "id": str(row.id),
        "plugin_id": row.repository_id,
        "repository_id": row.repository_id,
        "content_md": row.content_md,
        "content_json": row.content_json or {},
        "evidence": row.evidence or [],
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _commercial_out(row: CommercialReport) -> dict:
    return {
        "id": str(row.id),
        "plugin_id": row.repository_id,
        "repository_id": row.repository_id,
        "market_research_id": str(row.market_research_id) if row.market_research_id else None,
        "content_md": row.content_md,
        "content_json": row.content_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/plugins/{plugin_id}/market-research")
@router.post("/repos/{plugin_id}/market-research")
def post_market_research(
    plugin_id: int,
    body: ResearchIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    repo = _repo(db, plugin_id)
    llm_id = body.llm_config_id if body else None
    row = generate_market_research(db, repo, user_id=user.id, llm_config_id=llm_id)
    return envelope(_market_out(row))


@router.get("/plugins/{plugin_id}/market-research")
@router.get("/repos/{plugin_id}/market-research")
def get_market_research(
    plugin_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    _repo(db, plugin_id)
    row = db.scalar(select(MarketResearchReport).where(MarketResearchReport.repository_id == plugin_id))
    if row is None:
        raise HTTPException(status_code=404, detail="market research not generated")
    return envelope(_market_out(row))


@router.put("/market-research/{report_id}")
def put_market_research(
    report_id: UUID,
    body: MarketResearchUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    row = db.get(MarketResearchReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    if body.content_json is not None:
        row.content_json = body.content_json
        if not body.content_md:
            row.content_md = render_market_markdown(body.content_json)
            row.evidence = body.content_json.get("evidence") or row.evidence
    if body.content_md is not None:
        if not isinstance(body.content_md, str) or not body.content_md.strip():
            raise HTTPException(status_code=400, detail="content_md required")
        row.content_md = body.content_md
    if body.status:
        row.status = body.status
    db.commit()
    db.refresh(row)
    return envelope(_market_out(row))


@router.post("/plugins/{plugin_id}/commercial-report")
@router.post("/repos/{plugin_id}/commercial-report")
def post_commercial(
    plugin_id: int,
    body: ResearchIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    repo = _repo(db, plugin_id)
    llm_id = body.llm_config_id if body else None
    market = db.scalar(select(MarketResearchReport).where(MarketResearchReport.repository_id == plugin_id))
    if market is None:
        market = generate_market_research(db, repo, user_id=user.id, llm_config_id=llm_id)
    row = generate_commercial_report(db, repo, market)
    return envelope(_commercial_out(row))


@router.get("/plugins/{plugin_id}/commercial-report")
@router.get("/repos/{plugin_id}/commercial-report")
def get_commercial(
    plugin_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    _repo(db, plugin_id)
    row = db.scalar(select(CommercialReport).where(CommercialReport.repository_id == plugin_id))
    if row is None:
        raise HTTPException(status_code=404, detail="commercial report not generated")
    return envelope(_commercial_out(row))
