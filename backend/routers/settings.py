import ipaddress
import logging
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from urllib.parse import urlparse

from models import SettingsUpdate, StoragePathRequest, PlexSettingsRequest, MediaSettingsRequest, SignalCheckRequest, SignalDeployRequest, SignalRegisterRequest, SignalVerifyRequest, SignalResetRequest
from auth import get_current_user, get_password_hash
from config import get_config, save_config
from database import DB_PATH
from services.alldebrid import alldebrid
from services.jellyfin import jellyfin
from services.plex import plex
from services.webhook import send_webhook

router = APIRouter()
logger = logging.getLogger(__name__)

REPO = "Vayaris/Download-Manager"
INSTALL_DIR = Path("/opt/download-manager")
# Find the git repo: could be /opt/download-manager or the dev repo
_runtime_root = Path(__file__).parent.parent.parent
GIT_DIR = _runtime_root if (_runtime_root / ".git").exists() else INSTALL_DIR


def _is_git_dirty(path: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(path),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return bool(result.stdout.strip())


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _plex_public_config(cfg: dict, include_status: bool = False) -> dict:
    plex_cfg = cfg.get("plex", {})
    token = plex_cfg.get("token", "")
    data = {
        "enabled": bool(plex_cfg.get("enabled", False)),
        "url": plex_cfg.get("url", "http://127.0.0.1:32400"),
        "token_configured": bool(token),
        "last_refreshes": plex_cfg.get("last_refreshes", {}),
        "favorite_keys": plex_cfg.get("favorite_keys", []),
    }
    if include_status:
        data["configured"] = bool(token and plex_cfg.get("url"))
    return data


def _active_media_provider(cfg: dict) -> str:
    if cfg.get("jellyfin", {}).get("enabled"):
        return "jellyfin"
    if cfg.get("plex", {}).get("enabled"):
        return "plex"
    active = str(cfg.get("media", {}).get("active", "plex")).strip().lower()
    return active if active in ("plex", "jellyfin") else "plex"


def _media_defaults(provider: str) -> dict:
    if provider == "jellyfin":
        return {
            "enabled": False,
            "url": "http://127.0.0.1:8096",
            "token": "",
            "last_refreshes": {},
            "favorite_keys": [],
        }
    return {
        "enabled": False,
        "url": "http://127.0.0.1:32400",
        "token": "",
        "last_refreshes": {},
        "favorite_keys": [],
    }


def _media_service(provider: str):
    return jellyfin if provider == "jellyfin" else plex


def _validate_media_url(url: str, provider: str = "media") -> str:
    clean = (url or "").strip().rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail=f"{provider.title()} URL must use http or https")
    return clean


def _media_public_config(cfg: dict, include_status: bool = False) -> dict:
    provider = _active_media_provider(cfg)
    media_cfg = cfg.get(provider, {})
    token = media_cfg.get("token", "")
    data = {
        "provider": provider,
        "enabled": bool(media_cfg.get("enabled", False)),
        "url": media_cfg.get("url", _media_defaults(provider)["url"]),
        "token_configured": bool(token),
        "last_refreshes": media_cfg.get("last_refreshes", {}),
        "favorite_keys": media_cfg.get("favorite_keys", []),
        "providers": {
            "plex": _plex_public_config(cfg, include_status=False),
            "jellyfin": {
                "enabled": bool(cfg.get("jellyfin", {}).get("enabled", False)),
                "url": cfg.get("jellyfin", {}).get("url", "http://127.0.0.1:8096"),
                "token_configured": bool(cfg.get("jellyfin", {}).get("token", "")),
                "last_refreshes": cfg.get("jellyfin", {}).get("last_refreshes", {}),
                "favorite_keys": cfg.get("jellyfin", {}).get("favorite_keys", []),
            },
        },
    }
    if include_status:
        data["configured"] = bool(token and media_cfg.get("url"))
    return data


def _require_media_config(cfg: dict) -> tuple[str, str, str]:
    provider = _active_media_provider(cfg)
    media_cfg = cfg.get(provider, {})
    if not media_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail=f"{provider.title()} integration is disabled")
    url = (media_cfg.get("url") or "").strip()
    token = (media_cfg.get("token") or "").strip()
    if not url or not token:
        raise HTTPException(status_code=400, detail=f"{provider.title()} URL or token is missing")
    return provider, url, token


def _require_plex_config(cfg: dict) -> tuple[str, str]:
    plex_cfg = cfg.get("plex", {})
    if not plex_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="Plex integration is disabled")
    url = (plex_cfg.get("url") or "").strip()
    token = (plex_cfg.get("token") or "").strip()
    if not url or not token:
        raise HTTPException(status_code=400, detail="Plex URL or token is missing")
    return url, token


def _validate_plex_url(url: str) -> str:
    return _validate_media_url(url, "Plex")


