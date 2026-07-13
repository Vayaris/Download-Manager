from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from services.aria2_service import Aria2RpcError


def looks_like_nfo(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(str(value))
    path = unquote(parsed.path or str(value)).lower().rstrip("/")
    return path.rsplit("/", 1)[-1].endswith(".nfo")


def is_missing_aria2_gid_error(exc: Exception) -> bool:
    if isinstance(exc, Aria2RpcError):
        return exc.category == "missing_gid"
    msg = str(exc).lower()
    return "gid" in msg and ("not found" in msg or "no such" in msg or "unknown" in msg)


def is_transient_aria2_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, Aria2RpcError):
        return exc.category not in ("missing_gid", "download_error")
    return not is_missing_aria2_gid_error(exc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def path_is_allowed(path: Path, destination: str, config: dict) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    roots = [destination, config["downloads"].get("default_destination", "")]
    roots.extend(config["downloads"].get("allowed_paths", []))
    for root in roots:
        if not root:
            continue
        try:
            resolved.relative_to(Path(root).resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def aria2_file_path(data: dict) -> Path | None:
    files = data.get("files") or []
    if not files:
        return None
    raw_path = str(files[0].get("path") or "").strip()
    return Path(raw_path) if raw_path else None


def file_matches_size(path: Path, expected_size: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size == expected_size
    except OSError:
        return False
