from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class JobType(str, enum.Enum):
    ALBUM = "album"
    PHOTO = "photo"
    MULTI_ALBUM = "multi_album"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    MERGING = "merging"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"
    CLEANED = "cleaned"


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED, nullable=False)

    result_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_token: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)

    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
