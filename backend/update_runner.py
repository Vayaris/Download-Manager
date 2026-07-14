#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml


INSTALL_DIR = Path("/opt/download-manager")
CONFIG_FILE = Path("/etc/download-manager/config.yml")
DB_FILE = INSTALL_DIR / "config" / "downloads.db"
STATE_DIR = Path("/var/lib/download-manager")
BACKUP_DIR = Path("/var/backups/download-manager")
STATUS_FILE = STATE_DIR / "update-status.json"


def write_status(job_id: str, state: str, message: str, **extra):
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "job_id": job_id,
        "state": state,
        "message": message[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True))
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATUS_FILE)


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 180, check: bool = True):
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{command[0]} failed: {detail[:400]}")
    return result


def sync_runtime(git_dir: Path):
    if git_dir == INSTALL_DIR:
        return
    for name in ("backend", "frontend"):
        target = INSTALL_DIR / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(git_dir / name, target)
    for name in ("VERSION", "start.sh", "requirements.txt"):
        source = git_dir / name
        if source.exists():
            shutil.copy2(source, INSTALL_DIR / name)


def backup(job_id: str, git_dir: Path) -> tuple[Path, str]:
    target = BACKUP_DIR / job_id
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    previous_commit = run(["git", "rev-parse", "HEAD"], cwd=git_dir).stdout.strip()
    (target / "previous-commit").write_text(previous_commit)
    if CONFIG_FILE.exists():
        shutil.copy2(CONFIG_FILE, target / "config.yml")
    if DB_FILE.exists():
        shutil.copy2(DB_FILE, target / "downloads.db")
    if git_dir != INSTALL_DIR:
        shutil.copytree(INSTALL_DIR / "backend", target / "backend")
        shutil.copytree(INSTALL_DIR / "frontend", target / "frontend")
        for name in ("VERSION", "start.sh", "requirements.txt"):
            source = INSTALL_DIR / name
            if source.exists():
                shutil.copy2(source, target / name)
    backups = sorted((p for p in BACKUP_DIR.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[3:]:
        shutil.rmtree(old, ignore_errors=True)
    return target, previous_commit


def install_dependencies():
    pip = INSTALL_DIR / "venv" / "bin" / "pip"
    requirements = INSTALL_DIR / "requirements.txt"
    if pip.exists() and requirements.exists():
        run([str(pip), "install", "--quiet", "-r", str(requirements)], timeout=300)
    start = INSTALL_DIR / "start.sh"
    if start.exists():
        os.chmod(start, 0o755)


def install_target(git_dir: Path, tag: str, expected_commit: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag or ""):
        raise RuntimeError("invalid release tag")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit or ""):
        raise RuntimeError("invalid release commit")
    run(
        ["git", "fetch", "--force", "origin", f"refs/tags/{tag}:refs/tags/{tag}"],
        cwd=git_dir,
        timeout=120,
    )
    resolved = run(["git", "rev-list", "-n", "1", tag], cwd=git_dir).stdout.strip()
    if resolved.lower() != expected_commit.lower():
        raise RuntimeError("release tag does not match the commit announced by GitHub")
    run(["git", "reset", "--hard", resolved], cwd=git_dir)
    return resolved


def healthy(expected_version: str, timeout: int = 90) -> bool:
    port = 40320
    try:
        port = int((yaml.safe_load(CONFIG_FILE.read_text()) or {}).get("server", {}).get("port", port))
    except Exception:
        pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = run(["systemctl", "is-active", "download-manager"], check=False, timeout=10)
        if active.returncode == 0:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auth/status", timeout=3) as response:
                    if response.status == 200:
                        installed = (INSTALL_DIR / "VERSION").read_text().strip()
                        if not expected_version or installed == expected_version:
                            return True
            except Exception:
                pass
        time.sleep(2)
    return False


def rollback(git_dir: Path, target: Path, previous_commit: str):
    run(["systemctl", "stop", "download-manager"], check=False, timeout=30)
    run(["git", "reset", "--hard", previous_commit], cwd=git_dir)
    if (target / "config.yml").exists():
        shutil.copy2(target / "config.yml", CONFIG_FILE)
    if (target / "downloads.db").exists():
        shutil.copy2(target / "downloads.db", DB_FILE)
    if git_dir != INSTALL_DIR and (target / "backend").exists():
        for name in ("backend", "frontend"):
            current = INSTALL_DIR / name
            if current.exists():
                shutil.rmtree(current)
            shutil.copytree(target / name, current)
        for name in ("VERSION", "start.sh", "requirements.txt"):
            if (target / name).exists():
                shutil.copy2(target / name, INSTALL_DIR / name)
    else:
        sync_runtime(git_dir)
    install_dependencies()
    run(["systemctl", "restart", "download-manager"], timeout=30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--git-dir", required=True)
    parser.add_argument("--expected-version", default="")
    parser.add_argument("--expected-tag", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    git_dir = Path(args.git_dir).resolve()
    target = None
    previous_commit = ""
    try:
        time.sleep(2)
        write_status(args.job_id, "backing_up", "Creating update backup")
        run(["systemctl", "stop", "download-manager"], timeout=30)
        target, previous_commit = backup(args.job_id, git_dir)
        write_status(args.job_id, "installing", "Installing the new version", previous_commit=previous_commit)
        installed_commit = install_target(git_dir, args.expected_tag, args.expected_commit)
        sync_runtime(git_dir)
        install_dependencies()
        run(["systemctl", "restart", "download-manager"], timeout=30)
        write_status(args.job_id, "checking", "Checking service health")
        if not healthy(args.expected_version):
            raise RuntimeError("new service did not pass its health check")
        write_status(
            args.job_id,
            "success",
            "Update installed successfully",
            version=args.expected_version,
            commit=installed_commit,
        )
    except Exception as exc:
        if target and previous_commit:
            try:
                write_status(args.job_id, "rolling_back", str(exc))
                rollback(git_dir, target, previous_commit)
                previous_version = (INSTALL_DIR / "VERSION").read_text().strip()
                if healthy(previous_version, timeout=60):
                    write_status(args.job_id, "rolled_back", f"Update failed and was rolled back: {exc}", version=previous_version)
                    return
                raise RuntimeError("rollback service failed its health check")
            except Exception as rollback_exc:
                write_status(args.job_id, "failed", f"Update failed: {exc}; rollback failed: {rollback_exc}")
                return
        write_status(args.job_id, "failed", f"Update failed before backup: {exc}")
        run(["systemctl", "restart", "download-manager"], check=False, timeout=30)


if __name__ == "__main__":
    main()
