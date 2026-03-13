"""SMB/CIFS share mounting service."""
import subprocess
from pathlib import Path
from config import get_config


def _get_smb_shares() -> list:
    cfg = get_config()
    return cfg.get("smb_shares", [])


def is_mounted(mount_point: str) -> bool:
    """Check if a path is currently a mount point."""
    mp = str(Path(mount_point).resolve())
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mp:
                    return True
    except Exception:
        pass
    return False


def mount_share(share: dict) -> tuple:
    """Mount an SMB share. Returns (success: bool, message: str)."""
    mp = share.get("mount_point", "")
    if not mp:
        return False, "No mount point configured"

    Path(mp).mkdir(parents=True, exist_ok=True)

    if is_mounted(mp):
        return True, "Already mounted"

    host = share.get("host", "")
    share_name = share.get("share", "")
    username = share.get("username", "")
    password = share.get("password", "")

    opts = ["uid=0", "gid=0", "iocharset=utf8", "vers=3.0,2.1,2.0"]
    if username:
        opts.append(f"username={username}")
        if password:
            opts.append(f"password={password}")
    else:
        opts.append("guest")

    cmd = ["mount", "-t", "cifs", f"//{host}/{share_name}", mp, "-o", ",".join(opts)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            return True, "Mounted successfully"
        err = (result.stderr or result.stdout or "").strip()
        return False, err or "Mount failed (unknown error)"
    except subprocess.TimeoutExpired:
        return False, "Mount timed out (20s)"
    except Exception as e:
        return False, str(e)


def unmount_share(mount_point: str) -> tuple:
    """Unmount an SMB share. Returns (success: bool, message: str)."""
    if not mount_point:
        return True, "No mount point"
    if not is_mounted(mount_point):
        return True, "Not mounted"
    try:
        result = subprocess.run(["umount", mount_point], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, "Unmounted"
        err = (result.stderr or "").strip()
        return False, err or "Unmount failed"
    except Exception as e:
        return False, str(e)


def mount_all_auto():
    """Mount all shares with auto_mount=True. Called on service startup."""
    for share in _get_smb_shares():
        if share.get("auto_mount", False):
            mount_share(share)


def get_all_mount_points() -> list:
    """Return mount points of all configured SMB shares."""
    return [s["mount_point"] for s in _get_smb_shares() if s.get("mount_point")]
