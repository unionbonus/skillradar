from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.analysis.deep_dive import analyze_deep_dive
from app.analysis.highlights import mine_highlights
from app.analysis.market import analyze_market
from app.analysis.report import render_business_report
from app.main import create_app
from app.notification.dispatcher import NotificationDispatcher, NotifyError
from app.scanner.adapters import PluginHit, search_npm, upsert_hit
from app.search.embed import cosine, embed_text
from app.search.vectors import MemoryVectorStore, get_vector_store, reset_vector_store
from app.storage.objects import LocalObjectStore, aws_v4_headers, get_object_store

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample-skill"


def _client() -> TestClient:
    return TestClient(create_app())


def _auth(c: TestClient) -> dict[str, str]:
    email = f"u{uuid4().hex[:8]}@example.com"
    reg = c.post("/api/v1/auth/register", json={"email": email, "password": "password1"})
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}


def test_health_exposes_vector_and_objects():
    with _client() as c:
        health = c.get("/api/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["version"] == "0.5.2"
        assert body["vector"]["backend"] in {"memory", "qdrant"}
        assert body["objects"]["backend"] in {"local", "minio"}


def test_embed_and_memory_search():
    reset_vector_store()
    a = embed_text("mcp filesystem server")
    b = embed_text("mcp filesystem tool")
    assert cosine(a, b) > cosine(a, embed_text("unrelated cooking recipe"))
    store = MemoryVectorStore()
    store.upsert(1, "mcp filesystem server skill", {"kind": "plugin"})
    hits = store.search("filesystem mcp", limit=3)
    assert hits and hits[0]["id"] == "1"


def test_local_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(tmp_path)
    key = store.put("prd/1.md", b"# hi", "text/markdown")
    assert store.get(key) == b"# hi"
    assert store.status()["objects"] >= 1
    assert "AWS4-HMAC-SHA256" in aws_v4_headers("PUT", "http://localhost:9000/b/k", b"x", "a", "s", "text/plain")["Authorization"]


def test_search_report_config_and_deep_dive():
    with _client() as c:
        headers = _auth(c)
        health = c.get("/api/v1/health")
        assert health.json()["version"] == "0.5.2"
        dec = c.post(
            "/api/v1/plugins/decompose",
            json={"repo_url": "file://" + str(FIXTURE), "local_path": str(FIXTURE)},
            headers=headers,
        )
        assert dec.status_code == 200, dec.text
        repos = c.get("/api/v1/plugins", headers=headers)
        assert repos.status_code == 200
        items = repos.json()["data"]["items"]
        assert items
        pid = items[0]["id"]
        deep = c.post(f"/api/v1/plugins/{pid}/deep-dive", headers=headers)
        assert deep.status_code == 200
        assert deep.json()["data"]["architecture"]["style"]
        market = c.post(f"/api/v1/plugins/{pid}/market-research", headers=headers)
        assert market.status_code == 200
        assert market.json()["data"]["competitors"]
        got = c.get(f"/api/v1/plugins/{pid}/deep-dive", headers=headers)
        assert got.status_code == 200
        report = c.post("/api/v1/reports/generate", json={"plugin_id": pid}, headers=headers)
        assert report.status_code == 200, report.text
        rid = report.json()["data"]["id"]
        listed = c.get("/api/v1/reports", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["data"]["items"]
        one = c.get(f"/api/v1/reports/{rid}", headers=headers)
        assert "商业拆解" in one.json()["data"]["content_md"]
        search = c.get("/api/v1/search", params={"q": "web-search"}, headers=headers)
        assert search.status_code == 200
        assert search.json()["data"]["backend"]
        llm = c.post(
            "/api/v1/configs/llm",
            json={"name": "local", "provider": "openai", "model_name": "gpt-4o-mini", "is_default": True},
            headers=headers,
        )
        assert llm.status_code == 200
        ch = c.post(
            "/api/v1/configs/channels",
            json={"name": "fs", "channel_type": "feishu", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/x"},
            headers=headers,
        )
        assert ch.status_code == 200
        llms = c.get("/api/v1/configs/llm", headers=headers)
        assert llms.json()["data"]["items"]


def test_npm_adapter_and_upsert(monkeypatch):
    from app.db import SessionLocal
    from app.models import Repository

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "package": {
                            "name": "@modelcontextprotocol/server-fs",
                            "description": "mcp filesystem",
                            "version": "1.0.0",
                            "keywords": ["mcp"],
                            "links": {"npm": "https://www.npmjs.com/package/@modelcontextprotocol/server-fs"},
                            "publisher": {"username": "mcp"},
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    hits = search_npm(client, "mcp", 5)
    assert hits and hits[0].source == "npm"
    db = SessionLocal()
    try:
        repo = upsert_hit(db, hits[0])
        db.commit()
        assert db.get(Repository, repo.id).source == "npm"
    finally:
        db.close()


def test_email_requires_smtp():
    d = NotificationDispatcher()
    try:
        d.send("email", {"email": "a@b.com"}, "hi", "t")
        raise AssertionError("expected NotifyError")
    except NotifyError as exc:
        assert "SMTP" in str(exc)


def test_channel_adapters_mock_http():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "pypi.org" in url:
            return httpx.Response(200, json={"info": {"name": "mcp-server-demo", "summary": "mcp", "version": "1.2", "license": "MIT", "project_url": "https://pypi.org/project/mcp-server-demo/"}})
        if "huggingface.co" in url:
            return httpx.Response(200, json=[{"id": "org/model", "likes": 3, "downloads": 9, "pipeline_tag": "text-generation"}])
        if "hub.docker.com" in url:
            return httpx.Response(200, json={"results": [{"repo_name": "mcp/demo", "short_description": "img", "star_count": 4}]})
        if "modelcontextprotocol.io" in url:
            return httpx.Response(200, json={"servers": [{"name": "filesystem", "description": "mcp filesystem"}]})
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    from app.scanner.adapters import search_dockerhub, search_huggingface, search_mcp_registry, search_pypi, search_channel

    assert search_pypi(client, "mcp-server-demo", 3)
    assert search_huggingface(client, "model", 3)
    assert search_dockerhub(client, "mcp", 3)
    assert search_mcp_registry(client, "file", 3)
    assert search_channel("npm", "x", 1, client) == []
    try:
        search_channel("nope", "x", 1, client)
        raise AssertionError("expected error")
    except Exception:
        pass


def test_report_renderer_contains_sections():
    structure = {"full_name": "acme/mcp", "fingerprint_type": "mcp_server", "skills": [{"name": "fs", "entry_file": "server.py", "tools": [{"name": "read"}]}]}
    deep = analyze_deep_dive(structure)
    highs = mine_highlights(structure, {"pain_points": [{"pain": "x", "evidence": "y"}]})
    market = analyze_market(structure, {"full_name": "acme/mcp", "stargazers_count": 12, "fingerprint_type": "mcp_server"})
    md = render_business_report({"full_name": "acme/mcp", "source": "github", "stargazers_count": 12}, structure, {"design_principles": ["清晰"]}, deep, highs, market)
    assert "执行摘要" in md and "PEST" in md and "MVP" in md
