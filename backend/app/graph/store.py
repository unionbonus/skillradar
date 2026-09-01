from __future__ import annotations

import json
import logging
import math
import threading
from typing import Any, Protocol

from app.config import get_settings
from app.models import Repository

logger = logging.getLogger("skillradar.graph")


class GraphStore(Protocol):
    backend: str

    def connected(self) -> bool: ...
    def upsert_structure(self, repo: Repository, graphs: dict[str, Any]) -> None: ...
    def query_repo(self, repo_id: int, graph_type: str) -> dict[str, list] | None: ...
    def upsert_radar_repo(self, repo: Repository) -> None: ...
    def link_keyword(self, query: str, search_type: str, repo: Repository) -> None: ...
    def link_related(self) -> None: ...
    def query_radar(self) -> dict[str, Any]: ...
    def status(self) -> dict[str, Any]: ...


class MemoryGraphStore:
    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.graphs: dict[int, dict[str, Any]] = {}
        self.repos: dict[int, dict[str, Any]] = {}
        self.hits: set[tuple[str, int]] = set()
        self.keywords: dict[str, str] = {}

    def connected(self) -> bool:
        return True

    def upsert_structure(self, repo: Repository, graphs: dict[str, Any]) -> None:
        with self._lock:
            self.graphs[int(repo.id)] = graphs
            self._put_repo_locked(repo)

    def query_repo(self, repo_id: int, graph_type: str) -> dict[str, list] | None:
        with self._lock:
            pack = self.graphs.get(int(repo_id)) or {}
            g = pack.get(graph_type) or pack.get("module_dependency")
            return g if isinstance(g, dict) else None

    def upsert_radar_repo(self, repo: Repository) -> None:
        with self._lock:
            self._put_repo_locked(repo)

    def link_keyword(self, query: str, search_type: str, repo: Repository) -> None:
        with self._lock:
            self.keywords[query] = search_type
            self.hits.add((query, int(repo.id)))
            self._put_repo_locked(repo)

    def link_related(self) -> None:
        return

    def query_radar(self) -> dict[str, Any]:
        with self._lock:
            repos = list(self.repos.values())
            nodes, edges = _layout_radar(repos, list(self.hits))
            edges.extend(_related_edges(repos))
        return {"nodes": nodes, "edges": edges, "backend": self.backend}

    def status(self) -> dict[str, Any]:
        with self._lock:
            n = len(self.repos)
        return {"backend": self.backend, "connected": True, "nodes": n}

    def _put_repo_locked(self, repo: Repository) -> None:
        self.repos[int(repo.id)] = {
            "id": int(repo.id),
            "full_name": repo.full_name,
            "stars": int(repo.stargazers_count or 0),
            "star_delta": int(getattr(repo, "star_delta", 0) or 0),
            "fingerprint": repo.fingerprint_type,
            "is_ai_skill": bool(repo.is_ai_skill),
            "html_url": repo.html_url,
            "keywords": list(repo.source_keywords or []),
        }


