from fastapi import APIRouter, Depends, Query
from pathlib import Path

from auth import get_current_user

router = APIRouter()


@router.get("/browse")
async def browse(path: str = Query(default="/"), _=Depends(get_current_user)):
    try:
        target = Path(path).resolve()

        if not target.exists() or not target.is_dir():
            return {"path": str(target), "directories": [], "breadcrumbs": [], "parent": None,
                    "error": "Dossier introuvable"}

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
