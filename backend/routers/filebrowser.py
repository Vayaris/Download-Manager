import re
from fastapi import APIRouter, Depends, Query, HTTPException
from pathlib import Path

from auth import get_current_user
from models import MkdirRequest

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


@router.post("/mkdir")
async def mkdir(body: MkdirRequest, _=Depends(get_current_user)):
    # Validate folder name
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom du dossier ne peut pas etre vide")

    # Block dangerous characters
    if re.search(r'[/\\<>:"|?*\x00-\x1f]', name):
        raise HTTPException(status_code=400, detail="Le nom contient des caracteres invalides")

    if name in (".", ".."):
        raise HTTPException(status_code=400, detail="Nom de dossier invalide")

    parent = Path(body.path).resolve()
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=400, detail="Le dossier parent n'existe pas")

    new_dir = parent / name
    if new_dir.exists():
        raise HTTPException(status_code=400, detail="Ce dossier existe deja")

    try:
        new_dir.mkdir(parents=False, exist_ok=False)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission refusee")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "created", "path": str(new_dir)}
