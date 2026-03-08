from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import List, Optional

import aiosqlite

from database import DB_PATH
from models import AddDownloadsRequest, AddPackageRequest, BulkActionRequest, ReorderRequest
from auth import get_current_user

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


@router.post("/")
async def add_downloads(body: AddDownloadsRequest, request: Request, _=Depends(get_current_user)):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
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


@router.delete("/history")
async def clear_history(_=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM history")
        await db.commit()
    return {"status": "cleared"}
