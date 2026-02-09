from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.models.job import JobStatus, JobType
from backend.app.models.user import User
from backend.app.schemas.job import (
    CancelJobResponse,
    CleanupJobsResponse,
    DownloadByIdRequest,
    DownloadJobOut,
    DownloadTokenOut,
    JmLoginRequest,
    JmLoginResponse,
    SearchRequest,
    SearchResultItem,
)
from backend.app.services.crypto_service import decrypt_text, encrypt_text
from backend.app.services.job_service import (
    count_user_album_units,
    create_job,
    get_job_by_token,
    get_job_for_user,
    list_jobs_for_user,
    normalize_multi_album_ids,
    payload_album_units,
)
from backend.app.services.job_service import clear_failed_expired_jobs_for_user
from backend.app.services.jm_service import JmCredential, fetch_favorites, fetch_ranking, search_album, verify_login
from backend.app.utils.file_utils import safe_remove_path
from backend.app.workers.job_runner import CANCELLED_MESSAGE, cleanup_job_artifacts, enqueue_job, request_cancel

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_saved_jm_credential(user: User) -> JmCredential | None:
    if not user.jm_username or not user.jm_password_encrypted:
        return None
    return JmCredential(username=user.jm_username, password=decrypt_text(user.jm_password_encrypted))


def _to_job_type(target_type: str) -> JobType:
    mapping = {
        "album": JobType.ALBUM,
        "photo": JobType.PHOTO,
        "multi_album": JobType.MULTI_ALBUM,
    }
    if target_type not in mapping:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_type")
    return mapping[target_type]


def _enforce_user_album_limit(db: Session, user: User, job_type: JobType, payload: dict) -> None:
    request_units = payload_album_units(job_type, payload)
    if request_units <= 0:
        return

    per_job_limit = settings.user_album_limit_per_job
    if per_job_limit > 0 and request_units > per_job_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"单次任务最多允许下载 {per_job_limit} 个本子，你这次请求了 {request_units} 个。",
        )

    inflight_limit = settings.user_album_limit_inflight
    if inflight_limit > 0:
        inflight_units = count_user_album_units(
            db,
            user.id,
            statuses={JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.MERGING},
        )
        if inflight_units + request_units > inflight_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"当前进行中的本子数量将超过上限（上限 {inflight_limit}，当前 {inflight_units}，本次 {request_units}）。",
            )

    window_limit = settings.user_album_limit_window_count
    window_minutes = settings.user_album_limit_window_minutes
    if window_limit > 0 and window_minutes > 0:
        window_units = count_user_album_units(
            db,
            user.id,
            statuses={JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.MERGING, JobStatus.DONE},
            window_minutes=window_minutes,
        )
        if window_units + request_units > window_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"{window_minutes} 分钟内本子下载数量将超过上限"
                    f"（上限 {window_limit}，当前 {window_units}，本次 {request_units}）。"
                ),
            )


@router.post("/jm-login", response_model=JmLoginResponse)
def jm_login(
    payload: JmLoginRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JmLoginResponse:
    credential = JmCredential(username=payload.username, password=payload.password)
    try:
        verify_login(credential)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"JM login failed: {exc}") from exc

    if payload.save_to_user:
        user = db.query(User).filter(User.id == current_user.id).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.jm_username = payload.username
        user.jm_password_encrypted = encrypt_text(payload.password)
        db.commit()

    return JmLoginResponse(ok=True)


@router.post("/search", response_model=list[SearchResultItem])
def search(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
) -> list[SearchResultItem]:
    credential = _get_saved_jm_credential(current_user)
    try:
        return search_album(payload.keyword, payload.page, credential)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Search failed: {exc}") from exc


@router.get("/favorites", response_model=list[SearchResultItem])
def favorites(
    page: int = Query(default=1, ge=1, le=200),
    current_user: User = Depends(get_current_user),
) -> list[SearchResultItem]:
    credential = _get_saved_jm_credential(current_user)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please login JM account first")
    try:
        return fetch_favorites(page, credential)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fetch favorites failed: {exc}") from exc


