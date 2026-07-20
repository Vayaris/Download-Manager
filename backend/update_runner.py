#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_URL = "https://github.com/Vayaris/Download-Manager.git"
INSTALL_DIR = Path("/opt/download-manager")
CONFIG_FILE = Path("/etc/download-manager/config.yml")
DB_FILE = INSTALL_DIR / "config" / "downloads.db"
STATE_DIR = Path("/var/lib/download-manager")
REPOSITORY_DIR = STATE_DIR / "repository.git"
RELEASES_DIR = INSTALL_DIR / "releases"
VENVS_DIR = INSTALL_DIR / "venvs"
CURRENT_LINK = INSTALL_DIR / "current"
VENV_LINK = INSTALL_DIR / "venv"
BACKUP_DIR = Path("/var/backups/download-manager")
STATUS_FILE = STATE_DIR / "update-status.json"
SYSTEMD_DIR = Path("/etc/systemd/system")
UNIT_NAMES = ("download-manager-aria2.service", "download-manager.service")


def write_status(job_id: str, state: str, message: str, **extra):
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "job_id": job_id,
        "state": state,
        "message": message[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True))
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATUS_FILE)


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 300, check: bool = True):
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{command[0]} failed: {detail[:500]}")
    return result


def backup_database(source: Path, destination: Path):
    """Create a consistent SQLite snapshot, including committed WAL pages."""
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    os.chmod(destination, 0o600)


def _link_target(path: Path) -> str:
    return str(path.resolve()) if path.exists() or path.is_symlink() else ""


def backup(job_id: str) -> tuple[Path, dict]:
    target = BACKUP_DIR / job_id
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    previous_release = _link_target(CURRENT_LINK)
    if not previous_release and (INSTALL_DIR / "backend" / "main.py").is_file():
        previous_release = str(INSTALL_DIR)
    previous = {"release": previous_release, "venv": _link_target(VENV_LINK)}
    (target / "previous.json").write_text(json.dumps(previous))
    os.chmod(target / "previous.json", 0o600)
    if CONFIG_FILE.exists():
        shutil.copy2(CONFIG_FILE, target / "config.yml")
    if DB_FILE.exists():
        backup_database(DB_FILE, target / "downloads.db")
    units = target / "systemd"
    units.mkdir(mode=0o700)
    for name in UNIT_NAMES:
        source = SYSTEMD_DIR / name
        if source.exists():
            shutil.copy2(source, units / name)
    return target, previous


def ensure_repository():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not REPOSITORY_DIR.exists():
        run(["git", "clone", "--mirror", REPO_URL, str(REPOSITORY_DIR)], timeout=180)
    run(
        ["git", f"--git-dir={REPOSITORY_DIR}", "fetch", "--force", "--prune", "origin", "+refs/tags/*:refs/tags/*"],
        timeout=180,
    )


def _validate_release(tag: str, expected_commit: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag or ""):
        raise RuntimeError("invalid release tag")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit or ""):
        raise RuntimeError("invalid release commit")
    resolved = run(
        ["git", f"--git-dir={REPOSITORY_DIR}", "rev-list", "-n", "1", tag]
    ).stdout.strip()
    if resolved.lower() != expected_commit.lower():
        raise RuntimeError("release tag does not match the commit announced by GitHub")
    return resolved


def _safe_extract(archive: Path, destination: Path):
    root = destination.resolve()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise RuntimeError("release archive contains an unsupported entry")
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("release archive contains an unsafe path")
        bundle.extractall(destination)  # nosec B202 - paths are validated above


def prepare_release(job_id: str, tag: str, expected_commit: str) -> tuple[Path, str]:
    ensure_repository()
    commit = _validate_release(tag, expected_commit)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    staging = RELEASES_DIR / f".{tag}-{job_id}.staging"
    final = RELEASES_DIR / tag
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(mode=0o755)
    archive = staging / ".release.tar"
    run([
        "git", f"--git-dir={REPOSITORY_DIR}", "archive", "--format=tar",
        f"--output={archive}", commit,
    ])
    _safe_extract(archive, staging)
    archive.unlink()
    if (staging / "VERSION").read_text().strip() != tag.removeprefix("v"):
        raise RuntimeError("release VERSION does not match its tag")
    for required in ("backend/main.py", "frontend/index.html", "requirements.txt", "start.sh", "start-aria2.sh"):
        if not (staging / required).exists():
            raise RuntimeError(f"release is missing {required}")
    if final.exists():
        shutil.rmtree(final)
    os.replace(staging, final)
    return final, commit


