import asyncio
import ipaddress
import logging
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from urllib.parse import urlparse

from models import SettingsUpdate, StoragePathRequest, MediaSettingsRequest, SignalCheckRequest, SignalDeployRequest, SignalRegisterRequest, SignalVerifyRequest, SignalResetRequest
from auth import get_current_user, get_password_hash
from config import get_config, update_config
from database import db_session
from services.alldebrid import alldebrid
from services.jellyfin import jellyfin
from services.media_refresh import (
    MediaRefreshError,
    media_auto_public_fields,
    media_defaults as _service_media_defaults,
    media_refresh_suggestions as _service_media_refresh_suggestions,
    refresh_library_from_config,
)
from services.plex import plex
from services.smb import is_mounted
from services.webhook import send_webhook
from services.diagnostics import clear_events, list_events, record_event_nowait
from services.update_service import (
    UpdateError, check_latest, get_current_version, read_update_status,
    start_latest_update,
)
from utils import validate_destination

router = APIRouter()
logger = logging.getLogger(__name__)

def _plex_public_config(cfg: dict, include_status: bool = False) -> dict:
    plex_cfg = cfg.get("plex", {})
    token = plex_cfg.get("token", "")
    data = {
        "enabled": bool(plex_cfg.get("enabled", False)),
        "url": plex_cfg.get("url", "http://127.0.0.1:32400"),
        "token_configured": bool(token),
        "last_refreshes": plex_cfg.get("last_refreshes", {}),
        "favorite_keys": plex_cfg.get("favorite_keys", []),
        **media_auto_public_fields(plex_cfg),
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
    return _service_media_defaults(provider)


def _media_service(provider: str):
    return jellyfin if provider == "jellyfin" else plex


def _validate_media_url(url: str, provider: str = "media") -> str:
    clean = (url or "").strip().rstrip("/")
    if len(clean) > 2048:
        raise HTTPException(status_code=400, detail=f"{provider.title()} URL is too long")
    parsed = urlparse(clean)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
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
        **media_auto_public_fields(media_cfg),
        "providers": {
            "plex": _plex_public_config(cfg, include_status=False),
            "jellyfin": {
                "enabled": bool(cfg.get("jellyfin", {}).get("enabled", False)),
                "url": cfg.get("jellyfin", {}).get("url", "http://127.0.0.1:8096"),
                "token_configured": bool(cfg.get("jellyfin", {}).get("token", "")),
                "last_refreshes": cfg.get("jellyfin", {}).get("last_refreshes", {}),
                "favorite_keys": cfg.get("jellyfin", {}).get("favorite_keys", []),
                **media_auto_public_fields(cfg.get("jellyfin", {})),
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
        "stalled_timeout_hours": cfg["downloads"].get("stalled_timeout_hours", 3),
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
    current = get_config()
    ranges = (
        ("simultaneous_downloads", body.simultaneous_downloads, 1, 20),
        ("download_segments", body.download_segments, 1, 16),
        ("speed_limit", body.speed_limit, 0, 1_000_000),
        ("max_retries", body.max_retries, 0, 20),
        ("retry_delay_seconds", body.retry_delay_seconds, 0, 3600),
        ("stalled_timeout_hours", body.stalled_timeout_hours, 0, 168),
    )
    for name, value, minimum, maximum in ranges:
        if value is not None and not minimum <= value <= maximum:
            raise HTTPException(status_code=400, detail=f"{name} must be between {minimum} and {maximum}")
    if body.alldebrid_api_key is not None and len(body.alldebrid_api_key) > 512:
        raise HTTPException(status_code=400, detail="AllDebrid API key is too long")
    if body.default_destination is not None:
        validate_destination(body.default_destination)

    allowed_formats = {"generic", "discord", "slack", "telegram", "gotify", "ntfy", "signal"}
    allowed_events = {"download_complete", "download_failed", "package_complete"}
    effective_format = body.webhook_format or current.get("webhooks", {}).get("format", "generic")
    if effective_format not in allowed_formats:
        raise HTTPException(status_code=400, detail="Unsupported webhook format")
    if body.webhook_events is not None and not set(body.webhook_events).issubset(allowed_events):
        raise HTTPException(status_code=400, detail="Unsupported webhook event")
    if body.webhook_url is not None:
        if len(body.webhook_url) > 2048:
            raise HTTPException(status_code=400, detail="Webhook URL is too long")
        if body.webhook_url:
            parsed = urlparse(body.webhook_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise HTTPException(status_code=400, detail="Webhook URL must use http or https")
            if effective_format != "signal":
                try:
                    infos = socket.getaddrinfo(parsed.hostname, None)
                    for info in infos:
                        addr = ipaddress.ip_address(info[4][0])
                        if addr.is_private or addr.is_reserved or addr.is_loopback or addr.is_link_local:
                            raise HTTPException(status_code=400, detail="Webhook URL cannot target a private or local address")
                except socket.gaierror:
                    raise HTTPException(status_code=400, detail="Webhook hostname cannot be resolved")

    def mutate(cfg):
        downloads_cfg = cfg.setdefault("downloads", {})
        alldebrid_cfg = cfg.setdefault("alldebrid", {})
        webhooks_cfg = cfg.setdefault("webhooks", {"enabled": False, "url": "", "format": "generic", "events": []})
        updates = {
            "simultaneous": body.simultaneous_downloads,
            "default_destination": body.default_destination,
            "download_segments": body.download_segments,
            "speed_limit": body.speed_limit,
            "max_retries": body.max_retries,
            "retry_delay_seconds": body.retry_delay_seconds,
            "skip_nfo_files": body.skip_nfo_files,
            "stalled_timeout_hours": body.stalled_timeout_hours,
        }
        for key, value in updates.items():
            if value is not None:
                downloads_cfg[key] = value
        if body.alldebrid_api_key is not None:
            alldebrid_cfg["api_key"] = body.alldebrid_api_key.strip()
        if body.alldebrid_enabled is not None:
            alldebrid_cfg["enabled"] = body.alldebrid_enabled
        if body.webhook_enabled is not None:
            webhooks_cfg["enabled"] = body.webhook_enabled
        if body.webhook_url is not None:
            webhooks_cfg["url"] = body.webhook_url.strip()
        if body.webhook_format is not None:
            webhooks_cfg["format"] = body.webhook_format
        if body.webhook_events is not None:
            webhooks_cfg["events"] = list(dict.fromkeys(body.webhook_events))

    cfg, _ = update_config(mutate)
    response = {"status": "saved"}
    if body.speed_limit is not None and body.speed_limit >= 0:
        from services.aria2_service import aria2
        expected_bytes = body.speed_limit * 1024 * 1024 if body.speed_limit > 0 else 0
        try:
            limit_str = f"{body.speed_limit}M" if body.speed_limit > 0 else "0"
            await asyncio.wait_for(
                aria2.change_global_option({"max-overall-download-limit": limit_str}),
                timeout=5,
            )
            options = await asyncio.wait_for(aria2.get_global_option(), timeout=5)
            effective_bytes = int(options.get("max-overall-download-limit", 0) or 0)
            response["speed_limit"] = {
                "configured_mb_s": body.speed_limit,
                "effective_bytes_s": effective_bytes,
                "applied": effective_bytes == expected_bytes,
            }
        except Exception as exc:
            logger.warning("Speed limit saved but not applied to aria2: %s", exc)
            response["speed_limit"] = {
                "configured_mb_s": body.speed_limit,
                "effective_bytes_s": None,
                "applied": False,
                "error": type(exc).__name__,
            }
    return response


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
    current = get_config()
    provider = (body.provider or _active_media_provider(current)).strip().lower()
    if provider not in ("plex", "jellyfin"):
        raise HTTPException(status_code=400, detail="Media provider must be plex or jellyfin")

    validated_url = _validate_media_url(body.url, provider) if body.url is not None else None
    if body.token is not None and len(body.token) > 2048:
        raise HTTPException(status_code=400, detail="Media token is too long")
    if body.favorite_keys is not None and len(body.favorite_keys) > 500:
        raise HTTPException(status_code=400, detail="Too many favorite libraries")

    def mutate(cfg):
        media_cfg = cfg.setdefault(provider, _media_defaults(provider))
        other = "jellyfin" if provider == "plex" else "plex"
        cfg.setdefault(other, _media_defaults(other))
        cfg.setdefault("media", {})["active"] = provider
        if body.enabled is not None:
            media_cfg["enabled"] = bool(body.enabled)
            if body.enabled:
                cfg[other]["enabled"] = False
        if validated_url is not None:
            media_cfg["url"] = validated_url
        if body.token is not None and body.token.strip():
            media_cfg["token"] = body.token.strip()
        if body.favorite_keys is not None:
            media_cfg["favorite_keys"] = _normalize_plex_favorite_keys(body.favorite_keys)
        if body.auto_refresh_enabled is not None:
            previous = bool(media_cfg.get("auto_refresh_enabled", False))
            media_cfg["auto_refresh_enabled"] = bool(body.auto_refresh_enabled)
            if body.auto_refresh_enabled and not previous:
                media_cfg["auto_refresh_enabled_at"] = datetime.now(timezone.utc).isoformat()
        media_cfg.setdefault("last_refreshes", {})
        media_cfg.setdefault("favorite_keys", [])
        media_cfg.setdefault("auto_refreshes", {})
        media_cfg.setdefault("auto_refresh_enabled", False)
        media_cfg.setdefault("auto_refresh_enabled_at", None)

    cfg, _ = update_config(mutate)
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
        suggestions = await _service_media_refresh_suggestions(cfg)
        return {"suggestions": suggestions, "total": len(suggestions), "window_hours": 24}
    except MediaRefreshError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


@router.post("/media/libraries/{library_key}/refresh")
async def refresh_media_library(library_key: str, _=Depends(get_current_user)):
    cfg = get_config()
    try:
        return await refresh_library_from_config(cfg, library_key)
    except MediaRefreshError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])


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
                update_config(lambda cfg: cfg.update({"signal_registered": True}))
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
    def clear_signal(cfg):
        cfg.pop("signal_registered", None)
        wh = cfg.get("webhooks", {})
        if wh.get("format") == "signal":
            wh["url"] = ""
            wh["format"] = "generic"
            wh["enabled"] = False
    update_config(clear_signal)
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


async def _disk_usage_with_timeout(path: str) -> tuple[int, int, int, float]:
    process = await asyncio.create_subprocess_exec(
        "df", "-B1", "--output=size,used,avail,pcent", "--", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=3)
    except asyncio.TimeoutError:
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass
        raise
    if process.returncode != 0:
        raise OSError(f"df failed for {path}")
    lines = [line.split() for line in stdout.decode(errors="replace").splitlines() if line.strip()]
    if len(lines) < 2 or len(lines[-1]) != 4:
        raise ValueError(f"Invalid df output for {path}")
    total, used, free, percent = lines[-1]
    return int(total), int(used), int(free), float(percent.rstrip("%"))


async def _storage_usage_entry(descriptor: dict) -> dict:
    entry = dict(descriptor)
    if entry["kind"] == "smb" and not entry.get("mounted", False):
        entry.update(total=0, used=0, free=0, percent=0.0, available=False)
        return entry
    try:
        total, used, free, percent = await _disk_usage_with_timeout(entry["path"])
        entry.update(
            total=total,
            used=used,
            free=free,
            percent=round(percent, 1),
            available=True,
        )
    except Exception:
        entry.update(total=0, used=0, free=0, percent=0.0, available=False)
    return entry


@router.get("/storage")
async def get_storage(
    include_smb: bool = Query(default=False),
    _=Depends(get_current_user),
):
    cfg = get_config()
    paths = cfg.get("storage_extra_paths", [])
    descriptors = {}
    for path in paths:
        if not path:
            continue
        normalized = os.path.normpath(path)
        descriptors[normalized] = {
            "path": path,
            "name": Path(normalized).name or normalized,
            "kind": "disk",
            "mounted": True,
            "configured_storage": True,
        }

    if include_smb:
        for share in cfg.get("smb_shares", []):
            path = str(share.get("mount_point") or "").strip()
            if not path:
                continue
            normalized = os.path.normpath(path)
            descriptor = descriptors.get(normalized, {
                "path": path,
                "configured_storage": False,
            })
            descriptor.update(
                name=str(share.get("name") or Path(normalized).name or normalized),
                kind="smb",
                mounted=is_mounted(path),
            )
            descriptors[normalized] = descriptor

    return await asyncio.gather(*(
        _storage_usage_entry(descriptor) for descriptor in descriptors.values()
    ))


@router.post("/storage/paths")
async def add_storage_path(body: StoragePathRequest, _=Depends(get_current_user)):
    path = body.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path required")
    def add(cfg):
        extra = cfg.setdefault("storage_extra_paths", [])
        if path not in extra:
            extra.append(path)
    update_config(add)
    return {"status": "added"}


@router.delete("/storage/paths")
async def remove_storage_path(body: StoragePathRequest, _=Depends(get_current_user)):
    path = body.path.strip()
    update_config(lambda cfg: cfg.update({
        "storage_extra_paths": [p for p in cfg.get("storage_extra_paths", []) if p != path]
    }))
    return {"status": "removed"}


@router.get("/version")
async def get_version(_=Depends(get_current_user)):
    return {"version": get_current_version()}


@router.get("/speed-limit/status")
async def get_speed_limit_status(_=Depends(get_current_user)):
    from services.aria2_service import aria2

    configured = max(0, int(get_config()["downloads"].get("speed_limit", 0) or 0))
    expected_bytes = configured * 1024 * 1024 if configured > 0 else 0
    try:
        options = await asyncio.wait_for(aria2.get_global_option(), timeout=5)
        effective_bytes = int(options.get("max-overall-download-limit", 0) or 0)
        return {
            "configured_mb_s": configured,
            "effective_bytes_s": effective_bytes,
            "applied": effective_bytes == expected_bytes,
            "available": True,
        }
    except Exception as exc:
        return {
            "configured_mb_s": configured,
            "effective_bytes_s": None,
            "applied": False,
            "available": False,
            "error": type(exc).__name__,
        }


@router.get("/runtime-status")
async def get_runtime_status(request: Request, _=Depends(get_current_user)):
    """Return the small health snapshot needed by the downloads workspace."""
    from services.aria2_service import aria2

    queue_manager = getattr(request.app.state, "queue_manager", None)
    queue = queue_manager.health_snapshot() if queue_manager else {"running": False}
    try:
        await asyncio.wait_for(aria2.get_global_option(), timeout=2)
        aria2_ok = True
    except Exception:
        aria2_ok = False

    return {
        "ok": bool(queue.get("running")) and aria2_ok and not queue.get("last_tick_error"),
        "aria2_ok": aria2_ok,
        "queue_running": bool(queue.get("running")),
        "queue_error": str(queue.get("last_tick_error") or "")[:200],
    }


@router.get("/diagnostics")
async def diagnostics(request: Request, _=Depends(get_current_user)):
    import asyncio
    from services.aria2_service import aria2

    db_info = {"tables": {}, "download_statuses": []}
    async with db_session() as db:
        for table in ("downloads", "packages", "torrents", "history", "users", "blocked_ips"):
            # Table names come exclusively from the static tuple above.
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608
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
        "version": get_current_version(),
        "database": db_info,
        "aria2": aria2_info,
        "queue": queue_info,
        "events": await list_events(100),
    }


@router.get("/diagnostics/events")
async def diagnostic_events(limit: int = 100, _=Depends(get_current_user)):
    return {"items": await list_events(limit)}


@router.delete("/diagnostics/events")
async def delete_diagnostic_events(_=Depends(get_current_user)):
    await clear_events()
    return {"status": "cleared"}


@router.get("/check-update")
async def check_update(_=Depends(get_current_user)):
    try:
        return await check_latest()
    except UpdateError as exc:
        return {
            "update_available": False,
            "current": get_current_version(),
            "message": str(exc),
            "error": True,
        }


@router.get("/update-status")
async def update_status(_=Depends(get_current_user)):
    return read_update_status()


@router.post("/update")
async def perform_update(_=Depends(get_current_user)):
    try:
        return await start_latest_update()
    except UpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
