from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext
from config import get_config
from database import open_db

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
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    token = credentials.credentials if credentials else request.cookies.get("dm_session", "")
    return await validate_access_token(token)


async def validate_access_token(token: str):
    db = await open_db(row_factory=True)
    try:
        cursor = await db.execute("SELECT COUNT(*) AS count FROM users")
        if (await cursor.fetchone())["count"] == 0:
            return {"username": "anonymous", "token_version": 0}
    finally:
        await db.close()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Check otp_verified claim if user has 2FA
        if payload.get("otp_required") and not payload.get("otp_verified"):
            raise HTTPException(status_code=401, detail="OTP verification required")
        db = await open_db(row_factory=True)
        try:
            cursor = await db.execute(
                "SELECT username, token_version FROM users WHERE username = ?",
                (username,),
            )
            user = await cursor.fetchone()
        finally:
            await db.close()
        if not user or int(payload.get("ver", -1)) != int(user["token_version"] or 0):
            raise HTTPException(status_code=401, detail="Session expired")
        return {"username": user["username"], "token_version": int(user["token_version"] or 0)}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
