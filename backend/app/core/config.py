from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("backend/.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "JM Web"
    api_prefix: str = "/api/v1"

    secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    access_token_expire_minutes: int = 24 * 60

    database_url: str = "sqlite:///./backend/storage/app.db"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    download_root: Path = Path("./backend/storage/downloads")
    temp_root: Path = Path("./backend/storage/tmp")
    link_expire_minutes: int = 60

    max_parallel_jobs: int = 2

    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    jm_client_impl: str = "api"
    jm_fallback_impl: str = "html"
    jm_retry_times: int = 5
    jm_proxy: str = "system"
    jm_timeout_seconds: int = 15
    jm_html_domains: str | None = None
    jm_api_domains: str | None = None

    user_album_limit_inflight: int = 20
    user_album_limit_window_count: int = 100
    user_album_limit_window_minutes: int = 60
    user_album_limit_per_job: int = 20

    credential_key: str | None = None


settings = Settings()