@router.get("/ranking/week", response_model=list[SearchResultItem])
def ranking_week(
    page: int = Query(default=1, ge=1, le=200),
    current_user: User = Depends(get_current_user),
) -> list[SearchResultItem]:
    credential = _get_saved_jm_credential(current_user)
    try:
        return fetch_ranking(page, credential)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fetch ranking failed: {exc}") from exc


@router.post("/download-by-id", response_model=DownloadJobOut)
def download_by_id(
    payload: DownloadByIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    job_type = _to_job_type(payload.target_type)

    if job_type in {JobType.ALBUM, JobType.PHOTO} and not payload.id_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="id_value is required")

    if job_type == JobType.MULTI_ALBUM:
        if not payload.album_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="album_ids is required")
        normalized_ids = normalize_multi_album_ids(payload.album_ids)
        if not normalized_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="album_ids is empty after normalization")
        body = {"album_ids": normalized_ids}
    else:
        body = {"id_value": payload.id_value}

    _enforce_user_album_limit(db, current_user, job_type, body)
    job = create_job(db, current_user, job_type, body)
    enqueue_job(job.id)
    return DownloadJobOut.model_validate(job)


@router.post("/download-from-search/{album_id}", response_model=DownloadJobOut)
def download_from_search(
    album_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    payload = {"id_value": album_id}
    _enforce_user_album_limit(db, current_user, JobType.ALBUM, payload)
    job = create_job(db, current_user, JobType.ALBUM, payload)
    enqueue_job(job.id)
    return DownloadJobOut.model_validate(job)


@router.get("", response_model=list[DownloadJobOut])
def list_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DownloadJobOut]:
    jobs = list_jobs_for_user(db, current_user)
    return [DownloadJobOut.model_validate(job) for job in jobs]


@router.delete("/clear-failed-expired", response_model=CleanupJobsResponse)
def clear_failed_expired_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CleanupJobsResponse:
    count = clear_failed_expired_jobs_for_user(db, current_user)
    return CleanupJobsResponse(deleted_count=count)


@router.get("/{job_id}", response_model=DownloadJobOut)
def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    job = get_job_for_user(db, current_user, job_id)
    return DownloadJobOut.model_validate(job)


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
def cancel_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CancelJobResponse:
    job = get_job_for_user(db, current_user, job_id)
    if job.status in {JobStatus.DONE, JobStatus.EXPIRED, JobStatus.CLEANED, JobStatus.FAILED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job status is {job.status.value}")

    request_cancel(job.id)
    cleanup_job_artifacts(job.id)

    if job.result_file_path:
        safe_remove_path(Path(job.result_file_path).parent)
    if job.source_dir:
        source_path = Path(job.source_dir)
        safe_remove_path(source_path)
        safe_remove_path(source_path.parent)

    job.status = JobStatus.FAILED
    job.error_message = CANCELLED_MESSAGE
    job.result_file_path = None
    job.result_file_name = None
    job.source_dir = None
    job.download_token = None
    job.merged_at = None
    job.expires_at = None
    db.commit()

    return CancelJobResponse(cancelled=True)


@router.get("/{job_id}/download-link", response_model=DownloadTokenOut)
def get_download_link(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadTokenOut:
    job = get_job_for_user(db, current_user, job_id)
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job status is {job.status.value}")

    expire_at = _ensure_utc(job.expires_at)
    if not job.download_token or not expire_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download link unavailable")

    now = datetime.now(timezone.utc)
    if expire_at <= now:
        job.status = JobStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Download link expired")

    return DownloadTokenOut(
        download_url=f"{settings.api_prefix}/jobs/download/{job.download_token}",
        expires_at=expire_at,
    )


@router.get("/download/{token}")
def download_by_token(token: str, db: Session = Depends(get_db)) -> FileResponse:
    job = get_job_by_token(db, token)
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Download not available")

    expire_at = _ensure_utc(job.expires_at)
    now = datetime.now(timezone.utc)
    if expire_at is None or expire_at <= now:
        job.status = JobStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Download link expired")

    if not job.result_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact missing")

    artifact = Path(job.result_file_path)
    if not artifact.exists() or not artifact.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return FileResponse(path=artifact, filename=job.result_file_name or artifact.name)
