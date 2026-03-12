from pathlib import Path
from fastapi import HTTPException
from config import get_config


def validate_destination(dest: str):
    """Validate download destination is within allowed paths."""
    if not dest:
        return
    cfg = get_config()
    resolved = Path(dest).resolve()
    allowed = [Path(p).resolve() for p in cfg["downloads"].get("allowed_paths", [])]
    default_dest = cfg["downloads"].get("default_destination", "")
    if default_dest:
        allowed.append(Path(default_dest).resolve())
    if not allowed:
        return  # No restrictions configured
    for a in allowed:
        try:
            resolved.relative_to(a)
            return
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Destination not allowed")
