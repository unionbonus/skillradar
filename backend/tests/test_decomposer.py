from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.decomposer.engine import Decomposer
from app.graph.builder import build_graphs, persist_graphs


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample-skill"


def test_decompose_sample_skill():
    db: Session = SessionLocal()
    try:
        engine = Decomposer(db)
        repo, structure = engine.decompose("file://" + str(FIXTURE), local_path=str(FIXTURE))
        assert repo.is_ai_skill is True
        assert repo.fingerprint_type == "claude_skill"
        assert structure["skills"]
        assert structure["skills"][0]["name"] == "web-search"
        graphs = persist_graphs(db, repo, structure)
        assert graphs["module_dependency"]["nodes"]
        built = build_graphs(structure)
        assert any(n["type"] == "skill" for n in built["data_flow"]["nodes"])
    finally:
        db.close()
