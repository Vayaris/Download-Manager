import uuid
import io
import base64
from datetime import datetime

import aiosqlite
from fastapi import APIRouter, HTTPException, Depends

from models import (
    LoginRequest, LoginResponse, SetupAdminRequest,
    SetupOTPResponse, VerifyOTPRequest,
)
from auth import verify_password, get_password_hash, create_access_token, get_current_user
from config import get_config, save_config
from database import DB_PATH

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    cfg = get_config()
    if not cfg["auth"]["enabled"]:
        token = create_access_token({"sub": "anonymous"})
        return LoginResponse(token=token)

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?", (body.username,)
        )
        user = await cursor.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    # Check 2FA
    if user["otp_enabled"]:
        if not body.otp_code:
            # Return a partial token that requires OTP verification
            token = create_access_token({
                "sub": body.username,
                "otp_required": True,
                "otp_verified": False,
            })
            return LoginResponse(token=token, otp_required=True)

        # Verify OTP code
        try:
            import pyotp
            totp = pyotp.TOTP(user["otp_secret"])
            if not totp.verify(body.otp_code, valid_window=1):
                raise HTTPException(status_code=401, detail="Code OTP invalide")
        except ImportError:
            raise HTTPException(status_code=500, detail="Module pyotp non installe")

    token = create_access_token({
        "sub": body.username,
        "otp_required": bool(user["otp_enabled"]),
        "otp_verified": True,
    })
    return LoginResponse(token=token)


@router.get("/status")
async def auth_status():
    cfg = get_config()

    # Check if admin account exists (always, regardless of auth state)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        (count,) = await cursor.fetchone()
        admin_exists = count > 0

    return {
        "auth_enabled": cfg["auth"]["enabled"],
        "admin_exists": admin_exists,
    }


@router.post("/setup-admin")
async def setup_admin(body: SetupAdminRequest):
    """Create the initial admin account. Only works if no users exist."""
    cfg = get_config()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        (count,) = await cursor.fetchone()

        if count > 0:
            raise HTTPException(status_code=400, detail="Un compte admin existe deja")

        if not body.username.strip() or not body.password:
            raise HTTPException(status_code=400, detail="Nom d'utilisateur et mot de passe requis")

        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 6 caracteres")

        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        pw_hash = get_password_hash(body.password)

        await db.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, body.username.strip(), pw_hash, now),
        )
        await db.commit()

    # Enable auth
    cfg["auth"]["enabled"] = True
    save_config(cfg)

    token = create_access_token({"sub": body.username.strip(), "otp_verified": True})
    return {"status": "created", "token": token, "access_token": token}


@router.post("/change-password")
async def change_password(body: SetupAdminRequest, user=Depends(get_current_user)):
    """Change password for current user."""
    if user["username"] == "anonymous":
        raise HTTPException(status_code=403, detail="Auth non activee")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 6 caracteres")

    pw_hash = get_password_hash(body.password)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (pw_hash, user["username"]),
        )
        await db.commit()

    return {"status": "updated"}


@router.post("/setup-otp", response_model=SetupOTPResponse)
async def setup_otp(user=Depends(get_current_user)):
    """Generate OTP secret and QR code for 2FA setup."""
    if user["username"] == "anonymous":
        raise HTTPException(status_code=403, detail="Auth non activee")

    try:
        import pyotp
        import qrcode
    except ImportError:
        raise HTTPException(status_code=500, detail="Modules pyotp/qrcode non installes")

    secret = pyotp.random_base32()

    # Save secret (not yet enabled)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE users SET otp_secret = ? WHERE username = ?",
            (secret, user["username"]),
        )
        await db.commit()

    # Generate QR code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user["username"], issuer_name="Download Manager")

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return SetupOTPResponse(secret=secret, qr_code=qr_b64)


@router.post("/verify-otp")
async def verify_otp(body: VerifyOTPRequest, user=Depends(get_current_user)):
    """Verify OTP code and enable 2FA."""
    if user["username"] == "anonymous":
        raise HTTPException(status_code=403, detail="Auth non activee")

    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=500, detail="Module pyotp non installe")

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT otp_secret FROM users WHERE username = ?", (user["username"],)
        )
        row = await cursor.fetchone()

    if not row or not row["otp_secret"]:
        raise HTTPException(status_code=400, detail="OTP non configure. Appelez /setup-otp d'abord")

    totp = pyotp.TOTP(row["otp_secret"])
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Code OTP invalide")

    # Enable 2FA
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE users SET otp_enabled = 1 WHERE username = ?",
            (user["username"],),
        )
        await db.commit()

    return {"status": "enabled", "message": "2FA activee avec succes"}


@router.post("/disable-otp")
async def disable_otp(body: VerifyOTPRequest, user=Depends(get_current_user)):
    """Disable 2FA (requires current OTP code)."""
    if user["username"] == "anonymous":
        raise HTTPException(status_code=403, detail="Auth non activee")

    try:
        import pyotp
    except ImportError:
        raise HTTPException(status_code=500, detail="Module pyotp non installe")

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT otp_secret, otp_enabled FROM users WHERE username = ?", (user["username"],)
        )
        row = await cursor.fetchone()

    if not row or not row["otp_enabled"]:
        raise HTTPException(status_code=400, detail="2FA n'est pas activee")

    totp = pyotp.TOTP(row["otp_secret"])
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Code OTP invalide")

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE users SET otp_enabled = 0, otp_secret = NULL WHERE username = ?",
            (user["username"],),
        )
        await db.commit()

    return {"status": "disabled", "message": "2FA desactivee"}


@router.get("/user-info")
async def user_info(user=Depends(get_current_user)):
    """Get current user info including OTP status."""
    if user["username"] == "anonymous":
        return {"username": "anonymous", "otp_enabled": False}

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT username, otp_enabled FROM users WHERE username = ?", (user["username"],)
        )
        row = await cursor.fetchone()

    if not row:
        return {"username": user["username"], "otp_enabled": False}

    return {"username": row["username"], "otp_enabled": bool(row["otp_enabled"])}
