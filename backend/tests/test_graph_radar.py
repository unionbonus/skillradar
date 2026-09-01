from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.graph.store import MemoryGraphStore, Neo4jGraphStore, build_graph_store, get_graph_store, reset_graph_store
from app.main import create_app
from app.models import Repository, ScanKeyword
from app.scanner.keywords import due_keywords, keyword_is_due, seed_keywords
from app.scanner.pipeline import infer_fingerprint, sync_scan_to_graph
from app.scanner.service import ScannerError, ScannerService


GH_ITEM = {
    "id": 7,
    "full_name": "acme/claude-skill",
    "html_url": "https://github.com/acme/claude-skill",
    "description": "claude skill pack",
    "stargazers_count": 30,
    "forks_count": 1,
    "language": "Python",
    "topics": ["claude"],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-02-01T00:00:00Z",
}


def _client() -> TestClient:
    return TestClient(create_app())


def _auth(c: TestClient) -> dict[str, str]:
    reg = c.post("/api/v1/auth/register", json={"email": "radar@example.com", "password": "password1"})
    assert reg.status_code == 200, reg.text
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _patch_github(monkeypatch, items: list[dict] | None = None, fail: bool = False) -> None:
    payload = items if items is not None else [GH_ITEM]

    def fake_scan(self: ScannerService, keyword: str, limit: int = 50, search_type: str = "keyword") -> list[Repository]:
        if fail:
            raise ScannerError("GitHub search failed: boom")
        repos: list[Repository] = []
        for item in payload[:limit]:
            repos.append(self._upsert_repo(item))
        self.db.commit()
        for repo in repos:
            self.db.refresh(repo)
        return repos

    monkeypatch.setattr("app.scanner.service.ScannerService.scan_keyword", fake_scan)


def test_memory_graph_and_radar_layout():
    reset_graph_store()
    store = get_graph_store()
    assert store.backend == "memory"
    db: Session = SessionLocal()
    try:
        repo = Repository(full_name="acme/mcp-kit", html_url="https://github.com/acme/mcp-kit", description="MCP server", stargazers_count=42)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        sync_scan_to_graph([repo], "mcp server", "keyword")
        db.commit()
        radar = store.query_radar()
        assert radar["nodes"]
        assert any(n["data"].get("repo_id") == repo.id for n in radar["nodes"] if n.get("type") == "repository")
        assert any(e["data"].get("rel") == "HIT" for e in radar["edges"])
        assert infer_fingerprint(repo) == "mcp_server"
    finally:
        db.close()
        reset_graph_store()


def test_keyword_due_and_seed():
    db: Session = SessionLocal()
    try:
        n = seed_keywords(db)
        assert n >= 1
        rows = due_keywords(db)
        assert rows
        kw = ScanKeyword(query="solo-test", search_type="keyword", enabled=True, interval_hours=6)
        kw.last_run_at = datetime.now(timezone.utc)
        assert keyword_is_due(kw) is False
        kw.last_run_at = datetime.now(timezone.utc) - timedelta(hours=7)
        assert keyword_is_due(kw) is True
        kw.enabled = False
        assert keyword_is_due(kw) is False
    finally:
        db.close()


def test_scan_syncs_star_delta_and_keywords():
    db: Session = SessionLocal()
    try:
        client = httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": [GH_ITEM]}))
        )
        svc = ScannerService(db, client=client)
        first = svc.scan_keyword("claude skill", limit=5)
        assert first[0].star_delta == 0

        hotter = dict(GH_ITEM)
        hotter["stargazers_count"] = 40
        svc2 = ScannerService(
            db,
            client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": [hotter]}))),
        )
        second = svc2.scan_keyword("claude skill", limit=5)
        assert second[0].star_delta == 10
        sync_scan_to_graph(second, "claude skill", "keyword")
        db.commit()
        assert "claude skill" in (second[0].source_keywords or [])
        radar = get_graph_store().query_radar()
        assert radar["nodes"]
        client.close()
    finally:
        db.close()


