from fastapi import APIRouter, Depends

from models import SettingsUpdate
from auth import get_current_user, get_password_hash
from config import get_config, save_config
from services.alldebrid import alldebrid

router = APIRouter()


@router.get("/")
async def get_settings(_=Depends(get_current_user)):
    cfg = get_config()
    return {
        "alldebrid_enabled": cfg["alldebrid"]["enabled"],
        "alldebrid_api_key": cfg["alldebrid"]["api_key"],
        "simultaneous_downloads": cfg["downloads"]["simultaneous"],
        "default_destination": cfg["downloads"]["default_destination"],
        "allowed_paths": cfg["downloads"]["allowed_paths"],
        "auth_enabled": cfg["auth"]["enabled"],
        "auth_username": cfg["auth"]["username"],
        "port": cfg["server"]["port"],
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
    if body.auth_enabled is not None:
        cfg["auth"]["enabled"] = body.auth_enabled
    if body.auth_username is not None:
        cfg["auth"]["username"] = body.auth_username
    if body.auth_password is not None and body.auth_password:
        cfg["auth"]["password_hash"] = get_password_hash(body.auth_password)

    save_config(cfg)
    return {"status": "saved"}


@router.post("/test-alldebrid")
async def test_alldebrid(_=Depends(get_current_user)):
    cfg = get_config()
    api_key = cfg["alldebrid"]["api_key"]
    if not api_key:
        return {"valid": False, "message": "Aucune clé API configurée"}
    valid = await alldebrid.test_key(api_key)
    return {"valid": valid, "message": "Clé API valide" if valid else "Clé API invalide"}
