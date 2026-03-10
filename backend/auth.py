from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from config import get_config

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def _get_secret() -> str:
    return get_config()["auth"]["jwt_secret"]


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        (count,) = await cursor.fetchone()

    # No users yet — allow anonymous access for setup-admin
    if count == 0:
        return {"username": "anonymous"}

    # Users exist — require valid Bearer token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, _get_secret(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Check otp_verified claim if user has 2FA
        if payload.get("otp_required") and not payload.get("otp_verified"):
            raise HTTPException(status_code=401, detail="OTP verification required")
        return {"username": username}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
