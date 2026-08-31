from __future__ import annotations

import os
from pathlib import Path

os.environ["SKILLRADAR_DISABLE_SCHEDULER"] = "1"
os.environ["SKILLRADAR_OFFLINE"] = "1"
os.environ["SECRET_KEY"] = "unit-test-secret-key-please-change"
os.environ["ENCRYPTION_KEY"] = "unit-test-encryption-key"
os.environ["APP_VERSION"] = "0.5.0"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DATABASE_URL"] = "sqlite:////dev/shm/skillradar-test.db"
os.environ["CLONE_DIR"] = str(Path(__file__).resolve().parent / "_clones")

from app.config import reset_settings
from app.db import Base, configure_engine, engine, init_db
import pytest

reset_settings()
configure_engine()
init_db()


@pytest.fixture(autouse=True)
def _reset_db():
    from app.db import engine as eng
    from app.graph.store import reset_graph_store

    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    reset_graph_store()
    yield
    reset_graph_store()
