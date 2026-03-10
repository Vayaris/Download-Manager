import httpx
import asyncio
from datetime import datetime, timezone
from config import get_config


def _fmt_size(size_bytes: int) -> str:
    if not size_bytes:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


async def send_webhook(event: str, data: dict):
    """Send a webhook notification. Non-blocking, errors are silently ignored."""
    config = get_config()
    wh = config.get("webhooks", {})

    if not wh.get("enabled") or not wh.get("url"):
        return

    events = wh.get("events", [])
    if event not in events:
        return

    fmt = wh.get("format", "generic")
    url = wh["url"]

    try:
        payload = _build_payload(fmt, event, data)
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception:
        pass


def _build_payload(fmt: str, event: str, data: dict) -> dict:
    name = data.get("name", "Unknown")
    dest = data.get("destination", "")
    size = _fmt_size(data.get("size", 0))
    error = data.get("error_msg", "")
    status = data.get("status", "")
    pkg_name = data.get("package_name", "")

    if fmt == "discord":
        return _discord_payload(event, name, dest, size, error, pkg_name)
    elif fmt == "slack":
        return _slack_payload(event, name, dest, size, error, pkg_name)
    elif fmt == "telegram":
        return _telegram_payload(event, name, dest, size, error, pkg_name)
    elif fmt == "gotify":
        return _gotify_payload(event, name, dest, size, error, pkg_name)
    elif fmt == "ntfy":
        return _ntfy_payload(event, name, dest, size, error, pkg_name)
    else:
        return _generic_payload(event, name, dest, size, error, status, pkg_name, data)


def _generic_payload(event, name, dest, size, error, status, pkg_name, data):
    return {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "name": name,
            "destination": dest,
            "size": size,
            "status": status,
            "error": error,
            "package": pkg_name,
        }
    }


def _discord_payload(event, name, dest, size, error, pkg_name):
    titles = {
        "download_complete": "Download Complete",
        "download_failed": "Download Failed",
        "package_complete": "Package Complete",
    }
    colors = {
        "download_complete": 0x22c55e,
        "download_failed": 0xef4444,
        "package_complete": 0x3b82f6,
    }
    fields = [
        {"name": "File", "value": name, "inline": True},
        {"name": "Size", "value": size, "inline": True},
        {"name": "Destination", "value": f"`{dest}`", "inline": False},
    ]
    if pkg_name:
        fields.append({"name": "Package", "value": pkg_name, "inline": True})
    if error:
        fields.append({"name": "Error", "value": error[:200], "inline": False})

    return {
        "embeds": [{
            "title": titles.get(event, event),
            "color": colors.get(event, 0x7c3aed),
            "fields": fields,
            "footer": {"text": "Download Manager"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }


def _slack_payload(event, name, dest, size, error, pkg_name):
    titles = {
        "download_complete": ":white_check_mark: Download Complete",
        "download_failed": ":x: Download Failed",
        "package_complete": ":package: Package Complete",
    }
    text = f"*{titles.get(event, event)}*\n*File:* {name}\n*Size:* {size}\n*Destination:* `{dest}`"
    if pkg_name:
        text += f"\n*Package:* {pkg_name}"
    if error:
        text += f"\n*Error:* {error[:200]}"
    return {"text": text}


def _telegram_payload(event, name, dest, size, error, pkg_name):
    emojis = {
        "download_complete": "✅",
        "download_failed": "❌",
        "package_complete": "📦",
    }
    text = f"{emojis.get(event, '📥')} *{event.replace('_', ' ').title()}*\n\n"
    text += f"📄 *File:* {name}\n💾 *Size:* {size}\n📁 *Dest:* `{dest}`"
    if pkg_name:
        text += f"\n📦 *Package:* {pkg_name}"
    if error:
        text += f"\n⚠️ *Error:* {error[:200]}"
    return {"text": text, "parse_mode": "Markdown"}


def _gotify_payload(event, name, dest, size, error, pkg_name):
    titles = {
        "download_complete": "Download Complete",
        "download_failed": "Download Failed",
        "package_complete": "Package Complete",
    }
    msg = f"File: {name}\nSize: {size}\nDestination: {dest}"
    if pkg_name:
        msg += f"\nPackage: {pkg_name}"
    if error:
        msg += f"\nError: {error[:200]}"
    priority = 5 if "failed" in event else 3
    return {"title": titles.get(event, event), "message": msg, "priority": priority}


def _ntfy_payload(event, name, dest, size, error, pkg_name):
    titles = {
        "download_complete": "Download Complete",
        "download_failed": "Download Failed",
        "package_complete": "Package Complete",
    }
    tags = {
        "download_complete": "white_check_mark",
        "download_failed": "x",
        "package_complete": "package",
    }
    msg = f"File: {name}\nSize: {size}\nDestination: {dest}"
    if pkg_name:
        msg += f"\nPackage: {pkg_name}"
    if error:
        msg += f"\nError: {error[:200]}"
    return {
        "title": titles.get(event, event),
        "message": msg,
        "tags": [tags.get(event, "arrow_down")],
        "priority": 4 if "failed" in event else 3,
    }
