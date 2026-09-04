from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def extract_access_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = None,
    x_token: str | None = None,
    query_token: str | None = None,
) -> str:
    if creds is not None and creds.scheme.lower() == "bearer" and creds.credentials:
        return creds.credentials.strip()
    header_alt = (x_token or request.headers.get("x-skillradar-token") or "").strip()
    if header_alt:
        return header_alt
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        raw = auth.split(" ", 1)[1].strip()
        if raw:
            return raw
    cookie = (request.cookies.get("sr_token") or "").strip()
    if cookie:
        return cookie
    if query_token and query_token.strip():
        return query_token.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")


def resolve_user(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
        user_id = UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    x_skillradar_token: str | None = Header(default=None, alias="X-SkillRadar-Token"),
) -> User:
    return resolve_user(extract_access_token(request, creds, x_skillradar_token), db)


def live_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    token: str | None = Query(default=None),
    x_skillradar_token: str | None = Header(default=None, alias="X-SkillRadar-Token"),
) -> User:
    return resolve_user(extract_access_token(request, creds, x_skillradar_token, token), db)
