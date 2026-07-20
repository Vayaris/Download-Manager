import uuid
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from typing import List, Optional

from database import db_session
from models import (
    AddDownloadsRequest, AddPackageRequest, BulkActionRequest, ReorderRequest,
    DuplicateCommitRequest, DuplicateResolutionRequest, HistoryRemoveRequest,
)
from auth import get_current_user
from config import get_config
from services.alldebrid import alldebrid
from services.duplicates import (
    STAGING_ROOT, apply_replacement, create_submission, finish_submission,
    load_submission,
)
from services.history import history_group, history_view, remove_history_entries
from services.diagnostics import record_event_nowait
from utils import validate_destination as _validate_destination

router = APIRouter()


def _qm(request: Request):
    return request.app.state.queue_manager


@router.get("/")
async def list_downloads(request: Request, _=Depends(get_current_user)):
    async with db_session(row_factory=True) as db:
        cursor = await db.execute(
            "SELECT * FROM downloads ORDER BY position ASC, created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@router.get("/snapshot")
async def queue_snapshot(
    request: Request,
    since: int = Query(0, ge=0),
    _=Depends(get_current_user),
):
    snapshot = await _qm(request).get_snapshot()
    if since == snapshot["revision"]:
        return {"revision": snapshot["revision"], "changed": False}
    return {**snapshot, "changed": True}



@router.post("/")
async def add_downloads(body: AddDownloadsRequest, request: Request, _=Depends(get_current_user)):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    _validate_destination(body.destination)
    ids = await _qm(request).add_downloads(urls, body.destination)
    return {"added": len(ids), "ids": ids}


@router.post("/batch")
async def add_automatic_batch(
    request: Request,
    links: str = Form(""),
    destination: str = Form(...),
    package_name: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    allow_duplicates: bool = Form(False),
    _=Depends(get_current_user),
):
    """Accept direct links, magnets and torrent files as one submission."""
    _validate_destination(destination)
    qm = _qm(request)

    normalized_links = []
    seen = set()
    for raw in links.splitlines():
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            normalized_links.append(value)

    direct_links = [value for value in normalized_links if not value.lower().startswith("magnet:")]
    magnet_links = [value for value in normalized_links if value.lower().startswith("magnet:")]
    torrent_files = list(files or [])
    files_data = []
    for file in torrent_files:
        filename = (file.filename or "").strip()
        if not filename.lower().endswith(".torrent"):
            raise HTTPException(status_code=400, detail=".torrent files required")
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{filename} is too large (max 10MB)")
        files_data.append((filename, content))

    source_count = len(normalized_links) + len(files_data)
    if source_count == 0:
        raise HTTPException(status_code=400, detail="Add at least one link or .torrent file")
    if source_count > 100:
        raise HTTPException(status_code=400, detail="A submission is limited to 100 sources")

    use_package = source_count >= 2
    safe_package_name = package_name.strip()[:160] or f"Batch - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    package_id = None
    if use_package:
        package_id = await qm.create_package(
            safe_package_name,
            destination,
            status="assembling",
            source_count=source_count,
        )

    uploaded = []
    failed_sources = []
    try:
        if magnet_links:
            results = await alldebrid.magnet_upload(magnet_links)
            uploaded.extend(result for result in results if not result.get("error"))
            failed_sources.extend(
                (result.get("name") or "Magnet", alldebrid.error_message(result.get("error")))
                for result in results if result.get("error")
            )
            rejected = sum(1 for result in results if result.get("error"))
            if rejected:
                record_event_nowait(
                    "alldebrid", "magnet_rejected", "AllDebrid rejected magnet sources",
                    severity="warning", context={"count": rejected},
                )
    except Exception as exc:
        record_event_nowait(
            "alldebrid", "magnet_upload_failed", exc,
            context={"count": len(magnet_links)},
        )
        failed_sources.extend(("Magnet", str(exc)) for _ in magnet_links)

    try:
        if files_data:
            results = await alldebrid.magnet_upload_files(files_data)
            uploaded.extend(result for result in results if not result.get("error"))
            failed_sources.extend(
                (result.get("name") or "Torrent", alldebrid.error_message(result.get("error")))
                for result in results if result.get("error")
            )
    except Exception as exc:
        record_event_nowait(
            "alldebrid", "torrent_upload_failed", exc,
            context={"count": len(files_data)},
        )
        failed_sources.extend((name, str(exc)) for name, _ in files_data)

    if not use_package and (magnet_links or files_data) and not uploaded:
        raise HTTPException(status_code=502, detail=failed_sources[0][1] if failed_sources else "Torrent rejected by AllDebrid")

    direct_ids = await qm.add_downloads(
        direct_links, destination, package_id=package_id, allow_duplicates=allow_duplicates
    )
    added_torrents = []
    pending_torrents = []
    now = datetime.now(timezone.utc).isoformat()

    # Reuse the torrent import primitives so delayed and instantly-ready torrents
    # have exactly the same package behavior.
    from routers.torrents import (
        _insert_torrent,
        _process_ready_into_package,
        _process_ready_without_package,
    )

    for magnet in uploaded:
        name = magnet.get("name", "Torrent")
        if magnet.get("ready", False):
            try:
                imported = await (
                    _process_ready_into_package(magnet["id"], destination, package_id, qm)
                    if package_id
                    else _process_ready_without_package(magnet["id"], name, destination, qm)
                )
                if imported == 0:
                    failed_sources.append((name, "AllDebrid returned no downloadable files"))
                added_torrents.append({
                    "id": magnet["id"], "name": name,
                    "ready": True, "imported": imported,
                })
            except Exception:
                pending_torrents.append(magnet)
        else:
            pending_torrents.append(magnet)

    async with db_session() as db:
        for magnet in pending_torrents:
            added_torrents.append(
                await _insert_torrent(db, magnet, destination, now, package_id=package_id)
            )
        if package_id and failed_sources:
            for name, error in failed_sources:
                await db.execute(
                    """INSERT OR REPLACE INTO history
                       (id, name, url, destination, size, status, error_msg,
                        package_name, created_at, completed_at, package_id)
                       VALUES (?, ?, '', ?, 0, 'failed', ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), name, destination,
                        error[:400], safe_package_name, now, now, package_id,
                    ),
                )
        await db.commit()

    if package_id:
        await qm.activate_package(package_id, failed_sources=len(failed_sources))

    added = len(direct_ids) + len(added_torrents)
    response = {
        "added": added,
        "download_ids": direct_ids,
        "torrents": added_torrents,
        "failed": len(failed_sources),
    }
    if package_id:
        response.update({"package_id": package_id, "package_name": safe_package_name})
    return response


@router.post("/preflight")
async def preflight_batch(
    links: str = Form(""),
    destination: str = Form(...),
    package_name: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    user=Depends(get_current_user),
):
    _validate_destination(destination)
    normalized_links = [line.strip() for line in links.splitlines() if line.strip()]
    files_data = []
    for file in list(files or []):
        filename = (file.filename or "").strip()
        if not filename.lower().endswith(".torrent"):
            raise HTTPException(status_code=400, detail=".torrent files required")
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{filename} is too large (max 10MB)")
        files_data.append((filename, content))
    if not normalized_links and not files_data:
        raise HTTPException(status_code=400, detail="Add at least one link or .torrent file")
    return await create_submission(
        user["username"], destination, package_name.strip()[:160], normalized_links, files_data
    )


@router.post("/submissions/{submission_id}/commit")
async def commit_submission(
    submission_id: str,
    body: DuplicateCommitRequest,
    request: Request,
    user=Depends(get_current_user),
):
    submission = await load_submission(submission_id, user["username"])
    decisions = {decision.source_id: decision for decision in body.decisions}
    selected = []
    for item in submission["items"]:
        decision = decisions.get(item["id"])
        action = decision.action if decision else ("download" if not item["conflicts"] else "")
        if action not in ("ignore", "download", "replace"):
            raise HTTPException(status_code=400, detail=f"A decision is required for {item['display_name']}")
        if action == "ignore":
            continue
        disk_conflict = any(conflict["type"] == "destination" for conflict in item["conflicts"])
        if action == "download" and disk_conflict and not decision.confirm_overwrite:
            raise HTTPException(status_code=409, detail="Explicit overwrite confirmation is required")
        if action == "replace":
            await apply_replacement(item, _qm(request))
        selected.append((item, action, bool(decision and decision.confirm_overwrite)))

    if not selected:
        await finish_submission(submission_id)
        return {"added": 0, "ignored": len(submission["items"]), "cancelled": True}

    link_items = [entry for entry in selected if entry[0]["kind"] in ("url", "magnet")]
    file_items = [entry for entry in selected if entry[0]["kind"] == "torrent"]
    staged_files = []
    handles = []
    try:
        for item, _, _ in file_items:
            handle = open(STAGING_ROOT / submission_id / item["stored"], "rb")
            handles.append(handle)
            staged_files.append(UploadFile(filename=item["display_name"], file=handle))
        result = await add_automatic_batch(
            request=request,
            links="\n".join(item["value"] for item, _, _ in link_items),
            destination=submission["destination"],
            package_name=submission["package_name"],
            files=staged_files,
            allow_duplicates=True,
            _=user,
        )
        if result.get("download_ids"):
            async with db_session() as db:
                for download_id, (item, action, confirmed) in zip(result["download_ids"], link_items):
                    await db.execute(
                        "UPDATE downloads SET source_key = ?, overwrite_confirmed = ? WHERE id = ?",
                        (item["source_key"], 1 if confirmed or action == "replace" else 0, download_id),
                    )
                await db.commit()
        torrent_sources = [entry for entry in selected if entry[0]["kind"] in ("magnet", "torrent")]
        if result.get("torrents") and torrent_sources:
            async with db_session() as db:
                for torrent, (item, _, _) in zip(result["torrents"], torrent_sources):
                    await db.execute("UPDATE torrents SET source_key = ? WHERE id = ?", (item["source_key"], torrent["id"]))
                await db.commit()
        result["ignored"] = len(submission["items"]) - len(selected)
        await finish_submission(submission_id)
        return result
    finally:
        for handle in handles:
            handle.close()


@router.get("/conflicts")
async def pending_conflicts(_=Depends(get_current_user)):
    async with db_session(row_factory=True) as db:
        cursor = await db.execute(
            """SELECT id, name, url, destination, target_path, package_id
               FROM downloads WHERE status = 'duplicate_pending' ORDER BY created_at"""
        )
        return [dict(row) for row in await cursor.fetchall()]


@router.post("/conflicts/{download_id}/resolve")
async def resolve_pending_conflict(
    download_id: str,
    body: DuplicateResolutionRequest,
    request: Request,
    _=Depends(get_current_user),
):
    if body.action not in ("ignore", "download", "replace"):
        raise HTTPException(status_code=400, detail="Invalid duplicate action")
    async with db_session(row_factory=True) as db:
        cursor = await db.execute("SELECT * FROM downloads WHERE id = ? AND status = 'duplicate_pending'", (download_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Duplicate conflict not found")
        target = Path(row["target_path"] or "")
        if body.action == "ignore":
            await db.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
        else:
            if body.action == "download" and not body.confirm_overwrite:
                raise HTTPException(status_code=409, detail="Explicit overwrite confirmation is required")
            if body.action == "replace":
                from services.duplicates import _path_allowed
                if target.is_file():
                    if not _path_allowed(target):
                        raise HTTPException(status_code=403, detail="Duplicate path cannot be replaced safely")
                    target.unlink()
                await db.execute(
                    "DELETE FROM history WHERE status = 'complete' AND destination = ? AND name = ?",
                    (row["destination"], row["name"]),
                )
            await db.execute(
                """UPDATE downloads SET status = 'pending', overwrite_confirmed = 1,
                   error_msg = NULL, updated_at = ? WHERE id = ?""",
                (datetime.now(timezone.utc).isoformat(), download_id),
            )
        await db.commit()
    return {"status": "resolved", "action": body.action}


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
    async with db_session(row_factory=True) as db:
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

@router.get("/history/view")
async def get_history_view(
    scope: str = Query(default="all"),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str = Query(default=""),
    today_from: str = Query(default=""),
    _=Depends(get_current_user),
):
    return await history_view(scope, limit, cursor, today_from)


@router.get("/history/groups/{group_id}")
async def get_history_group(group_id: str, _=Depends(get_current_user)):
    return await history_group(group_id)


@router.post("/history/remove")
async def remove_history_items(body: HistoryRemoveRequest, _=Depends(get_current_user)):
    removed = await remove_history_entries(body.ids)
    return {"status": "removed", "removed": removed}


@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _=Depends(get_current_user),
):
    async with db_session(row_factory=True) as db:
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
    async with db_session(row_factory=True) as db:
        cursor = await db.execute("SELECT * FROM history WHERE id = ?", (history_id,))
        item = await cursor.fetchone()

    if not item:
        raise HTTPException(status_code=404, detail="Entry not found")

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
                raise HTTPException(status_code=403, detail="Path not allowed")

            if resolved.is_file():
                resolved.unlink()

    async with db_session() as db:
        await db.execute("DELETE FROM history WHERE id = ?", (history_id,))
        await db.commit()

    return {"status": "deleted"}


@router.delete("/history")
async def clear_history(_=Depends(get_current_user)):
    async with db_session() as db:
        await db.execute("DELETE FROM history")
        await db.commit()
    return {"status": "cleared"}


@router.delete("/{download_id}")
async def remove_download(download_id: str, request: Request, _=Depends(get_current_user)):
    await _qm(request).remove_download(download_id)
    return {"status": "removed"}
