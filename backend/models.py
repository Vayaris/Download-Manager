from pydantic import BaseModel
from typing import Optional, List


class AddDownloadsRequest(BaseModel):
    urls: List[str]
    destination: str


class BulkActionRequest(BaseModel):
    action: str  # pause_all | resume_all | clear_completed


class ReorderRequest(BaseModel):
    ids: List[str]


class SettingsUpdate(BaseModel):
    alldebrid_api_key: Optional[str] = None
    alldebrid_enabled: Optional[bool] = None
    simultaneous_downloads: Optional[int] = None
    default_destination: Optional[str] = None
    auth_enabled: Optional[bool] = None
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
