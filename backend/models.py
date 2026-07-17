from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class AddDownloadsRequest(BaseModel):
    urls: List[str] = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=4096)


class AddPackageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    urls: List[str] = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=4096)


class BulkActionRequest(BaseModel):
    action: str  # pause_all | resume_all | clear_completed


class ReorderRequest(BaseModel):
    ids: List[str] = Field(max_length=500)


class DuplicateDecision(BaseModel):
    source_id: str
    action: str
    confirm_overwrite: bool = False


class DuplicateCommitRequest(BaseModel):
    decisions: List[DuplicateDecision] = Field(default_factory=list, max_length=100)


class DuplicateResolutionRequest(BaseModel):
    action: str
    confirm_overwrite: bool = False


class HistoryRemoveRequest(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=500)


class SettingsUpdate(BaseModel):
    alldebrid_api_key: Optional[str] = None
    alldebrid_enabled: Optional[bool] = None
    simultaneous_downloads: Optional[int] = None
    default_destination: Optional[str] = None
    download_segments: Optional[int] = None
    speed_limit: Optional[int] = None
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    skip_nfo_files: Optional[bool] = None
    stalled_timeout_hours: Optional[int] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    webhook_format: Optional[str] = None
    webhook_events: Optional[List[str]] = None
    youtube_direct_enabled: Optional[bool] = None
    youtube_max_concurrent: Optional[int] = None
    youtube_speed_limit: Optional[int] = None


class YouTubeAnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    content_filter: Literal["videos", "shorts", "both"] = "both"
    expand_playlist: bool = True


class YouTubeSubmitRequest(BaseModel):
    selected_ids: List[str] = Field(min_length=1, max_length=500)
    destination: str = Field(min_length=1, max_length=4096)
    engine: Literal["alldebrid", "youtube"] = "alldebrid"
    output_profile: Literal["mp4", "mkv_multi"] = "mp4"
    package_name: str = Field(default="", max_length=160)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)
    otp_code: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    otp_required: bool = False


class SetupAdminRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class SetupOTPResponse(BaseModel):
    secret: str
    qr_code: str  # base64 PNG


class VerifyOTPRequest(BaseModel):
    code: str


class UserPreferencesRequest(BaseModel):
    ui_style: Literal["classic", "modern"]


class MkdirRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=255)


class FileBrowserPathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class FileBrowserReorderRequest(BaseModel):
    paths: List[str] = Field(max_length=50)


class MagnetUploadRequest(BaseModel):
    magnets: List[str] = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=4096)


class StoragePathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class MediaSettingsRequest(BaseModel):
    provider: Optional[str] = None
    enabled: Optional[bool] = None
    url: Optional[str] = None
    token: Optional[str] = None
    favorite_keys: Optional[List[str]] = None
    auto_refresh_enabled: Optional[bool] = None


class SignalCheckRequest(BaseModel):
    host: str
    port: int


class SignalDeployRequest(BaseModel):
    port: int


class SignalRegisterRequest(BaseModel):
    host: str
    port: int
    number: str
    captcha: str


class SignalVerifyRequest(BaseModel):
    host: str
    port: int
    number: str
    code: str


class SignalResetRequest(BaseModel):
    host: str = "localhost"
    port: int = 8080
    number: str = ""
