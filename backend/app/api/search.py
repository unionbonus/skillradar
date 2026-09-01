from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User
from app.search.index import search_repositories

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=256),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    data = search_repositories(db, q, limit=limit)
    return {"code": 0, "data": data, "message": "success"}
