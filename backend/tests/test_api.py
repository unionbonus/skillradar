from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Repository
from app.scanner.service import ScannerService

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample-skill"


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_register_decompose_subscription(monkeypatch):
    def fake_scan(self: ScannerService, keyword: str, limit: int = 50, search_type: str = "keyword") -> list[Repository]:
        return []

    monkeypatch.setattr("app.scanner.service.ScannerService.scan_keyword", fake_scan)
    with _client() as c:
        health = c.get("/api/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.5.3"

        reg = c.post("/api/v1/auth/register", json={"email": "pm@example.com", "password": "password1"})
        assert reg.status_code == 200, reg.text
        token = reg.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        login = c.post("/api/v1/auth/login", json={"email": "pm@example.com", "password": "password1"})
        assert login.status_code == 200

        dec = c.post(
            "/api/v1/repos/decompose",
            json={"repo_url": "file://" + str(FIXTURE), "local_path": str(FIXTURE)},
            headers=headers,
        )
        assert dec.status_code == 200, dec.text
        task_id = dec.json()["data"]["task_id"]
        st = c.get(f"/api/v1/scan/tasks/{task_id}", headers=headers)
        assert st.status_code == 200
        assert st.json()["data"]["status"] in {"success", "running", "queued"}

        repos = c.get("/api/v1/repos", headers=headers)
        assert repos.status_code == 200
        items = repos.json()["data"]["items"]
        assert items
        repo_id = items[0]["id"]
        mot = c.post(f"/api/v1/repos/{repo_id}/motivation", headers=headers)
        assert mot.status_code == 200
        prd = c.get(f"/api/v1/repos/{repo_id}/prd", headers=headers)
        assert prd.status_code == 200
        assert "PRD" in prd.json()["data"]["markdown"]
        graph = c.get(f"/api/v1/repos/{repo_id}/graph?type=module_dependency", headers=headers)
        assert graph.status_code == 200
        assert graph.json()["data"]["nodes"]

        sub = c.post(
            "/api/v1/subscriptions",
            json={
                "name": "AI Agent 赛道",
                "conditions": {"keywords": ["skill"], "authors": [], "organizations": [], "topics": [], "specific_repos": []},
                "frequency": "weekly",
                "channel": "feishu",
                "channel_config": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"},
            },
            headers=headers,
        )
        assert sub.status_code == 200, sub.text
        sub_id = sub.json()["data"]["subscription_id"]
        listed = c.get("/api/v1/subscriptions", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["data"]["items"]
        test_send = c.post(f"/api/v1/subscriptions/{sub_id}/send-test", headers=headers)
        assert test_send.status_code == 200
        hist = c.get(f"/api/v1/subscriptions/{sub_id}/history", headers=headers)
        assert hist.status_code == 200
        detail = c.get(f"/api/v1/subscriptions/{sub_id}", headers=headers)
        assert detail.status_code == 200
        structure = c.get(f"/api/v1/repos/{repo_id}/structure", headers=headers)
        assert structure.status_code == 200
        got_mot = c.get(f"/api/v1/repos/{repo_id}/motivation", headers=headers)
        assert got_mot.status_code == 200
        put = c.put(f"/api/v1/repos/{repo_id}/prd", headers=headers, json={"markdown": "# edited"})
        assert put.status_code == 200
        scan = c.post(
            "/api/v1/scan/github",
            json={"query": "mcp", "type": "keyword", "limit": 1},
            headers=headers,
        )
        assert scan.status_code == 200
        c.delete(f"/api/v1/subscriptions/{sub_id}", headers=headers)


