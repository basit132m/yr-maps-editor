"""Short-lived on-disk storage for uploads between the two request steps.

Tokens are random hex, so one user cannot reach another's upload by
guessing, and every lookup re-validates the token shape before it is used
to build a path.
"""

from __future__ import annotations

import re
import secrets
import time

from .config import UPLOAD_DIR, UPLOAD_TTL_SECONDS

TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


class StorageError(Exception):
    pass


def _ensure_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def store(data: bytes, filename: str) -> str:
    _ensure_dir()
    sweep()
    token = secrets.token_hex(16)
    (UPLOAD_DIR / f"{token}.map").write_bytes(data)
    (UPLOAD_DIR / f"{token}.name").write_text(filename[:200], encoding="utf-8")
    return token


def load(token: str) -> tuple[bytes, str]:
    if not TOKEN_RE.match(token or ""):
        raise StorageError("That upload link is not valid. Please upload the map again.")
    payload = UPLOAD_DIR / f"{token}.map"
    if not payload.exists():
        raise StorageError(
            "Your upload has expired. Uploads are deleted after 30 minutes — "
            "please upload the map again."
        )
    name_file = UPLOAD_DIR / f"{token}.name"
    original = name_file.read_text(encoding="utf-8") if name_file.exists() else "map.map"
    return payload.read_bytes(), original


def discard(token: str) -> None:
    if not TOKEN_RE.match(token or ""):
        return
    for suffix in (".map", ".name"):
        (UPLOAD_DIR / f"{token}{suffix}").unlink(missing_ok=True)


def sweep() -> int:
    """Delete uploads older than the TTL. Returns how many files went."""
    if not UPLOAD_DIR.exists():
        return 0
    cutoff = time.time() - UPLOAD_TTL_SECONDS
    removed = 0
    for path in UPLOAD_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed
