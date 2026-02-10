from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.job import DownloadJob, JobStatus, JobType
from backend.app.models.user import User, UserRole
from backend.app.utils.file_utils import safe_remove_path

_ALBUM_PATH_RE = re.compile(r"/album/(\d+)", flags=re.IGNORECASE)


def _normalize_album_id(value: str) -> str:
    text = value.strip()
    album_match = _ALBUM_PATH_RE.search(text)
    if album_match:
        return album_match.group(1)
    if text.lower().startswith("jm"):
        return text[2:]
    return text


def payload_album_units(job_type: JobType, payload: dict) -> int:
    if job_type == JobType.ALBUM:
        value = str(payload.get("id_value") or "").strip()
        return 1 if value else 0

    if job_type == JobType.MULTI_ALBUM:
        raw_ids = payload.get("album_ids") or []
        normalized = {_normalize_album_id(str(item)) for item in raw_ids if str(item).strip()}
        return len(normalized)

    return 0


def normalize_multi_album_ids(album_ids: list[str] | None) -> list[str]:
    if not album_ids:
        return []
    # 去重后返回，保证multi_album按唯一本子计数
    seen: set[str] = set()
    result: list[str] = []
    for value in album_ids:
        normalized = _normalize_album_id(str(value))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def count_user_album_units(
    db: Session,
    user_id: int,
    *,
    statuses: set[JobStatus] | None = None,
    window_minutes: int | None = None,
) -> int:
    query = db.query(DownloadJob).filter(DownloadJob.user_id == user_id)
    if statuses:
        query = query.filter(DownloadJob.status.in_(statuses))

    if window_minutes is not None and window_minutes > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        query = query.filter(DownloadJob.created_at >= cutoff)

    total = 0
    for job in query.all():
        try:
            payload = json.loads(job.payload_json)
        except Exception:  # noqa: BLE001
            payload = {}
        total += payload_album_units(job.job_type, payload)
    return total


def create_job(db: Session, user: User, job_type: JobType, payload: dict) -> DownloadJob:
    job = DownloadJob(
        user_id=user.id,
        job_type=job_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_jobs_for_user(db: Session, user: User) -> list[DownloadJob]:
    query = db.query(DownloadJob)
    if user.role != UserRole.ADMIN:
        query = query.filter(DownloadJob.user_id == user.id)
    return query.order_by(DownloadJob.id.desc()).all()


def get_job_for_user(db: Session, user: User, job_id: int) -> DownloadJob:
    query = db.query(DownloadJob).filter(DownloadJob.id == job_id)
    if user.role != UserRole.ADMIN:
        query = query.filter(DownloadJob.user_id == user.id)

    job = query.first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def get_job_by_token(db: Session, token: str) -> DownloadJob:
    job = db.query(DownloadJob).filter(DownloadJob.download_token == token).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download token not found")
    return job


def clear_failed_expired_jobs_for_user(db: Session, user: User) -> int:
    target_statuses = {JobStatus.FAILED, JobStatus.EXPIRED, JobStatus.CLEANED}

    query = db.query(DownloadJob).filter(DownloadJob.status.in_(target_statuses))
    if user.role != UserRole.ADMIN:
        query = query.filter(DownloadJob.user_id == user.id)

    jobs = query.all()
    if not jobs:
        return 0

    for job in jobs:
        if job.result_file_path:
            artifact_dir = Path(job.result_file_path).parent
            safe_remove_path(artifact_dir)
        if job.source_dir:
            source_dir = Path(job.source_dir)
            safe_remove_path(source_dir)
            safe_remove_path(source_dir.parent)
        db.delete(job)

    db.commit()
    return len(jobs)


def expire_and_cleanup_jobs(db: Session) -> None:
    now = datetime.now(timezone.utc)

    just_expired = (
        db.query(DownloadJob)
        .filter(DownloadJob.status == JobStatus.DONE)
        .filter(DownloadJob.expires_at.isnot(None))
        .filter(DownloadJob.expires_at <= now)
        .all()
    )
    for job in just_expired:
        job.status = JobStatus.EXPIRED

    db.commit()

    cleanup_jobs = (
        db.query(DownloadJob)
        .filter(DownloadJob.status == JobStatus.EXPIRED)
        .filter(DownloadJob.expires_at.isnot(None))
        .filter(DownloadJob.expires_at <= now)
        .all()
    )

    for job in cleanup_jobs:
        if job.result_file_path:
            artifact_dir = Path(job.result_file_path).parent
            safe_remove_path(artifact_dir)
        if job.source_dir:
            source_dir = Path(job.source_dir)
            safe_remove_path(source_dir)
            safe_remove_path(source_dir.parent)

        job.status = JobStatus.CLEANED
        job.download_token = None

    db.commit()
