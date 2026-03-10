from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import List, Optional

import aiosqlite

from database import DB_PATH
from models import AddDownloadsRequest, AddPackageRequest, BulkActionRequest, ReorderRequest
from auth import get_current_user
from config import get_config

router = APIRouter()


def _qm(request: Request):
    return request.app.state.queue_manager


@router.get("/")
async def list_downloads(request: Request, _=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM downloads ORDER BY position ASC, created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


def _validate_destination(dest: str):
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
    raise HTTPException(status_code=403, detail="Destination non autorisée")


@router.post("/")
async def add_downloads(body: AddDownloadsRequest, request: Request, _=Depends(get_current_user)):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    _validate_destination(body.destination)
    ids = await _qm(request).add_downloads(urls, body.destination)
    return {"added": len(ids), "ids": ids}


@router.delete("/{download_id}")
async def remove_download(download_id: str, request: Request, _=Depends(get_current_user)):
    await _qm(request).remove_download(download_id)
    return {"status": "removed"}


@router.post("/{download_id}/pause")
async def pause_download(download_id: str, request: Request, _=Depends(get_current_user)):
    await _qm(request).pause_download(download_id)
    return {"status": "paused"}


@router.post("/{download_id}/resume")
async def resume_download(download_id: str, request: Request, _=Depends(get_current_user)):
    await _qm(request).resume_download(download_id)
    return {"status": "resumed"}


@router.post("/actions")
async def bulk_action(body: BulkActionRequest, request: Request, _=Depends(get_current_user)):
    qm = _qm(request)
    if body.action == "pause_all":
        await qm.pause_all()
    elif body.action == "resume_all":
        await qm.resume_all()
    elif body.action == "clear_completed":
        await qm.clear_completed()
    elif body.action == "remove_all":
        await qm.remove_all()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
    return {"status": "ok"}


@router.put("/reorder")
async def reorder_downloads(body: ReorderRequest, request: Request, _=Depends(get_current_user)):
    await _qm(request).reorder(body.ids)
    return {"status": "ok"}


# ---- Packages ---- #

@router.post("/packages")
async def create_package(body: AddPackageRequest, request: Request, _=Depends(get_current_user)):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    _validate_destination(body.destination)
    result = await _qm(request).add_package(body.name, urls, body.destination)
    return {"added": len(result["download_ids"]), **result}


@router.get("/packages")
async def list_packages(_=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM packages ORDER BY created_at DESC")
        packages = [dict(r) for r in await cursor.fetchall()]

        for pkg in packages:
            cursor = await db.execute(
                "SELECT * FROM downloads WHERE package_id = ? ORDER BY position ASC",
                (pkg["id"],),
            )
            pkg["downloads"] = [dict(r) for r in await cursor.fetchall()]

            # Compute aggregate progress
            total_size = sum(d["size"] or 0 for d in pkg["downloads"])
            total_downloaded = sum(d["downloaded"] or 0 for d in pkg["downloads"])
            pkg["total_size"] = total_size
            pkg["total_downloaded"] = total_downloaded
            pkg["progress"] = round(total_downloaded / total_size * 100, 1) if total_size > 0 else 0
            pkg["total_files"] = len(pkg["downloads"])
            pkg["completed_files"] = sum(1 for d in pkg["downloads"] if d["status"] == "complete")
            pkg["active_files"] = sum(1 for d in pkg["downloads"] if d["status"] == "downloading")

        return packages


@router.delete("/packages/{package_id}")
async def remove_package(package_id: str, request: Request, _=Depends(get_current_user)):
    await _qm(request).remove_package(package_id)
    return {"status": "removed"}


# ---- History ---- #

@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _=Depends(get_current_user),
):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT COUNT(*) FROM history"
        )
        (total,) = await cursor.fetchone()

        cursor = await db.execute(
            "SELECT * FROM history ORDER BY completed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return {"total": total, "items": rows}


@router.delete("/history/{history_id}")
async def delete_history_item(
    history_id: str,
    delete_file: bool = Query(default=False),
    _=Depends(get_current_user),
):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM history WHERE id = ?", (history_id,))
        item = await cursor.fetchone()

    if not item:
        raise HTTPException(status_code=404, detail="Entrée introuvable")

    if delete_file:
        cfg = get_config()
        dest = item["destination"] or ""
        name = item["name"] or ""
        if dest and name:
            file_path = Path(dest) / name
            resolved = file_path.resolve()

            # Security: ensure path is within allowed_paths or default_destination
            allowed = [Path(p).resolve() for p in cfg["downloads"].get("allowed_paths", [])]
            default_dest = cfg["downloads"].get("default_destination", "")
            if default_dest:
                allowed.append(Path(default_dest).resolve())

            path_allowed = False
            for a in allowed:
                try:
                    resolved.relative_to(a)
                    path_allowed = True
                    break
                except ValueError:
                    continue
            if not path_allowed:
                raise HTTPException(status_code=403, detail="Chemin non autorisé")

            if resolved.is_file():
                resolved.unlink()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM history WHERE id = ?", (history_id,))
        await db.commit()

    return {"status": "deleted"}


@router.delete("/history")
async def clear_history(_=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM history")
        await db.commit()
    return {"status": "cleared"}