def test_memory_store_structure_roundtrip():
    store = MemoryGraphStore()
    repo = Repository(id=99, full_name="a/b", html_url="https://github.com/a/b")
    graphs = {"module_dependency": {"nodes": [{"id": "n1"}], "edges": []}}
    store.upsert_structure(repo, graphs)
    got = store.query_repo(99, "module_dependency")
    assert got and got["nodes"][0]["id"] == "n1"
    assert store.status()["connected"] is True


def test_related_edges_same_fingerprint():
    store = MemoryGraphStore()
    a = Repository(id=1, full_name="a/one", html_url="https://github.com/a/one", fingerprint_type="mcp_server")
    b = Repository(id=2, full_name="a/two", html_url="https://github.com/a/two", fingerprint_type="mcp_server")
    store.upsert_radar_repo(a)
    store.upsert_radar_repo(b)
    edges = store.query_radar()["edges"]
    assert any(e["data"].get("rel") == "RELATED_TO" for e in edges)


def test_build_graph_store_memory_and_neo4j_fallback(monkeypatch):
    reset_graph_store()
    assert build_graph_store().backend == "memory"

    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:1")
    from app.config import reset_settings

    reset_settings()

    class Boom:
        @staticmethod
        def driver(*args, **kwargs):
            raise RuntimeError("refused")

    import neo4j

    monkeypatch.setattr(neo4j, "GraphDatabase", Boom)
    store = build_graph_store()
    assert store.backend == "memory"
    monkeypatch.delenv("NEO4J_URI", raising=False)
    reset_settings()
    reset_graph_store()


class _Rec(dict):
    def get(self, k, default=None):
        return super().get(k, default)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def single(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _FakeSession:
    def __init__(self, db: dict):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, cypher: str, **params):
        cy = " ".join(cypher.split())
        if self.db.get("raise"):
            raise RuntimeError("neo4j down")
        if "RETURN r.graph_json AS g" in cy:
            g = self.db["graphs"].get(params.get("id"))
            return _Result([_Rec(g=g)] if g is not None else [])
        if "count(r) AS n" in cy:
            return _Result([_Rec(n=len(self.db["repos"]))])
        if "collect(DISTINCT k.query)" in cy:
            rows = []
            for rid, repo in self.db["repos"].items():
                kws = [q for q, hid in self.db["hits"] if hid == rid]
                rows.append(
                    _Rec(
                        id=rid,
                        full_name=repo.get("name"),
                        stars=repo.get("stars") or 0,
                        star_delta=repo.get("delta") or 0,
                        fingerprint=repo.get("fp"),
                        is_ai_skill=repo.get("skill"),
                        html_url=repo.get("url"),
                        keywords=kws,
                    )
                )
            return _Result(rows)
        if "type(rel) AS rel" in cy:
            rels = []
            by_fp: dict[str, list[int]] = {}
            for rid, repo in self.db["repos"].items():
                fp = repo.get("fp")
                if fp:
                    by_fp.setdefault(fp, []).append(rid)
            for ids in by_fp.values():
                ids = sorted(set(ids))
                for i, src in enumerate(ids):
                    for dst in ids[i + 1 :]:
                        rels.append(_Rec(src=src, rel="RELATED_TO", dst=dst))
            return _Result(rels)
        if "MERGE (k:Keyword" in cy:
            self.db["keywords"][params["q"]] = params["t"]
            self.db["hits"].add((params["q"], params["id"]))
            return _Result([])
        if "MERGE (r:Repository" in cy:
            rec = self.db["repos"].setdefault(params["id"], {})
            rec.update(
                {
                    "name": params.get("name"),
                    "stars": params.get("stars"),
                    "delta": params.get("delta"),
                    "fp": params.get("fp"),
                    "skill": params.get("skill"),
                    "url": params.get("url"),
                }
            )
            if params.get("g") is not None:
                self.db["graphs"][params["id"]] = params["g"]
            return _Result([])
        return _Result([])


class _FakeDriver:
    def __init__(self):
        self.db = {"repos": {}, "keywords": {}, "hits": set(), "graphs": {}, "raise": False}
        self.dead = False

    def verify_connectivity(self):
        if self.dead:
            raise RuntimeError("offline")

    def session(self):
        return _FakeSession(self.db)


