import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_current_user
from database import db_session
from services.aria2_service import aria2
from services.diagnostics import clear_events, list_events
from services.update_service import (
    UpdateError,
    check_latest,
    get_current_version,
    read_update_status,
    start_latest_update,
)

router = APIRouter()


@router.get("/version")
async def get_version(_=Depends(get_current_user)):
    return {"version": get_current_version()}


@router.get("/speed-limit/status")
async def get_speed_limit_status(_=Depends(get_current_user)):
    from services.interface_priority import interface_priority
    state = interface_priority.snapshot()
    try:
        options, stats = await asyncio.wait_for(asyncio.gather(
            aria2.get_global_option(), aria2._call("aria2.getGlobalStat")), timeout=3)
        effective = int(options.get("max-overall-download-limit", 0) or 0)
        cap = state["configured_mib_s"] * 1048576
        reserved = bool(state["priority_interface_enabled"] and cap > 0 and cap * 80 // 100 <= effective <= cap)
        return {**state, "target_percent": state["effective_percent"],
                "effective_percent": round(effective * 100 / cap) if cap else 100,
                "priority_interface_active": reserved and effective < cap,
                "effective_bytes_s": effective,
                "measured_bytes_s": int(stats.get("downloadSpeed", 0) or 0),
                "applied": effective == state["temporary_limit_bytes_s"] or reserved, "available": True}
    except Exception as exc:
        return {**state, "effective_bytes_s": None, "measured_bytes_s": None,
                "applied": False, "available": False, "error": type(exc).__name__}


@router.get("/runtime-status")
async def get_runtime_status(request: Request, _=Depends(get_current_user)):
    """Return the small health snapshot needed by the downloads workspace."""
    queue_manager = getattr(request.app.state, "queue_manager", None)
    queue = queue_manager.health_snapshot() if queue_manager else {"running": False}
    try:
        await asyncio.wait_for(aria2.get_global_option(), timeout=2)
        aria2_ok = True
    except Exception:
        aria2_ok = False

    return {
        "ok": bool(queue.get("running")) and aria2_ok and not queue.get("last_tick_error"),
        "aria2_ok": aria2_ok,
        "queue_running": bool(queue.get("running")),
        "queue_error": str(queue.get("last_tick_error") or "")[:200],
    }


@router.get("/diagnostics")
async def diagnostics(request: Request, _=Depends(get_current_user)):
    db_info = {"tables": {}, "download_statuses": []}
    async with db_session() as db:
        for table in ("downloads", "packages", "torrents", "history", "users", "blocked_ips"):
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608
            (count,) = await cursor.fetchone()
            db_info["tables"][table] = count
        cursor = await db.execute(
            "SELECT status, COUNT(*) FROM downloads GROUP BY status ORDER BY status"
        )
        db_info["download_statuses"] = [
            {"status": status, "count": count}
            for status, count in await cursor.fetchall()
        ]

    aria2_info = {"ok": False}
    try:
        active, waiting, stopped = await asyncio.wait_for(
            asyncio.gather(
                aria2._call("aria2.tellActive"),
                aria2._call("aria2.tellWaiting", [0, 100]),
                aria2._call("aria2.tellStopped", [0, 100]),
            ),
            timeout=5,
        )
        aria2_info = {
            "ok": True,
            "active": len(active or []),
            "waiting": len(waiting or []),
            "stopped": len(stopped or []),
        }
    except Exception as exc:
        aria2_info = {"ok": False, "error": str(exc)[:200]}

    manager = getattr(request.app.state, "queue_manager", None)
    queue_info = (
        manager.health_snapshot()
        if manager and hasattr(manager, "health_snapshot") else {"running": False}
    )
    from routers.filebrowser import browse_diagnostics
    return {
        "version": get_current_version(),
        "database": db_info,
        "aria2": aria2_info,
        "queue": queue_info,
        "events": await list_events(100),
        "filebrowser": browse_diagnostics(),
    }


@router.get("/diagnostics/events")
async def diagnostic_events(limit: int = 100, _=Depends(get_current_user)):
    return {"items": await list_events(limit)}


@router.delete("/diagnostics/events")
async def delete_diagnostic_events(_=Depends(get_current_user)):
    await clear_events()
    return {"status": "cleared"}


@router.get("/check-update")
async def check_update(_=Depends(get_current_user)):
    try:
        return await check_latest()
    except UpdateError as exc:
        return {
            "update_available": False,
            "current": get_current_version(),
            "message": str(exc),
            "error": True,
        }


@router.get("/update-status")
async def update_status(_=Depends(get_current_user)):
    return read_update_status()


@router.post("/update")
async def perform_update(_=Depends(get_current_user)):
    try:
        return await start_latest_update()
    except UpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
