from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.decomposer.parsers import ClaudeSkillParser, LangChainParser, MCPServerParser, extract_imports
from app.models import RepoAnalysis, Repository, Skill, utcnow
from app.scanner.fingerprints import detect_fingerprint, list_files


class DecomposeError(Exception):
    pass


PARSERS = {
    "claude_skill": ClaudeSkillParser(),
    "mcp_server": MCPServerParser(),
    "langchain_tool": LangChainParser(),
}


class Decomposer:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def decompose(self, repo_url: str, local_path: str | None = None) -> tuple[Repository, dict]:
        workdir, cleanup = self._prepare_workdir(repo_url, local_path)
        try:
            files = list_files(workdir)
            package_text = _package_blob(workdir)
            ftype = detect_fingerprint(files, package_text)
            parser = PARSERS.get(ftype or "claude_skill", ClaudeSkillParser())
            skills = parser.parse(workdir, files)
            deps = extract_imports(workdir, files)
            repo = self._upsert_repo(repo_url, ftype)
            self._replace_skills(repo, skills)
            structure = {
                "repository_id": repo.id,
                "full_name": repo.full_name,
                "fingerprint_type": ftype,
                "skills": skills,
                "dependencies": deps,
                "file_count": len(files),
                "files": files[:200],
            }
            analysis = self.db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
            if analysis is None:
                analysis = RepoAnalysis(repository_id=repo.id)
                self.db.add(analysis)
            analysis.structure = structure
            self.db.commit()
            self.db.refresh(repo)
            return repo, structure
        finally:
            if cleanup and workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)

    def _prepare_workdir(self, repo_url: str, local_path: str | None) -> tuple[Path, bool]:
        if local_path:
            path = Path(local_path).resolve()
            if not path.is_dir():
                raise DecomposeError(f"local_path not found: {path}")
            return path, False
        if repo_url.startswith("file://"):
            path = Path(urlparse(repo_url).path)
            if not path.is_dir():
                raise DecomposeError(f"file path not found: {path}")
            return path, False
        return self._shallow_clone(repo_url), True

    def _shallow_clone(self, repo_url: str) -> Path:
        parsed = urlparse(repo_url)
        if parsed.scheme not in {"http", "https"}:
            raise DecomposeError("only http(s) clone is allowed")
        host = parsed.hostname or ""
        if host not in {"github.com", "gitlab.com", "gitee.com"}:
            raise DecomposeError(f"clone host not allowed: {host}")
        dest = Path(self.settings.clone_dir).resolve() / "tmp" / _safe_name(repo_url)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                ["git", "clone", "--depth=1", "--single-branch", repo_url, str(dest)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DecomposeError("git clone timed out") from exc
        except OSError as exc:
            raise DecomposeError(f"git clone failed to start: {exc}") from exc
        if proc.returncode != 0:
            raise DecomposeError(f"git clone failed: {proc.stderr[-400:]}")
        return dest

    def _upsert_repo(self, repo_url: str, ftype: str | None) -> Repository:
        full_name = _full_name_from_url(repo_url)
        existing = self.db.scalar(select(Repository).where(Repository.full_name == full_name))
        if existing is None:
            existing = Repository(full_name=full_name, html_url=repo_url)
            self.db.add(existing)
            self.db.flush()
        existing.html_url = repo_url if repo_url.startswith("http") else existing.html_url
        existing.fingerprint_type = ftype
        existing.is_ai_skill = ftype is not None
        existing.last_scanned_at = utcnow()
        existing.source = existing.source or "github"
        existing.identifier = existing.identifier or full_name
        return existing

    def _replace_skills(self, repo: Repository, skills: list[dict]) -> None:
        for old in list(repo.skills):
            self.db.delete(old)
        self.db.flush()
        for item in skills:
            self.db.add(
                Skill(
                    repository_id=repo.id,
                    name=str(item.get("name") or "skill")[:255],
                    description=item.get("description"),
                    entry_file=item.get("entry_file"),
                    config=item.get("config") or {},
                    prompt_templates=item.get("prompt_templates") or [],
                    tools=item.get("tools") or [],
                    examples=item.get("examples") or [],
                )
            )


def _safe_name(url: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in url)[-80:]


def _full_name_from_url(url: str) -> str:
    if url.startswith("file://") or url.startswith("/"):
        return Path(url.replace("file://", "")).name
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    return parsed.path.strip("/") or url


def _package_blob(root: Path) -> str:
    chunks: list[str] = []
    for name in ("package.json", "pyproject.toml", "requirements.txt", "mcp.json"):
        path = root / name
        if path.is_file():
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[:20_000])
            except OSError as exc:
                raise DecomposeError(f"read {name} failed: {exc}") from exc
    return "\n".join(chunks)
