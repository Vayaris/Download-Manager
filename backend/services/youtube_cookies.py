import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


COOKIE_PATH = Path(os.environ.get(
    "DM_YOUTUBE_COOKIES",
    "/opt/download-manager/config/youtube-cookies.txt",
))
MAX_COOKIE_FILE_SIZE = 1024 * 1024
COOKIE_HEADERS = ("# Netscape HTTP Cookie File", "# HTTP Cookie File")


def _is_youtube_domain(value: str) -> bool:
    domain = value.removeprefix("#HttpOnly_").lstrip(".").lower()
    return domain == "youtube.com" or domain.endswith(".youtube.com")


def _validated_content(content: bytes) -> bytes:
    if not content:
        raise ValueError("The cookies file is empty")
    if len(content) > MAX_COOKIE_FILE_SIZE:
        raise ValueError("The cookies file is limited to 1 MB")
    if b"\x00" in content:
        raise ValueError("The cookies file contains invalid data")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The cookies file must use UTF-8 encoding") from exc

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not any(line.startswith(COOKIE_HEADERS) for line in lines[:5]):
        raise ValueError("Export cookies in Netscape cookies.txt format")

    youtube_lines = []
    for line in lines:
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        fields = line.split("\t", 6)
        if len(fields) != 7 or not fields[5].strip():
            raise ValueError("The cookies.txt file contains an invalid cookie line")
        if _is_youtube_domain(fields[0]):
            youtube_lines.append(line)
    if not youtube_lines:
        raise ValueError("The file does not contain any YouTube cookies")
    return ("# Netscape HTTP Cookie File\n" + "\n".join(youtube_lines) + "\n").encode("utf-8")


def cookie_status() -> dict:
    try:
        stat = COOKIE_PATH.stat()
        configured = COOKIE_PATH.is_file() and stat.st_size > 0
    except OSError:
        return {"configured": False, "updated_at": None, "count": 0}
    count = 0
    if configured:
        try:
            count = sum(
                1 for line in COOKIE_PATH.read_text("utf-8").splitlines()
                if line and (not line.startswith("#") or line.startswith("#HttpOnly_"))
            )
        except (OSError, UnicodeDecodeError):
            configured = False
    return {
        "configured": configured,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if configured else None,
        "count": count if configured else 0,
    }


def save_cookies(content: bytes) -> dict:
    validated = _validated_content(content)
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(COOKIE_PATH.parent, 0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".youtube-cookies-", dir=COOKIE_PATH.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.chmod(temporary, 0o600)
            output.write(validated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, COOKIE_PATH)
        os.chmod(COOKIE_PATH, 0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return cookie_status()


def remove_cookies() -> dict:
    try:
        COOKIE_PATH.unlink()
    except FileNotFoundError:
        pass
    return cookie_status()


@contextmanager
def temporary_cookie_file():
    """Give each yt-dlp process a private copy to avoid concurrent cookie writes."""
    try:
        content = COOKIE_PATH.read_bytes()
    except OSError:
        content = b""
    if not content:
        yield None
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix="dm-youtube-cookies-", delete=False) as output:
            temporary = Path(output.name)
            os.chmod(temporary, 0o600)
            output.write(content)
        yield str(temporary)
    finally:
        if temporary:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
