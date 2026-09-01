from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.channels.live import reset_live_state
from app.channels.qrcode_svg import qr_svg
from app.main import create_app


def _client() -> TestClient:
    reset_live_state()
    return TestClient(create_app())


def _auth(c: TestClient) -> dict[str, str]:
    email = f"live{uuid4().hex[:8]}@example.com"
    reg = c.post("/api/v1/auth/register", json={"email": email, "password": "password1"})
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}


def test_qr_svg_contains_path():
    svg = qr_svg("https://example.com/bind/demo")
    assert "<svg" in svg
    assert "path" in svg.lower() or "rect" in svg.lower()


def test_channel_qr_then_confirm_avatar_state():
    with _client() as c:
        headers = _auth(c)
        st = c.get("/api/v1/channels/live/status", headers=headers)
        assert st.status_code == 200, st.text
        data = st.json()["data"]
        assert data["keep_alive"] is True
        feishu = data["channels"]["feishu"]
        wecom = data["channels"]["wecom"]
        assert feishu["connected"] is False
        assert wecom["connected"] is False
        assert feishu["qr_svg"]
        assert wecom["qr_svg"]
        assert feishu["ticket"]
        ticket = feishu["ticket"]
        page = c.get(f"/api/v1/channels/bind/{ticket}")
        assert page.status_code == 200
        assert "确认绑定" in page.text
        done = c.post(f"/api/v1/channels/bind/{ticket}", json={"display_name": "飞书测试员"})
        assert done.status_code == 200
        after = c.get("/api/v1/channels/live/status", headers=headers).json()["data"]
        assert after["channels"]["feishu"]["connected"] is True
        assert after["channels"]["feishu"]["display_name"] == "飞书测试员"
        assert not after["channels"]["feishu"]["qr_svg"]
        wecom_ok = c.post("/api/v1/channels/live/wecom/confirm", headers=headers, json={})
        assert wecom_ok.status_code == 200
        assert wecom_ok.json()["data"]["channels"]["wecom"]["connected"] is True
        off = c.post("/api/v1/channels/live/feishu/disconnect", headers=headers)
        assert off.status_code == 200
        assert off.json()["data"]["channels"]["feishu"]["connected"] is False
        assert off.json()["data"]["channels"]["feishu"]["qr_svg"]


def test_channel_websocket_keep_alive():
    with _client() as c:
        headers = _auth(c)
        token = headers["Authorization"].split(" ", 1)[1]
        c.get("/api/v1/channels/live/status", headers=headers)
        sse = c.get(f"/api/v1/channels/live/stream?token={token}&once=true")
        assert sse.status_code == 200
        assert "feishu" in sse.text
        with c.websocket_connect(f"/api/v1/channels/live?token={token}") as ws:
            msg = ws.receive_json()
            assert "channels" in msg
            assert msg["channels"]["feishu"]["keep_alive"] is True
            assert msg["channels"]["wecom"]["keep_alive"] is True