def _normalize_plex_favorite_keys(keys: list[str] | None) -> list[str]:
    if keys is None:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for key in keys:
        clean = str(key).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _parse_iso_datetime(value: str | None) -> datetime | None:
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


async def _media_refresh_suggestions(cfg: dict, limit: int = 20) -> list[dict]:
    provider, url, token = _require_media_config(cfg)
    libraries = await _media_service(provider).libraries(url, token)
    libraries_with_locations = [
        library for library in libraries
        if library.get("locations") and library.get("key") and library.get("title")
    ]
    if not libraries_with_locations:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT id, name, destination, status, completed_at
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
        completed_at = _parse_iso_datetime(row.get("completed_at"))
        if not completed_at or completed_at < cutoff:
            continue

        destination = _normalize_media_path(row.get("destination"))
        name = str(row.get("name") or "").strip()
        candidates = [destination]
        if destination and name:
            candidates.insert(0, _normalize_media_path(os.path.join(destination, name)))

        for library in libraries_with_locations:
            library_key = str(library.get("key", "")).strip()
            refreshed_at = _parse_iso_datetime(last_refreshes.get(library_key))
            if refreshed_at and refreshed_at >= completed_at:
                continue

            matched_location = ""
            for location in library.get("locations", []):
                if any(_path_is_inside(candidate, location) for candidate in candidates):
                    matched_location = _normalize_media_path(location)
                    break

            if not matched_location:
                continue

            unique_key = (str(row["id"]), library_key)
            if unique_key in seen:
                continue
            seen.add(unique_key)
            suggestions.append({
                "history_id": row["id"],
                "library_key": library_key,
                "library_title": library.get("title", ""),
                "library_type": library.get("type", ""),
                "download_name": name or row["id"],
                "destination": destination,
                "completed_at": row.get("completed_at"),
                "matched_location": matched_location,
            })
            break

        if len(suggestions) >= limit:
            break

    return suggestions


async def _plex_refresh_suggestions(cfg: dict, limit: int = 20) -> list[dict]:
    scoped = dict(cfg)
    scoped["plex"] = {**cfg.get("plex", {}), "enabled": True}
    scoped["jellyfin"] = {**cfg.get("jellyfin", {}), "enabled": False}
    scoped["media"] = {"active": "plex"}
    return await _media_refresh_suggestions(scoped, limit=limit)


@router.get("/")
async def get_settings(_=Depends(get_current_user)):
    cfg = get_config()
    wh = cfg.get("webhooks", {})
    ad_key = cfg["alldebrid"]["api_key"]
    return {
        "alldebrid_enabled": cfg["alldebrid"]["enabled"],
        "alldebrid_api_key": "",
        "alldebrid_api_key_configured": bool(ad_key),
        "simultaneous_downloads": cfg["downloads"]["simultaneous"],
        "default_destination": cfg["downloads"]["default_destination"],
        "allowed_paths": cfg["downloads"]["allowed_paths"],
        "download_segments": cfg["downloads"].get("download_segments", 1),
        "speed_limit": cfg["downloads"].get("speed_limit", 0),
        "max_retries": cfg["downloads"].get("max_retries", 3),
        "retry_delay_seconds": cfg["downloads"].get("retry_delay_seconds", 5),
        "skip_nfo_files": cfg["downloads"].get("skip_nfo_files", True),
        "media_provider": _active_media_provider(cfg),
        "port": cfg["server"]["port"],
        "webhook_enabled": wh.get("enabled", False),
        "webhook_url": wh.get("url", ""),
        "webhook_format": wh.get("format", "generic"),
        "webhook_events": wh.get("events", []),
        "signal_registered": cfg.get("signal_registered", False),
    }


