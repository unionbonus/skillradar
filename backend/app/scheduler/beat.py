from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Repository, ScanTask

logger = logging.getLogger("skillradar.beat")
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job_scan_keywords, "interval", hours=1, id="scan_github_keywords", replace_existing=True)
    sched.add_job(job_update_stats, "cron", hour=2, minute=0, id="update_repo_stats", replace_existing=True)
    sched.add_job(job_subscription_briefs, "interval", hours=1, id="generate_subscription_briefs", replace_existing=True)
    sched.add_job(job_cleanup, "cron", hour=3, minute=0, id="cleanup_temp_files", replace_existing=True)
    sched.start()
    _scheduler = sched
    logger.info("in-process scheduler started")


def job_scan_keywords() -> None:
    from app.api.scan import _run_scan
    from app.scanner.keywords import due_keywords

    db = SessionLocal()
    try:
        due = due_keywords(db)
        logger.info("scan_github_keywords due=%s", len(due))
        for kw in due:
            task = ScanTask(kind="cron", query=kw.query, status="queued")
            db.add(task)
            db.commit()
            db.refresh(task)
            _run_scan(task.id, kw.query, kw.search_type, kw.limit, True, str(kw.id))
    except Exception as exc:
        logger.exception("scan keywords failed: %s", exc)
    finally:
        db.close()


def job_update_stats() -> None:
    db = SessionLocal()
    try:
        n = len(list(db.scalars(select(Repository)).all()))
        logger.info("update_repo_stats watched %s repos", n)
    finally:
        db.close()


def job_subscription_briefs() -> None:
    from app.api.subscriptions import generate_due_briefs

    db = SessionLocal()
    try:
        sent = generate_due_briefs(db)
        logger.info("subscription briefs sent=%s", sent)
    except Exception as exc:
        logger.exception("subscription briefs failed: %s", exc)
    finally:
        db.close()


def job_cleanup() -> None:
    import shutil
    from pathlib import Path

    from app.config import get_settings

    tmp = Path(get_settings().clone_dir) / "tmp"
    if tmp.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
