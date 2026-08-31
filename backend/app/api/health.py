from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.graph.store import get_graph_store
from app.models import Repository, Subscription, User

router = APIRouter()


@router.get("/health")
@router.get("/api/health")
@router.get("/api/v1/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    graph = get_graph_store().status()
    try:
        users = db.scalar(select(func.count()).select_from(User)) or 0
        repos = db.scalar(select(func.count()).select_from(Repository)) or 0
        subs = db.scalar(select(func.count()).select_from(Subscription)) or 0
    except Exception as exc:
        return {
            "status": "degraded",
            "version": settings.app_version,
            "message": f"db error: {exc}",
            "graph": graph,
        }
    return {
        "status": "ok",
        "version": settings.app_version,
        "name": settings.app_name,
        "users": users,
        "repositories": repos,
        "subscriptions": subs,
        "graph": graph,
    }
