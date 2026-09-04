from __future__ import annotations

import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, ensure_sqlite_columns
from app.main import create_app
from app.models import User
from app.security import hash_password, verify_password


def _client() -> TestClient:
    return TestClient(create_app())


def test_register_then_login_and_duplicate_conflict():
    email = f"qa{uuid4().hex[:8]}@example.com"
    with _client() as c:
        reg = c.post("/api/v1/auth/register", json={"email": email, "password": "password1"})
        assert reg.status_code == 200, reg.text
        assert reg.json()["data"]["access_token"]
        assert reg.json()["data"]["email"] == email
        dup = c.post("/api/v1/auth/register", json={"email": email, "password": "password1"})
        assert dup.status_code == 409
        assert "already registered" in dup.json()["message"]
        bad = c.post("/api/v1/auth/login", json={"email": email, "password": "wrongpass"})
        assert bad.status_code == 401
        login = c.post("/api/v1/auth/login", json={"email": email, "password": "password1"})
        assert login.status_code == 200, login.text
        assert login.json()["data"]["access_token"]


def test_legacy_sqlite_users_schema_can_register(tmp_path):
    dbfile = tmp_path / "legacy.db"
    conn = sqlite3.connect(dbfile)
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
        "password_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO users (id, email, password_hash, created_at) VALUES "
        "('11111111-1111-1111-1111-111111111111', 'pm@example.com', 'legacy-hash', '2020-01-01')"
    )
    conn.commit()
    conn.close()

    eng = create_engine(f"sqlite:///{dbfile}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    ensure_sqlite_columns(eng)
    cols = {row[1] for row in sqlite3.connect(dbfile).execute("pragma table_info(users)")}
    assert "wecom_user_id" in cols
    assert "feishu_user_id" in cols

    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        existing = db.scalar(select(User).where(User.email == "pm@example.com"))
        assert existing is not None
        user = User(email=f"new{uuid4().hex[:8]}@example.com", password_hash=hash_password("password1"))
        db.add(user)
        db.commit()
        db.refresh(user)
        assert verify_password("password1", user.password_hash)
        assert user.id is not None
    finally:
        db.close()
        eng.dispose()
