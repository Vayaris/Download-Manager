import logging
import os
from datetime import datetime, timedelta, timezone

from config import get_config, update_config
from database import db_session
from services.diagnostics import record_event_nowait
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
        "auto_refresh_last_result": None,
        "path_mappings": [],
    }


def media_auto_public_fields(media_cfg: dict) -> dict:
    return {
        "auto_refresh_enabled": bool(media_cfg.get("auto_refresh_enabled", False)),
        "auto_refresh_enabled_at": media_cfg.get("auto_refresh_enabled_at"),
        "auto_refreshes": media_cfg.get("auto_refreshes", {}),
        "auto_refresh_last_result": media_cfg.get("auto_refresh_last_result"),
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


def _normalized_path_mappings(media_cfg: dict) -> list[dict[str, str]]:
    mappings = []
    for item in media_cfg.get("path_mappings", []):
        if not isinstance(item, dict):
            continue
        download_prefix = _normalize_media_path(item.get("download_prefix"))
        jellyfin_prefix = _normalize_media_path(item.get("jellyfin_prefix"))
        if download_prefix and jellyfin_prefix:
            mappings.append({
                "download_prefix": download_prefix,
                "jellyfin_prefix": jellyfin_prefix,
            })
    return sorted(mappings, key=lambda item: len(item["download_prefix"]), reverse=True)


def _media_candidates(candidate: str, mappings: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return the original path plus its most specific Docker path translation."""
    normalized = _normalize_media_path(candidate)
    if not normalized:
        return []
    results = [(normalized, "")]
    for mapping in mappings:
        source = mapping["download_prefix"]
        if not _path_is_inside(normalized, source):
            continue
        relative = os.path.relpath(normalized, source)
        translated = mapping["jellyfin_prefix"]
        if relative != ".":
            translated = os.path.join(translated, relative)
        results.insert(0, (_normalize_media_path(translated), source))
        break
    return results


async def media_refresh_analysis(
    cfg: dict,
    limit: int = 20,
    since: datetime | None = None,
) -> dict:
    provider, url, token = require_media_config(cfg)
    libraries = await media_service(provider).libraries(url, token)
    libraries_with_locations = [
        library for library in libraries
        if library.get("locations") and library.get("key") and library.get("title")
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    if since and since > cutoff:
        cutoff = since

    async with db_session(row_factory=True) as db:
        cursor = await db.execute(
            """SELECT id, name, destination, status, package_name, completed_at
               FROM history
               WHERE status = 'complete'
               ORDER BY completed_at DESC
               LIMIT 100"""
        )
        history_rows = [dict(row) for row in await cursor.fetchall()]

    last_refreshes = cfg.get(provider, {}).get("last_refreshes", {})
    mappings = _normalized_path_mappings(cfg.get(provider, {})) if provider == "jellyfin" else []
    suggestions: list[dict] = []
    unmatched: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seen_unmatched: set[str] = set()

    for row in history_rows:
        completed_at = parse_iso_datetime(row.get("completed_at"))
        if not completed_at or completed_at < cutoff:
            continue

        destination = _normalize_media_path(row.get("destination"))
        name = str(row.get("name") or "").strip()
        candidates = [destination]
        if destination and name:
            candidates.insert(0, _normalize_media_path(os.path.join(destination, name)))

        matched = False
        for library in libraries_with_locations:
            library_key = str(library.get("key", "")).strip()
            matched_location = ""
            mapped_from = ""
            matched_candidate = ""
            for location in library.get("locations", []):
                for candidate in candidates:
                    for media_candidate, source_prefix in _media_candidates(candidate, mappings):
                        if _path_is_inside(media_candidate, location):
                            matched_location = _normalize_media_path(location)
                            mapped_from = source_prefix
                            matched_candidate = media_candidate
                            break
                    if matched_location:
                        break
                if matched_location:
                    break

            if not matched_location:
                continue

            matched = True
            refreshed_at = parse_iso_datetime(last_refreshes.get(library_key))
            if refreshed_at and refreshed_at >= completed_at:
                break

            package_name = str(row.get("package_name") or "").strip()
            unique_key = (f"pkg:{package_name}" if package_name else f"history:{row['id']}", library_key)
            if unique_key in seen:
                break
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
                "matched_candidate": matched_candidate,
                "mapped_from": mapped_from,
            })
            break

        unmatched_key = str(row.get("package_name") or row.get("id") or "")
        if not matched and unmatched_key and unmatched_key not in seen_unmatched:
            seen_unmatched.add(unmatched_key)
            unmatched.append({
                "history_id": unmatched_key,
                "download_name": str(row.get("package_name") or name or row.get("id") or ""),
                "destination": destination,
                "completed_at": row.get("completed_at"),
            })

        if len(suggestions) >= limit:
            break

    return {"suggestions": suggestions, "unmatched": unmatched[:limit]}


async def media_refresh_suggestions(
    cfg: dict,
    limit: int = 20,
    since: datetime | None = None,
) -> list[dict]:
    analysis = await media_refresh_analysis(cfg, limit=limit, since=since)
    return analysis["suggestions"]


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
    suggestion = suggestion or {}

    def record_refresh(current):
        media_cfg = current.setdefault(provider, media_defaults(provider))
        media_cfg.setdefault("last_refreshes", {})[str(library_key)] = refreshed_at
        if automatic:
            auto_refreshes = media_cfg.setdefault("auto_refreshes", {})
            auto_refreshes[str(library_key)] = {
                "refreshed_at": refreshed_at,
                "library_key": str(library_key),
                "library_title": suggestion.get("library_title", ""),
                "library_type": suggestion.get("library_type", ""),
                "download_name": suggestion.get("download_name", ""),
                "matched_location": suggestion.get("matched_location", ""),
            }

    update_config(record_refresh)
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
    analysis = await media_refresh_analysis(cfg, limit=limit, since=since)
    suggestions = analysis["suggestions"]
    unmatched = analysis["unmatched"]
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
            record_event_nowait(
                "media_refresh", "automatic_refresh_failed", exc,
                context={"provider": provider, "library_key": library_key},
            )
            errors.append({
                "library_key": library_key,
                "library_title": suggestion.get("library_title", ""),
                "error": str(exc)[:200],
            })

    completed_at = datetime.now(timezone.utc).isoformat()
    status = (
        "partial" if refreshed and (errors or unmatched)
        else "refreshed" if refreshed
        else "error" if errors
        else "unmatched" if unmatched
        else "idle"
    )
    last_result = {
        "status": status,
        "completed_at": completed_at,
        "refreshed_libraries": [item.get("library_title") or item.get("library_key", "") for item in refreshed],
        "unmatched_destinations": list(dict.fromkeys(item.get("destination", "") for item in unmatched if item.get("destination")))[:10],
        "errors": [item.get("error", "") for item in errors][:5],
    }

    def record_result(current):
        current.setdefault(provider, media_defaults(provider))["auto_refresh_last_result"] = last_result

    update_config(record_result)
    if unmatched:
        record_event_nowait(
            "media_refresh", "unmatched_path",
            f"No {provider.title()} library matches the completed download destination",
            severity="warning",
            context={"provider": provider, "destinations": last_result["unmatched_destinations"]},
        )

    return {
        "attempted": bool(by_library),
        "provider": provider,
        "refreshed": refreshed,
        "errors": errors,
        "unmatched": unmatched,
        "status": status,
    }
