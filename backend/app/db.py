from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("skillradar.db")


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def configure_engine() -> None:
    global engine, SessionLocal
    from sqlalchemy.pool import StaticPool

    settings = get_settings()
    settings.data_dir()
    connect_args = {}
    engine_kwargs: dict = {"future": True, "pool_pre_ping": True}
    url = settings.database_url
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in url or url.rstrip("/") == "sqlite:":
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["pool_pre_ping"] = False
    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
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


def ensure_sqlite_columns(bind=None) -> None:
    """Add mapped columns missing from an existing SQLite file (create_all does not ALTER)."""
    bind = bind if bind is not None else engine
    if bind is None or not str(bind.url).startswith("sqlite"):
        return
    inspector = inspect(bind)
    dialect = bind.dialect
    tables = set(inspector.get_table_names())
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            existing = {col["name"] for col in inspect(conn).get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                type_sql = col.type.compile(dialect=dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {type_sql}'
                logger.info("sqlite migrate %s", ddl)
                conn.execute(text(ddl))


def init_db() -> None:
    from app import models  # noqa: F401
    from app.scanner.keywords import seed_keywords
    from sqlalchemy.exc import OperationalError

    if engine is None:
        configure_engine()
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        if "already exists" not in str(exc):
            raise
    ensure_sqlite_columns()
    db = SessionLocal()
    try:
        seed_keywords(db)
    except Exception as exc:
        logger.warning("keyword seed skipped: %s", exc)
        db.rollback()
    finally:
        db.close()
