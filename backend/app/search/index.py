from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import RepoAnalysis, Repository
from app.search.vectors import get_vector_store


def document_text(repo: Repository, extra: str = "") -> str:
    parts = [
        getattr(repo, "source", None) or "github",
        repo.full_name or "",
        getattr(repo, "identifier", None) or "",
        repo.description or "",
        " ".join(repo.topics or []),
        " ".join(getattr(repo, "tags", None) or []),
        " ".join(repo.source_keywords or []),
        repo.fingerprint_type or "",
        extra or "",
    ]
    return " ".join(str(p) for p in parts if p).strip()


def extra_from_structure(structure: dict[str, Any] | None) -> str:
    if not structure:
        return ""
    bits: list[str] = []
    for skill in structure.get("skills") or []:
        if isinstance(skill, dict):
            bits.append(str(skill.get("name") or ""))
            bits.append(str(skill.get("description") or ""))
        else:
            bits.append(str(skill))
    deps = structure.get("dependencies") or {}
    if isinstance(deps, dict):
        bits.extend(str(x) for x in (deps.get("internal") or [])[:30])
        bits.extend(str(x) for x in (deps.get("external") or [])[:30])
    elif isinstance(deps, list):
        bits.extend(str(x) for x in deps[:40])
    return " ".join(bits)


def index_repository(repo: Repository, extra: str = "") -> None:
    text = document_text(repo, extra)
    if not text:
        return
    get_vector_store().upsert(
        int(repo.id),
        text,
        payload={
            "kind": "plugin",
            "full_name": repo.full_name,
            "fingerprint_type": repo.fingerprint_type,
            "html_url": repo.html_url,
            "source": getattr(repo, "source", None) or "github",
        },
    )


def index_repositories(repos: Iterable[Repository], extra: str = "") -> None:
    for repo in repos:
        index_repository(repo, extra)


def index_report(report_id: str, title: str, body: str, extra: dict[str, Any] | None = None) -> None:
    text = f"{title}\n{body}"[:12000]
    payload = {"kind": "report", "title": title, **(extra or {})}
    get_vector_store().upsert(report_id, text, payload=payload)


def ensure_indexed(db: Session) -> None:
    store = get_vector_store()
    if store.count() > 0:
        return
    rows = list(db.scalars(select(Repository)).all())
    for repo in rows:
        analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
        extra = extra_from_structure(analysis.structure if analysis else None)
        if analysis and analysis.prd_markdown:
            extra = f"{extra} {analysis.prd_markdown[:1500]}"
        index_repository(repo, extra)


def search_repositories(db: Session, query: str, limit: int = 10) -> dict[str, Any]:
    q = (query or "").strip()
    store = get_vector_store()
    ensure_indexed(db)
    hits = store.search(q, limit=max(limit, 1) * 3) if q else []
    plugin_scores: dict[int, float] = {}
    payloads: dict[int, dict[str, Any]] = {}
    reports: list[dict[str, Any]] = []
    for hit in hits:
        payload = hit.get("payload") if isinstance(hit.get("payload"), dict) else {}
        kind = payload.get("kind") or "plugin"
        if kind == "report":
            reports.append(
                {
                    "id": str(hit.get("id")),
                    "title": payload.get("title") or "",
                    "score": hit.get("score"),
                    "snippet": str(payload.get("text") or "")[:240],
                }
            )
            continue
        try:
            pid = int(hit["id"])
        except (TypeError, ValueError, KeyError):
            continue
        plugin_scores[pid] = float(hit.get("score") or 0)
        payloads[pid] = payload
    if q:
        needle = q.lower()
        lex = list(
            db.scalars(
                select(Repository).where(
                    or_(
                        func.lower(Repository.full_name).contains(needle),
                        func.lower(Repository.description).contains(needle),
                    )
                )
            ).all()
        )
        for repo in lex:
            plugin_scores[int(repo.id)] = max(plugin_scores.get(int(repo.id), 0.0), 0.58)
    ranked = sorted(plugin_scores.items(), key=lambda kv: kv[1], reverse=True)[: max(limit, 1)]
    items: list[dict[str, Any]] = []
    for pid, score in ranked:
        repo = db.get(Repository, pid)
        if repo is None:
            continue
        items.append(
            {
                "id": repo.id,
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "description": repo.description,
                "stargazers_count": repo.stargazers_count,
                "fingerprint_type": repo.fingerprint_type,
                "is_ai_skill": repo.is_ai_skill,
                "source": getattr(repo, "source", None) or "github",
                "score": round(score, 4),
                "snippet": str((payloads.get(pid) or {}).get("text") or repo.description or "")[:240],
            }
        )
    return {
        "query": q,
        "backend": store.backend,
        "items": items,
        "reports": reports[:limit],
    }
