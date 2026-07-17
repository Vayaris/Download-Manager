import asyncio
import hashlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path


DENO_VERSION = "2.9.3"
DENO_ROOT = Path("/opt/download-manager/tools/deno")
DENO_BIN = DENO_ROOT / "deno"
DENO_ASSETS = {
    "x86_64": (
        "deno-x86_64-unknown-linux-gnu.zip",
        "8101865641cbede56f08ad19c0a67a87df84bce127fee0d3e3e1f7467717ffa6",
    ),
    "aarch64": (
        "deno-aarch64-unknown-linux-gnu.zip",
        "753937db98a4b56cbbbd26e8f00eb4b789191a229afec93f74bcfa4e79bc2c8b",
    ),
}

_install_task: asyncio.Task | None = None
_install_error = ""


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
        return (result.stdout or result.stderr).splitlines()[0][:120]
    except Exception:
        return ""


def ffmpeg_path() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if Path(bundled).is_file() else ""
    except (ImportError, RuntimeError, OSError):
        return ""


def runtime_options() -> dict:
    """Return the shared yt-dlp runtime configuration for analysis and downloads."""
    options = {}
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    if DENO_BIN.is_file():
        options["js_runtimes"] = {"deno": {"path": str(DENO_BIN)}}
    return options


def friendly_error(message: str) -> str:
    text = str(message or "YouTube operation failed")
    lower = text.lower()
    if "confirm you’re not a bot" in lower or "confirm you're not a bot" in lower:
        return "YouTube requires valid cookies for this video. Import or renew cookies.txt in Settings > YouTube"
    if "sign in to confirm your age" in lower:
        return "This age-restricted video requires valid cookies. Import or renew cookies.txt in Settings > YouTube"
    return text[-500:]


def status() -> dict:
    try:
        yt_dlp_version = importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        yt_dlp_version = ""
    ffmpeg = ffmpeg_path()
    deno = str(DENO_BIN) if DENO_BIN.is_file() else ""
    installing = bool(_install_task and not _install_task.done())
    return {
        "ready": bool(yt_dlp_version and ffmpeg and deno),
        "installing": installing,
        "error": _install_error,
        "yt_dlp": {"available": bool(yt_dlp_version), "version": yt_dlp_version},
        "ffmpeg": {"available": bool(ffmpeg), "version": _version([ffmpeg, "-version"]) if ffmpeg else ""},
        "deno": {"available": bool(deno), "version": _version([deno, "--version"]) if deno else ""},
    }


def _install_sync():
    if os.geteuid() != 0:
        raise RuntimeError("The Download Manager service must run as root to install its local tools")
    if not ffmpeg_path():
        raise RuntimeError("The bundled Download Manager ffmpeg is unavailable")
    machine = platform.machine().lower()
    if machine not in DENO_ASSETS:
        raise RuntimeError(f"Unsupported architecture for Deno: {machine}")
    asset, expected = DENO_ASSETS[machine]
    url = f"https://github.com/denoland/deno/releases/download/v{DENO_VERSION}/{asset}"
    with tempfile.TemporaryDirectory(prefix="dm-deno-") as temp:
        archive = Path(temp) / asset
        with urllib.request.urlopen(url, timeout=120) as response, open(archive, "wb") as output:  # nosec B310
            shutil.copyfileobj(response, output)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError("Deno archive checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            if set(bundle.namelist()) != {"deno"}:
                raise RuntimeError("Unexpected Deno archive content")
            DENO_ROOT.mkdir(parents=True, exist_ok=True)
            os.chmod(DENO_ROOT, 0o700)
            extracted = Path(temp) / "deno"
            bundle.extract("deno", temp)
            os.chmod(extracted, 0o700)
            os.replace(extracted, DENO_BIN)
    if not status()["ready"]:
        raise RuntimeError("YouTube dependencies did not pass their health check")


async def _run_install():
    global _install_error
    _install_error = ""
    try:
        await asyncio.to_thread(_install_sync)
    except Exception as exc:
        _install_error = str(exc)[:300]


def start_install() -> dict:
    global _install_task
    if _install_task and not _install_task.done():
        return status()
    _install_task = asyncio.create_task(_run_install())
    return status()
