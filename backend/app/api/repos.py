from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.motivation import analyze_motivation, render_prd
from app.db import SessionLocal, get_db
from app.decomposer.engine import DecomposeError, Decomposer
from app.deps import current_user
from app.graph.builder import persist_graphs
from app.models import RepoAnalysis, Repository, ScanTask, User
from app.schemas import DecomposeIn

router = APIRouter(prefix="/api/v1", tags=["repos"])


def envelope(data, message: str = "success") -> dict:
    return {"code": 0, "data": data, "message": message}


@router.get("/repos")
def list_repos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    stmt = select(Repository).order_by(Repository.stargazers_count.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all())
    return envelope({"items": [_repo_json(r) for r in rows], "page": page, "page_size": page_size})


@router.post("/repos/decompose")
def decompose(
    body: DecomposeIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    task = ScanTask(user_id=user.id, kind="decompose", query=body.repo_url, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(_run_decompose, task.id, body.repo_url, body.local_path)
    return envelope({"task_id": str(task.id)})


@router.get("/repos/{repo_id}")
def repo_detail(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return envelope(_repo_json(repo))


@router.get("/repos/{repo_id}/structure")
def repo_structure(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo_id))
    if analysis is None:
        raise HTTPException(status_code=404, detail="structure not found; decompose first")
    return envelope(analysis.structure)


@router.get("/repos/{repo_id}/graph")
def repo_graph(
    repo_id: int,
    type: str = Query("module_dependency"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    from app.graph.store import get_graph_store

    store_graph = get_graph_store().query_repo(repo_id, type)
    if store_graph and store_graph.get("nodes"):
        return envelope({**store_graph, "source": get_graph_store().backend})
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo_id))
    if analysis is None or not analysis.graph:
        raise HTTPException(status_code=404, detail="graph not found; decompose first")
    graph = analysis.graph.get(type) or analysis.graph.get("module_dependency")
    if not graph:
        raise HTTPException(status_code=400, detail=f"unknown graph type: {type}")
    return envelope({**graph, "source": "postgres"})


@router.post("/repos/{repo_id}/motivation")
def run_motivation(
    repo_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    analysis = _require_analysis(db, repo_id)
    motivation = analyze_motivation(analysis.structure or {})
    analysis.motivation = motivation
    analysis.prd_markdown = render_prd(analysis.structure or {}, motivation)
    db.commit()
    from app.storage.objects import store_prd

    store_prd(repo_id, analysis.prd_markdown)
    return envelope({"task_id": f"sync-{repo_id}", "motivation": motivation})


@router.get("/repos/{repo_id}/motivation")
def get_motivation(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    analysis = _require_analysis(db, repo_id)
    if not analysis.motivation:
        raise HTTPException(status_code=404, detail="motivation not generated")
    return envelope(analysis.motivation)


@router.get("/repos/{repo_id}/prd")
def get_prd(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    analysis = _require_analysis(db, repo_id)
    if not analysis.prd_markdown:
        raise HTTPException(status_code=404, detail="prd not generated")
    return envelope({"markdown": analysis.prd_markdown})


@router.put("/repos/{repo_id}/prd")
def put_prd(repo_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    analysis = _require_analysis(db, repo_id)
    md = body.get("markdown")
    if not isinstance(md, str) or not md.strip():
        raise HTTPException(status_code=400, detail="markdown required")
    analysis.prd_markdown = md
    db.commit()
    from app.storage.objects import store_prd

    store_prd(repo_id, md)
    return envelope({"markdown": analysis.prd_markdown})


def _require_analysis(db: Session, repo_id: int) -> RepoAnalysis:
    if db.get(Repository, repo_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo_id))
    if analysis is None:
        raise HTTPException(status_code=404, detail="decompose first")
    return analysis


def _repo_json(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "github_id": repo.github_id,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": repo.description,
        "stargazers_count": repo.stargazers_count,
        "forks_count": repo.forks_count,
        "language": repo.language,
        "topics": repo.topics or [],
        "is_ai_skill": repo.is_ai_skill,
        "fingerprint_type": repo.fingerprint_type,
        "last_scanned_at": repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
        "source_keywords": repo.source_keywords or [],
        "star_delta": repo.star_delta or 0,
        "source": getattr(repo, "source", None) or "github",
        "identifier": getattr(repo, "identifier", None) or repo.full_name,
        "author": getattr(repo, "author", None),
        "license": getattr(repo, "license", None),
        "version": getattr(repo, "version", None),
        "popularity": getattr(repo, "popularity", None) or {},
        "tags": getattr(repo, "tags", None) or [],
    }


def _run_decompose(task_id: UUID, repo_url: str, local_path: str | None) -> None:
    db = SessionLocal()
    try:
        task = db.get(ScanTask, task_id)
        if task is None:
            return
        task.status = "running"
        db.commit()
        engine = Decomposer(db)
        repo, structure = engine.decompose(repo_url, local_path=local_path)
        persist_graphs(db, repo, structure)
        motivation = analyze_motivation(structure)
        analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
        if analysis is not None:
            analysis.motivation = motivation
            analysis.prd_markdown = render_prd(structure, motivation)
            db.commit()
            from app.storage.objects import store_prd

            store_prd(repo.id, analysis.prd_markdown)
        from app.analysis.deep_dive import analyze_deep_dive
        from app.analysis.highlights import mine_highlights
        from app.analysis.market import analyze_market
        from app.analysis.store import upsert_analysis
        from app.search.index import extra_from_structure, index_repository

        deep = analyze_deep_dive(structure)
        highs = mine_highlights(structure, motivation)
        market = analyze_market(structure, _repo_json(repo))
        upsert_analysis(db, repo.id, "deep_dive", deep)
        upsert_analysis(db, repo.id, "highlights", highs)
        upsert_analysis(db, repo.id, "market_research", market)
        upsert_analysis(db, repo.id, "motivation", motivation)
        index_repository(repo, extra_from_structure(structure))
        from app.scanner.service import mark_task

        mark_task(db, task, "success", result={"repo_id": repo.id, "fingerprint_type": repo.fingerprint_type})
    except DecomposeError as exc:
        from app.scanner.service import mark_task

        task = db.get(ScanTask, task_id)
        if task is not None:
            mark_task(db, task, "failed", error=str(exc))
    except Exception as exc:
        from app.scanner.service import mark_task

        task = db.get(ScanTask, task_id)
        if task is not None:
            mark_task(db, task, "failed", error=f"unexpected: {exc}")
    finally:
        db.close()


def _analysis_payload(db: Session, repo_id: int, analysis_type: str) -> dict:
    from app.analysis.store import get_analysis

    row = get_analysis(db, repo_id, analysis_type)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{analysis_type} not generated")
    return envelope(row.content_json)


@router.post("/repos/{repo_id}/deep-dive")
@router.post("/plugins/{repo_id}/deep-dive")
def run_deep_dive(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    from app.analysis.deep_dive import analyze_deep_dive
    from app.analysis.store import upsert_analysis

    analysis = _require_analysis(db, repo_id)
    content = analyze_deep_dive(analysis.structure or {})
    upsert_analysis(db, repo_id, "deep_dive", content)
    return envelope(content)


@router.get("/repos/{repo_id}/deep-dive")
@router.get("/plugins/{repo_id}/deep-dive")
def get_deep_dive(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _analysis_payload(db, repo_id, "deep_dive")


@router.post("/repos/{repo_id}/market-research")
@router.post("/plugins/{repo_id}/market-research")
def run_market(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    from app.analysis.market import analyze_market
    from app.analysis.store import upsert_analysis

    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo_id))
    structure = (analysis.structure if analysis else {}) or {"full_name": repo.full_name, "fingerprint_type": repo.fingerprint_type}
    content = analyze_market(structure, _repo_json(repo))
    upsert_analysis(db, repo_id, "market_research", content)
    return envelope(content)


@router.get("/repos/{repo_id}/market-research")
@router.get("/plugins/{repo_id}/market-research")
def get_market(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _analysis_payload(db, repo_id, "market_research")


@router.get("/plugins")
def list_plugins(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return list_repos(page=page, page_size=page_size, db=db, user=user)


@router.post("/plugins/decompose")
def decompose_plugin(
    body: DecomposeIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return decompose(body=body, background=background, db=db, user=user)


@router.get("/plugins/{repo_id}")
def plugin_detail(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return repo_detail(repo_id=repo_id, db=db, user=user)


@router.get("/plugins/{repo_id}/structure")
def plugin_structure(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return repo_structure(repo_id=repo_id, db=db, user=user)


@router.get("/plugins/{repo_id}/graph")
def plugin_graph(
    repo_id: int,
    type: str = Query("module_dependency"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return repo_graph(repo_id=repo_id, type=type, db=db, user=user)


@router.post("/plugins/{repo_id}/motivation")
def plugin_run_motivation(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return run_motivation(repo_id=repo_id, db=db, user=user)


@router.get("/plugins/{repo_id}/motivation")
def plugin_get_motivation(repo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return get_motivation(repo_id=repo_id, db=db, user=user)
