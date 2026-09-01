from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.deps import current_user
from app.graph.store import get_graph_store
from app.models import Repository, ScanKeyword, ScanTask, User, utcnow
from app.scanner.keywords import due_keywords, keyword_is_due
from app.scanner.pipeline import sync_scan_to_graph
from app.scanner.service import ScannerError, ScannerService, mark_task
from app.schemas import KeywordIn, ScanIn

router = APIRouter(prefix="/api/v1", tags=["scan"])


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


@router.post("/scan/github")
@router.post("/scan")
def scan_github(
    body: ScanIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    task = ScanTask(user_id=user.id, kind=body.type, query=body.query, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(_run_scan, task.id, body.query, body.type, body.limit, body.watch, None, body.source)
    return envelope({"task_id": str(task.id)})


@router.get("/scan/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    rows = list(
        db.scalars(select(ScanTask).where(ScanTask.user_id == user.id).order_by(desc(ScanTask.created_at)).limit(20)).all()
    )
    return envelope({"items": [_task_json(t) for t in rows]})


@router.get("/scan/tasks/{task_id}")
def scan_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    task = db.get(ScanTask, task_id)
    if task is None or (task.user_id and task.user_id != user.id):
        raise HTTPException(status_code=404, detail="task not found")
    return envelope(_task_json(task))


@router.get("/scan/keywords")
def list_keywords(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = list(db.scalars(select(ScanKeyword).order_by(ScanKeyword.query)).all())
    return envelope({"items": [_kw_json(k) for k in rows]})


@router.post("/scan/keywords")
def create_keyword(
    body: KeywordIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    q = body.query.strip()
    existing = db.scalar(select(ScanKeyword).where(ScanKeyword.query == q))
    if existing:
        raise HTTPException(status_code=409, detail="keyword already exists")
    kw = ScanKeyword(
        query=q,
        search_type=body.search_type,
        enabled=body.enabled,
        interval_hours=body.interval_hours,
        limit=body.limit,
        created_by=user.id,
        last_status="idle",
    )
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return envelope(_kw_json(kw))


@router.put("/scan/keywords/{kw_id}")
def update_keyword(
    kw_id: UUID,
    body: KeywordIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    kw = db.get(ScanKeyword, kw_id)
    if kw is None:
        raise HTTPException(status_code=404, detail="keyword not found")
    q = body.query.strip()
    clash = db.scalar(select(ScanKeyword).where(ScanKeyword.query == q, ScanKeyword.id != kw.id))
    if clash:
        raise HTTPException(status_code=409, detail="keyword already exists")
    kw.query = q
    kw.search_type = body.search_type
    kw.enabled = body.enabled
    kw.interval_hours = body.interval_hours
    kw.limit = body.limit
    db.commit()
    db.refresh(kw)
    return envelope(_kw_json(kw))


@router.delete("/scan/keywords/{kw_id}")
def delete_keyword(kw_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    kw = db.get(ScanKeyword, kw_id)
    if kw is None:
        raise HTTPException(status_code=404, detail="keyword not found")
    db.delete(kw)
    db.commit()
    return envelope({"deleted": True})


@router.post("/scan/keywords/{kw_id}/run")
def run_keyword(
    kw_id: UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    kw = db.get(ScanKeyword, kw_id)
    if kw is None:
        raise HTTPException(status_code=404, detail="keyword not found")
    task = ScanTask(user_id=user.id, kind="watch", query=kw.query, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(_run_scan, task.id, kw.query, kw.search_type, kw.limit, True, str(kw.id))
    return envelope({"task_id": str(task.id), "keyword_id": str(kw.id)})


@router.post("/scan/keywords/run-due")
def run_due(background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    due = due_keywords(db)
    task_ids = []
    for kw in due:
        task = ScanTask(user_id=user.id, kind="cron", query=kw.query, status="queued")
        db.add(task)
        db.commit()
        db.refresh(task)
        background.add_task(_run_scan, task.id, kw.query, kw.search_type, kw.limit, True, str(kw.id))
        task_ids.append(str(task.id))
    return envelope({"due": len(due), "task_ids": task_ids})


@router.get("/radar")
def radar_snapshot(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    store = get_graph_store()
    repos = list(db.scalars(select(Repository).order_by(desc(Repository.last_scanned_at)).limit(80)).all())
    keywords = list(db.scalars(select(ScanKeyword).order_by(ScanKeyword.query)).all())
    tasks = list(db.scalars(select(ScanTask).order_by(desc(ScanTask.created_at)).limit(12)).all())
    total = db.scalar(select(func.count()).select_from(Repository)) or 0
    skills = db.scalar(select(func.count()).select_from(Repository).where(Repository.is_ai_skill.is_(True))) or 0
    last = repos[0].last_scanned_at.isoformat() if repos and repos[0].last_scanned_at else None
    return envelope(
        {
            "stats": {
                "repositories": total,
                "ai_skills": skills,
                "keywords_active": sum(1 for k in keywords if k.enabled),
                "last_scan": last,
                "graph": store.status(),
            },
            "keywords": [_kw_json(k) for k in keywords],
            "tasks": [_task_json(t) for t in tasks],
            "items": [_radar_repo(r) for r in repos],
            "graph": store.query_radar(),
        }
    )


def _run_scan(
    task_id: UUID,
    query: str,
    search_type: str,
    limit: int,
    watch: bool = False,
    keyword_id: str | None = None,
    source: str = "github",
) -> None:
    db = SessionLocal()
    try:
        task = db.get(ScanTask, task_id)
        if task is None:
            return
        task.status = "running"
        db.commit()
        if keyword_id:
            kw = db.get(ScanKeyword, UUID(keyword_id))
            if kw is not None:
                kw.last_status = "running"
                db.add(kw)
                db.commit()
        with httpx.Client(timeout=30.0) as client:
            if source and source != "github":
                from app.scanner.adapters import scan_source

                repos = scan_source(db, source, query, limit, client)
            else:
                svc = ScannerService(db, client=client)
                repos = svc.scan_keyword(query, limit=limit, search_type=search_type)
        graph_status = sync_scan_to_graph(repos, query, search_type)
        from app.search.index import index_repositories

        index_repositories(repos)
        db.commit()
        if keyword_id:
            kw = db.get(ScanKeyword, UUID(keyword_id))
            if kw is not None:
                from app.models import utcnow

                kw.last_run_at = utcnow()
                kw.last_status = "success"
                kw.last_count = len(repos)
                kw.last_error = None
                db.add(kw)
                db.commit()
        elif watch:
            _ensure_watch_keyword(db, query, search_type, limit)
        mark_task(
            db,
            task,
            "success",
            result={
                "count": len(repos),
                "repos": [{"id": r.id, "full_name": r.full_name, "fingerprint_type": r.fingerprint_type} for r in repos],
                "graph": graph_status,
            },
        )
    except ScannerError as exc:
        _fail_task(db, task_id, keyword_id, str(exc))
    except Exception as exc:
        _fail_task(db, task_id, keyword_id, f"unexpected: {exc}")
    finally:
        db.close()


def _fail_task(db: Session, task_id: UUID, keyword_id: str | None, error: str) -> None:
    task = db.get(ScanTask, task_id)
    if task is not None:
        mark_task(db, task, "failed", error=error)
    if keyword_id:
        kw = db.get(ScanKeyword, UUID(keyword_id))
        if kw is not None:
            from app.models import utcnow

            kw.last_run_at = utcnow()
            kw.last_status = "failed"
            kw.last_error = error[:500]
            db.add(kw)
            db.commit()


def _ensure_watch_keyword(db: Session, query: str, search_type: str, limit: int) -> None:
    existing = db.scalar(select(ScanKeyword).where(ScanKeyword.query == query))
    if existing:
        return
    db.add(
        ScanKeyword(
            query=query,
            search_type=search_type,
            enabled=True,
            interval_hours=6,
            limit=limit,
            last_status="idle",
        )
    )
    db.commit()


def _task_json(task: ScanTask) -> dict:
    return {
        "task_id": str(task.id),
        "status": task.status,
        "kind": task.kind,
        "query": task.query,
        "result": task.result,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _kw_json(kw: ScanKeyword) -> dict:
    due = keyword_is_due(kw)
    next_due_at = None
    if kw.enabled:
        if kw.last_run_at is None:
            next_due_at = utcnow().isoformat()
        else:
            last = kw.last_run_at
            hours = kw.interval_hours if kw.interval_hours > 0 else 6
            next_due_at = (last + timedelta(hours=hours)).isoformat()
    return {
        "id": str(kw.id),
        "query": kw.query,
        "search_type": kw.search_type,
        "enabled": kw.enabled,
        "interval_hours": kw.interval_hours,
        "limit": kw.limit,
        "last_run_at": kw.last_run_at.isoformat() if kw.last_run_at else None,
        "last_status": kw.last_status,
        "last_count": kw.last_count,
        "last_error": kw.last_error,
        "is_due": due,
        "next_due_at": next_due_at,
    }


def _radar_repo(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": repo.description,
        "stargazers_count": repo.stargazers_count,
        "star_delta": repo.star_delta or 0,
        "fingerprint_type": repo.fingerprint_type,
        "is_ai_skill": repo.is_ai_skill,
        "source_keywords": repo.source_keywords or [],
        "last_scanned_at": repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
        "source": getattr(repo, "source", None) or "github",
    }
