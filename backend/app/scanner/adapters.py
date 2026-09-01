from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Repository, utcnow
from app.scanner.service import ScannerError, ScannerService


@dataclass
class PluginHit:
    source: str
    identifier: str
    name: str
    html_url: str
    description: str = ""
    stars: int = 0
    downloads: int = 0
    fingerprint_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


SOURCES = ("github", "npm", "pypi", "mcp_registry", "huggingface", "dockerhub")


def _get(client: httpx.Client, url: str, **kwargs) -> dict[str, Any] | list | None:
    try:
        resp = client.get(url, timeout=20.0, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def search_npm(client: httpx.Client, query: str, limit: int) -> list[PluginHit]:
    data = _get(
        client,
        "https://registry.npmjs.org/-/v1/search",
        params={"text": query, "size": min(limit, 20)},
    )
    objects = data.get("objects") if isinstance(data, dict) else None
    if not isinstance(objects, list):
        return []
    hits: list[PluginHit] = []
    for row in objects[:limit]:
        pkg = (row or {}).get("package") if isinstance(row, dict) else None
        if not isinstance(pkg, dict) or not pkg.get("name"):
            continue
        kws = pkg.get("keywords") or []
        fp = "mcp_server" if any("mcp" in str(k).lower() for k in kws) or "mcp" in str(pkg.get("name")).lower() else "npm_package"
        hits.append(
            PluginHit(
                source="npm",
                identifier=str(pkg["name"]),
                name=str(pkg["name"]),
                html_url=str((pkg.get("links") or {}).get("npm") or f"https://www.npmjs.com/package/{pkg['name']}"),
                description=str(pkg.get("description") or ""),
                downloads=int(((row.get("downloads") or {}) if isinstance(row, dict) else {}).get("weekly") or 0),
                fingerprint_type=fp,
                extra={"version": pkg.get("version"), "publisher": (pkg.get("publisher") or {}).get("username")},
            )
        )
    return hits


def search_pypi(client: httpx.Client, query: str, limit: int) -> list[PluginHit]:
    # Warehouse JSON for exact project; fallback wraps the query as a project name plus common mcp prefix.
    names = [query.replace(" ", "-"), f"mcp-server-{query.replace(' ', '-')}"]
    hits: list[PluginHit] = []
    seen: set[str] = set()
    for name in names:
        data = _get(client, f"https://pypi.org/pypi/{name}/json")
        if not isinstance(data, dict) or "info" not in data:
            continue
        info = data["info"]
        ident = str(info.get("name") or name)
        if ident in seen:
            continue
        seen.add(ident)
        fp = "mcp_server" if "mcp" in ident.lower() else "pypi_package"
        hits.append(
            PluginHit(
                source="pypi",
                identifier=ident,
                name=ident,
                html_url=str(info.get("project_url") or f"https://pypi.org/project/{ident}/"),
                description=str(info.get("summary") or ""),
                fingerprint_type=fp,
                extra={"version": info.get("version"), "license": info.get("license")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_mcp_registry(client: httpx.Client, query: str, limit: int) -> list[PluginHit]:
    data = _get(
        client,
        "https://registry.modelcontextprotocol.io/v0/servers",
        params={"search": query, "limit": min(limit, 30)},
    )
    servers = None
    if isinstance(data, dict):
        servers = data.get("servers") or data.get("items") or data.get("data")
    elif isinstance(data, list):
        servers = data
    if not isinstance(servers, list):
        return []
    hits: list[PluginHit] = []
    q = query.lower()
    for row in servers:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("id") or "")
        desc = str(row.get("description") or "")
        if q and q not in name.lower() and q not in desc.lower():
            continue
        if not name:
            continue
        hits.append(
            PluginHit(
                source="mcp_registry",
                identifier=name,
                name=name,
                html_url=str(row.get("repository") or row.get("url") or f"https://github.com/search?q={name}"),
                description=desc,
                fingerprint_type="mcp_server",
                extra={"version": row.get("version")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_huggingface(client: httpx.Client, query: str, limit: int) -> list[PluginHit]:
    data = _get(
        client,
        "https://huggingface.co/api/models",
        params={"search": query, "limit": min(limit, 20)},
    )
    rows = data if isinstance(data, list) else []
    hits: list[PluginHit] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or row.get("modelId") or "")
        if not ident:
            continue
        hits.append(
            PluginHit(
                source="huggingface",
                identifier=ident,
                name=ident,
                html_url=f"https://huggingface.co/{ident}",
                description=str(row.get("pipeline_tag") or "HF model"),
                stars=int(row.get("likes") or 0),
                downloads=int(row.get("downloads") or 0),
                fingerprint_type="hf_model",
            )
        )
    return hits


def search_dockerhub(client: httpx.Client, query: str, limit: int) -> list[PluginHit]:
    data = _get(
        client,
        "https://hub.docker.com/v2/search/repositories/",
        params={"query": query, "page_size": min(limit, 20)},
    )
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    hits: list[PluginHit] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("repo_name") or row.get("name") or "")
        if not ident:
            continue
        hits.append(
            PluginHit(
                source="dockerhub",
                identifier=ident,
                name=ident,
                html_url=f"https://hub.docker.com/r/{ident}",
                description=str(row.get("short_description") or ""),
                stars=int(row.get("star_count") or 0),
                fingerprint_type="container",
            )
        )
    return hits


def search_channel(source: str, query: str, limit: int, client: httpx.Client) -> list[PluginHit]:
    src = (source or "github").lower()
    if src == "npm":
        return search_npm(client, query, limit)
    if src == "pypi":
        return search_pypi(client, query, limit)
    if src == "mcp_registry":
        return search_mcp_registry(client, query, limit)
    if src in {"huggingface", "hf"}:
        return search_huggingface(client, query, limit)
    if src in {"dockerhub", "docker"}:
        return search_dockerhub(client, query, limit)
    raise ScannerError(f"unsupported source: {source}")


def upsert_hit(db: Session, hit: PluginHit) -> Repository:
    full_name = hit.identifier if hit.source == "github" else f"{hit.source}:{hit.identifier}"
    full_name = full_name[:255]
    existing = db.scalar(select(Repository).where(Repository.full_name == full_name))
    popularity = {"stars": hit.stars, "downloads": hit.downloads}
    fields = {
        "full_name": full_name,
        "html_url": hit.html_url,
        "description": hit.description,
        "stargazers_count": hit.stars,
        "source": hit.source,
        "identifier": hit.identifier[:512],
        "author": str((hit.extra or {}).get("publisher") or "")[:255] or None,
        "license": str((hit.extra or {}).get("license") or "")[:100] or None,
        "version": str((hit.extra or {}).get("version") or "")[:50] or None,
        "popularity": popularity,
        "tags": [hit.source, hit.fingerprint_type or ""],
        "fingerprint_type": hit.fingerprint_type,
        "is_ai_skill": hit.fingerprint_type in {"claude_skill", "mcp_server", "langchain_tool"},
        "last_scanned_at": utcnow(),
        "extra_metadata": hit.extra or {},
    }
    if existing:
        prev = int(existing.stargazers_count or 0)
        fields["star_delta"] = int(hit.stars) - prev
        for k, v in fields.items():
            setattr(existing, k, v)
        return existing
    repo = Repository(**fields)
    db.add(repo)
    db.flush()
    return repo


def scan_source(db: Session, source: str, query: str, limit: int, client: httpx.Client) -> list[Repository]:
    src = (source or "github").lower()
    if src == "github":
        svc = ScannerService(db, client=client)
        repos = svc.scan_keyword(query, limit=limit, search_type="keyword")
        for repo in repos:
            repo.source = "github"
            repo.identifier = repo.full_name
        db.commit()
        return repos
    hits = search_channel(src, query, limit, client)
    repos = [upsert_hit(db, h) for h in hits]
    db.commit()
    for repo in repos:
        db.refresh(repo)
    return repos
