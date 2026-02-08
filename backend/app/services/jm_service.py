from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jmcomic
import yaml

from backend.app.core.config import settings
from backend.app.models.job import JobType
from backend.app.schemas.job import SearchResultItem
from backend.app.utils.file_utils import ensure_dir


@dataclass
class JmCredential:
    username: str
    password: str


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _impl_order() -> list[str]:
    order: list[str] = []
    primary = (settings.jm_client_impl or "").strip()
    fallback = (settings.jm_fallback_impl or "").strip()

    if primary:
        order.append(primary)
    if fallback and fallback not in order:
        order.append(fallback)

    if not order:
        order = ["api", "html"]
    return order


def _domains_for_impl(impl: str) -> list[str]:
    if impl == "html":
        return _split_csv(settings.jm_html_domains)
    if impl == "api":
        return _split_csv(settings.jm_api_domains)
    return []


def _meta_data_args() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    proxy_value = (settings.jm_proxy or "").strip()
    if proxy_value and proxy_value.lower() not in {"none", "null"}:
        kwargs["proxies"] = proxy_value

    if settings.jm_timeout_seconds > 0:
        kwargs["timeout"] = settings.jm_timeout_seconds

    return kwargs


def _normalize_album_id(value: str) -> str:
    text = value.strip()
    if text.lower().startswith("jm"):
        return text[2:]
    return text


def _normalize_photo_id(value: str) -> str:
    text = value.strip()
    if text.lower().startswith("p"):
        return text[1:]
    return text


def build_option_file(base_dir: Path, option_file: Path, credential: JmCredential | None, client_impl: str) -> None:
    ensure_dir(base_dir)
    ensure_dir(option_file.parent)

    client_config: dict[str, Any] = {
        "impl": client_impl,
        "retry_times": settings.jm_retry_times,
    }
    domain_list = _domains_for_impl(client_impl)
    if domain_list:
        client_config["domain"] = {client_impl: domain_list}

    postman_meta_data: dict[str, Any] = {}
    proxy_value = (settings.jm_proxy or "").strip()
    if proxy_value and proxy_value.lower() not in {"none", "null"}:
        postman_meta_data["proxies"] = proxy_value
    if settings.jm_timeout_seconds > 0:
        postman_meta_data["timeout"] = settings.jm_timeout_seconds
    if postman_meta_data:
        client_config["postman"] = {"meta_data": postman_meta_data}

    data: dict[str, Any] = {
        "dir_rule": {
            "base_dir": str(base_dir),
            "rule": "Bd_Aid_Pindex",
        },
        "client": client_config,
        "download": {
            "cache": True,
            "image": {
                "decode": True,
            },
        },
    }

    if credential is not None:
        data["plugins"] = {
            "after_init": [
                {
                    "plugin": "login",
                    "kwargs": {
                        "username": credential.username,
                        "password": credential.password,
                    },
                }
            ]
        }

    option_file.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _build_client(credential: JmCredential | None):
    return _build_client_by_impl(settings.jm_client_impl, credential)


def _build_client_by_impl(impl: str, credential: JmCredential | None):
    option = jmcomic.JmOption.default()
    kwargs = _meta_data_args()
    domain_list = _domains_for_impl(impl)
    if domain_list:
        kwargs["domain_list"] = domain_list
    client = option.new_jm_client(impl=impl, **kwargs)
    if credential is not None:
        client.login(credential.username, credential.password)
    return client


def verify_login(credential: JmCredential) -> bool:
    errors: list[str] = []
    for impl in _impl_order():
        try:
            # _build_client_by_impl 内部会调用 client.login(...)
            # login 未抛异常即视为登录成功，避免额外探测请求导致误判。
            _build_client_by_impl(impl, credential)
            return True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{impl}: {exc}")
    raise RuntimeError("; ".join(errors))


def search_album(keyword: str, page: int, credential: JmCredential | None) -> list[SearchResultItem]:
    errors: list[str] = []
    for impl in _impl_order():
        try:
            client = _build_client_by_impl(impl, credential)
            search_page = client.search_site(search_query=keyword, page=page)

            if hasattr(search_page, "iter_id_title"):
                iterator = search_page.iter_id_title()
            else:
                iterator = iter(search_page)

            results: list[SearchResultItem] = []
            for aid, title in iterator:
                results.append(SearchResultItem(album_id=str(aid), title=str(title)))
            return results
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{impl}: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_favorites(page: int, credential: JmCredential) -> list[SearchResultItem]:
    errors: list[str] = []
    for impl in _impl_order():
        try:
            client = _build_client_by_impl(impl, credential)
            favorite_page = client.favorite_folder(page=page)
            if hasattr(favorite_page, "iter_id_title"):
                iterator = favorite_page.iter_id_title()
            else:
                iterator = iter(favorite_page)

            items: list[SearchResultItem] = []
            for aid, title in iterator:
                items.append(SearchResultItem(album_id=str(aid), title=str(title)))
            return items
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{impl}: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_ranking(page: int, credential: JmCredential | None) -> list[SearchResultItem]:
    errors: list[str] = []
    for impl in _impl_order():
        try:
            client = _build_client_by_impl(impl, credential)
            ranking_page = client.week_ranking(page)
            iterator = ranking_page.iter_id_title() if hasattr(ranking_page, "iter_id_title") else iter(ranking_page)
            results: list[SearchResultItem] = []
            for aid, title in iterator:
                results.append(SearchResultItem(album_id=str(aid), title=str(title)))
            return results
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{impl}: {exc}")
    raise RuntimeError("; ".join(errors))


def run_download_job(
    job_type: JobType,
    payload: dict[str, Any],
    source_dir: Path,
    option_file: Path,
    credential: JmCredential | None,
) -> None:
    errors: list[str] = []
    for impl in _impl_order():
        try:
            build_option_file(source_dir, option_file, credential, impl)
            option = jmcomic.create_option_by_file(str(option_file))

            if job_type == JobType.ALBUM:
                album_id = _normalize_album_id(str(payload["id_value"]))
                jmcomic.download_album(album_id, option)
                return

            if job_type == JobType.PHOTO:
                photo_id = _normalize_photo_id(str(payload["id_value"]))
                jmcomic.download_photo(photo_id, option)
                return

            if job_type == JobType.MULTI_ALBUM:
                raw_ids = payload.get("album_ids") or []
                ids = [_normalize_album_id(str(value)) for value in raw_ids]
                jmcomic.download_album(ids, option)
                return

            raise ValueError(f"Unsupported job_type: {job_type}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{impl}: {exc}")

    raise RuntimeError("; ".join(errors))


def artifact_base_name(job_type: JobType, payload: dict[str, Any], fallback_name: str) -> str:
    if job_type == JobType.ALBUM:
        value = payload.get("id_value")
        if value:
            return _normalize_album_id(str(value))

    if job_type == JobType.PHOTO:
        value = payload.get("id_value")
        if value:
            return _normalize_photo_id(str(value))

    if job_type == JobType.MULTI_ALBUM:
        raw_ids = payload.get("album_ids") or []
        ids = [_normalize_album_id(str(item)) for item in raw_ids if str(item).strip()]
        if len(ids) == 1:
            return ids[0]
        if len(ids) > 1:
            return f"{ids[0]}_and_{len(ids)-1}_more"

    return fallback_name