def prepare_venv(job_id: str, tag: str, release: Path) -> Path:
    VENVS_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    staging = VENVS_DIR / f".{tag}-{job_id}.staging"
    final = VENVS_DIR / tag
    if staging.exists():
        shutil.rmtree(staging)
    run([sys.executable, "-m", "venv", str(staging)], timeout=120)
    run([
        str(staging / "bin" / "pip"), "install", "--quiet", "--disable-pip-version-check",
        "-r", str(release / "requirements.txt"),
    ], timeout=600)
    run([str(staging / "bin" / "python"), "-m", "compileall", "-q", str(release / "backend")])
    if final.exists():
        shutil.rmtree(final)
    os.replace(staging, final)
    return final


def atomic_symlink(target: Path, link: Path, job_id: str):
    temporary = link.with_name(f".{link.name}-{job_id}.tmp")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    os.symlink(str(target), temporary)
    os.replace(temporary, link)


def migrate_legacy_runtime(previous: dict, backup_dir: Path, job_id: str):
    """Preserve pre-v2.1.1 directory layouts before creating atomic links."""
    if VENV_LINK.is_dir() and not VENV_LINK.is_symlink():
        legacy_venv = VENVS_DIR / f"legacy-{job_id}"
        if legacy_venv.exists():
            raise RuntimeError("legacy virtualenv backup path already exists")
        shutil.move(str(VENV_LINK), str(legacy_venv))
        previous["venv"] = str(legacy_venv)
        (backup_dir / "previous.json").write_text(json.dumps(previous))
        os.chmod(backup_dir / "previous.json", 0o600)


def install_units(release: Path):
    source_dir = release / "deploy" / "systemd"
    for name in UNIT_NAMES:
        source = source_dir / name
        if not source.is_file():
            raise RuntimeError(f"release is missing systemd unit {name}")
        shutil.copy2(source, SYSTEMD_DIR / name)
        os.chmod(SYSTEMD_DIR / name, 0o644)
    verify = run(["systemd-analyze", "verify", *(str(SYSTEMD_DIR / name) for name in UNIT_NAMES)], check=False)
    if verify.returncode != 0:
        raise RuntimeError(f"systemd unit verification failed: {(verify.stderr or verify.stdout)[:500]}")
    run(["systemctl", "daemon-reload"], timeout=30)


def _runtime_port_and_secret() -> tuple[int, str]:
    config = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    return (
        int(config.get("server", {}).get("port", 40320)),
        str(config.get("aria2", {}).get("rpc_secret", "download-manager-secret")),
    )


def _aria2_healthy(port: int, secret: str) -> bool:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": "health", "method": "aria2.getVersion",
        "params": [f"token:{secret}"],
    }).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/jsonrpc", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # nosec B310 - fixed loopback URL
            return response.status == 200 and "result" in json.loads(response.read())
    except Exception:
        return False


def healthy(expected_version: str, timeout: int = 90) -> bool:
    try:
        app_port, secret = _runtime_port_and_secret()
        aria2_port = int((yaml.safe_load(CONFIG_FILE.read_text()) or {}).get("aria2", {}).get("rpc_port", 6800))
    except Exception:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        installed_units = [name for name in UNIT_NAMES if (SYSTEMD_DIR / name).is_file()]
        services_ok = bool(installed_units) and all(
            run(["systemctl", "is-active", name], check=False, timeout=10).returncode == 0
            for name in installed_units
        )
        if services_ok and _aria2_healthy(aria2_port, secret):
            try:
                with urllib.request.urlopen(  # nosec B310 - fixed loopback URL
                    f"http://127.0.0.1:{app_port}/api/auth/status", timeout=3
                ) as response:
                    version_file = CURRENT_LINK / "VERSION"
                    if not version_file.is_file():
                        version_file = INSTALL_DIR / "VERSION"
                    installed = version_file.read_text().strip()
                    if response.status == 200 and installed == expected_version:
                        return True
            except Exception:
                pass
        time.sleep(2)
    return False


