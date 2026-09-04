from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.channels import live as chlive
from app.db import SessionLocal, get_db
from app.deps import live_user, resolve_user
from app.models import User

router = APIRouter(prefix="/api/v1/channels", tags=["channels-live"])


class BindIn(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


def public_origin(request: Request) -> str:
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin.startswith("http"):
        return origin
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}"


@router.get("/live/status")
def live_status(request: Request, db: Session = Depends(get_db), user: User = Depends(live_user)) -> dict:
    return envelope(chlive.ensure_status(db, user.id, public_origin(request)))


@router.post("/live/{channel_type}/refresh")
def refresh_qr(
    channel_type: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(live_user),
) -> dict:
    try:
        chlive.refresh_ticket(db, user.id, channel_type, public_origin(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return envelope(chlive.ensure_status(db, user.id, public_origin(request)))


@router.post("/live/{channel_type}/confirm")
def confirm_from_app(
    channel_type: str,
    request: Request,
    body: BindIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(live_user),
) -> dict:
    snap = chlive.ensure_status(db, user.id, public_origin(request))
    ch = snap["channels"].get(channel_type)
    if not ch or not ch.get("ticket"):
        if ch and ch.get("connected"):
            return envelope(snap)
        raise HTTPException(status_code=400, detail="no pending ticket")
    name = (body.display_name if body else None) or chlive.DEFAULT_NAMES[channel_type]
    try:
        chlive.confirm_ticket(db, ch["ticket"], display_name=name)
    except KeyError as exc:
        raise HTTPException(status_code=410, detail="ticket expired") from exc
    return envelope(chlive.ensure_status(db, user.id, public_origin(request)))


@router.post("/live/{channel_type}/disconnect")
def disconnect_channel(
    channel_type: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(live_user),
) -> dict:
    try:
        chlive.disconnect(db, user.id, channel_type, public_origin(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return envelope(chlive.ensure_status(db, user.id, public_origin(request)))


def _bind_html(ticket: str, rec: chlive.ChannelTicket | None) -> str:
    label = chlive.LABELS.get(rec.channel_type, "渠道") if rec else "渠道"
    if rec is None:
        body = "<p>二维码已过期，请在 SkillRadar 设置页刷新后重新扫描。</p>"
    elif rec.connected:
        body = f"<p>{label}已连接。可以关闭此页。</p>"
    else:
        body = f"""
        <p>确认为 SkillRadar 绑定{label}客户端，并保持长连接。</p>
        <form method="post">
          <input type="hidden" name="ok" value="1"/>
          <button type="submit">确认绑定</button>
        </form>
        """
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SkillRadar {label}</title>
<style>
body{{font-family:Inter,sans-serif;background:#0F1419;color:#E2E8F0;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#1A2029;border:1px solid #2D3748;border-radius:12px;padding:24px;max-width:360px}}
button{{background:#4F8CFF;color:#fff;border:0;border-radius:8px;padding:10px 16px;width:100%}}
</style></head>
<body><div class="card"><h1>SkillRadar</h1>{body}</div></body></html>"""


@router.get("/bind/{ticket}", response_class=HTMLResponse)
def bind_page(ticket: str) -> HTMLResponse:
    rec = chlive.get_ticket(ticket)
    return HTMLResponse(_bind_html(ticket, rec), status_code=200 if rec else 410)


@router.post("/bind/{ticket}")
async def bind_confirm(ticket: str, request: Request, db: Session = Depends(get_db)):
    rec = chlive.get_ticket(ticket)
    if rec is None:
        return HTMLResponse(_bind_html(ticket, None), status_code=410)
    form = {}
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            form = await request.json()
        except Exception:
            form = {}
    try:
        chlive.confirm_ticket(
            db,
            ticket,
            display_name=(form or {}).get("display_name") if isinstance(form, dict) else None,
            avatar_url=(form or {}).get("avatar_url") if isinstance(form, dict) else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=410, detail="ticket expired") from exc
    if "application/json" in ctype:
        return envelope({"ok": True, "channel_type": rec.channel_type})
    rec2 = chlive.get_ticket(ticket)
    return HTMLResponse(_bind_html(ticket, rec2))


async def _sse_gen(user_id: UUID, origin: str, once: bool = False):
    db = SessionLocal()
    chlive.attach(user_id)
    ev = chlive.subscribe(user_id)
    try:
        chlive.ensure_status(db, user_id, origin)
        while True:
            payload = json.dumps(chlive.snapshot(user_id), ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if once:
                break
            ev.clear()
            try:
                await asyncio.wait_for(ev.wait(), timeout=15)
            except TimeoutError:
                yield ": ping\n\n"
    finally:
        chlive.unsubscribe(user_id, ev)
        chlive.detach(user_id)
        db.close()


@router.get("/live/stream")
async def live_stream(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(live_user),
    once: bool = False,
):
    origin = public_origin(request)
    chlive.ensure_status(db, user.id, origin)
    return StreamingResponse(
        _sse_gen(user.id, origin, once=once),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.websocket("/live")
async def live_ws(ws: WebSocket, token: str = "") -> None:
    await ws.accept()
    db = SessionLocal()
    try:
        user = resolve_user(token, db)
    except HTTPException:
        await ws.close(code=4401)
        db.close()
        return
    origin = str(ws.url.scheme).replace("ws", "http") + "://" + ws.headers.get("host", "localhost")
    chlive.ensure_status(db, user.id, origin)
    chlive.attach(user.id)
    ev = chlive.subscribe(user.id)
    try:
        await ws.send_json(chlive.snapshot(user.id))
        while True:
            recv = asyncio.create_task(ws.receive_text())
            wait = asyncio.create_task(ev.wait())
            done, pending = await asyncio.wait({recv, wait}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, WebSocketDisconnect, Exception):
                    pass
            if not done:
                await ws.send_json({"type": "ping", **chlive.snapshot(user.id)})
                continue
            if recv in done:
                try:
                    recv.result()
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
            if wait in done:
                ev.clear()
                await ws.send_json(chlive.snapshot(user.id))
    except WebSocketDisconnect:
        pass
    finally:
        chlive.unsubscribe(user.id, ev)
        chlive.detach(user.id)
        db.close()
