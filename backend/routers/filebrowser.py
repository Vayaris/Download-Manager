import re
from fastapi import APIRouter, Depends, Query, HTTPException
from pathlib import Path

from auth import get_current_user
from config import get_config
from models import MkdirRequest

router = APIRouter()


def _get_allowed_roots() -> list:
    """Get list of allowed browseable paths from config."""
    cfg = get_config()
    allowed = [Path(p).resolve() for p in cfg["downloads"].get("allowed_paths", [])]
    default_dest = cfg["downloads"].get("default_destination", "")
    if default_dest:
        allowed.append(Path(default_dest).resolve())
    # Also include SMB mount points (mounted or not, so user can navigate to them)
    try:
        from services.smb import get_all_mount_points
        for mp in get_all_mount_points():
            allowed.append(Path(mp).resolve())
    except Exception:
        pass
    if not allowed:
        allowed.append(Path("/").resolve())
    return allowed


def _is_path_allowed(target: Path, allowed_roots: list) -> bool:
    """Check if target path is within an allowed root or is a parent of one."""
    target = target.resolve()
    for root in allowed_roots:
        # target is inside an allowed root
        try:
            target.relative_to(root)
            return True
        except ValueError:
            pass
        # target is a parent of an allowed root (needed for navigation)
        try:
            root.relative_to(target)
            return True
        except ValueError:
            pass
    return False


@router.get("/browse")
async def browse(path: str = Query(default="/"), _=Depends(get_current_user)):
    try:
        target = Path(path).resolve()
        allowed_roots = _get_allowed_roots()

        if not _is_path_allowed(target, allowed_roots):
            return {"path": str(target), "directories": [], "breadcrumbs": [], "parent": None,
                    "error": "Access denied for this path"}

        if not target.exists() or not target.is_dir():
            return {"path": str(target), "directories": [], "breadcrumbs": [], "parent": None,
                    "error": "Folder not found"}

        dirs = []
        try:
            for item in sorted(target.iterdir()):
                if not item.is_dir() or item.name.startswith("."):
                    continue
                try:
                    has_children = any(
                        x.is_dir() and not x.name.startswith(".")
                        for x in item.iterdir()
                    )
                    dirs.append({"name": item.name, "path": str(item), "has_children": has_children})
                except PermissionError:
                    dirs.append({"name": item.name, "path": str(item), "has_children": False, "restricted": True})
        except PermissionError:
            pass

        # Breadcrumbs
        parts = target.parts
        breadcrumbs = [
            {"name": p, "path": str(Path(*parts[: i + 1]))}
            for i, p in enumerate(parts)
        ]

        return {
            "path": str(target),
            "parent": str(target.parent) if target != target.parent else None,
            "directories": dirs,
            "breadcrumbs": breadcrumbs,
        }
    except Exception as e:
        return {"path": path, "directories": [], "breadcrumbs": [], "parent": None, "error": str(e)}


@router.post("/mkdir")
async def mkdir(body: MkdirRequest, _=Depends(get_current_user)):
    # Validate folder name
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")

    # Block dangerous characters
    if re.search(r'[/\\<>:"|?*\x00-\x1f]', name):
        raise HTTPException(status_code=400, detail="Name contains invalid characters")

    if name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid folder name")

    parent = Path(body.path).resolve()
    allowed_roots = _get_allowed_roots()
    if not _is_path_allowed(parent, allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied for this path")
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent folder does not exist")

    new_dir = parent / name
    if new_dir.exists():
        raise HTTPException(status_code=400, detail="Folder already exists")

    try:
        new_dir.mkdir(parents=False, exist_ok=False)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "created", "path": str(new_dir)}
