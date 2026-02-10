from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.job import JobStatus, JobType


class DownloadByIdRequest(BaseModel):
    target_type: Literal["album", "photo", "multi_album"]
    id_value: str | None = None
    album_ids: list[str] | None = None


class SearchRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=256)
    page: int = Field(default=1, ge=1, le=200)


class SearchResultItem(BaseModel):
    album_id: str
    title: str


class DownloadJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_type: JobType
    status: JobStatus
    payload_json: str
    result_file_name: str | None = None
    expires_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("expires_at", "created_at", "updated_at", mode="before")
    @classmethod
    def ensure_utc_timezone(cls, value):
        if value is None:
            return value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value


class DownloadTokenOut(BaseModel):
    download_url: str
    expires_at: datetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def ensure_utc_timezone(cls, value):
        if value is None:
            return value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value


class JmLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    save_to_user: bool = True


class JmLoginResponse(BaseModel):
    ok: bool


class CleanupJobsResponse(BaseModel):
    deleted_count: int


class CancelJobResponse(BaseModel):
    cancelled: bool


class DeleteJobResponse(BaseModel):
    deleted: bool