def test_neo4j_store_with_fake_driver():
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    store.driver = _FakeDriver()
    repo = Repository(
        id=1,
        full_name="acme/mcp",
        html_url="https://github.com/acme/mcp",
        description="mcp",
        fingerprint_type="mcp_server",
        is_ai_skill=True,
        stargazers_count=9,
        star_delta=2,
    )
    store.upsert_radar_repo(repo)
    store.link_keyword("mcp server", "keyword", repo)
    store.link_related()
    graphs = {"module_dependency": {"nodes": [{"id": "n1"}], "edges": []}}
    store.upsert_structure(repo, graphs)
    got = store.query_repo(1, "module_dependency")
    assert got and got["nodes"][0]["id"] == "n1"
    radar = store.query_radar()
    assert radar["backend"] == "neo4j"
    assert any(n["type"] == "repository" for n in radar["nodes"])
    assert store.connected() is True
    assert store.status()["nodes"] == 1
    store.driver.dead = True
    assert store.connected() is False
    store.driver.dead = False
    store.driver.db["graphs"][1] = "{not-json"
    try:
        store.query_repo(1, "module_dependency")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    store.driver.db["raise"] = True
    empty = store.query_radar()
    assert empty["nodes"] == []
    assert store.query_repo(1, "module_dependency") is None


def test_radar_keywords_api_and_watch_scan(monkeypatch):
    _patch_github(monkeypatch)
    with _client() as c:
        headers = _auth(c)
        health = c.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.5.2"
        assert health.json()["graph"]["backend"] in {"memory", "neo4j"}

        listed = c.get("/api/v1/scan/keywords", headers=headers)
        assert listed.status_code == 200
        seeds = listed.json()["data"]["items"]
        assert any(k["query"] == "mcp server" for k in seeds)

        created = c.post(
            "/api/v1/scan/keywords",
            json={"query": "langgraph", "search_type": "keyword", "interval_hours": 6, "limit": 5},
            headers=headers,
        )
        assert created.status_code == 200, created.text
        kw_id = created.json()["data"]["id"]
        assert created.json()["data"]["is_due"] is True
        dup = c.post(
            "/api/v1/scan/keywords",
            json={"query": "langgraph", "search_type": "keyword"},
            headers=headers,
        )
        assert dup.status_code == 409

        radar = c.get("/api/v1/radar", headers=headers)
        assert radar.status_code == 200
        snap = radar.json()["data"]
        assert "keywords" in snap and "graph" in snap and "stats" in snap

        tasks = c.get("/api/v1/scan/tasks", headers=headers)
        assert tasks.status_code == 200
        missing_task = c.get("/api/v1/scan/tasks/00000000-0000-0000-0000-000000000000", headers=headers)
        assert missing_task.status_code == 404
        missing_put = c.put(
            "/api/v1/scan/keywords/00000000-0000-0000-0000-000000000000",
            json={"query": "nope", "search_type": "keyword", "enabled": True, "interval_hours": 6, "limit": 5},
            headers=headers,
        )
        assert missing_put.status_code == 404

        scan = c.post(
            "/api/v1/scan/github",
            json={"query": "unique-watch-term", "type": "keyword", "limit": 5, "watch": True},
            headers=headers,
        )
        assert scan.status_code == 200
        task_id = scan.json()["data"]["task_id"]
        status = None
        for _ in range(20):
            st = c.get(f"/api/v1/scan/tasks/{task_id}", headers=headers)
            assert st.status_code == 200
            status = st.json()["data"]["status"]
            if status in {"success", "failed"}:
                break
        assert status == "success", st.text

        run = c.post(f"/api/v1/scan/keywords/{kw_id}/run", headers=headers)
        assert run.status_code == 200
        due = c.post("/api/v1/scan/keywords/run-due", headers=headers)
        assert due.status_code == 200
        assert due.json()["data"]["due"] >= 1

        after = c.get("/api/v1/radar", headers=headers)
        body = after.json()["data"]
        assert body["stats"]["repositories"] >= 1
        assert any(n.get("type") == "repository" for n in body["graph"]["nodes"])
        assert any(r["full_name"] == "acme/claude-skill" for r in body["items"])
        watched = [k["query"] for k in body["keywords"]]
        assert "unique-watch-term" in watched
        repo_id = body["items"][0]["id"]
        detail = c.get(f"/api/v1/repos/{repo_id}", headers=headers)
        assert detail.status_code == 200
        graph_miss = c.get(f"/api/v1/repos/{repo_id}/graph", headers=headers)
        assert graph_miss.status_code == 404

        other = next(k for k in body["keywords"] if k["query"] == "mcp server")
        clash = c.put(
            f"/api/v1/scan/keywords/{kw_id}",
            json={"query": other["query"], "search_type": "keyword", "enabled": True, "interval_hours": 6, "limit": 5},
            headers=headers,
        )
        assert clash.status_code == 409

        paused = c.put(
            f"/api/v1/scan/keywords/{kw_id}",
            json={"query": "langgraph", "search_type": "keyword", "enabled": False, "interval_hours": 12, "limit": 5},
            headers=headers,
        )
        assert paused.status_code == 200
        assert paused.json()["data"]["enabled"] is False

        gone = c.delete(f"/api/v1/scan/keywords/{kw_id}", headers=headers)
        assert gone.status_code == 200
        missing = c.delete(f"/api/v1/scan/keywords/{kw_id}", headers=headers)
        assert missing.status_code == 404
        missing_run = c.post(f"/api/v1/scan/keywords/{kw_id}/run", headers=headers)
        assert missing_run.status_code == 404


