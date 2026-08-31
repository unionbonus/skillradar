from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Repository, ScanTask, utcnow
from app.scanner.fingerprints import detect_fingerprint


class ScannerError(Exception):
    pass


class TokenRotator:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self._i = 0

    def header(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "SkillRadar/0.3"}
        if not self.tokens:
            return headers
        token = self.tokens[self._i % len(self.tokens)]
        self._i += 1
        headers["Authorization"] = f"Bearer {token}"
        return headers


def parse_gh_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class ScannerService:
    def __init__(self, db: Session, client: httpx.Client | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.rotator = TokenRotator(self.settings.token_list())
        self.client = client

    def scan_keyword(self, keyword: str, limit: int = 50, search_type: str = "keyword") -> list[Repository]:
        q = self._build_query(keyword, search_type)
        items = self._github_search(q, limit)
        repos: list[Repository] = []
        for item in items:
            try:
                repos.append(self._upsert_repo(item))
            except (KeyError, TypeError, ValueError) as exc:
                raise ScannerError(f"malformed GitHub item: {exc}") from exc
        self.db.commit()
        for repo in repos:
            self.db.refresh(repo)
        return repos

    def detect_and_mark(self, repo: Repository, file_tree: list[str], package_text: str = "") -> str | None:
        ftype = detect_fingerprint(file_tree, package_text)
        repo.fingerprint_type = ftype
        repo.is_ai_skill = ftype is not None
        repo.last_scanned_at = utcnow()
        self.db.add(repo)
        self.db.commit()
        return ftype

    def _build_query(self, keyword: str, search_type: str) -> str:
        kw = keyword.strip()
        if not kw:
            raise ScannerError("query required")
        if search_type == "topic":
            return f"topic:{kw}"
        if search_type == "author":
            return f"user:{kw}"
        return f"{kw} SKILL.md OR mcp.json OR claude"

    def _github_search(self, q: str, limit: int) -> list[dict[str, Any]]:
        if self.client is None:
            raise ScannerError("http client not configured")
        try:
            resp = self.client.get(
                "https://api.github.com/search/repositories",
                params={"q": q, "per_page": min(limit, 50), "sort": "stars", "order": "desc"},
                headers=self.rotator.header(),
                timeout=30.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as exc:
            raise ScannerError(f"GitHub search failed: {exc}") from exc
        except ValueError as exc:
            raise ScannerError(f"GitHub response is not JSON: {exc}") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ScannerError("GitHub search missing items")
        return items[:limit]

    def _upsert_repo(self, item: dict[str, Any]) -> Repository:
        full_name = str(item["full_name"])
        existing = self.db.scalar(select(Repository).where(Repository.full_name == full_name))
        fields = {
            "github_id": item.get("id"),
            "full_name": full_name,
            "html_url": item.get("html_url") or f"https://github.com/{full_name}",
            "description": item.get("description"),
            "stargazers_count": int(item.get("stargazers_count") or 0),
            "forks_count": int(item.get("forks_count") or 0),
            "language": item.get("language"),
            "topics": item.get("topics") or [],
            "repo_created_at": parse_gh_time(item.get("created_at")),
            "repo_updated_at": parse_gh_time(item.get("updated_at") or item.get("pushed_at")),
            "last_scanned_at": utcnow(),
        }
        if existing:
            prev = int(existing.stargazers_count or 0)
            fields["star_delta"] = int(fields["stargazers_count"]) - prev
            for k, v in fields.items():
                setattr(existing, k, v)
            return existing
        repo = Repository(**fields)
        repo.star_delta = 0
        self.db.add(repo)
        self.db.flush()
        return repo


def mark_task(
    db: Session,
    task: ScanTask,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    task.status = status
    if result is not None:
        task.result = result
    if error is not None:
        task.error_message = error
    db.add(task)
    db.commit()
