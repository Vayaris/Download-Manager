from pydantic import BaseModel
from typing import Optional, List


class AddDownloadsRequest(BaseModel):
    urls: List[str]
    destination: str


class AddPackageRequest(BaseModel):
    name: str
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
    download_segments: Optional[int] = None
    speed_limit: Optional[int] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    webhook_format: Optional[str] = None
    webhook_events: Optional[List[str]] = None


class LoginRequest(BaseModel):
    username: str
    password: str
    otp_code: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    otp_required: bool = False


class SetupAdminRequest(BaseModel):
    username: str
    password: str


class SetupOTPResponse(BaseModel):
    secret: str
    qr_code: str  # base64 PNG


class VerifyOTPRequest(BaseModel):
    code: str


class MkdirRequest(BaseModel):
    path: str
    name: str


class MagnetUploadRequest(BaseModel):
    magnets: List[str]
    destination: str


class StoragePathRequest(BaseModel):
    path: str