@router.put("/")
async def update_settings(body: SettingsUpdate, _=Depends(get_current_user)):
    cfg = get_config()

    if body.alldebrid_api_key is not None:
        cfg["alldebrid"]["api_key"] = body.alldebrid_api_key
    if body.alldebrid_enabled is not None:
        cfg["alldebrid"]["enabled"] = body.alldebrid_enabled
    if body.simultaneous_downloads is not None and 1 <= body.simultaneous_downloads <= 20:
        cfg["downloads"]["simultaneous"] = body.simultaneous_downloads
    if body.default_destination is not None:
        cfg["downloads"]["default_destination"] = body.default_destination
    if body.download_segments is not None and 1 <= body.download_segments <= 16:
        cfg["downloads"]["download_segments"] = body.download_segments
    if body.speed_limit is not None and body.speed_limit >= 0:
        cfg["downloads"]["speed_limit"] = body.speed_limit
        # Apply speed limit to aria2 immediately
        from services.aria2_service import aria2
        import asyncio
        try:
            limit_str = f"{body.speed_limit}M" if body.speed_limit > 0 else "0"
            asyncio.create_task(aria2.change_global_option({"max-overall-download-limit": limit_str}))
        except Exception:
            pass
    if body.max_retries is not None and 0 <= body.max_retries <= 20:
        cfg["downloads"]["max_retries"] = body.max_retries
    if body.retry_delay_seconds is not None and 0 <= body.retry_delay_seconds <= 3600:
        cfg["downloads"]["retry_delay_seconds"] = body.retry_delay_seconds
    if body.skip_nfo_files is not None:
        cfg["downloads"]["skip_nfo_files"] = bool(body.skip_nfo_files)

    # Webhooks
    if "webhooks" not in cfg:
        cfg["webhooks"] = {"enabled": False, "url": "", "format": "generic", "events": []}
    if body.webhook_enabled is not None:
        cfg["webhooks"]["enabled"] = body.webhook_enabled
    if body.webhook_url is not None:
        # Validate webhook URL: must be http/https and not target internal services
        from urllib.parse import urlparse
        if body.webhook_url:
            parsed = urlparse(body.webhook_url)
            if parsed.scheme not in ("http", "https"):
                raise HTTPException(status_code=400, detail="Webhook URL must use http or https")
            # Signal intentionally targets a local service — skip SSRF check for that format
            if body.webhook_format != "signal":
                # Block private/reserved IPs (SSRF protection)
                host = parsed.hostname or ""
                try:
                    infos = socket.getaddrinfo(host, None)
                    for info in infos:
                        addr = ipaddress.ip_address(info[4][0])
                        if addr.is_private or addr.is_reserved or addr.is_loopback or addr.is_link_local:
                            raise HTTPException(status_code=400, detail="Webhook URL cannot target a private or local address")
                except socket.gaierror:
                    pass  # DNS resolution failed, allow (will fail on actual webhook call anyway)
        cfg["webhooks"]["url"] = body.webhook_url
    if body.webhook_format is not None:
        cfg["webhooks"]["format"] = body.webhook_format
    if body.webhook_events is not None:
        cfg["webhooks"]["events"] = body.webhook_events

    save_config(cfg)
    return {"status": "saved"}


@router.post("/test-alldebrid")
async def test_alldebrid(_=Depends(get_current_user)):
    cfg = get_config()
    api_key = cfg["alldebrid"]["api_key"]
    if not api_key:
        return {"valid": False, "message": "No API key configured"}
    valid = await alldebrid.test_key(api_key)
    return {"valid": valid, "message": "API key valid" if valid else "API key invalid"}