class Neo4jGraphStore:
    backend = "neo4j"

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()

    def connected(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("neo4j ping failed: %s", exc)
            return False

    def upsert_structure(self, repo: Repository, graphs: dict[str, Any]) -> None:
        self._write_repo(repo, graphs)

    def query_repo(self, repo_id: int, graph_type: str) -> dict[str, list] | None:
        try:
            with self.driver.session() as session:
                rec = session.run(
                    "MATCH (r:Repository {id: $id}) RETURN r.graph_json AS g",
                    id=int(repo_id),
                ).single()
        except Exception as exc:
            logger.warning("neo4j query_repo failed: %s", exc)
            return None
        if rec is None or rec.get("g") is None:
            return None
        try:
            pack = json.loads(rec["g"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"neo4j graph_json invalid: {exc}") from exc
        g = pack.get(graph_type) or pack.get("module_dependency")
        return g if isinstance(g, dict) else None

    def upsert_radar_repo(self, repo: Repository) -> None:
        self._write_repo(repo, None)

    def link_keyword(self, query: str, search_type: str, repo: Repository) -> None:
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    MERGE (k:Keyword {query: $q})
                    SET k.search_type = $t
                    MERGE (r:Repository {id: $id})
                    SET r.full_name = $name
                    MERGE (k)-[:HIT]->(r)
                    """,
                    q=query,
                    t=search_type,
                    id=int(repo.id),
                    name=repo.full_name,
                )
        except Exception as exc:
            logger.warning("neo4j link_keyword failed: %s", exc)
        self._write_repo(repo, None)

    def link_related(self) -> None:
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (a:Repository), (b:Repository)
                    WHERE a.fingerprint IS NOT NULL
                      AND a.fingerprint = b.fingerprint
                      AND a.id < b.id
                    MERGE (a)-[:RELATED_TO]->(b)
                    """
                )
        except Exception as exc:
            logger.warning("neo4j link_related failed: %s", exc)

    def query_radar(self) -> dict[str, Any]:
        try:
            with self.driver.session() as session:
                rows = list(
                    session.run(
                        """
                        MATCH (r:Repository)
                        OPTIONAL MATCH (k:Keyword)-[:HIT]->(r)
                        RETURN r.id AS id, r.full_name AS full_name, r.stars AS stars,
                               r.star_delta AS star_delta, r.fingerprint AS fingerprint,
                               r.is_ai_skill AS is_ai_skill, r.html_url AS html_url,
                               collect(DISTINCT k.query) AS keywords
                        """
                    )
                )
                rels = list(
                    session.run(
                        """
                        MATCH (a:Repository)-[rel:RELATED_TO|HIT]-(b)
                        RETURN a.id AS src, type(rel) AS rel, b.id AS dst
                        """
                    )
                )
        except Exception as exc:
            logger.warning("neo4j query_radar failed: %s", exc)
            return {"nodes": [], "edges": [], "backend": self.backend, "error": str(exc)}
        repos = []
        hits: list[tuple[str, int]] = []
        for row in rows:
            rid = int(row["id"])
            kws = [k for k in (row["keywords"] or []) if k]
            repos.append(
                {
                    "id": rid,
                    "full_name": row["full_name"],
                    "stars": int(row["stars"] or 0),
                    "star_delta": int(row["star_delta"] or 0),
                    "fingerprint": row["fingerprint"],
                    "is_ai_skill": bool(row["is_ai_skill"]),
                    "html_url": row["html_url"],
                    "keywords": kws,
                }
            )
            for k in kws:
                hits.append((k, rid))
        nodes, edges = _layout_radar(repos, hits)
        for row in rels:
            if row["rel"] == "RELATED_TO" and row["src"] is not None and row["dst"] is not None:
                edges.append(
                    {
                        "id": f"rel-{row['src']}-{row['dst']}",
                        "source": f"repo:{row['src']}",
                        "target": f"repo:{row['dst']}",
                        "data": {"rel": "RELATED_TO"},
                    }
                )
        return {"nodes": nodes, "edges": edges, "backend": self.backend}

    def status(self) -> dict[str, Any]:
        ok = self.connected()
        nodes: int | None = None
        if ok:
            try:
                with self.driver.session() as session:
                    rec = session.run("MATCH (r:Repository) RETURN count(r) AS n").single()
                    nodes = int(rec["n"]) if rec is not None else 0
            except Exception as exc:
                logger.warning("neo4j count failed: %s", exc)
        return {"backend": self.backend, "connected": ok, "nodes": nodes}

    def _write_repo(self, repo: Repository, graphs: dict[str, Any] | None) -> None:
        payload = {
            "id": int(repo.id),
            "name": repo.full_name,
            "stars": int(repo.stargazers_count or 0),
            "delta": int(getattr(repo, "star_delta", 0) or 0),
            "fp": repo.fingerprint_type,
            "skill": bool(repo.is_ai_skill),
            "url": repo.html_url,
            "g": json.dumps(graphs) if graphs is not None else None,
        }
        cypher = """
            MERGE (r:Repository {id: $id})
            SET r.full_name = $name, r.stars = $stars, r.star_delta = $delta,
                r.fingerprint = $fp, r.is_ai_skill = $skill, r.html_url = $url
            """
        if graphs is not None:
            cypher += ", r.graph_json = $g"
        try:
            with self.driver.session() as session:
                session.run(cypher, **payload)
                if repo.fingerprint_type:
                    session.run(
                        """
                        MATCH (r:Repository {id: $id})
                        MERGE (s:Skill {name: $fp})
                        MERGE (r)-[:CONTAINS]->(s)
                        """,
                        id=int(repo.id),
                        fp=repo.fingerprint_type,
                    )
        except Exception as exc:
            logger.warning("neo4j write repo failed: %s", exc)


_store: GraphStore | None = None


def get_graph_store() -> GraphStore:
    global _store
    if _store is not None:
        return _store
    _store = build_graph_store()
    return _store


def reset_graph_store() -> None:
    global _store
    _store = None


def build_graph_store() -> GraphStore:
    settings = get_settings()
    uri = (settings.neo4j_uri or "").strip()
    if not uri:
        logger.info("graph store: memory (NEO4J_URI empty)")
        return MemoryGraphStore()
    try:
        store = Neo4jGraphStore(uri, settings.neo4j_user, settings.neo4j_password)
        logger.info("graph store: neo4j %s", uri)
        return store
    except Exception as exc:
        logger.warning("neo4j unavailable (%s), falling back to memory", exc)
        return MemoryGraphStore()


def _layout_radar(repos: list[dict[str, Any]], hits: list[tuple[str, int]]) -> tuple[list, list]:
    rings = ["claude_skill", "mcp_server", "langchain_tool", None]
    grouped: dict[str | None, list[dict[str, Any]]] = {k: [] for k in rings}
    for repo in repos:
        fp = repo.get("fingerprint")
        grouped[fp if fp in grouped else None].append(repo)
    nodes: list[dict[str, Any]] = []
    cx, cy = 420.0, 300.0
    for ri, key in enumerate(rings):
        bucket = grouped[key]
        radius = 70 + ri * 70
        n = max(len(bucket), 1)
        for i, repo in enumerate(bucket):
            angle = (2 * math.pi * i) / n - math.pi / 2
            boost = min(math.log10((repo.get("stars") or 0) + 10), 3) * 8
            x = cx + math.cos(angle) * (radius + boost)
            y = cy + math.sin(angle) * (radius + boost)
            nodes.append(
                {
                    "id": f"repo:{repo['id']}",
                    "type": "repository",
                    "position": {"x": x, "y": y},
                    "data": {
                        "label": repo.get("full_name"),
                        "kind": "repository",
                        "stars": repo.get("stars"),
                        "star_delta": repo.get("star_delta"),
                        "fingerprint": repo.get("fingerprint"),
                        "is_ai_skill": repo.get("is_ai_skill"),
                        "keywords": repo.get("keywords") or [],
                        "html_url": repo.get("html_url"),
                        "repo_id": repo.get("id"),
                    },
                }
            )
    kw_ids = {q for q, _ in hits}
    for i, q in enumerate(sorted(kw_ids)):
        nodes.append(
            {
                "id": f"kw:{q}",
                "type": "keyword",
                "position": {"x": 40, "y": 40 + i * 48},
                "data": {"label": q, "kind": "keyword"},
            }
        )
    edges = [
        {
            "id": f"hit-{q}-{rid}",
            "source": f"kw:{q}",
            "target": f"repo:{rid}",
            "data": {"rel": "HIT"},
        }
        for q, rid in hits
    ]
    return nodes, edges


def _related_edges(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_fp: dict[str, list[int]] = {}
    for repo in repos:
        fp = repo.get("fingerprint")
        if not fp:
            continue
        by_fp.setdefault(str(fp), []).append(int(repo["id"]))
    edges: list[dict[str, Any]] = []
    for ids in by_fp.values():
        unique = sorted(set(ids))
        for i, src in enumerate(unique):
            for dst in unique[i + 1 :]:
                edges.append(
                    {
                        "id": f"rel-{src}-{dst}",
                        "source": f"repo:{src}",
                        "target": f"repo:{dst}",
                        "data": {"rel": "RELATED_TO"},
                    }
                )
    return edges
