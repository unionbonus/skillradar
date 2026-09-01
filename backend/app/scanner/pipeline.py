from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from app.graph.store import get_graph_store
from app.models import Repository


def infer_fingerprint(repo: Repository) -> str | None:
    if repo.fingerprint_type:
        return repo.fingerprint_type
    blob = " ".join(
        [
            repo.full_name or "",
            repo.description or "",
            " ".join(repo.topics or []),
        ]
    ).lower()
    if "mcp" in blob or "modelcontextprotocol" in blob:
        return "mcp_server"
    if "langchain" in blob or "langgraph" in blob:
        return "langchain_tool"
    if "skill" in blob or "claude" in blob:
        return "claude_skill"
    return None


def attach_keyword(repo: Repository, query: str) -> None:
    cur = list(repo.source_keywords or [])
    if query not in cur:
        cur.append(query)
        repo.source_keywords = cur[-20:]
        flag_modified(repo, "source_keywords")


def sync_scan_to_graph(repos: list[Repository], query: str, search_type: str) -> dict:
    store = get_graph_store()
    for repo in repos:
        fp = infer_fingerprint(repo)
        if fp and not repo.fingerprint_type:
            repo.fingerprint_type = fp
            repo.is_ai_skill = True
        attach_keyword(repo, query)
        store.upsert_radar_repo(repo)
        store.link_keyword(query, search_type, repo)
    store.link_related()
    return store.status()
