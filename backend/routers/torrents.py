import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

from database import db_session
from models import MagnetUploadRequest
from auth import get_current_user
from services.alldebrid import alldebrid
from services.diagnostics import record_event_nowait
from utils import validate_destination as _validate_destination

router = APIRouter()


def _qm(request: Request):
    return request.app.state.queue_manager


async def _delete_remote_magnet(magnet_id: int):
    try:
        await alldebrid.magnet_delete(magnet_id)
    except Exception as exc:
        record_event_nowait(
            "torrent", "remote_delete_failed", exc,
            severity="warning", context={"alldebrid_id": magnet_id},
        )


async def _process_ready_magnet(magnet_id: int, name: str, destination: str, qm):
    """Magnet is ready: import its files and clean up."""
    links = await alldebrid.magnet_files(magnet_id)
    if not links:
        raise Exception("No files found in torrent")
    await qm.import_torrent_links(name or "Torrent", links, destination)
    await _delete_remote_magnet(magnet_id)


async def _process_ready_into_package(magnet_id: int, destination: str, package_id: str, qm) -> int:
    links = await alldebrid.magnet_files(magnet_id)
    if not links:
        return 0
    result = await qm.import_torrent_links("Torrent", links, destination, package_id=package_id)
    await _delete_remote_magnet(magnet_id)
    return len(result["download_ids"])


async def _process_ready_without_package(magnet_id: int, name: str, destination: str, qm) -> int:
    links = await alldebrid.magnet_files(magnet_id)
    if not links:
        return 0
    result = await qm.import_torrent_links(name or "Torrent", links, destination)
    await _delete_remote_magnet(magnet_id)
    return len(result["download_ids"])


async def _insert_torrent(db, mag: dict, destination: str, now: str, package_id: Optional[str] = None) -> dict:
    t_id = str(uuid.uuid4())
    name = mag.get("name", "Torrent")
    await db.execute(
        """INSERT INTO torrents
           (id, alldebrid_id, name, size, status, destination, package_id,
            created_at, updated_at, last_progress_at)
           VALUES (?, ?, ?, ?, 'processing', ?, ?, ?, ?, ?)""",
        (t_id, mag["id"], name, mag.get("size", 0), destination, package_id, now, now, now),
    )
    return {"id": t_id, "name": name, "ready": False}


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
    pending = []

    for mag in results:
        if mag.get("error"):
            continue
        name = mag.get("name", "Torrent")
        if mag.get("ready", False):
            try:
                await _process_ready_magnet(mag["id"], name, body.destination, qm)
                added.append({"id": mag["id"], "name": name, "ready": True})
            except Exception:
                pending.append(mag)
        else:
            pending.append(mag)

    async with db_session() as db:
        for mag in pending:
            added.append(await _insert_torrent(db, mag, body.destination, now))
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
    pending = []

    for mag in results:
        if mag.get("error"):
            continue
        name = mag.get("name", file.filename)
        if mag.get("ready", False):
            try:
                await _process_ready_magnet(mag["id"], name, destination, qm)
                added.append({"id": mag["id"], "name": name, "ready": True})
            except Exception:
                pending.append(mag)
        else:
            pending.append(mag)

    async with db_session() as db:
        for mag in pending:
            added.append(await _insert_torrent(db, mag, destination, now))
        await db.commit()

    return {"added": len(added), "torrents": added}


@router.post("/batch")
async def upload_torrent_batch(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    magnets: str = Form(""),
    destination: str = Form(...),
    _=Depends(get_current_user),
):
    magnet_links = [m.strip() for m in magnets.splitlines() if m.strip()]
    torrent_files = list(files or [])
    if not magnet_links and not torrent_files:
        raise HTTPException(status_code=400, detail="Paste a magnet link or select a .torrent file")
    _validate_destination(destination)

    files_data = []
    for file in torrent_files:
        filename = file.filename or ""
        if not filename.lower().endswith(".torrent"):
            raise HTTPException(status_code=400, detail=".torrent files required")
        file_bytes = await file.read()
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{filename} is too large (max 10MB)")
        files_data.append((filename, file_bytes))

    uploaded = []
    try:
        if magnet_links:
            uploaded.extend(await alldebrid.magnet_upload(magnet_links))
        if files_data:
            uploaded.extend(await alldebrid.magnet_upload_files(files_data))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    uploaded = [mag for mag in uploaded if not mag.get("error")]
    if not uploaded:
        raise HTTPException(status_code=502, detail="No torrent was accepted by AllDebrid")

    now = datetime.now(timezone.utc).isoformat()
    qm = _qm(request)
    source_count = len(magnet_links) + len(files_data)
    use_package = source_count >= 2
    package_name = f"Lot torrents - {datetime.now().strftime('%Y-%m-%d %H:%M')}" if use_package else None
    package_id = await qm.create_package(package_name, destination) if use_package else None
    added = []
    pending = []

    for mag in uploaded:
        ad_id = mag["id"]
        name = mag.get("name", "Torrent")
        if mag.get("ready", False):
            try:
                imported = await (
                    _process_ready_into_package(ad_id, destination, package_id, qm)
                    if use_package
                    else _process_ready_without_package(ad_id, name, destination, qm)
                )
                added.append({"id": ad_id, "name": name, "ready": True, "imported": imported})
            except Exception:
                pending.append(mag)
        else:
            pending.append(mag)

    async with db_session() as db:
        for mag in pending:
            added.append(await _insert_torrent(db, mag, destination, now, package_id=package_id))
        await db.commit()

    response = {"added": len(added), "torrents": added}
    if use_package:
        response.update({"package_id": package_id, "package_name": package_name})
    return response


@router.get("/")
async def list_torrents(_=Depends(get_current_user)):
    async with db_session(row_factory=True) as db:
        cursor = await db.execute(
            "SELECT * FROM torrents ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@router.delete("/{torrent_id}")
async def delete_torrent(torrent_id: str, _=Depends(get_current_user)):
    async with db_session(row_factory=True) as db:
        cursor = await db.execute("SELECT * FROM torrents WHERE id = ?", (torrent_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Torrent not found")

    await _delete_remote_magnet(row["alldebrid_id"])

    async with db_session() as db:
        await db.execute("DELETE FROM torrents WHERE id = ?", (torrent_id,))
        await db.commit()

    return {"status": "removed"}
