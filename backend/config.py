import yaml
import os
import secrets
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("DM_CONFIG", "/etc/download-manager/config.yml"))

DEFAULT_CONFIG = {
    "server": {
        "port": 40320,
        "host": "0.0.0.0"
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
        ]
    },
    "auth": {
        "enabled": False,
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
    }
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH, "r") as f:
        loaded = yaml.safe_load(f) or {}
    cfg = _deep_merge(DEFAULT_CONFIG.copy(), loaded)
    # Auto-generate JWT secret if missing
    if not cfg["auth"].get("jwt_secret"):
        cfg["auth"]["jwt_secret"] = secrets.token_hex(32)
        save_config(cfg)
    return cfg


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
