from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import NotificationHistory, Subscription, User
from app.notification.briefs import load_channel_config, match_repos, render_brief, should_run
from app.notification.dispatcher import NotificationDispatcher, NotifyError
from app.schemas import SubscriptionIn, SubscriptionOut
from app.security import encrypt_secret

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


@router.post("")
def create_sub(body: SubscriptionIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = Subscription(
        user_id=user.id,
        name=body.name,
        conditions=body.conditions.model_dump(),
        frequency=body.frequency,
        channel=body.channel,
        channel_config_enc=encrypt_secret(json.dumps(body.channel_config.model_dump())),
        llm_config_id=body.llm_config_id,
        channel_config_id=body.channel_config_id,
        is_active=body.is_active,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return envelope(_out(sub).model_dump(mode="json"))


@router.get("")
def list_subs(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = list(db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all())
    return envelope({"items": [_out(s).model_dump(mode="json") for s in rows]})


@router.get("/{sub_id}")
def get_sub(sub_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = _owned(db, user, sub_id)
    return envelope(_out(sub).model_dump(mode="json"))


@router.put("/{sub_id}")
def update_sub(
    sub_id: UUID,
    body: SubscriptionIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    sub = _owned(db, user, sub_id)
    sub.name = body.name
    sub.conditions = body.conditions.model_dump()
    sub.frequency = body.frequency
    sub.channel = body.channel
    sub.llm_config_id = body.llm_config_id
    sub.channel_config_id = body.channel_config_id
    sub.is_active = body.is_active
    cfg = body.channel_config.model_dump()
    if cfg.get("webhook_url") or cfg.get("secret") or cfg.get("email"):
        merged = load_channel_config(sub, db)
        for k, v in cfg.items():
            if v:
                merged[k] = v
        sub.channel_config_enc = encrypt_secret(json.dumps(merged))
    db.commit()
    db.refresh(sub)
    return envelope(_out(sub).model_dump(mode="json"))


@router.delete("/{sub_id}")
def delete_sub(sub_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = _owned(db, user, sub_id)
    db.delete(sub)
    db.commit()
    return envelope({"deleted": True})


@router.post("/{sub_id}/send-test")
def send_test(sub_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = _owned(db, user, sub_id)
    return envelope(_dispatch(db, sub, test=True))


@router.get("/{sub_id}/history")
def history(sub_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    _owned(db, user, sub_id)
    rows = list(
        db.scalars(
            select(NotificationHistory)
            .where(NotificationHistory.subscription_id == sub_id)
            .order_by(NotificationHistory.sent_at.desc())
            .limit(50)
        ).all()
    )
    return envelope(
        {
            "items": [
                {
                    "id": r.id,
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                    "status": r.status,
                    "error_message": r.error_message,
                    "content": r.content,
                }
                for r in rows
            ]
        }
    )


@router.post("/{sub_id}/resend/{history_id}")
def resend(
    sub_id: UUID,
    history_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    sub = _owned(db, user, sub_id)
    row = db.get(NotificationHistory, history_id)
    if row is None or row.subscription_id != sub.id:
        raise HTTPException(status_code=404, detail="history not found")
    return envelope(_dispatch(db, sub, test=True, content=row.content))


def generate_due_briefs(db: Session) -> int:
    sent = 0
    subs = list(db.scalars(select(Subscription).where(Subscription.is_active.is_(True))).all())
    for sub in subs:
        try:
            due = should_run(sub)
        except ValueError:
            continue
        if due:
            _dispatch(db, sub, test=False)
            sent += 1
    return sent


def _dispatch(db: Session, sub: Subscription, test: bool, content: str | None = None) -> dict:
    repos = match_repos(db, sub.conditions or {})
    text = content or render_brief(sub, repos, "test" if test else "current period")
    history = NotificationHistory(subscription_id=sub.id, content=text, status="pending")
    db.add(history)
    db.flush()
    try:
        cfg = load_channel_config(sub, db)
        NotificationDispatcher().send(sub.channel, cfg, text, f"SkillRadar · {sub.name}")
        history.status = "success"
        if not test:
            sub.last_sent_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "success", "history_id": history.id}
    except (NotifyError, ValueError) as exc:
        history.status = "failed"
        history.error_message = str(exc)
        db.commit()
        return {"status": "failed", "error": str(exc), "history_id": history.id}


def _owned(db: Session, user: User, sub_id: UUID) -> Subscription:
    sub = db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub


def _out(sub: Subscription) -> SubscriptionOut:
    return SubscriptionOut(
        subscription_id=sub.id,
        user_id=sub.user_id,
        name=sub.name,
        conditions=sub.conditions or {},
        frequency=sub.frequency,
        channel=sub.channel,
        has_webhook=bool(sub.channel_config_enc or sub.channel_config_id),
        llm_config_id=sub.llm_config_id,
        channel_config_id=sub.channel_config_id,
        is_active=sub.is_active,
        last_sent_at=sub.last_sent_at,
        created_at=sub.created_at,
    )
