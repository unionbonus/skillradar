from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.models import ChannelConfig, LlmConfig, User
from app.notification.dispatcher import NotificationDispatcher, NotifyError
from app.security import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


class LlmIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = "openai"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4096
    is_default: bool = False


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel_type: str = Field(pattern="^(feishu|wecom|email)$")
    webhook_url: str | None = None
    secret: str | None = None
    email: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    is_default: bool = False


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


def _llm_out(row: LlmConfig) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "provider": row.provider,
        "base_url": row.base_url,
        "model_name": row.model_name,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "is_default": row.is_default,
        "has_api_key": bool(row.api_key_encrypted),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _channel_out(row: ChannelConfig) -> dict:
    cfg: dict = {}
    try:
        raw = decrypt_secret(row.config_encrypted)
        cfg = json.loads(raw) if raw else {}
    except (ValueError, json.JSONDecodeError):
        cfg = {}
    public = {k: v for k, v in cfg.items() if k not in {"secret", "smtp_password", "api_key"} and v}
    if cfg.get("webhook_url"):
        public["has_webhook"] = True
        public["webhook_hint"] = str(cfg["webhook_url"])[:32] + "…"
    if cfg.get("email"):
        public["email"] = cfg["email"]
    return {
        "id": str(row.id),
        "name": row.name,
        "channel_type": row.channel_type,
        "is_default": row.is_default,
        "config": public,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/llm")
def list_llm(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = list(db.scalars(select(LlmConfig).where(LlmConfig.user_id == user.id)).all())
    return envelope({"items": [_llm_out(r) for r in rows]})


@router.post("/llm")
def create_llm(body: LlmIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if body.is_default:
        for row in db.scalars(select(LlmConfig).where(LlmConfig.user_id == user.id)).all():
            row.is_default = False
    row = LlmConfig(
        user_id=user.id,
        name=body.name,
        provider=body.provider,
        api_key_encrypted=encrypt_secret(body.api_key or "") if body.api_key else "",
        base_url=body.base_url,
        model_name=body.model_name,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        is_default=body.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return envelope(_llm_out(row))


@router.put("/llm/{cfg_id}")
def update_llm(cfg_id: UUID, body: LlmIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(LlmConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="llm config not found")
    if body.is_default:
        for other in db.scalars(select(LlmConfig).where(LlmConfig.user_id == user.id)).all():
            other.is_default = False
    row.name = body.name
    row.provider = body.provider
    row.base_url = body.base_url
    row.model_name = body.model_name
    row.temperature = body.temperature
    row.max_tokens = body.max_tokens
    row.is_default = body.is_default
    if body.api_key:
        row.api_key_encrypted = encrypt_secret(body.api_key)
    db.commit()
    db.refresh(row)
    return envelope(_llm_out(row))


@router.delete("/llm/{cfg_id}")
def delete_llm(cfg_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(LlmConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="llm config not found")
    db.delete(row)
    db.commit()
    return envelope({"ok": True})


@router.post("/llm/{cfg_id}/test")
def test_llm(cfg_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(LlmConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="llm config not found")
    key = decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else get_settings().llm_api_key
    if not key:
        return envelope({"ok": False, "message": "missing api key"}, message="missing api key")
    from app.analysis.motivation import AnalysisError, llm_complete

    try:
        llm_complete('{"ping": true}', api_key=key, base_url=row.base_url, model=row.model_name)
        return envelope({"ok": True})
    except AnalysisError as exc:
        return envelope({"ok": False, "message": str(exc)})


@router.get("/channels")
def list_channels(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = list(db.scalars(select(ChannelConfig).where(ChannelConfig.user_id == user.id)).all())
    return envelope({"items": [_channel_out(r) for r in rows]})


def _channel_payload(body: ChannelIn) -> dict:
    return {
        "webhook_url": body.webhook_url,
        "secret": body.secret,
        "email": body.email,
        "smtp_host": body.smtp_host,
        "smtp_port": body.smtp_port,
        "smtp_user": body.smtp_user,
        "smtp_password": body.smtp_password,
        "smtp_from": body.smtp_from,
    }


@router.post("/channels")
def create_channel(body: ChannelIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if body.is_default:
        for row in db.scalars(select(ChannelConfig).where(ChannelConfig.user_id == user.id, ChannelConfig.channel_type == body.channel_type)).all():
            row.is_default = False
    row = ChannelConfig(
        user_id=user.id,
        name=body.name,
        channel_type=body.channel_type,
        config_encrypted=encrypt_secret(json.dumps(_channel_payload(body))),
        is_default=body.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return envelope(_channel_out(row))


@router.put("/channels/{cfg_id}")
def update_channel(cfg_id: UUID, body: ChannelIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(ChannelConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel config not found")
    row.name = body.name
    row.channel_type = body.channel_type
    row.is_default = body.is_default
    row.config_encrypted = encrypt_secret(json.dumps(_channel_payload(body)))
    db.commit()
    db.refresh(row)
    return envelope(_channel_out(row))


@router.delete("/channels/{cfg_id}")
def delete_channel(cfg_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(ChannelConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel config not found")
    db.delete(row)
    db.commit()
    return envelope({"ok": True})


@router.post("/channels/{cfg_id}/test")
def test_channel(cfg_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(ChannelConfig, cfg_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel config not found")
    try:
        cfg = json.loads(decrypt_secret(row.config_encrypted) or "{}")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid channel secret") from exc
    try:
        NotificationDispatcher().send(row.channel_type, cfg, "SkillRadar 渠道测试", "SkillRadar 测试")
        return envelope({"ok": True, "status": "success"})
    except NotifyError as exc:
        return envelope({"ok": False, "status": "failed", "error": str(exc)})
