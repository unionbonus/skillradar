from __future__ import annotations

import os
from pathlib import Path

os.environ["SKILLRADAR_DISABLE_SCHEDULER"] = "1"
os.environ["SECRET_KEY"] = "unit-test-secret-key-please-change"
os.environ["ENCRYPTION_KEY"] = "unit-test-encryption-key"
os.environ["APP_VERSION"] = "0.5.0"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(__file__).resolve().parent / "_test.db")
os.environ["CLONE_DIR"] = str(Path(__file__).resolve().parent / "_clones")
os.environ["OBJECT_DIR"] = str(Path(__file__).resolve().parent / "_objects")
os.environ["VECTOR_STORE_PATH"] = str(Path(__file__).resolve().parent / "_vectors.json")

from app.config import reset_settings
from app.db import Base, configure_engine, engine, init_db
from app.graph.store import reset_graph_store
from app.search.vectors import reset_vector_store
from app.storage.objects import reset_object_store
import pytest

reset_settings()
configure_engine()
init_db()


@pytest.fixture(autouse=True)
def _reset_db():
    from app.db import engine as eng

    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    reset_graph_store()
    reset_vector_store()
    reset_object_store()
    yield
    reset_graph_store()
    reset_vector_store()
    reset_object_store()
