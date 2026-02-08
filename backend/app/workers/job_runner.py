from __future__ import annotations

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.job import DownloadJob, JobStatus
from backend.app.models.user import User
from backend.app.services.crypto_service import decrypt_text
from backend.app.services.image_pdf_service import build_artifact_from_download
from backend.app.services.jm_service import JmCredential, artifact_base_name, run_download_job
from backend.app.utils.file_utils import ensure_dir

_executor = ThreadPoolExecutor(max_workers=settings.max_parallel_jobs)
_inflight_jobs: set[int] = set()
_lock = Lock()


def enqueue_job(job_id: int) -> None:
    with _lock:
        if job_id in _inflight_jobs:
            return
        _inflight_jobs.add(job_id)

    _executor.submit(_run_job, job_id)


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if job is None:
            return

        user = db.query(User).filter(User.id == job.user_id).first()
        if user is None:
            job.status = JobStatus.FAILED
            job.error_message = "Owner user does not exist"
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.error_message = None
        db.commit()

        payload = json.loads(job.payload_json)

        credential = None
        if user.jm_username and user.jm_password_encrypted:
            credential = JmCredential(
                username=user.jm_username,
                password=decrypt_text(user.jm_password_encrypted),
            )

        job_temp_dir = settings.temp_root / f"job_{job.id}"
        source_dir = job_temp_dir / "source"
        option_file = job_temp_dir / "option.yml"
        artifact_dir = settings.download_root / f"job_{job.id}"
        pdf_temp_dir = job_temp_dir / "pdf_tmp"

        ensure_dir(job_temp_dir)
        ensure_dir(source_dir)
        ensure_dir(artifact_dir)
        ensure_dir(pdf_temp_dir)

        run_download_job(
            job_type=job.job_type,
            payload=payload,
            source_dir=source_dir,
            option_file=option_file,
            credential=credential,
        )

        job.status = JobStatus.MERGING
        db.commit()

        base_name = artifact_base_name(job.job_type, payload, fallback_name=f"job_{job.id}")
        artifact_path, artifact_name = build_artifact_from_download(
            source_dir=source_dir,
            artifact_dir=artifact_dir,
            temp_dir=pdf_temp_dir,
            job_type=job.job_type,
            base_name=base_name,
        )

        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(minutes=settings.link_expire_minutes)

        job.result_file_path = str(artifact_path)
        job.result_file_name = artifact_name
        job.source_dir = str(source_dir)
        job.download_token = secrets.token_urlsafe(24)
        job.merged_at = now
        job.expires_at = expire_at
        job.status = JobStatus.DONE
        db.commit()

    except Exception as exc:  # noqa: BLE001
        failed_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if failed_job is not None:
            failed_job.status = JobStatus.FAILED
            failed_job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
        with _lock:
            _inflight_jobs.discard(job_id)
