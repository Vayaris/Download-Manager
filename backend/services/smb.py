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

    host      = share.get("host", "").strip()
    share_name = share.get("share", "").strip()
    username  = share.get("username", "").strip()
    password  = share.get("password", "").strip()
    domain    = share.get("domain", "").strip()
    vers      = share.get("vers", "").strip()   # e.g. "3.0", "2.1", "" = auto

    if not host or not share_name:
        return False, "Host and share name are required"

    # Build mount options
    opts = [
        "uid=0",
        "gid=0",
        "file_mode=0755",
        "dir_mode=0755",
        "_netdev",
    ]

    if username:
        opts.append(f"username={username}")
        if password:
            opts.append(f"password={password}")
    else:
        opts.append("guest")

    if domain:
        opts.append(f"domain={domain}")

    # Only set vers if explicitly chosen — no vers = kernel auto-negotiates
    if vers:
        opts.append(f"vers={vers}")

    cmd = ["mount", "-t", "cifs", f"//{host}/{share_name}", mp, "-o", ",".join(opts)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            return True, "Mounted successfully"
        err = (result.stderr or result.stdout or "").strip()
        # Provide helpful hint for common error codes
        hint = ""
        if "error(13)" in err:
            hint = " — Check username/password or enable guest access on the server"
        elif "error(2)" in err:
            hint = " — Share not found, check the share name"
        elif "error(111)" in err or "error(113)" in err:
            hint = " — Host unreachable, check IP address and network"
        elif "error(22)" in err:
            hint = " — Invalid argument: try setting SMB Version explicitly (e.g. 3.0 or 2.1)"
        return False, (err or "Mount failed") + hint
    except subprocess.TimeoutExpired:
        return False, "Mount timed out (20s) — check host IP and network connectivity"
    except FileNotFoundError:
        return False, "mount.cifs not found — install cifs-utils: apt-get install cifs-utils"
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
