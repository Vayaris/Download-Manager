import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

import aiosqlite

from database import DB_PATH
from models import MagnetUploadRequest
from auth import get_current_user
from services.alldebrid import alldebrid
from utils import validate_destination as _validate_destination

router = APIRouter()


def _qm(request: Request):
    return request.app.state.queue_manager


async def _process_ready_magnet(magnet_id: int, name: str, destination: str, qm):
    """Magnet is ready: get files, create package, clean up."""
    links = await alldebrid.magnet_files(magnet_id)
    if not links:
        raise Exception("No files found in torrent")
    await qm.add_package(name or "Torrent", links, destination)
    try:
        await alldebrid.magnet_delete(magnet_id)
    except Exception:
        pass


@router.post("/")
async def submit_magnets(body: MagnetUploadRequest, request: Request, _=Depends(get_current_user)):
    magnets = [m.strip() for m in body.magnets if m.strip()]
    if not magnets:
        raise HTTPException(status_code=400, detail="No magnet links provided")
    _validate_destination(body.destination)

    try:
        results = await alldebrid.magnet_upload(magnets)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    qm = _qm(request)
    added = []

    async with aiosqlite.connect(str(DB_PATH)) as db:
        for mag in results:
            if mag.get("error"):
                continue
            ad_id = mag["id"]
            name = mag.get("name", "Torrent")
            size = mag.get("size", 0)
            ready = mag.get("ready", False)

            if ready:
                # Instantly ready — create package directly
                try:
                    await _process_ready_magnet(ad_id, name, body.destination, qm)
                    added.append({"id": ad_id, "name": name, "ready": True})
                except Exception as e:
                    # Store as processing if package creation fails
                    t_id = str(uuid.uuid4())
                    await db.execute(
                        """INSERT INTO torrents
                           (id, alldebrid_id, name, size, status, destination, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'processing', ?, ?, ?)""",
                        (t_id, ad_id, name, size, body.destination, now, now),
                    )
                    added.append({"id": t_id, "name": name, "ready": False})
            else:
                t_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO torrents
                       (id, alldebrid_id, name, size, status, destination, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'processing', ?, ?, ?)""",
                    (t_id, ad_id, name, size, body.destination, now, now),
                )
                added.append({"id": t_id, "name": name, "ready": False})
        await db.commit()

    return {"added": len(added), "torrents": added}


@router.post("/upload")
async def upload_torrent(
    request: Request,
    file: UploadFile = File(...),
    destination: str = Form(...),
    _=Depends(get_current_user),
):
    if not file.filename or not file.filename.endswith(".torrent"):
        raise HTTPException(status_code=400, detail=".torrent file required")
    _validate_destination(destination)

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        results = await alldebrid.magnet_upload_file(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    qm = _qm(request)
    added = []

    async with aiosqlite.connect(str(DB_PATH)) as db:
        for mag in results:
            if mag.get("error"):
                continue
            ad_id = mag["id"]
            name = mag.get("name", file.filename)
            size = mag.get("size", 0)
            ready = mag.get("ready", False)

            if ready:
                try:
                    await _process_ready_magnet(ad_id, name, destination, qm)
                    added.append({"id": ad_id, "name": name, "ready": True})
                except Exception:
                    t_id = str(uuid.uuid4())
                    await db.execute(
                        """INSERT INTO torrents
                           (id, alldebrid_id, name, size, status, destination, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'processing', ?, ?, ?)""",
                        (t_id, ad_id, name, size, destination, now, now),
                    )
                    added.append({"id": t_id, "name": name, "ready": False})
            else:
                t_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO torrents
                       (id, alldebrid_id, name, size, status, destination, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'processing', ?, ?, ?)""",
                    (t_id, ad_id, name, size, destination, now, now),
                )
                added.append({"id": t_id, "name": name, "ready": False})
        await db.commit()

    return {"added": len(added), "torrents": added}


@router.get("/")
async def list_torrents(_=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM torrents ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@router.delete("/{torrent_id}")
async def delete_torrent(torrent_id: str, _=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM torrents WHERE id = ?", (torrent_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Torrent not found")

        try:
            await alldebrid.magnet_delete(row["alldebrid_id"])
        except Exception:
            pass

        await db.execute("DELETE FROM torrents WHERE id = ?", (torrent_id,))
        await db.commit()

    return {"status": "removed"}
