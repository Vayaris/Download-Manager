import yaml
import copy
import os
import secrets
import threading
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("DM_CONFIG", "/etc/download-manager/config.yml"))

DEFAULT_CONFIG = {
    "server": {
        "port": 40320,
        # Intentional self-hosted LAN default; users can bind a narrower address.
        "host": "0.0.0.0"  # nosec B104
    },
    "alldebrid": {
        "api_key": "",
        "enabled": False
    },
    "downloads": {
        "simultaneous": 3,
        "default_destination": "/opt/download-manager/downloads",
        "allowed_paths": [
            "/mnt/media",
            "/opt/download-manager/downloads"
        ],
        "download_segments": 1,
        "speed_limit": 0,
        "max_retries": 3,
        "retry_delay_seconds": 5,
        "skip_nfo_files": True,
        "existing_file_check_enabled": True,
        "stalled_timeout_hours": 3
    },
    "auth": {
        "jwt_secret": "",
    },
    "aria2": {
        "rpc_port": 6800,
        "rpc_secret": "download-manager-secret"
    },
    "webhooks": {
        "enabled": False,
        "url": "",
        "format": "generic",
        "events": ["download_complete", "download_failed", "package_complete"]
    },
    "plex": {
        "enabled": False,
        "url": "http://127.0.0.1:32400",
        "token": "",
        "last_refreshes": {},
        "favorite_keys": [],
        "auto_refresh_enabled": False,
        "auto_refresh_enabled_at": None,
        "auto_refreshes": {},
        "auto_refresh_last_result": None
    },
    "jellyfin": {
        "enabled": False,
        "url": "http://127.0.0.1:8096",
        "token": "",
        "last_refreshes": {},
        "favorite_keys": [],
        "auto_refresh_enabled": False,
        "auto_refresh_enabled_at": None,
        "auto_refreshes": {},
        "auto_refresh_last_result": None,
        "path_mappings": []
    },
    "media": {
        "active": "plex"
    },
    "youtube": {
        "direct_enabled": False,
        "max_concurrent": 2,
        "speed_limit": 0
    }
}

_CONFIG_LOCK = threading.RLock()
_CONFIG_CACHE = None
_CONFIG_MTIME_NS = None


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _write_unlocked(config: dict):
    global _CONFIG_CACHE, _CONFIG_MTIME_NS
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_name(f".{CONFIG_PATH.name}.{os.getpid()}.tmp")
    with open(tmp_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, CONFIG_PATH)
    _CONFIG_CACHE = copy.deepcopy(config)
    _CONFIG_MTIME_NS = CONFIG_PATH.stat().st_mtime_ns


def _load_unlocked() -> dict:
    global _CONFIG_CACHE, _CONFIG_MTIME_NS
    mtime_ns = CONFIG_PATH.stat().st_mtime_ns if CONFIG_PATH.exists() else None
    if _CONFIG_CACHE is not None and mtime_ns == _CONFIG_MTIME_NS:
        return copy.deepcopy(_CONFIG_CACHE)

    loaded = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            loaded = yaml.safe_load(f) or {}
    cfg = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), loaded)
    if not cfg["auth"].get("jwt_secret"):
        cfg["auth"]["jwt_secret"] = secrets.token_hex(32)
        _write_unlocked(cfg)
    else:
        _CONFIG_CACHE = copy.deepcopy(cfg)
        _CONFIG_MTIME_NS = mtime_ns
    return copy.deepcopy(cfg)


def get_config() -> dict:
    with _CONFIG_LOCK:
        return _load_unlocked()


def save_config(config: dict):
    with _CONFIG_LOCK:
        _write_unlocked(copy.deepcopy(config))


def update_config(mutator):
    """Atomically load, mutate and persist configuration in this process."""
    with _CONFIG_LOCK:
        config = _load_unlocked()
        result = mutator(config)
        _write_unlocked(config)
        return copy.deepcopy(config), result
