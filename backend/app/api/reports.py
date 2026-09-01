from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.analysis.deep_dive import analyze_deep_dive
from app.analysis.highlights import mine_highlights
from app.analysis.market import analyze_market
from app.analysis.motivation import analyze_motivation
from app.analysis.report import render_business_report, report_summary
from app.analysis.store import get_analysis, upsert_analysis
from app.db import get_db
from app.deps import current_user
from app.models import Report, RepoAnalysis, Repository, User
from app.search.index import index_report
from app.storage.objects import store_bytes

router = APIRouter(prefix="/api/v1", tags=["reports"])


class ReportGenerateIn(BaseModel):
    plugin_id: int | None = None
    repository_id: int | None = None
    options: dict | None = None


class ReportUpdateIn(BaseModel):
    title: str | None = None
    content_md: str | None = None
    status: str | None = None
    summary: str | None = None


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


def _repo_dict(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": repo.description,
        "stargazers_count": repo.stargazers_count,
        "star_delta": repo.star_delta or 0,
        "fingerprint_type": repo.fingerprint_type,
        "source": getattr(repo, "source", None) or "github",
        "identifier": getattr(repo, "identifier", None) or repo.full_name,
        "license": getattr(repo, "license", None),
    }


def _report_out(row: Report) -> dict:
    return {
        "id": str(row.id),
        "plugin_id": row.repository_id,
        "repository_id": row.repository_id,
        "title": row.title,
        "summary": row.summary,
        "content_md": row.content_md,
        "status": row.status,
        "version": row.version,
        "object_key": row.object_key,
        "tags": row.tags or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def generate_report_for(db: Session, repo: Repository, user: User | None) -> Report:
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
    structure = (analysis.structure if analysis else {}) or {
        "full_name": repo.full_name,
        "fingerprint_type": repo.fingerprint_type,
        "skills": [],
    }
    motivation = (analysis.motivation if analysis and analysis.motivation else None) or analyze_motivation(structure)
    deep = analyze_deep_dive(structure)
    highs = mine_highlights(structure, motivation)
    market = analyze_market(structure, _repo_dict(repo))
    upsert_analysis(db, repo.id, "deep_dive", deep)
    upsert_analysis(db, repo.id, "highlights", highs)
    upsert_analysis(db, repo.id, "market_research", market)
    upsert_analysis(db, repo.id, "motivation", motivation)
    md = render_business_report(_repo_dict(repo), structure, motivation, deep, highs, market)
    title = f"商业拆解 · {repo.full_name}"
    existing = db.scalar(select(Report).where(Report.repository_id == repo.id).order_by(desc(Report.version)))
    version = (existing.version + 1) if existing else 1
    row = Report(
        repository_id=repo.id,
        title=title,
        summary=report_summary(_repo_dict(repo), market),
        content_md=md,
        author_user_id=user.id if user else None,
        status="published",
        version=version,
        tags=[repo.fingerprint_type or "plugin", getattr(repo, "source", None) or "github"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    key = f"reports/{row.id}.md"
    store_bytes(key, md.encode("utf-8"), "text/markdown")
    row.object_key = key
    db.commit()
    index_report(str(row.id), title, md, extra={"plugin_id": repo.id, "full_name": repo.full_name})
    return row


@router.post("/reports/generate")
def generate_report(body: ReportGenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rid = body.plugin_id or body.repository_id
    if rid is None:
        raise HTTPException(status_code=400, detail="plugin_id required")
    repo = db.get(Repository, rid)
    if repo is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    row = generate_report_for(db, repo, user)
    return envelope(_report_out(row))


@router.get("/reports")
def list_reports(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    total = db.scalar(select(func.count()).select_from(Report)) or 0
    stmt = select(Report).order_by(desc(Report.updated_at))
    if q:
        needle = f"%{q}%"
        filt = or_(Report.title.ilike(needle), Report.summary.ilike(needle), Report.content_md.ilike(needle))
        total = db.scalar(select(func.count(Report.id)).where(filt)) or 0
        stmt = stmt.where(filt)
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all())
    return envelope({"items": [_report_out(r) for r in rows], "page": page, "page_size": page_size, "total": total})


@router.get("/reports/search")
def search_reports(
    q: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    from app.search.index import search_repositories

    packed = search_repositories(db, q or "report", limit=20)
    return envelope({"items": packed.get("reports") or [], "plugins": packed.get("items") or [], "backend": packed.get("backend")})


@router.get("/reports/{report_id}")
def get_report(report_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return envelope(_report_out(row))


@router.put("/reports/{report_id}")
def update_report(report_id: UUID, body: ReportUpdateIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    if body.title:
        row.title = body.title
    if body.content_md is not None:
        row.content_md = body.content_md
        store_bytes(f"reports/{row.id}.md", body.content_md.encode("utf-8"), "text/markdown")
    if body.status:
        row.status = body.status
    if body.summary is not None:
        row.summary = body.summary
    db.commit()
    db.refresh(row)
    return envelope(_report_out(row))
