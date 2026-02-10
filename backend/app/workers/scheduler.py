from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.services.job_service import expire_and_cleanup_jobs

_scheduler: BackgroundScheduler | None = None


def _cleanup_tick() -> None:
    db = SessionLocal()
    try:
        expire_and_cleanup_jobs(db)
    finally:
        db.close()


def start_cleanup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone=settings.app_timezone)
    _scheduler.add_job(_cleanup_tick, trigger="interval", minutes=1, id="cleanup-expired-jobs", replace_existing=True)
    _scheduler.start()
