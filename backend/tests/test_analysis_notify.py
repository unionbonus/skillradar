from __future__ import annotations

import json

from app.analysis.motivation import heuristic_motivation, render_prd
from app.notification.briefs import should_run
from app.notification.dispatcher import build_feishu_card, build_wecom_markdown, feishu_sign
from app.security import decrypt_secret, encrypt_secret, hash_password, verify_password
from app.models import Subscription
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def test_crypto_and_password():
    hashed = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", hashed)
    assert verify_password("wrong-pass", hashed) is False
    blob = encrypt_secret(json.dumps({"webhook_url": "https://open.feishu.cn/hook/x"}))
    assert "open.feishu" not in blob
    plain = decrypt_secret(blob)
    assert "open.feishu.cn" in plain


def test_motivation_and_prd():
    structure = {
        "full_name": "demo/web-search",
        "fingerprint_type": "claude_skill",
        "skills": [{"name": "web-search", "description": "search", "entry_file": "SKILL.md"}],
    }
    mot = heuristic_motivation(structure, "Why: 多工具编排复杂")
    assert mot["pain_points"]
    prd = render_prd(structure, mot)
    assert "PRD" in prd and "web-search" in prd


def test_should_run_and_payloads():
    sub = Subscription(id=uuid4(), user_id=uuid4(), name="t", frequency="weekly", is_active=True)
    assert should_run(sub) is True
    sub.last_sent_at = datetime.now(timezone.utc) - timedelta(days=8)
    assert should_run(sub) is True
    sub.last_sent_at = datetime.now(timezone.utc)
    assert should_run(sub) is False
    sign = feishu_sign("s", 1)
    assert isinstance(sign, str) and sign
    card = build_feishu_card("T", "**hi**")
    assert card["msg_type"] == "interactive"
    we = build_wecom_markdown("x" * 5000)
    assert len(we["markdown"]["content"].encode("utf-8")) <= 4096