def test_scan_github_failure_marks_task(monkeypatch):
    _patch_github(monkeypatch, fail=True)
    with _client() as c:
        headers = _auth(c)
        scan = c.post("/api/v1/scan/github", json={"query": "mcp", "type": "keyword", "limit": 1}, headers=headers)
        assert scan.status_code == 200
        task_id = scan.json()["data"]["task_id"]
        status = None
        for _ in range(20):
            st = c.get(f"/api/v1/scan/tasks/{task_id}", headers=headers)
            status = st.json()["data"]["status"]
            if status in {"success", "failed"}:
                break
        assert status == "failed"


def test_keyword_run_failure_records_error(monkeypatch):
    _patch_github(monkeypatch, fail=True)
    with _client() as c:
        headers = _auth(c)
        created = c.post(
            "/api/v1/scan/keywords",
            json={"query": "will-fail", "search_type": "keyword", "interval_hours": 6, "limit": 5},
            headers=headers,
        )
        kw_id = created.json()["data"]["id"]
        run = c.post(f"/api/v1/scan/keywords/{kw_id}/run", headers=headers)
        assert run.status_code == 200
        listed = c.get("/api/v1/scan/keywords", headers=headers)
        row = next(k for k in listed.json()["data"]["items"] if k["id"] == kw_id)
        assert row["last_status"] == "failed"
        assert row["last_error"]


def test_scheduler_scans_due_keywords(monkeypatch):
    _patch_github(monkeypatch)
    db: Session = SessionLocal()
    try:
        seed_keywords(db)
        from app.scheduler.beat import job_scan_keywords

        job_scan_keywords()
        radar = get_graph_store().query_radar()
        assert radar["nodes"]
    finally:
        db.close()


def test_run_scan_missing_task_is_noop():
    from uuid import uuid4

    from app.api.scan import _run_scan

    _run_scan(uuid4(), "ghost", "keyword", 1)


def test_infer_fingerprint_variants():
    assert infer_fingerprint(Repository(full_name="x/langgraph-bot", html_url="https://github.com/x/l", description="")) == "langchain_tool"
    assert infer_fingerprint(Repository(full_name="x/other", html_url="https://github.com/x/o", description="nothing")) is None
    marked = Repository(full_name="x/a", html_url="https://github.com/x/a", fingerprint_type="mcp_server")
    assert infer_fingerprint(marked) == "mcp_server"
