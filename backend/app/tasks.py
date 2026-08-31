"""Celery entry (optional). v0.1 also runs APScheduler inside the API process."""

from celery import Celery

from app.config import get_settings

settings = get_settings()
broker = settings.redis_url or "redis://localhost:6379/0"
celery_app = Celery("skillradar", broker=broker, backend=broker)
celery_app.conf.beat_schedule = {
    "scan_github_keywords": {"task": "app.tasks.scan_github_keywords", "schedule": 6 * 3600},
    "generate_subscription_briefs": {"task": "app.tasks.generate_subscription_briefs", "schedule": 3600},
}


@celery_app.task(name="app.tasks.scan_github_keywords")
def scan_github_keywords() -> str:
    from app.scheduler.beat import job_scan_keywords

    job_scan_keywords()
    return "ok"


@celery_app.task(name="app.tasks.generate_subscription_briefs", max_retries=3)
def generate_subscription_briefs() -> str:
    from app.scheduler.beat import job_subscription_briefs

    job_subscription_briefs()
    return "ok"
