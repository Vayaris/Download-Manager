from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List

import aiosqlite

from database import DB_PATH
from models import AddDownloadsRequest, BulkActionRequest, ReorderRequest
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