@router.get("/alldebrid/hosts")
async def alldebrid_hosts(_=Depends(get_current_user)):
    cfg = get_config()
    api_key = cfg["alldebrid"]["api_key"]
    if not cfg["alldebrid"]["enabled"] or not api_key:
        raise HTTPException(status_code=400, detail="AllDebrid not configured")
    try:
        hosts = await alldebrid.user_hosts(api_key)
        available = sum(1 for host in hosts if host.get("status"))
        return {"hosts": hosts, "available": available, "total": len(hosts)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/media")
async def get_media_settings(_=Depends(get_current_user)):
    cfg = get_config()
    data = _media_public_config(cfg, include_status=True)
    provider = data["provider"]
    if data["enabled"] and data["token_configured"]:
        try:
            service = _media_service(provider)
            info = await service.server_info(data["url"], cfg[provider]["token"])
            libraries = await service.libraries(data["url"], cfg[provider]["token"])
            data.update({
                "connected": True,
                "server": info,
                "library_count": len(libraries),
                "libraries": libraries,
            })
        except Exception as e:
            data.update({
                "connected": False,
                "error": str(e)[:200],
                "library_count": 0,
                "libraries": [],
            })
    else:
        data.update({"connected": False, "library_count": 0, "libraries": []})
    return data


@router.put("/media")
async def update_media_settings(body: MediaSettingsRequest, _=Depends(get_current_user)):
    cfg = get_config()
    provider = (body.provider or _active_media_provider(cfg)).strip().lower()
    if provider not in ("plex", "jellyfin"):
        raise HTTPException(status_code=400, detail="Media provider must be plex or jellyfin")

    media_cfg = cfg.setdefault(provider, _media_defaults(provider))
    other = "jellyfin" if provider == "plex" else "plex"
    cfg.setdefault(other, _media_defaults(other))
    cfg.setdefault("media", {})["active"] = provider

    if body.enabled is not None:
        media_cfg["enabled"] = bool(body.enabled)
        if body.enabled:
            cfg[other]["enabled"] = False
    if body.url is not None:
        media_cfg["url"] = _validate_media_url(body.url, provider)
    if body.token is not None and body.token.strip():
        media_cfg["token"] = body.token.strip()
    if body.favorite_keys is not None:
        media_cfg["favorite_keys"] = _normalize_plex_favorite_keys(body.favorite_keys)
    media_cfg.setdefault("last_refreshes", {})
    media_cfg.setdefault("favorite_keys", [])
    save_config(cfg)
    return {"status": "saved", **_media_public_config(cfg, include_status=True)}


@router.post("/media/test")
async def test_media(_=Depends(get_current_user)):
    cfg = get_config()
    provider, url, token = _require_media_config(cfg)
    try:
        service = _media_service(provider)
        info = await service.server_info(url, token)
        libraries = await service.libraries(url, token)
        return {"ok": True, "provider": provider, "server": info, "library_count": len(libraries)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.get("/media/libraries")
async def media_libraries(_=Depends(get_current_user)):
    cfg = get_config()
    provider, url, token = _require_media_config(cfg)
    try:
        libraries = await _media_service(provider).libraries(url, token)
        return {"provider": provider, "libraries": libraries, "total": len(libraries)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.get("/media/suggestions")
async def media_suggestions(_=Depends(get_current_user)):
    cfg = get_config()
    try:
        suggestions = await _media_refresh_suggestions(cfg)
        return {"suggestions": suggestions, "total": len(suggestions), "window_hours": 24}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.post("/media/libraries/{library_key}/refresh")
async def refresh_media_library(library_key: str, _=Depends(get_current_user)):
    cfg = get_config()
    provider, url, token = _require_media_config(cfg)
    try:
        logger.info("%s refresh requested for library key=%s", provider.title(), library_key)
        await _media_service(provider).refresh_library(url, token, library_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])

    refreshed_at = datetime.now(timezone.utc).isoformat()
    media_cfg = cfg.setdefault(provider, {})
    last_refreshes = media_cfg.setdefault("last_refreshes", {})
    last_refreshes[str(library_key)] = refreshed_at
    save_config(cfg)
    logger.info("%s refresh completed for library key=%s", provider.title(), library_key)
    return {"status": "refreshed", "provider": provider, "library_key": library_key, "refreshed_at": refreshed_at}


@router.get("/plex")
async def get_plex_settings(_=Depends(get_current_user)):
    cfg = get_config()
    data = _plex_public_config(cfg, include_status=True)
    if data["enabled"] and data["token_configured"]:
        try:
            info = await plex.server_info(data["url"], cfg["plex"]["token"])
            libraries = await plex.libraries(data["url"], cfg["plex"]["token"])
            data.update({
                "connected": True,
                "server": info,
                "library_count": len(libraries),
                "libraries": libraries,
            })
        except Exception as e:
            data.update({
                "connected": False,
                "error": str(e)[:200],
                "library_count": 0,
                "libraries": [],
            })
    else:
        data.update({"connected": False, "library_count": 0, "libraries": []})
    return data


@router.put("/plex")
async def update_plex_settings(body: PlexSettingsRequest, _=Depends(get_current_user)):
    cfg = get_config()
    plex_cfg = cfg.setdefault("plex", {
        "enabled": False,
        "url": "http://127.0.0.1:32400",
        "token": "",
        "last_refreshes": {},
        "favorite_keys": [],
    })
    if body.enabled is not None:
        plex_cfg["enabled"] = body.enabled
        if body.enabled:
            cfg.setdefault("jellyfin", _media_defaults("jellyfin"))["enabled"] = False
            cfg.setdefault("media", {})["active"] = "plex"
    if body.url is not None:
        plex_cfg["url"] = _validate_plex_url(body.url)
    if body.token is not None and body.token.strip():
        plex_cfg["token"] = body.token.strip()
    if body.favorite_keys is not None:
        plex_cfg["favorite_keys"] = _normalize_plex_favorite_keys(body.favorite_keys)
    plex_cfg.setdefault("last_refreshes", {})
    plex_cfg.setdefault("favorite_keys", [])
    save_config(cfg)
    return {"status": "saved", **_plex_public_config(cfg, include_status=True)}


@router.post("/plex/test")
async def test_plex(_=Depends(get_current_user)):
    cfg = get_config()
    url, token = _require_plex_config(cfg)
    try:
        info = await plex.server_info(url, token)
        libraries = await plex.libraries(url, token)
        return {"ok": True, "server": info, "library_count": len(libraries)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.get("/plex/libraries")
async def plex_libraries(_=Depends(get_current_user)):
    cfg = get_config()
    url, token = _require_plex_config(cfg)
    try:
        libraries = await plex.libraries(url, token)
        return {"libraries": libraries, "total": len(libraries)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.get("/plex/suggestions")
async def plex_suggestions(_=Depends(get_current_user)):
    cfg = get_config()
    try:
        suggestions = await _plex_refresh_suggestions(cfg)
        return {"suggestions": suggestions, "total": len(suggestions), "window_hours": 24}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.post("/plex/libraries/{library_key}/refresh")
async def refresh_plex_library(library_key: str, _=Depends(get_current_user)):
    cfg = get_config()
    url, token = _require_plex_config(cfg)
    try:
        logger.info("Plex refresh requested for library key=%s", library_key)
        await plex.refresh_library(url, token, library_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])

    refreshed_at = datetime.now(timezone.utc).isoformat()
    plex_cfg = cfg.setdefault("plex", {})
    last_refreshes = plex_cfg.setdefault("last_refreshes", {})
    last_refreshes[str(library_key)] = refreshed_at
    save_config(cfg)
    logger.info("Plex refresh completed for library key=%s", library_key)
    return {"status": "refreshed", "library_key": library_key, "refreshed_at": refreshed_at}


@router.post("/test-webhook")
async def test_webhook(_=Depends(get_current_user)):
    cfg = get_config()
    wh = cfg.get("webhooks", {})
    if not wh.get("url"):
        return {"success": False, "message": "No URL configured"}

    try:
        await send_webhook.__wrapped__(
            "download_complete",
            {
                "name": "test-file.mkv",
                "destination": "/mnt/media/test",
                "size": 1073741824,
                "status": "complete",
            },
        ) if hasattr(send_webhook, '__wrapped__') else None

        # Direct test call bypassing event filter
        import httpx
        from services.webhook import _build_payload
        wh_url = wh["url"]
        wh_fmt = wh.get("format", "generic")
        payload = _build_payload(wh_fmt, "download_complete", {
            "name": "test-file.mkv",
            "destination": "/mnt/media/test",
            "size": 1073741824,
            "status": "complete",
        }, wh_url)
        from urllib.parse import urlparse as _urlparse
        target_url = _urlparse(wh_url)._replace(query="", fragment="").geturl() if wh_fmt == "signal" else wh_url
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(target_url, json=payload)
            if resp.status_code < 400:
                return {"success": True, "message": f"Webhook sent (HTTP {resp.status_code})"}
            else:
                return {"success": False, "message": f"HTTP error {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


@router.post("/check-signal")
async def check_signal(body: SignalCheckRequest, _=Depends(get_current_user)):
    import httpx
    import re
    host = body.host.strip()
    port = body.port
    if not host or port < 1 or port > 65535:
        return {"running": False, "version": "", "message": "Invalid host or port"}
    if not re.match(r'^[a-zA-Z0-9._-]+$', host):
        return {"running": False, "version": "", "message": "Invalid host"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://{host}:{port}/v1/about")
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get("versions", {})
                version = versions.get("signal-cli", "") if isinstance(versions, dict) else ""
                return {"running": True, "version": version, "message": "Service is running"}
            else:
                return {"running": False, "version": "", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"running": False, "version": "", "message": str(e)[:100]}


@router.post("/deploy-signal")
async def deploy_signal(body: SignalDeployRequest, _=Depends(get_current_user)):
    port = body.port
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid port")

    try:
        # ── Check if container is already running ─────────────────────────
        try:
            ps = subprocess.run(
                ["docker", "ps", "--filter", "name=signal-cli-rest-api",
                 "--filter", "status=running", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
            if "signal-cli-rest-api" in ps.stdout:
                return {"success": True, "message": "Container already running", "action": "already_running"}
        except FileNotFoundError:
            pass  # Docker not installed yet — will install below

        # ── Install Docker Engine if missing ──────────────────────────────
        docker_missing = False
        try:
            subprocess.run(["docker", "--version"], capture_output=True, timeout=5, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            docker_missing = True

        if docker_missing:
            apt = subprocess.run(
                ["apt-get", "install", "-y", "--no-install-recommends", "docker.io"],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )
            if apt.returncode != 0:
                return {"success": False,
                        "message": f"Docker install failed: {apt.stderr[:200]}",
                        "action": None}
            # Start Docker daemon
            subprocess.run(["systemctl", "start", "docker"], capture_output=True, timeout=30)

        # ── Create data directory ─────────────────────────────────────────
        Path("/opt/signal").mkdir(parents=True, exist_ok=True)
        Path("/opt/signal").chmod(0o700)  # only root can read/write

        # ── Check if container exists (stopped) ───────────────────────────
        ps_all = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=signal-cli-rest-api",
             "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        status_out = ps_all.stdout.strip()

        if status_out.lower().startswith("up"):
            return {"success": True, "message": "Container already running", "action": "already_running"}

        # Container is stopped/errored or doesn't exist — remove if present, then recreate
        if status_out:
            subprocess.run(["docker", "rm", "-f", "signal-cli-rest-api"],
                           capture_output=True, timeout=15)

        # Pull image first (separate step so timeout applies only to pull)
        pull = subprocess.run(
            ["docker", "pull", "bbernhard/signal-cli-rest-api"],
            capture_output=True, text=True, timeout=600,  # 10 min for slow connections
        )
        if pull.returncode != 0:
            err = (pull.stderr or pull.stdout).strip()
            error_lines = [l for l in err.splitlines() if not any(
                kw in l for kw in ("Pulling from", "Pulling fs layer", "Pull complete",
                                   "Waiting", "Verifying", "Download complete",
                                   "Already exists", "Digest:", "Status:")
            )]
            msg = "\n".join(error_lines).strip() or err
            return {"success": False, "message": f"Image pull failed: {msg[:400]}", "action": None}

        # Create and start container with AppArmor disabled (works on restricted hosts)
        run = subprocess.run(
            ["docker", "run", "-d", "--name", "signal-cli-rest-api",
             "--restart", "unless-stopped",
             "--security-opt", "apparmor=unconfined",
             "-p", f"{port}:8080",
             "-v", "/opt/signal:/home/.local/share/signal-cli",
             "bbernhard/signal-cli-rest-api"],
            capture_output=True, text=True, timeout=30,
        )
        if run.returncode != 0:
            return {"success": False, "message": run.stderr.strip()[:400], "action": None}
        return {"success": True, "message": "Container created and started", "action": "created"}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Operation timed out — the image may still be downloading in the background. Wait a minute then click 'Check connection'.", "action": None}
    except Exception as e:
        return {"success": False, "message": str(e)[:400], "action": None}


@router.post("/signal-register")
async def signal_register(body: SignalRegisterRequest, _=Depends(get_current_user)):
    import httpx
    import re
    host = body.host.strip()
    port = body.port
    number = body.number.strip()
    captcha = body.captcha.strip()
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid host or port")
    if not re.match(r'^\+[0-9]{7,15}$', number):
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    number_encoded = number.replace("+", "%2B")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"http://{host}:{port}/v1/register/{number_encoded}",
                json={"captcha": captcha},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code in (200, 201, 204):
                return {"success": True, "message": "Registration request sent — check your SMS"}
            else:
                try:
                    detail = resp.json()
                    msg = detail.get("error", str(detail))[:200]
                except Exception:
                    msg = resp.text[:200]
                return {"success": False, "message": f"HTTP {resp.status_code}: {msg}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


@router.post("/signal-verify")
async def signal_verify(body: SignalVerifyRequest, _=Depends(get_current_user)):
    import httpx
    import re
    host = body.host.strip()
    port = body.port
    number = body.number.strip()
    code = body.code.strip()
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid host or port")
    if not re.match(r'^\+[0-9]{7,15}$', number):
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    if not re.match(r'^[0-9]{3,8}$', code):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    number_encoded = number.replace("+", "%2B")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"http://{host}:{port}/v1/register/{number_encoded}/verify/{code}",
            )
            if resp.status_code in (200, 201, 204):
                # Store registration status in config
                cfg = get_config()
                cfg["signal_registered"] = True
                save_config(cfg)
                return {"success": True, "message": "Number verified and registered"}
            else:
                try:
                    detail = resp.json()
                    msg = detail.get("error", str(detail))[:200]
                except Exception:
                    msg = resp.text[:200]
                return {"success": False, "message": f"HTTP {resp.status_code}: {msg}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


@router.post("/signal-reset")
async def signal_reset(body: SignalResetRequest, _=Depends(get_current_user)):
    import httpx
    import re
    steps = []

    # ── 1. Unregister number from Signal's servers (best effort) ──────────
    number = body.number.strip()
    if number and re.match(r'^\+[0-9]{7,15}$', number):
        host = body.host.strip() or "localhost"
        port = body.port if 1 <= body.port <= 65535 else 8080
        number_encoded = number.replace("+", "%2B")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"http://{host}:{port}/v1/accounts/{number_encoded}",
                    params={"delete_local_data": "true"},
                )
                if resp.status_code in (200, 201, 204):
                    steps.append("number unregistered from Signal")
                else:
                    steps.append(f"unregister returned HTTP {resp.status_code}")
        except Exception as e:
            steps.append(f"unregister skipped ({str(e)[:80]})")

    # ── 2. Clear local config ─────────────────────────────────────────────
    cfg = get_config()
    cfg.pop("signal_registered", None)
    wh = cfg.get("webhooks", {})
    if wh.get("format") == "signal":
        wh["url"] = ""
        wh["format"] = "generic"
        wh["enabled"] = False
    save_config(cfg)
    steps.append("local config cleared")

    # ── 3. Stop and remove Docker container (best effort) ────────────────
    try:
        subprocess.run(["docker", "stop", "signal-cli-rest-api"], capture_output=True, timeout=15)
        subprocess.run(["docker", "rm", "signal-cli-rest-api"], capture_output=True, timeout=10)
        steps.append("container stopped and removed")
    except Exception:
        steps.append("container cleanup skipped (Docker not found)")

    return {"success": True, "message": " — ".join(steps)}


@router.get("/signal-status")
async def signal_status(_=Depends(get_current_user)):
    from urllib.parse import urlparse, unquote
    cfg = get_config()
    registered = cfg.get("signal_registered", False)
    wh = cfg.get("webhooks", {})
    host, port, number_from, number_to = "localhost", 8080, "", ""
    if wh.get("format") == "signal" and wh.get("url"):
        try:
            u = urlparse(wh["url"])
            host = u.hostname or "localhost"
            port = int(u.port or 8080)
            q = dict(pair.split("=", 1) for pair in u.query.split("&") if "=" in pair)
            number_from = unquote(q.get("from", ""))
            number_to   = unquote(q.get("to", ""))
        except Exception:
            pass
    return {"registered": registered, "number_from": number_from, "number_to": number_to, "host": host, "port": port}


@router.post("/signal-test")
async def signal_test(_=Depends(get_current_user)):
    import httpx
    from urllib.parse import urlparse, unquote, urlunparse
    cfg = get_config()
    wh = cfg.get("webhooks", {})
    if wh.get("format") != "signal" or not wh.get("url"):
        return {"success": False, "message": "Signal not configured"}
    wh_url = wh["url"]
    try:
        u = urlparse(wh_url)
        q = dict(pair.split("=", 1) for pair in u.query.split("&") if "=" in pair)
        number_from = unquote(q.get("from", ""))
        number_to   = unquote(q.get("to", ""))
        if not number_from or not number_to:
            return {"success": False, "message": "Missing from/to numbers"}
        target = urlunparse(u._replace(query="", fragment=""))
        payload = {"message": "✅ Test — Download Manager", "number": number_from, "recipients": [number_to]}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(target, json=payload)
            if resp.status_code < 400:
                return {"success": True}
            else:
                return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:100]}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


@router.get("/storage")
async def get_storage(_=Depends(get_current_user)):
    cfg = get_config()
    paths = cfg.get("storage_extra_paths", [])

    result = []
    for path in paths:
        if not path:
            continue
        entry: dict = {"path": path}
        try:
            usage = shutil.disk_usage(path)
            entry["total"] = usage.total
            entry["used"] = usage.used
            entry["free"] = usage.free
            entry["percent"] = round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0.0
            entry["available"] = True
        except Exception:
            entry["total"] = 0
            entry["used"] = 0
            entry["free"] = 0
            entry["percent"] = 0.0
            entry["available"] = False
        result.append(entry)

    return result


@router.post("/storage/paths")
async def add_storage_path(body: StoragePathRequest, _=Depends(get_current_user)):
    path = body.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path required")
    cfg = get_config()
    extra = cfg.get("storage_extra_paths", [])
    if path not in extra:
        extra.append(path)
        cfg["storage_extra_paths"] = extra
        save_config(cfg)
    return {"status": "added"}


@router.delete("/storage/paths")
async def remove_storage_path(body: StoragePathRequest, _=Depends(get_current_user)):
    path = body.path.strip()
    cfg = get_config()
    extra = cfg.get("storage_extra_paths", [])
    cfg["storage_extra_paths"] = [p for p in extra if p != path]
    save_config(cfg)
    return {"status": "removed"}


def _get_current_version() -> str:
    # Check install dir first, then git dir
    for d in [INSTALL_DIR, GIT_DIR]:
        vf = d / "VERSION"
        if vf.exists():
            return vf.read_text().strip()
    return "0.0.0"


def _parse_version_tag(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


async def _get_latest_github_version(client) -> dict:
    resp = await client.get(
        f"https://api.github.com/repos/{REPO}/tags",
        params={"per_page": 100},
        headers={"Accept": "application/vnd.github+json"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub error ({resp.status_code})")

    latest_tag = ""
    latest_version = None
    for item in resp.json():
        name = str(item.get("name", "")).strip()
        version = _parse_version_tag(name)
        if version is None:
            continue
        if latest_version is None or version > latest_version:
            latest_version = version
            latest_tag = name

    if latest_version is None:
        raise HTTPException(status_code=502, detail="No valid version tag found")

    body = ""
    release_resp = await client.get(
        f"https://api.github.com/repos/{REPO}/releases/tags/{latest_tag}",
        headers={"Accept": "application/vnd.github+json"},
    )
    if release_resp.status_code == 200:
        body = release_resp.json().get("body", "") or ""

    return {
        "tag": latest_tag,
        "version": ".".join(str(part) for part in latest_version),
        "version_tuple": latest_version,
        "changelog": body,
    }


def _find_git_dir() -> Path:
    """Find the git repo directory (may differ from install dir)."""
    for d in [INSTALL_DIR, GIT_DIR, Path("/root/download-manager")]:
        if (d / ".git").exists():
            return d
    return INSTALL_DIR


@router.get("/version")
async def get_version(_=Depends(get_current_user)):
    return {"version": _get_current_version()}


@router.get("/diagnostics")
async def diagnostics(request: Request, _=Depends(get_current_user)):
    import asyncio
    import aiosqlite
    from database import DB_PATH
    from services.aria2_service import aria2

    db_info = {"tables": {}, "download_statuses": []}
    async with aiosqlite.connect(str(DB_PATH)) as db:
        for table in ("downloads", "packages", "torrents", "history", "users", "blocked_ips"):
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
            (count,) = await cursor.fetchone()
            db_info["tables"][table] = count
        cursor = await db.execute(
            "SELECT status, COUNT(*) FROM downloads GROUP BY status ORDER BY status"
        )
        db_info["download_statuses"] = [
            {"status": status, "count": count}
            for status, count in await cursor.fetchall()
        ]

    aria2_info = {"ok": False}
    try:
        active, waiting, stopped = await asyncio.wait_for(
            asyncio.gather(
                aria2._call("aria2.tellActive"),
                aria2._call("aria2.tellWaiting", [0, 100]),
                aria2._call("aria2.tellStopped", [0, 100]),
            ),
            timeout=5,
        )
        aria2_info = {
            "ok": True,
            "active": len(active or []),
            "waiting": len(waiting or []),
            "stopped": len(stopped or []),
        }
    except Exception as e:
        aria2_info = {"ok": False, "error": str(e)[:200]}

    qm = getattr(request.app.state, "queue_manager", None)
    queue_info = qm.health_snapshot() if qm and hasattr(qm, "health_snapshot") else {"running": False}

    return {
        "version": _get_current_version(),
        "database": db_info,
        "aria2": aria2_info,
        "queue": queue_info,
    }


@router.get("/check-update")
async def check_update(_=Depends(get_current_user)):
    import httpx

    current = _get_current_version()
    current_version = _parse_version_tag(current)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            latest_info = await _get_latest_github_version(client)
            update_available = current_version is not None and latest_info["version_tuple"] > current_version
            return {
                "update_available": update_available,
                "current": current,
                "latest": latest_info["version"],
                "latest_tag": latest_info["tag"],
                "changelog": latest_info["changelog"],
                "message": "Update available" if update_available else "Up to date",
            }
    except HTTPException as e:
        return {"update_available": False, "current": current, "message": e.detail, "error": True}
    except Exception as e:
        return {"update_available": False, "current": current, "message": f"Error: {str(e)[:200]}", "error": True}


def _do_restart():
    """Restart the systemd service. Called as a background task after the HTTP response is sent."""
    import time
    time.sleep(1)  # Let the response reach the client
    subprocess.run(["systemctl", "reset-failed", "download-manager"],
                   capture_output=True, timeout=10)
    subprocess.run(["systemctl", "restart", "download-manager"],
                   capture_output=True, timeout=30)


@router.post("/update")
async def perform_update(background_tasks: BackgroundTasks, _=Depends(get_current_user)):
    import httpx

    current = _get_current_version()
    current_version = _parse_version_tag(current)

    try:
        # Fetch latest release info
        async with httpx.AsyncClient(timeout=15.0) as client:
            latest_info = await _get_latest_github_version(client)
            latest = latest_info["version"]
            changelog = latest_info["changelog"]

            if current_version is None or latest_info["version_tuple"] <= current_version:
                return {"success": True, "message": "Already up to date", "version": current, "changelog": ""}

        # Perform git pull from the project root
        install_dir = INSTALL_DIR
        git_dir = _find_git_dir()
        if _is_git_dirty(git_dir):
            raise HTTPException(
                status_code=409,
                detail="Update blocked: local files have uncommitted changes.",
            )

        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=str(git_dir),
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "git pull failed").strip()
            raise HTTPException(
                status_code=409,
                detail=f"Update requires manual intervention: {msg[:300]}",
            )

        # Always ensure start.sh is executable (git may strip the bit)
        start_sh = install_dir / "start.sh"
        if start_sh.exists():
            start_sh.chmod(0o755)

        # If install_dir != git_dir, sync files
        if git_dir != install_dir:
            subprocess.run(
                ["cp", "-r", f"{git_dir}/backend/.", f"{install_dir}/backend/"],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["cp", "-r", f"{git_dir}/frontend/.", f"{install_dir}/frontend/"],
                capture_output=True, timeout=30,
            )
            # Copy root-level files (VERSION, start.sh, requirements.txt)
            for fname in ["VERSION", "start.sh", "requirements.txt"]:
                src = git_dir / fname
                if src.exists():
                    subprocess.run(
                        ["cp", str(src), str(install_dir / fname)],
                        capture_output=True, timeout=10,
                    )
            # Re-apply executable bit after copy
            start_sh = install_dir / "start.sh"
            if start_sh.exists():
                start_sh.chmod(0o755)

        # Update pip dependencies if requirements.txt exists
        pip_bin = install_dir / "venv" / "bin" / "pip"
        req_file = install_dir / "requirements.txt"
        if pip_bin.exists() and req_file.exists():
            subprocess.run(
                [str(pip_bin), "install", "--quiet", "-r", str(req_file)],
                capture_output=True, timeout=120,
            )

        # Schedule restart AFTER the HTTP response is sent (BackgroundTask)
        background_tasks.add_task(_do_restart)

        return {
            "success": True,
            "message": f"Updated to v{latest}",
            "version": latest,
            "changelog": changelog,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal error during update")
