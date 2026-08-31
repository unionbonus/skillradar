from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.llm import LLMError, ping
from app.models import ChannelConfig, LLMConfig, User
from app.notification.dispatcher import NotificationDispatcher, NotifyError
from app.security import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


class LLMConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(default="openai", max_length=50)
    api_key: str | None = None
    base_url: str | None = Field(default=None, max_length=512)
    model_name: str = Field(default="gpt-4o", max_length=128)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=16, le=128000)
    is_default: bool = False


class ChannelConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel_type: str = Field(default="feishu", max_length=20)
    webhook_url: str | None = None
    secret: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    is_default: bool = False


def _mask_key(blob: str) -> str:
    if not blob:
        return ""
    try:
        plain = decrypt_secret(blob)
    except ValueError:
        return "••••"
    if len(plain) <= 4:
        return "••••"
    return "••••" + plain[-4:]


def _llm_out(row: LLMConfig) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "provider": row.provider,
        "api_key_masked": _mask_key(row.api_key_encrypted),
        "has_api_key": bool(row.api_key_encrypted),
        "base_url": row.base_url,
        "model_name": row.model_name,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "is_default": row.is_default,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _channel_plain(row: ChannelConfig) -> dict:
    raw = decrypt_secret(row.config_encrypted) if row.config_encrypted else "{}"
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def _channel_out(row: ChannelConfig) -> dict:
    cfg = _channel_plain(row)
    webhook = (cfg.get("webhook_url") or "").strip()
    masked = ""
    if webhook:
        masked = webhook[:24] + "…" if len(webhook) > 24 else webhook
    return {
        "id": str(row.id),
        "name": row.name,
        "channel_type": row.channel_type,
        "webhook_url_masked": masked,
        "has_secret": bool(cfg.get("secret") or cfg.get("smtp_password")),
        "smtp_host": cfg.get("smtp_host"),
        "smtp_port": cfg.get("smtp_port"),
        "smtp_user": cfg.get("smtp_user"),
        "from_email": cfg.get("from_email"),
        "to_email": cfg.get("to_email"),
        "is_default": row.is_default,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _owned_llm(db: Session, user: User, config_id: UUID) -> LLMConfig:
    row = db.get(LLMConfig, config_id)
    if row is None or (row.user_id is not None and row.user_id != user.id):
        raise HTTPException(status_code=404, detail="llm config not found")
    return row


def _owned_channel(db: Session, user: User, config_id: UUID) -> ChannelConfig:
    row = db.get(ChannelConfig, config_id)
    if row is None or (row.user_id is not None and row.user_id != user.id):
        raise HTTPException(status_code=404, detail="channel config not found")
    return row


def _unset_default_llm(db: Session, user_id: UUID) -> None:
    rows = list(db.scalars(select(LLMConfig).where(LLMConfig.user_id == user_id, LLMConfig.is_default.is_(True))).all())
    for r in rows:
        r.is_default = False


def _unset_default_channel(db: Session, user_id: UUID, channel_type: str) -> None:
    rows = list(
        db.scalars(
            select(ChannelConfig).where(
                ChannelConfig.user_id == user_id,
                ChannelConfig.channel_type == channel_type,
                ChannelConfig.is_default.is_(True),
            )
        ).all()
    )
    for r in rows:
        r.is_default = False


@router.get("/llm")
def list_llm(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = list(db.scalars(select(LLMConfig).where(LLMConfig.user_id == user.id)).all())
    return envelope({"items": [_llm_out(r) for r in rows]})


@router.post("/llm")
def create_llm(body: LLMConfigIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if body.is_default:
        _unset_default_llm(db, user.id)
    row = LLMConfig(
        user_id=user.id,
        name=body.name,
        provider=body.provider.lower(),
        api_key_encrypted=encrypt_secret(body.api_key) if body.api_key else "",
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


@router.put("/llm/{config_id}")
def update_llm(
    config_id: UUID,
    body: LLMConfigIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    row = _owned_llm(db, user, config_id)
    if body.is_default:
        _unset_default_llm(db, user.id)
    row.name = body.name
    row.provider = body.provider.lower()
    if body.api_key:
        row.api_key_encrypted = encrypt_secret(body.api_key)
    row.base_url = body.base_url
    row.model_name = body.model_name
    row.temperature = body.temperature
    row.max_tokens = body.max_tokens
    row.is_default = body.is_default
    db.commit()
    db.refresh(row)
    return envelope(_llm_out(row))


@router.delete("/llm/{config_id}")
def delete_llm(config_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned_llm(db, user, config_id)
    db.delete(row)
    db.commit()
    return envelope({"deleted": True})


@router.post("/llm/{config_id}/test")
def test_llm(config_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned_llm(db, user, config_id)
    try:
        text = ping(row)
        return envelope({"ok": True, "reply": text[:200]})
    except LLMError as exc:
        return envelope({"ok": False, "error": str(exc)})


@router.get("/channels")
def list_channels(
    channel_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    stmt = select(ChannelConfig).where(ChannelConfig.user_id == user.id)
    if channel_type:
        stmt = stmt.where(ChannelConfig.channel_type == channel_type)
    rows = list(db.scalars(stmt).all())
    return envelope({"items": [_channel_out(r) for r in rows]})


@router.post("/channels")
def create_channel(body: ChannelConfigIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    ctype = body.channel_type.lower()
    if ctype not in {"feishu", "wecom", "email"}:
        raise HTTPException(status_code=400, detail="channel_type must be feishu, wecom or email")
    if body.is_default:
        _unset_default_channel(db, user.id, ctype)
    cfg = body.model_dump(exclude={"name", "channel_type", "is_default"})
    row = ChannelConfig(
        user_id=user.id,
        name=body.name,
        channel_type=ctype,
        config_encrypted=encrypt_secret(json.dumps(cfg)),
        is_default=body.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return envelope(_channel_out(row))


@router.put("/channels/{config_id}")
def update_channel(
    config_id: UUID,
    body: ChannelConfigIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    row = _owned_channel(db, user, config_id)
    ctype = body.channel_type.lower()
    if body.is_default:
        _unset_default_channel(db, user.id, ctype)
    merged = _channel_plain(row)
    incoming = body.model_dump(exclude={"name", "channel_type", "is_default"})
    for k, v in incoming.items():
        if v not in (None, ""):
            merged[k] = v
    row.name = body.name
    row.channel_type = ctype
    row.config_encrypted = encrypt_secret(json.dumps(merged))
    row.is_default = body.is_default
    db.commit()
    db.refresh(row)
    return envelope(_channel_out(row))


@router.delete("/channels/{config_id}")
def delete_channel(config_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned_channel(db, user, config_id)
    db.delete(row)
    db.commit()
    return envelope({"deleted": True})


@router.post("/channels/{config_id}/test")
def test_channel(config_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned_channel(db, user, config_id)
    cfg = _channel_plain(row)
    try:
        NotificationDispatcher().send(row.channel_type, cfg, "SkillRadar 渠道测试消息。", f"SkillRadar · {row.name}")
        return envelope({"ok": True})
    except (NotifyError, ValueError) as exc:
        return envelope({"ok": False, "error": str(exc)})