def _restore_units(backup_dir: Path):
    saved = backup_dir / "systemd"
    for name in UNIT_NAMES:
        source = saved / name
        target = SYSTEMD_DIR / name
        if source.exists():
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    run(["systemctl", "daemon-reload"], timeout=30)


def rollback(job_id: str, backup_dir: Path, previous: dict):
    run(["systemctl", "stop", "download-manager.service", "download-manager-aria2.service"], check=False, timeout=30)
    if previous.get("release"):
        previous_release = Path(previous["release"])
        if previous_release == INSTALL_DIR:
            try:
                CURRENT_LINK.unlink()
            except FileNotFoundError:
                pass
        else:
            atomic_symlink(previous_release, CURRENT_LINK, job_id)
    if previous.get("venv"):
        atomic_symlink(Path(previous["venv"]), VENV_LINK, job_id)
    if (backup_dir / "config.yml").exists():
        shutil.copy2(backup_dir / "config.yml", CONFIG_FILE)
    if (backup_dir / "downloads.db").exists():
        for suffix in ("-wal", "-shm"):
            try:
                Path(f"{DB_FILE}{suffix}").unlink()
            except FileNotFoundError:
                pass
        shutil.copy2(backup_dir / "downloads.db", DB_FILE)
    _restore_units(backup_dir)
    restored_units = [name for name in UNIT_NAMES if (SYSTEMD_DIR / name).is_file()]
    if not restored_units:
        raise RuntimeError("rollback restored no Download Manager service unit")
    run(["systemctl", "restart", *restored_units], timeout=30)


def cleanup_versions(current_release: Path, current_venv: Path):
    for root, current in ((RELEASES_DIR, current_release), (VENVS_DIR, current_venv)):
        candidates = sorted(
            (path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        keep = {current.resolve(), *(path.resolve() for path in candidates[:2])}
        for old in candidates:
            if old.resolve() not in keep:
                shutil.rmtree(old, ignore_errors=True)


def cleanup_backups(current_backup: Path):
    backups = sorted(
        (path for path in BACKUP_DIR.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    keep = {current_backup.resolve(), *(path.resolve() for path in backups[:3])}
    for old in backups:
        if old.resolve() not in keep:
            shutil.rmtree(old, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-tag", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    backup_dir = None
    previous = None
    try:
        write_status(args.job_id, "preparing", "Preparing verified release and isolated dependencies")
        release, commit = prepare_release(args.job_id, args.expected_tag, args.expected_commit)
        venv = prepare_venv(args.job_id, args.expected_tag, release)
        write_status(args.job_id, "backing_up", "Creating update backup")
        backup_dir, previous = backup(args.job_id)
        write_status(args.job_id, "installing", "Switching to the prepared release")
        run(["systemctl", "stop", "download-manager.service", "download-manager-aria2.service"], check=False, timeout=30)
        migrate_legacy_runtime(previous, backup_dir, args.job_id)
        atomic_symlink(release, CURRENT_LINK, args.job_id)
        atomic_symlink(venv, VENV_LINK, args.job_id)
        install_units(release)
        run(["systemctl", "enable", "download-manager-aria2.service", "download-manager.service"], timeout=30)
        run(["systemctl", "restart", "download-manager-aria2.service", "download-manager.service"], timeout=30)
        write_status(args.job_id, "checking", "Checking FastAPI and aria2 health")
        if not healthy(args.expected_version):
            raise RuntimeError("new release did not pass the FastAPI and aria2 health checks")
        cleanup_versions(release, venv)
        cleanup_backups(backup_dir)
        write_status(
            args.job_id, "success", "Update installed successfully",
            version=args.expected_version, commit=commit,
        )
        return 0
    except Exception as exc:
        if backup_dir and previous:
            try:
                write_status(args.job_id, "rolling_back", str(exc))
                rollback(args.job_id, backup_dir, previous)
                previous_version = (CURRENT_LINK / "VERSION").read_text().strip()
                if healthy(previous_version, timeout=60):
                    write_status(
                        args.job_id, "rolled_back",
                        f"Update failed and was rolled back: {exc}", version=previous_version,
                    )
                    return 1
                raise RuntimeError("rollback services failed their health checks")
            except Exception as rollback_exc:
                write_status(args.job_id, "failed", f"Update failed: {exc}; rollback failed: {rollback_exc}")
                return 1
        write_status(args.job_id, "failed", f"Update failed before runtime switch: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
