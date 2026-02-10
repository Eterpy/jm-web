from __future__ import annotations

import ctypes
import json
import secrets
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock, get_ident

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.job import DownloadJob, JobStatus
from backend.app.models.user import User
from backend.app.services.crypto_service import decrypt_text
from backend.app.services.image_pdf_service import build_artifact_from_download
from backend.app.services.jm_service import JmCredential, artifact_base_name, run_download_job
from backend.app.utils.file_utils import ensure_dir, safe_remove_path

_executor = ThreadPoolExecutor(max_workers=settings.max_parallel_jobs)
_inflight_jobs: set[int] = set()
_futures: dict[int, Future] = {}
_thread_ids: dict[int, int] = {}
_cancel_requested: set[int] = set()
_lock = Lock()

CANCELLED_MESSAGE = "任务已由用户中止"


class JobCancelledError(Exception):
    pass


def cleanup_job_artifacts(job_id: int) -> None:
    safe_remove_path(settings.temp_root / f"job_{job_id}")
    safe_remove_path(settings.download_root / f"job_{job_id}")


def _is_cancel_requested(job_id: int) -> bool:
    with _lock:
        return job_id in _cancel_requested


def _raise_async_exception(thread_id: int, exc_type: type[BaseException]) -> bool:
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(  # type: ignore[attr-defined]
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_type),
    )
    if result == 0:
        return False
    if result > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(  # type: ignore[attr-defined]
            ctypes.c_ulong(thread_id),
            ctypes.py_object(None),
        )
        return False
    return True


def request_cancel(job_id: int) -> bool:
    with _lock:
        future = _futures.get(job_id)
        thread_id = _thread_ids.get(job_id)
        # 仅对真正存在中的任务设置取消标记，避免“孤立取消标记”污染后续复用的任务ID
        if future is None and thread_id is None:
            return False
        _cancel_requested.add(job_id)

    if future is not None and future.cancel():
        return True

    if thread_id is not None:
        return _raise_async_exception(thread_id, JobCancelledError)

    return False


def _finalize_job_tracking(job_id: int) -> None:
    with _lock:
        _inflight_jobs.discard(job_id)
        _futures.pop(job_id, None)
        _thread_ids.pop(job_id, None)
        _cancel_requested.discard(job_id)


def _job_marked_cancelled_in_db(db, job_id: int) -> bool:
    db.expire_all()
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if job is None:
        return False
    return job.status == JobStatus.FAILED and (job.error_message or "").startswith(CANCELLED_MESSAGE)


def _ensure_not_cancelled(job_id: int, db=None) -> None:
    if _is_cancel_requested(job_id):
        raise JobCancelledError(CANCELLED_MESSAGE)
    if db is not None and _job_marked_cancelled_in_db(db, job_id):
        raise JobCancelledError(CANCELLED_MESSAGE)


def recover_unfinished_jobs() -> None:
    """
    Recover persisted jobs after backend restart:
    - mark interrupted running/merging jobs as failed
    - re-enqueue queued jobs
    """
    db = SessionLocal()
    queued_ids: list[int] = []
    try:
        interrupted_jobs = (
            db.query(DownloadJob)
            .filter(DownloadJob.status.in_([JobStatus.RUNNING, JobStatus.MERGING]))
            .all()
        )
        for job in interrupted_jobs:
            job.status = JobStatus.FAILED
            if not job.error_message:
                job.error_message = "任务在服务重启后中断，已标记为失败，请重新创建任务。"

        queued_jobs = db.query(DownloadJob).filter(DownloadJob.status == JobStatus.QUEUED).all()
        queued_ids = [job.id for job in queued_jobs]
        db.commit()
    finally:
        db.close()

    for job_id in queued_ids:
        enqueue_job(job_id)


def enqueue_job(job_id: int) -> None:
    with _lock:
        if job_id in _inflight_jobs:
            return
        _inflight_jobs.add(job_id)

    future = _executor.submit(_run_job, job_id)
    with _lock:
        _futures[job_id] = future
    future.add_done_callback(lambda _done, jid=job_id: _finalize_job_tracking(jid))


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    job_temp_dir = settings.temp_root / f"job_{job_id}"
    source_dir = job_temp_dir / "source"
    option_file = job_temp_dir / "option.yml"
    artifact_dir = settings.download_root / f"job_{job_id}"
    pdf_temp_dir = job_temp_dir / "pdf_tmp"
    try:
        with _lock:
            _thread_ids[job_id] = get_ident()

        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if job is None:
            return
        if job.status == JobStatus.FAILED and (job.error_message or "").startswith(CANCELLED_MESSAGE):
            return

        user = db.query(User).filter(User.id == job.user_id).first()
        if user is None:
            job.status = JobStatus.FAILED
            job.error_message = "Owner user does not exist"
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.error_message = None
        job.source_dir = str(source_dir)
        db.commit()
        _ensure_not_cancelled(job_id, db)

        payload = json.loads(job.payload_json)

        credential = None
        if user.jm_username and user.jm_password_encrypted:
            credential = JmCredential(
                username=user.jm_username,
                password=decrypt_text(user.jm_password_encrypted),
            )

        ensure_dir(job_temp_dir)
        ensure_dir(source_dir)
        ensure_dir(artifact_dir)
        ensure_dir(pdf_temp_dir)
        _ensure_not_cancelled(job_id, db)

        run_download_job(
            job_type=job.job_type,
            payload=payload,
            source_dir=source_dir,
            option_file=option_file,
            credential=credential,
        )
        _ensure_not_cancelled(job_id, db)

        job.status = JobStatus.MERGING
        db.commit()
        _ensure_not_cancelled(job_id, db)

        base_name = artifact_base_name(job.job_type, payload, fallback_name=f"job_{job.id}")
        artifact_path, artifact_name = build_artifact_from_download(
            source_dir=source_dir,
            artifact_dir=artifact_dir,
            temp_dir=pdf_temp_dir,
            job_type=job.job_type,
            base_name=base_name,
        )
        _ensure_not_cancelled(job_id, db)

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

    except JobCancelledError:
        failed_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if failed_job is not None:
            failed_job.status = JobStatus.FAILED
            failed_job.error_message = CANCELLED_MESSAGE
            failed_job.result_file_path = None
            failed_job.result_file_name = None
            failed_job.download_token = None
            failed_job.merged_at = None
            failed_job.expires_at = None
            failed_job.source_dir = None
            db.commit()
        cleanup_job_artifacts(job_id)
    except Exception as exc:  # noqa: BLE001
        failed_job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if failed_job is not None:
            failed_job.status = JobStatus.FAILED
            failed_job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
