from __future__ import annotations

import shutil
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def sanitize_filename(name: str) -> str:
    blocked = '<>:"/\\|?*'
    output = "".join("_" if ch in blocked else ch for ch in name).strip()
    return output or "download"
