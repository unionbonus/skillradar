from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.store import get_graph_store
from app.models import RepoAnalysis, Repository


def build_graphs(structure: dict[str, Any]) -> dict[str, dict[str, list]]:
    skills = structure.get("skills") or []
    deps = structure.get("dependencies") or {}
    repo_id = str(structure.get("repository_id") or "repo")
    repo_name = structure.get("full_name") or "repository"

    nodes = [
        {"id": f"repo:{repo_id}", "type": "repository", "data": {"label": repo_name, "kind": "repository"}}
    ]
    edges: list[dict[str, Any]] = []
    for i, skill in enumerate(skills):
        sid = f"skill:{i}:{skill.get('name')}"
        nodes.append({"id": sid, "type": "skill", "data": {"label": skill.get("name"), "kind": "skill", **skill}})
        edges.append({"id": f"e-repo-{i}", "source": f"repo:{repo_id}", "target": sid, "data": {"rel": "CONTAINS"}})
        for j, tool in enumerate(skill.get("tools") or []):
            tid = f"tool:{i}:{j}:{tool.get('name')}"
            nodes.append({"id": tid, "type": "tool", "data": {"label": tool.get("name"), "kind": "tool", **tool}})
            edges.append({"id": f"e-tool-{i}-{j}", "source": sid, "target": tid, "data": {"rel": "CALLS"}})
        for j, prompt in enumerate(skill.get("prompt_templates") or []):
            pid = f"prompt:{i}:{j}"
            nodes.append({"id": pid, "type": "prompt", "data": {"label": prompt, "kind": "prompt"}})
            edges.append({"id": f"e-prompt-{i}-{j}", "source": sid, "target": pid, "data": {"rel": "USES"}})

    for name in deps.get("internal") or []:
        mid = f"mod:{name}"
        nodes.append({"id": mid, "type": "module", "data": {"label": name, "kind": "module"}})
        if skills:
            edges.append({"id": f"e-int-{name}", "source": f"skill:0:{skills[0].get('name')}", "target": mid, "data": {"rel": "IMPORTS"}})
    for name in (deps.get("external") or [])[:20]:
        eid = f"ext:{name}"
        nodes.append({"id": eid, "type": "external", "data": {"label": name, "kind": "external"}})
        edges.append({"id": f"e-ext-{name}", "source": f"repo:{repo_id}", "target": eid, "data": {"rel": "DEPENDS_ON"}})

    module_nodes = [n for n in nodes if n["type"] in {"module", "skill", "repository"}]
    module_edges = [e for e in edges if e["data"]["rel"] in {"CONTAINS", "IMPORTS", "DEPENDS_ON"}]
    call_nodes = [n for n in nodes if n["type"] in {"skill", "tool", "external"}]
    call_edges = [e for e in edges if e["data"]["rel"] in {"CALLS"}]
    flow_edges = edges
    return {
        "module_dependency": {"nodes": module_nodes, "edges": module_edges},
        "call_chain": {"nodes": call_nodes, "edges": call_edges},
        "data_flow": {"nodes": nodes, "edges": flow_edges},
        "layered": {"nodes": nodes, "edges": edges},
        "ecosystem": {"nodes": nodes, "edges": edges},
    }


def persist_graphs(db: Session, repo: Repository, structure: dict[str, Any]) -> dict[str, Any]:
    graphs = build_graphs(structure)
    analysis = db.scalar(select(RepoAnalysis).where(RepoAnalysis.repository_id == repo.id))
    if analysis is None:
        analysis = RepoAnalysis(repository_id=repo.id, structure=structure)
        db.add(analysis)
    analysis.graph = graphs
    analysis.structure = structure
    db.commit()
    try:
        store = get_graph_store()
        store.upsert_structure(repo, graphs)
        store.link_related()
    except Exception as exc:
        import logging

        logging.getLogger("skillradar.graph").warning("graph persist skipped: %s", exc)
    return graphs
