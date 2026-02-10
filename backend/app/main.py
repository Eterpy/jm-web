from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import auth, jobs, users
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.session import SessionLocal, engine
from backend.app.models import DownloadJob, User  # noqa: F401
from backend.app.services.user_service import ensure_default_admin
from backend.app.utils.file_utils import ensure_dir
from backend.app.workers.job_runner import recover_unfinished_jobs
from backend.app.workers.scheduler import start_cleanup_scheduler


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _apply_app_timezone() -> None:
    os.environ["TZ"] = settings.app_timezone
    if hasattr(time, "tzset"):
        time.tzset()


@app.on_event("startup")
def on_startup() -> None:
    _apply_app_timezone()
    ensure_dir(settings.download_root)
    ensure_dir(settings.temp_root)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_default_admin(db, settings.default_admin_username, settings.default_admin_password)
    finally:
        db.close()

    recover_unfinished_jobs()
    start_cleanup_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
