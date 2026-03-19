import ipaddress
import os
import shutil
import socket
import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from models import SettingsUpdate
from auth import get_current_user, get_password_hash
from config import get_config, save_config
from services.alldebrid import alldebrid
from services.webhook import send_webhook

router = APIRouter()

REPO = "Vayaris/Download-Manager"
INSTALL_DIR = Path("/opt/download-manager")
# Find the git repo: could be /opt/download-manager or the dev repo
_runtime_root = Path(__file__).parent.parent.parent
GIT_DIR = _runtime_root if (_runtime_root / ".git").exists() else INSTALL_DIR


@router.get("/")
async def get_settings(_=Depends(get_current_user)):
    cfg = get_config()
    wh = cfg.get("webhooks", {})
    return {
        "alldebrid_enabled": cfg["alldebrid"]["enabled"],
        "alldebrid_api_key": cfg["alldebrid"]["api_key"],
        "simultaneous_downloads": cfg["downloads"]["simultaneous"],
        "default_destination": cfg["downloads"]["default_destination"],
        "allowed_paths": cfg["downloads"]["allowed_paths"],
        "download_segments": cfg["downloads"].get("download_segments", 1),
        "speed_limit": cfg["downloads"].get("speed_limit", 0),
        "port": cfg["server"]["port"],
        "webhook_enabled": wh.get("enabled", False),
        "webhook_url": wh.get("url", ""),
        "webhook_format": wh.get("format", "generic"),
        "webhook_events": wh.get("events", []),
    }


@router.put("/")
async def update_settings(body: SettingsUpdate, _=Depends(get_current_user)):
    cfg = get_config()

    if body.alldebrid_api_key is not None:
        cfg["alldebrid"]["api_key"] = body.alldebrid_api_key
    if body.alldebrid_enabled is not None:
        cfg["alldebrid"]["enabled"] = body.alldebrid_enabled
    if body.simultaneous_downloads is not None and 1 <= body.simultaneous_downloads <= 10:
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


@router.get("/storage")
async def get_storage(_=Depends(get_current_user)):
    cfg = get_config()

    paths_to_check = []

    # Default destination
    default_dest = cfg["downloads"].get("default_destination", "")
    if default_dest:
        paths_to_check.append((default_dest, "downloads", False))

    # Allowed paths
    for p in cfg["downloads"].get("allowed_paths", []):
        if p:
            paths_to_check.append((p, p, False))

    # SMB shares
    for s in cfg.get("smb_shares", []):
        mp = s.get("mount_point", "")
        name = s.get("name", mp)
        if mp:
            paths_to_check.append((mp, f"SMB: {name}", True))

    # Deduplicate by device ID
    seen_devs = {}
    result = []
    for path, label, is_smb in paths_to_check:
        entry = {"path": path, "label": label, "is_smb": is_smb}
        try:
            dev = os.stat(path).st_dev
            if dev in seen_devs:
                continue
            seen_devs[dev] = path
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

    result.sort(key=lambda x: x["path"])
    return result


def _get_current_version() -> str:
    # Check install dir first, then git dir
    for d in [INSTALL_DIR, GIT_DIR]:
        vf = d / "VERSION"
        if vf.exists():
            return vf.read_text().strip()
    return "0.0.0"


def _find_git_dir() -> Path:
    """Find the git repo directory (may differ from install dir)."""
    for d in [INSTALL_DIR, GIT_DIR, Path("/root/download-manager")]:
        if (d / ".git").exists():
            return d
    return INSTALL_DIR


@router.get("/version")
async def get_version(_=Depends(get_current_user)):
    return {"version": _get_current_version()}


@router.get("/check-update")
async def check_update(_=Depends(get_current_user)):
    import httpx

    current = _get_current_version()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 404:
                return {"update_available": False, "current": current, "message": "No release found"}
            if resp.status_code != 200:
                return {"update_available": False, "current": current, "message": f"GitHub error ({resp.status_code})"}

            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            body = data.get("body", "")

            if not latest:
                return {"update_available": False, "current": current, "message": "Tag not found"}

            update_available = latest != current
            return {
                "update_available": update_available,
                "current": current,
                "latest": latest,
                "changelog": body,
                "message": "Update available" if update_available else "Up to date",
            }
    except Exception as e:
        return {"update_available": False, "current": current, "message": f"Error: {str(e)[:200]}"}


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

    try:
        # Fetch latest release info
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Unable to reach GitHub")

            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            changelog = data.get("body", "")

            if latest == current:
                return {"success": True, "message": "Already up to date", "version": current, "changelog": ""}

        # Perform git pull from the project root
        install_dir = INSTALL_DIR
        git_dir = _find_git_dir()

        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=str(git_dir),
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            # Try with reset if ff-only fails
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(git_dir),
                capture_output=True, text=True, timeout=30,
            )
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=str(git_dir),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail="Update failed. Check system logs.")

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
