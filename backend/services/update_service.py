import json
import re
import secrets
import subprocess
from pathlib import Path

import httpx

from services.diagnostics import record_event_nowait

REPO = "Vayaris/Download-Manager"
INSTALL_DIR = Path("/opt/download-manager")
CURRENT_DIR = INSTALL_DIR / "current"
UPDATE_STATUS_FILE = Path("/var/lib/download-manager/update-status.json")


class UpdateError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def get_current_version() -> str:
    for directory in (CURRENT_DIR, INSTALL_DIR, Path(__file__).resolve().parents[2]):
        version_file = directory / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    return "0.0.0"


def parse_version_tag(value: str) -> tuple[int, int, int, int, int] | None:
    match = re.fullmatch(
        r"v?(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?",
        (value or "").strip(),
    )
    if not match:
        return None
    major, minor, patch, rc_number = match.groups()
    # A stable release sorts after every RC with the same numeric version.
    return int(major), int(minor), int(patch), 1 if rc_number is None else 0, int(rc_number or 0)


async def get_latest_github_version(client: httpx.AsyncClient) -> dict:
    response = await client.get(
        f"https://api.github.com/repos/{REPO}/tags",
        params={"per_page": 100},
        headers={"Accept": "application/vnd.github+json"},
    )
    if response.status_code != 200:
        raise UpdateError(f"GitHub error ({response.status_code})", 502)

    candidates = []
    for item in response.json():
        tag_name = str(item.get("name", ""))
        if "-rc." in tag_name.lower():
            continue
        version = parse_version_tag(tag_name)
        if version is not None:
            candidates.append((version, item))
    if not candidates:
        raise UpdateError("No valid version tag found", 502)

    version, item = max(candidates, key=lambda candidate: candidate[0])
    tag = str(item.get("name", "")).strip()
    commit_sha = str(item.get("commit", {}).get("sha", "")).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
        raise UpdateError("GitHub returned an invalid release commit", 502)

    changelog = ""
    release = await client.get(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
        headers={"Accept": "application/vnd.github+json"},
    )
    if release.status_code == 200:
        changelog = release.json().get("body", "") or ""
    return {
        "tag": tag,
        "version": ".".join(str(part) for part in version[:3]),
        "version_tuple": version,
        "commit_sha": commit_sha,
        "changelog": changelog,
    }


async def check_latest() -> dict:
    current = get_current_version()
    current_tuple = parse_version_tag(current)
    async with httpx.AsyncClient(timeout=15.0) as client:
        latest = await get_latest_github_version(client)
    available = current_tuple is not None and latest["version_tuple"] > current_tuple
    return {
        "update_available": available,
        "current": current,
        "latest": latest["version"],
        "latest_tag": latest["tag"],
        "changelog": latest["changelog"],
        "message": "Update available" if available else "Up to date",
    }


def read_update_status() -> dict:
    if not UPDATE_STATUS_FILE.exists():
        return {"state": "idle", "message": "No update has run yet"}
    try:
        return json.loads(UPDATE_STATUS_FILE.read_text())
    except (OSError, ValueError):
        return {"state": "unknown", "message": "Update status is unreadable"}


async def start_latest_update() -> dict:
    current = get_current_version()
    current_tuple = parse_version_tag(current)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            latest = await get_latest_github_version(client)
        if current_tuple is None or latest["version_tuple"] <= current_tuple:
            return {"success": True, "message": "Already up to date", "version": current, "changelog": ""}

        job_id = f"dm-{secrets.token_hex(6)}"
        runner = CURRENT_DIR / "backend" / "update_runner.py"
        if not runner.exists():
            runner = INSTALL_DIR / "backend" / "update_runner.py"
        command = [
            "systemd-run", "--quiet", f"--unit=download-manager-update-{job_id}",
            "--property=Type=exec", str(INSTALL_DIR / "venv" / "bin" / "python"),
            str(runner), "--job-id", job_id,
            "--expected-version", latest["version"],
            "--expected-tag", latest["tag"],
            "--expected-commit", latest["commit_sha"],
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "systemd-run failed").strip()
            raise UpdateError(f"Unable to start updater: {detail[:300]}")
        return {
            "success": True,
            "message": f"Update to v{latest['version']} started",
            "version": latest["version"],
            "changelog": latest["changelog"],
            "job_id": job_id,
        }
    except UpdateError:
        raise
    except Exception as exc:
        record_event_nowait("updates", "update_failed", exc)
        raise UpdateError("Internal error during update") from exc
