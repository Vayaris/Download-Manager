from fastapi import APIRouter, Depends

from models import SettingsUpdate
from auth import get_current_user, get_password_hash
from config import get_config, save_config
from services.alldebrid import alldebrid
from services.webhook import send_webhook

router = APIRouter()


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

    # Webhooks
    if "webhooks" not in cfg:
        cfg["webhooks"] = {"enabled": False, "url": "", "format": "generic", "events": []}
    if body.webhook_enabled is not None:
        cfg["webhooks"]["enabled"] = body.webhook_enabled
    if body.webhook_url is not None:
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
        return {"valid": False, "message": "Aucune cle API configuree"}
    valid = await alldebrid.test_key(api_key)
    return {"valid": valid, "message": "Cle API valide" if valid else "Cle API invalide"}


@router.post("/test-webhook")
async def test_webhook(_=Depends(get_current_user)):
    cfg = get_config()
    wh = cfg.get("webhooks", {})
    if not wh.get("url"):
        return {"success": False, "message": "Aucune URL configuree"}

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
        payload = _build_payload(wh.get("format", "generic"), "download_complete", {
            "name": "test-file.mkv",
            "destination": "/mnt/media/test",
            "size": 1073741824,
            "status": "complete",
        })
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(wh["url"], json=payload)
            if resp.status_code < 400:
                return {"success": True, "message": f"Webhook envoye (HTTP {resp.status_code})"}
            else:
                return {"success": False, "message": f"Erreur HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}
