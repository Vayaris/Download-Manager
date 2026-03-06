from fastapi import APIRouter, HTTPException

from models import LoginRequest, LoginResponse
from auth import verify_password, create_access_token
from config import get_config

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    cfg = get_config()
    if not cfg["auth"]["enabled"]:
        token = create_access_token({"sub": "anonymous"})
        return LoginResponse(token=token)

    if body.username != cfg["auth"]["username"]:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    pw_hash = cfg["auth"]["password_hash"]
    if not pw_hash or not verify_password(body.password, pw_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    token = create_access_token({"sub": body.username})
    return LoginResponse(token=token)


@router.get("/status")
async def auth_status():
    cfg = get_config()
    return {
        "auth_enabled": cfg["auth"]["enabled"],
        "username": cfg["auth"]["username"] if cfg["auth"]["enabled"] else None,
    }
