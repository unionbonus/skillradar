from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.decomposer.engine import DecomposeError, Decomposer
from app.models import Repository, Subscription
from app.notification.briefs import load_channel_config, match_repos, render_brief, should_run
from app.notification.dispatcher import NotificationDispatcher, NotifyError
from app.scanner.service import ScannerError, ScannerService, TokenRotator, parse_gh_time
from app.security import create_access_token, decode_token, encrypt_secret


def test_token_rotator_and_parse_time():
    rot = TokenRotator(["a", "b"])
    assert "Bearer a" in rot.header()["Authorization"]
    assert "Bearer b" in rot.header()["Authorization"]
    assert parse_gh_time("2024-01-02T03:04:05Z") is not None
    assert parse_gh_time("bad") is None
    assert TokenRotator([]).header()["User-Agent"].startswith("SkillRadar")


def test_scanner_upsert_with_mock_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": 99,
                        "full_name": "acme/mcp-demo",
                        "html_url": "https://github.com/acme/mcp-demo",
                        "description": "demo",
                        "stargazers_count": 12,
                        "forks_count": 1,
                        "language": "Python",
                        "topics": ["mcp"],
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-02-01T00:00:00Z",
                    }
                ]
            },
        )

    db: Session = SessionLocal()
    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        svc = ScannerService(db, client=client)
        repos = svc.scan_keyword("mcp", limit=5, search_type="keyword")
        assert repos[0].full_name == "acme/mcp-demo"
        again = svc.scan_keyword("mcp", limit=5, search_type="topic")
        assert again[0].id == repos[0].id
        ftype = svc.detect_and_mark(repos[0], ["mcp.json", "server.py"])
        assert ftype == "mcp_server"
        client.close()
    finally:
        db.close()


def test_scanner_errors():
    db: Session = SessionLocal()
    try:
        svc = ScannerService(db, client=None)
        try:
            svc.scan_keyword("x")
            raise AssertionError("expected ScannerError")
        except ScannerError:
            pass
        try:
            svc._build_query("  ", "keyword")
            raise AssertionError("expected")
        except ScannerError:
            pass
    finally:
        db.close()


def test_decompose_rejects_bad_host():
    db: Session = SessionLocal()
    try:
        eng = Decomposer(db)
        try:
            eng.decompose("https://evil.example/repo.git")
            raise AssertionError("expected")
        except DecomposeError as exc:
            assert "host" in str(exc)
    finally:
        db.close()


def test_briefs_and_dispatcher_mock():
    db: Session = SessionLocal()
    try:
        repo = Repository(full_name="acme/skill", html_url="https://github.com/acme/skill", description="agent memory", stargazers_count=9)
        db.add(repo)
        db.commit()
        user_id = uuid4()
        from app.models import User
        from app.security import hash_password

        user = User(id=user_id, email="n@example.com", password_hash=hash_password("password1"))
        db.add(user)
        db.commit()
        sub = Subscription(
            user_id=user_id,
            name="watch",
            conditions={"keywords": ["skill"]},
            frequency="daily",
            channel="feishu",
            channel_config_enc=encrypt_secret('{"webhook_url":"https://open.feishu.cn/open-apis/bot/v2/hook/x"}'),
            is_active=True,
        )
        db.add(sub)
        db.commit()
        found = match_repos(db, sub.conditions)
        assert found
        md = render_brief(sub, found, "this week")
        assert "SkillRadar" in md
        cfg = load_channel_config(sub)
        assert cfg["webhook_url"].startswith("https://")

        posts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posts.append(str(request.url))
            return httpx.Response(200, json={"code": 0})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        NotificationDispatcher(client=client).send("feishu", cfg, md, "t")
        assert posts
        we_cfg = {"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc"}
        NotificationDispatcher(client=client).send("wecom", we_cfg, "hello", "t")
        try:
            NotificationDispatcher(client=client).send("email", cfg, md, "t")
            raise AssertionError("expected")
        except NotifyError:
            pass
        client.close()
        sub.frequency = "monthly"
        sub.last_sent_at = datetime.now(timezone.utc) - timedelta(days=40)
        assert should_run(sub) is True
        tok = create_access_token(user_id, user.email)
        payload = decode_token(tok)
        assert payload["email"] == user.email
    finally:
        db.close()


def test_scheduler_jobs_do_not_crash():
    from app.scheduler.beat import job_cleanup, job_scan_keywords, job_subscription_briefs, job_update_stats

    job_scan_keywords()
    job_update_stats()
    job_subscription_briefs()
    job_cleanup()
