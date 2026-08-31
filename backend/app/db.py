from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def configure_engine() -> None:
    global engine, SessionLocal
    settings = get_settings()
    settings.data_dir()
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in settings.database_url or settings.database_url.rstrip("/") == "sqlite://":
            kwargs["poolclass"] = StaticPool
            kwargs["pool_pre_ping"] = False
    engine = create_engine(settings.database_url, **kwargs)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


configure_engine()


def get_db() -> Session:
    if SessionLocal is None:
        configure_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_sqlite() -> None:
    """Add v0.5 columns on existing SQLite files (create_all does not ALTER)."""
    if engine is None:
        return
    if not str(engine.url).startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        tables = {r[0] for r in rows}
        if "subscriptions" not in tables:
            return
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(subscriptions)")).fetchall()}
        if "llm_config_id" not in cols:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN llm_config_id CHAR(32)"))
        if "channel_config_id" not in cols:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN channel_config_id CHAR(32)"))


def init_db() -> None:
    from app import models  # noqa: F401
    from app.scanner.keywords import seed_keywords

    if engine is None:
        configure_engine()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise
    try:
        migrate_sqlite()
    except Exception as exc:
        import logging

        logging.getLogger("skillradar").warning("sqlite migrate skipped: %s", exc)
    db = SessionLocal()
    try:
        seed_keywords(db)
    except Exception as exc:
        import logging

        logging.getLogger("skillradar").warning("keyword seed skipped: %s", exc)
        db.rollback()
    finally:
        db.close()
