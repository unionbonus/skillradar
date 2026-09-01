from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def configure_engine() -> None:
    global engine, SessionLocal
    settings = get_settings()
    settings.data_dir()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )
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
    db = SessionLocal()
    try:
        seed_keywords(db)
    except Exception as exc:
        import logging

        logging.getLogger("skillradar").warning("keyword seed skipped: %s", exc)
        db.rollback()
    finally:
        db.close()
