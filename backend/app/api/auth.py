from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def envelope(data: dict, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    try:
        user = User(email=str(body.email).lower(), password_hash=hash_password(body.password))
        db.add(user)
        db.commit()
        db.refresh(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_access_token(user.id, user.email)
    return envelope(TokenOut(access_token=token, user_id=user.id, email=user.email).model_dump(mode="json"))


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    try:
        ok = verify_password(body.password, user.password_hash)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid credentials") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_access_token(user.id, user.email)
    return envelope(TokenOut(access_token=token, user_id=user.id, email=user.email).model_dump(mode="json"))
