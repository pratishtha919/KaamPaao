"""File-upload helpers for provider documents.

Files live under ``<instance>/uploads/providers/<user_id>/<kind>_<uuid>.<ext>``.
The serving route (``/uploads/providers/<doc_id>``) authorizes per-doc before
calling ``send_from_directory`` — these helpers only handle on-disk I/O and
path safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


def _ext_of(filename: str) -> str | None:
    if "." not in filename:
        return None
    return filename.rsplit(".", 1)[1].lower()


def save_document(
    instance_path: str | Path,
    user_id: int,
    kind: str,
    file_storage: FileStorage,
) -> dict[str, Any]:
    """Save an uploaded file. Returns metadata dict for the DB upsert.

    Raises ValueError on invalid extension / empty upload.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided.")

    safe_original = secure_filename(file_storage.filename) or "upload"
    ext = _ext_of(safe_original)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type.")

    instance = Path(instance_path)
    user_dir = instance / "uploads" / "providers" / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{kind}_{uuid4().hex}.{ext}"
    abs_path = user_dir / filename
    file_storage.save(abs_path)
    size_bytes = abs_path.stat().st_size

    relative_path = str(abs_path.relative_to(instance))
    return {
        "file_path": relative_path,
        "mime_type": MIME_BY_EXT[ext],
        "original_name": safe_original,
        "size_bytes": size_bytes,
    }


def delete_document_file(instance_path: str | Path, relative_path: str) -> None:
    """Best-effort: delete the file at <instance>/<relative_path>. Silent if missing."""
    try:
        path = absolute_path(instance_path, relative_path)
        path.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def absolute_path(instance_path: str | Path, relative_path: str) -> Path:
    """Resolve <instance>/<relative_path>, guarding against path traversal."""
    instance = Path(instance_path).resolve()
    upload_root = (instance / "uploads").resolve()
    candidate = (instance / relative_path).resolve()
    if not candidate.is_relative_to(upload_root):
        raise ValueError("Path escapes upload root.")
    return candidate
