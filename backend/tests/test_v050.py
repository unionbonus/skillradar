from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Repository
from app.scanner.service import ScannerService

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample-skill"


def _client() -> TestClient:
    return TestClient(create_app())


def test_v050_configs_market_research_commercial(monkeypatch):
    def fake_scan(self: ScannerService, keyword: str, limit: int = 50, search_type: str = "keyword") -> list[Repository]:
        return []

    monkeypatch.setattr("app.scanner.service.ScannerService.scan_keyword", fake_scan)
    monkeypatch.setattr("app.market_research.collectors._get_json", lambda *a, **k: None)
    with _client() as c:
        health = c.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.5.0"
        assert health.json()["status"] in {"ok", "degraded"}

        reg = c.post("/api/v1/auth/register", json={"email": "intel@example.com", "password": "password1"})
        assert reg.status_code == 200, reg.text
        token = reg.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        llm = c.post(
            "/api/v1/configs/llm",
            headers=headers,
            json={
                "name": "GPT-4o 默认",
                "provider": "openai",
                "api_key": "sk-test-secret-key-1234",
                "model_name": "gpt-4o",
                "temperature": 0.2,
                "is_default": True,
            },
        )
        assert llm.status_code == 200, llm.text
        llm_body = llm.json()["data"]
        assert llm_body["api_key_masked"].endswith("1234")
        assert "sk-test" not in str(llm.json())
        llm_id = llm_body["id"]
        listed = c.get("/api/v1/configs/llm", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["data"]["items"]
        ping = c.post(f"/api/v1/configs/llm/{llm_id}/test", headers=headers)
        assert ping.status_code == 200
        assert ping.json()["data"]["ok"] is False

        ch = c.post(
            "/api/v1/configs/channels",
            headers=headers,
            json={
                "name": "公司飞书群",
                "channel_type": "feishu",
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "secret": "hook-secret",
                "is_default": True,
            },
        )
        assert ch.status_code == 200, ch.text
        assert "hook-secret" not in str(ch.json())
        ch_id = ch.json()["data"]["id"]
        ch_test = c.post(f"/api/v1/configs/channels/{ch_id}/test", headers=headers)
        assert ch_test.status_code == 200

        mail = c.post(
            "/api/v1/configs/channels",
            headers=headers,
            json={
                "name": "情报邮箱",
                "channel_type": "email",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_user": "bot@example.com",
                "smtp_password": "mail-pass",
                "from_email": "bot@example.com",
                "to_email": "pm@example.com",
            },
        )
        assert mail.status_code == 200

        dec = c.post(
            "/api/v1/repos/decompose",
            json={"repo_url": "file://" + str(FIXTURE), "local_path": str(FIXTURE)},
            headers=headers,
        )
        assert dec.status_code == 200, dec.text
        repos = c.get("/api/v1/repos", headers=headers)
        repo_id = repos.json()["data"]["items"][0]["id"]

        mr = c.post(f"/api/v1/plugins/{repo_id}/market-research", headers=headers, json={})
        assert mr.status_code == 200, mr.text
        md = mr.json()["data"]["content_md"]
        assert "市场调研报告" in md
        assert "PEST" in md
        assert "MVP" in md
        competitors = mr.json()["data"]["content_json"]["competitors"]
        assert len(competitors) >= 5
        pains = mr.json()["data"]["content_json"]["pain_points"]
        assert 3 <= len(pains) <= 5
        assert mr.json()["data"]["evidence"]
        report_id = mr.json()["data"]["id"]

        got = c.get(f"/api/v1/repos/{repo_id}/market-research", headers=headers)
        assert got.status_code == 200
        edited = c.put(
            f"/api/v1/market-research/{report_id}",
            headers=headers,
            json={"content_md": "# 人工修订\n\n已确认。"},
        )
        assert edited.status_code == 200
        assert "人工修订" in edited.json()["data"]["content_md"]

        com = c.post(f"/api/v1/repos/{repo_id}/commercial-report", headers=headers, json={})
        assert com.status_code == 200, com.text
        cmd = com.json()["data"]["content_md"]
        assert "商业拆解报告" in cmd
        assert "需求调研详细分析" in cmd
        assert "## 6. 商业机会" in cmd

        sub = c.post(
            "/api/v1/subscriptions",
            headers=headers,
            json={
                "name": "MCP 赛道",
                "conditions": {"keywords": ["mcp"], "authors": [], "organizations": [], "topics": [], "specific_repos": []},
                "frequency": "weekly",
                "channel": "feishu",
                "channel_config": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"},
                "llm_config_id": llm_id,
                "channel_config_id": ch_id,
            },
        )
        assert sub.status_code == 200, sub.text
        assert sub.json()["data"]["llm_config_id"] == llm_id
        assert sub.json()["data"]["channel_config_id"] == ch_id
