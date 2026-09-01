"""Feishu / WeCom bind tickets and keep-alive long connections."""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.qrcode_svg import qr_svg
from app.models import ChannelConfig, utcnow
from app.security import decrypt_secret, encrypt_secret

TTL = timedelta(minutes=10)
TYPES = ("feishu", "wecom")
LABELS = {"feishu": "飞书", "wecom": "企业微信"}
DEFAULT_NAMES = {"feishu": "飞书客户端", "wecom": "企业微信客户端"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ChannelTicket:
    ticket: str
    user_id: UUID
    channel_type: str
    expires_at: datetime
    bind_url: str = ""
    qr_svg: str = ""
    connected: bool = False
    display_name: str | None = None
    avatar_url: str | None = None
    keep_alive: bool = True
    live_clients: int = 0
    confirmed_at: datetime | None = None


@dataclass
class UserLive:
    channels: dict[str, ChannelTicket] = field(default_factory=dict)
    waiters: list[asyncio.Event] = field(default_factory=list)


_lock = Lock()
_by_user: dict[str, UserLive] = {}
_by_ticket: dict[str, ChannelTicket] = {}


def _uid(user_id: UUID) -> str:
    return str(user_id)


def _notify(user_id: UUID) -> None:
    live = _by_user.get(_uid(user_id))
    if not live:
        return
    for ev in list(live.waiters):
        ev.set()


def _load_saved(db: Session, user_id: UUID, channel_type: str) -> dict:
    rows = list(
        db.scalars(
            select(ChannelConfig).where(
                ChannelConfig.user_id == user_id,
                ChannelConfig.channel_type == channel_type,
            )
        ).all()
    )
    for row in rows:
        try:
            cfg = json.loads(decrypt_secret(row.config_encrypted) or "{}")
        except (ValueError, json.JSONDecodeError):
            cfg = {}
        link = cfg.get("link") if isinstance(cfg.get("link"), dict) else {}
        webhook = bool(cfg.get("webhook_url"))
        connected = bool(link.get("connected") or webhook)
        if connected or link:
            return {
                "connected": connected,
                "display_name": link.get("display_name") or row.name,
                "avatar_url": link.get("avatar_url"),
                "keep_alive": link.get("keep_alive", True),
                "confirmed_at": link.get("confirmed_at"),
                "has_webhook": webhook,
            }
    return {}


def _persist_link(
    db: Session,
    user_id: UUID,
    channel_type: str,
    *,
    connected: bool,
    display_name: str | None,
    avatar_url: str | None,
    keep_alive: bool,
) -> None:
    rows = list(
        db.scalars(
            select(ChannelConfig).where(
                ChannelConfig.user_id == user_id,
                ChannelConfig.channel_type == channel_type,
            )
        ).all()
    )
    payload = {
        "link": {
            "connected": connected,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "keep_alive": keep_alive,
            "confirmed_at": utcnow().isoformat() if connected else None,
        }
    }
    if rows:
        row = rows[0]
        try:
            cfg = json.loads(decrypt_secret(row.config_encrypted) or "{}")
        except (ValueError, json.JSONDecodeError):
            cfg = {}
        cfg.update(payload)
        if not connected:
            cfg.get("link", {}).pop("confirmed_at", None)
        row.config_encrypted = encrypt_secret(json.dumps(cfg))
        if display_name:
            row.name = display_name
        db.commit()
        return
    if not connected:
        return
    row = ChannelConfig(
        user_id=user_id,
        name=display_name or DEFAULT_NAMES[channel_type],
        channel_type=channel_type,
        config_encrypted=encrypt_secret(json.dumps(payload)),
        is_default=True,
    )
    db.add(row)
    db.commit()


def _issue_ticket(user_id: UUID, channel_type: str, origin: str) -> ChannelTicket:
    ticket = secrets.token_urlsafe(18)
    bind_url = f"{origin.rstrip('/')}/api/v1/channels/bind/{ticket}"
    rec = ChannelTicket(
        ticket=ticket,
        user_id=user_id,
        channel_type=channel_type,
        expires_at=_now() + TTL,
        bind_url=bind_url,
        qr_svg=qr_svg(bind_url),
        keep_alive=True,
    )
    live = _by_user.setdefault(_uid(user_id), UserLive())
    old = live.channels.get(channel_type)
    if old:
        _by_ticket.pop(old.ticket, None)
        rec.live_clients = old.live_clients
        rec.keep_alive = old.keep_alive
    live.channels[channel_type] = rec
    _by_ticket[ticket] = rec
    return rec


def ensure_status(db: Session, user_id: UUID, origin: str) -> dict:
    with _lock:
        live = _by_user.setdefault(_uid(user_id), UserLive())
        channels = {}
        for ctype in TYPES:
            saved = _load_saved(db, user_id, ctype)
            rec = live.channels.get(ctype)
            if rec is None or (not rec.connected and rec.expires_at <= _now()):
                rec = _issue_ticket(user_id, ctype, origin)
            if saved.get("connected"):
                rec.connected = True
                rec.display_name = saved.get("display_name") or rec.display_name
                rec.avatar_url = saved.get("avatar_url") or rec.avatar_url
                rec.keep_alive = bool(saved.get("keep_alive", True))
                if saved.get("confirmed_at"):
                    try:
                        rec.confirmed_at = datetime.fromisoformat(str(saved["confirmed_at"]))
                    except ValueError:
                        rec.confirmed_at = rec.confirmed_at or _now()
            channels[ctype] = _public(rec)
        return {"keep_alive": True, "channels": channels}


def refresh_ticket(db: Session, user_id: UUID, channel_type: str, origin: str) -> dict:
    if channel_type not in TYPES:
        raise ValueError("unsupported channel")
    with _lock:
        rec = _issue_ticket(user_id, channel_type, origin)
        saved = _load_saved(db, user_id, channel_type)
        if saved.get("connected"):
            rec.connected = True
            rec.display_name = saved.get("display_name")
            rec.avatar_url = saved.get("avatar_url")
        _notify(user_id)
        return _public(rec)


def confirm_ticket(db: Session, ticket: str, display_name: str | None = None, avatar_url: str | None = None) -> ChannelTicket:
    with _lock:
        rec = _by_ticket.get(ticket)
        if rec is None or rec.expires_at <= _now():
            raise KeyError("ticket expired")
        rec.connected = True
        rec.display_name = display_name or DEFAULT_NAMES[rec.channel_type]
        rec.avatar_url = avatar_url
        rec.confirmed_at = _now()
        rec.keep_alive = True
        uid = rec.user_id
        ctype = rec.channel_type
        keep = rec.keep_alive
        name = rec.display_name
        avatar = rec.avatar_url
    _persist_link(db, uid, ctype, connected=True, display_name=name, avatar_url=avatar, keep_alive=keep)
    with _lock:
        _notify(uid)
    return rec


def disconnect(db: Session, user_id: UUID, channel_type: str, origin: str) -> dict:
    if channel_type not in TYPES:
        raise ValueError("unsupported channel")
    _persist_link(db, user_id, channel_type, connected=False, display_name=None, avatar_url=None, keep_alive=True)
    with _lock:
        rec = _issue_ticket(user_id, channel_type, origin)
        rec.connected = False
        rec.display_name = None
        rec.avatar_url = None
        rec.confirmed_at = None
        _notify(user_id)
        return _public(rec)


def attach(user_id: UUID) -> None:
    with _lock:
        live = _by_user.setdefault(_uid(user_id), UserLive())
        for rec in live.channels.values():
            rec.live_clients += 1
        _notify(user_id)


def detach(user_id: UUID) -> None:
    with _lock:
        live = _by_user.get(_uid(user_id))
        if not live:
            return
        for rec in live.channels.values():
            rec.live_clients = max(0, rec.live_clients - 1)
        _notify(user_id)


def subscribe(user_id: UUID) -> asyncio.Event:
    ev = asyncio.Event()
    with _lock:
        live = _by_user.setdefault(_uid(user_id), UserLive())
        live.waiters.append(ev)
    return ev


def unsubscribe(user_id: UUID, ev: asyncio.Event) -> None:
    with _lock:
        live = _by_user.get(_uid(user_id))
        if not live:
            return
        live.waiters = [x for x in live.waiters if x is not ev]


def snapshot(user_id: UUID) -> dict:
    with _lock:
        live = _by_user.get(_uid(user_id))
        if not live:
            return {"keep_alive": True, "channels": {}}
        return {"keep_alive": True, "channels": {k: _public(v) for k, v in live.channels.items()}}


def get_ticket(ticket: str) -> ChannelTicket | None:
    with _lock:
        rec = _by_ticket.get(ticket)
        if rec is None or rec.expires_at <= _now():
            return None
        return rec


def reset_live_state() -> None:
    with _lock:
        _by_user.clear()
        _by_ticket.clear()


def _public(rec: ChannelTicket) -> dict:
    connected = rec.connected
    return {
        "type": rec.channel_type,
        "label": LABELS[rec.channel_type],
        "connected": connected,
        "live": rec.live_clients > 0 and rec.keep_alive,
        "keep_alive": rec.keep_alive,
        "display_name": rec.display_name if connected else None,
        "avatar_url": rec.avatar_url if connected else None,
        "ticket": None if connected else rec.ticket,
        "qr_svg": "" if connected else rec.qr_svg,
        "bind_url": None if connected else rec.bind_url,
        "expires_at": rec.expires_at.isoformat(),
        "confirmed_at": rec.confirmed_at.isoformat() if rec.confirmed_at else None,
    }
