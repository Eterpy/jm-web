from __future__ import annotations

import re
import zipfile
from pathlib import Path

import img2pdf
from PIL import Image

from backend.app.models.job import JobType
from backend.app.utils.file_utils import ensure_dir, sanitize_filename

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_DIGIT_SPLIT_RE = re.compile(r"\d+|\D+")


def _natural_chunks(value: str) -> tuple[tuple[int, int | str], ...]:
    chunks: list[tuple[int, int | str]] = []
    for chunk in _DIGIT_SPLIT_RE.findall(value):
        if chunk.isdigit():
            chunks.append((0, int(chunk)))
        else:
            chunks.append((1, chunk.lower()))
    return tuple(chunks)


def _segment_key(value: str) -> tuple[int, int | tuple[tuple[int, int | str], ...]]:
    if value.isdigit():
        return (0, int(value))
    return (1, _natural_chunks(value))


def _path_sort_key(path: Path, root: Path):
    rel = path.relative_to(root)
    key = []
    for segment in rel.parts[:-1]:
        key.append(_segment_key(segment))

    stem = Path(rel.parts[-1]).stem
    key.append(_segment_key(stem))
    return tuple(key)


def list_images_sorted(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
            files.append(path)
    files.sort(key=lambda p: _path_sort_key(p, root))
    return files


def merge_tree_to_pdf(source_root: Path, output_pdf: Path, temp_dir: Path) -> Path:
    ensure_dir(temp_dir)
    images = list_images_sorted(source_root)
    if not images:
        raise ValueError(f"No images found in {source_root}")

    converted_paths: list[str] = []
    for index, img_path in enumerate(images, start=1):
        converted = temp_dir / f"{index:06d}.jpg"
        with Image.open(img_path) as image:
            rgb = image.convert("RGB")
            rgb.save(converted, "JPEG", quality=95)
        converted_paths.append(str(converted))

    with output_pdf.open("wb") as stream:
        stream.write(img2pdf.convert(converted_paths))

    return output_pdf


def build_artifact_from_download(
    source_dir: Path,
    artifact_dir: Path,
    temp_dir: Path,
    job_type: JobType,
    base_name: str,
) -> tuple[Path, str]:
    ensure_dir(artifact_dir)
    ensure_dir(temp_dir)

    safe_base = sanitize_filename(base_name)

    if job_type in {JobType.ALBUM, JobType.PHOTO}:
        target = artifact_dir / f"{safe_base}.pdf"
        merge_tree_to_pdf(source_dir, target, temp_dir / "single")
        return target, target.name

    album_dirs = [d for d in source_dir.iterdir() if d.is_dir()]
    album_dirs.sort(key=lambda p: _segment_key(p.name))
    if not album_dirs:
        raise ValueError("No album directories found for multi-album download")

    pdf_paths: list[Path] = []
    for index, album_dir in enumerate(album_dirs, start=1):
        pdf_name = f"{index:03d}_{sanitize_filename(album_dir.name)}.pdf"
        pdf_path = artifact_dir / pdf_name
        merge_tree_to_pdf(album_dir, pdf_path, temp_dir / f"album_{index:03d}")
        pdf_paths.append(pdf_path)

    zip_path = artifact_dir / f"{safe_base}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pdf_path in pdf_paths:
            zf.write(pdf_path, pdf_path.name)

    return zip_path, zip_path.name
