import logging
import os
from datetime import datetime, timedelta, timezone

import aiosqlite

from config import get_config, save_config
from database import DB_PATH
from services.jellyfin import jellyfin
from services.plex import plex

logger = logging.getLogger(__name__)


class MediaRefreshError(Exception):
    pass


def active_media_provider(cfg: dict) -> str:
    if cfg.get("jellyfin", {}).get("enabled"):
        return "jellyfin"
    if cfg.get("plex", {}).get("enabled"):
        return "plex"
    active = str(cfg.get("media", {}).get("active", "plex")).strip().lower()
    return active if active in ("plex", "jellyfin") else "plex"


def media_defaults(provider: str) -> dict:
    base_url = "http://127.0.0.1:8096" if provider == "jellyfin" else "http://127.0.0.1:32400"
    return {
        "enabled": False,
        "url": base_url,
        "token": "",
        "last_refreshes": {},
        "favorite_keys": [],
        "auto_refresh_enabled": False,
        "auto_refresh_enabled_at": None,
        "auto_refreshes": {},
    }


def media_auto_public_fields(media_cfg: dict) -> dict:
    return {
        "auto_refresh_enabled": bool(media_cfg.get("auto_refresh_enabled", False)),
        "auto_refresh_enabled_at": media_cfg.get("auto_refresh_enabled_at"),
        "auto_refreshes": media_cfg.get("auto_refreshes", {}),
    }


def media_service(provider: str):
    return jellyfin if provider == "jellyfin" else plex


def require_media_config(cfg: dict) -> tuple[str, str, str]:
    provider = active_media_provider(cfg)
    media_cfg = cfg.get(provider, {})
    if not media_cfg.get("enabled"):
        raise MediaRefreshError(f"{provider.title()} integration is disabled")
    url = (media_cfg.get("url") or "").strip()
    token = (media_cfg.get("token") or "").strip()
    if not url or not token:
        raise MediaRefreshError(f"{provider.title()} URL or token is missing")
    return provider, url, token


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        clean = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_media_path(value: str | None) -> str:
    clean = os.path.normpath(str(value or "").strip())
    if clean == ".":
        return ""
    return clean.rstrip("/")


def _path_is_inside(candidate: str, root: str) -> bool:
    candidate_norm = _normalize_media_path(candidate)
    root_norm = _normalize_media_path(root)
    if not candidate_norm or not root_norm:
        return False
    return candidate_norm == root_norm or candidate_norm.startswith(root_norm + "/")


async def media_refresh_suggestions(
    cfg: dict,
    limit: int = 20,
    since: datetime | None = None,
) -> list[dict]:
    provider, url, token = require_media_config(cfg)
    libraries = await media_service(provider).libraries(url, token)
    libraries_with_locations = [
        library for library in libraries
        if library.get("locations") and library.get("key") and library.get("title")
    ]
    if not libraries_with_locations:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    if since and since > cutoff:
        cutoff = since

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT id, name, destination, status, package_name, completed_at
               FROM history
               WHERE status = 'complete'
               ORDER BY completed_at DESC
               LIMIT 100"""
        )
        history_rows = [dict(row) for row in await cursor.fetchall()]

    last_refreshes = cfg.get(provider, {}).get("last_refreshes", {})
    suggestions: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for row in history_rows:
        completed_at = parse_iso_datetime(row.get("completed_at"))
        if not completed_at or completed_at < cutoff:
            continue

        destination = _normalize_media_path(row.get("destination"))
        name = str(row.get("name") or "").strip()
        candidates = [destination]
        if destination and name:
            candidates.insert(0, _normalize_media_path(os.path.join(destination, name)))

        for library in libraries_with_locations:
            library_key = str(library.get("key", "")).strip()
            refreshed_at = parse_iso_datetime(last_refreshes.get(library_key))
            if refreshed_at and refreshed_at >= completed_at:
                continue

            matched_location = ""
            for location in library.get("locations", []):
                if any(_path_is_inside(candidate, location) for candidate in candidates):
                    matched_location = _normalize_media_path(location)
                    break

            if not matched_location:
                continue

            package_name = str(row.get("package_name") or "").strip()
            unique_key = (f"pkg:{package_name}" if package_name else f"history:{row['id']}", library_key)
            if unique_key in seen:
                continue
            seen.add(unique_key)
            suggestions.append({
                "history_id": package_name or row["id"],
                "library_key": library_key,
                "library_title": library.get("title", ""),
                "library_type": library.get("type", ""),
                "download_name": package_name or name or row["id"],
                "destination": destination,
                "completed_at": row.get("completed_at"),
                "matched_location": matched_location,
            })
            break

        if len(suggestions) >= limit:
            break

    return suggestions


async def refresh_library_from_config(
    cfg: dict,
    library_key: str,
    automatic: bool = False,
    suggestion: dict | None = None,
) -> dict:
    provider, url, token = require_media_config(cfg)
    logger.info("%s refresh requested for library key=%s automatic=%s", provider.title(), library_key, automatic)
    await media_service(provider).refresh_library(url, token, library_key)

    refreshed_at = datetime.now(timezone.utc).isoformat()
    media_cfg = cfg.setdefault(provider, media_defaults(provider))
    media_cfg.setdefault("last_refreshes", {})[str(library_key)] = refreshed_at

    if automatic:
        auto_refreshes = media_cfg.setdefault("auto_refreshes", {})
        suggestion = suggestion or {}
        auto_refreshes[str(library_key)] = {
            "refreshed_at": refreshed_at,
            "library_key": str(library_key),
            "library_title": suggestion.get("library_title", ""),
            "library_type": suggestion.get("library_type", ""),
            "download_name": suggestion.get("download_name", ""),
            "matched_location": suggestion.get("matched_location", ""),
        }

    save_config(cfg)
    logger.info("%s refresh completed for library key=%s automatic=%s", provider.title(), library_key, automatic)
    return {
        "status": "refreshed",
        "provider": provider,
        "library_key": str(library_key),
        "refreshed_at": refreshed_at,
    }


async def auto_refresh_recommended_libraries(limit: int = 50) -> dict:
    cfg = get_config()
    provider = active_media_provider(cfg)
    media_cfg = cfg.get(provider, {})
    if not media_cfg.get("enabled") or not media_cfg.get("auto_refresh_enabled", False):
        return {"attempted": False, "provider": provider, "refreshed": [], "errors": []}

    since = parse_iso_datetime(media_cfg.get("auto_refresh_enabled_at"))
    suggestions = await media_refresh_suggestions(cfg, limit=limit, since=since)
    by_library: dict[str, dict] = {}
    for suggestion in suggestions:
        key = str(suggestion.get("library_key") or "").strip()
        if key and key not in by_library:
            by_library[key] = suggestion

    refreshed = []
    errors = []
    for library_key, suggestion in by_library.items():
        try:
            current_cfg = get_config()
            current_provider = active_media_provider(current_cfg)
            current_media_cfg = current_cfg.get(current_provider, {})
            if current_provider != provider or not current_media_cfg.get("auto_refresh_enabled", False):
                break
            result = await refresh_library_from_config(
                current_cfg,
                library_key,
                automatic=True,
                suggestion=suggestion,
            )
            refreshed.append({**suggestion, **result})
        except Exception as exc:
            errors.append({
                "library_key": library_key,
                "library_title": suggestion.get("library_title", ""),
                "error": str(exc)[:200],
            })

    return {
        "attempted": bool(by_library),
        "provider": provider,
        "refreshed": refreshed,
        "errors": errors,
    }
