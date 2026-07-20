import asyncio
from datetime import datetime, timedelta, timezone

from config import get_config
from database import db_session
from services.alldebrid import alldebrid
from services.queue_utils import parse_datetime


async def check_torrents(manager, now: str) -> None:
    """Poll AllDebrid without retaining SQLite connections during network I/O."""
    async with db_session(row_factory=True) as db:
        rows = [dict(row) for row in await (
            await db.execute(
                "SELECT * FROM torrents WHERE status IN ('processing', 'ready_importing')"
            )
        ).fetchall()]

    timeout_hours = max(
        0,
        min(168, int(get_config()["downloads"].get("stalled_timeout_hours", 3) or 0)),
    )
    now_dt = parse_datetime(now) or datetime.now(timezone.utc)
    expired_ids = {
        row["id"] for row in rows
        if timeout_hours > 0 and now_dt - (
            parse_datetime(row["last_progress_at"] or row["created_at"]) or now_dt
        ) >= timedelta(hours=timeout_hours)
    }
    semaphore = asyncio.Semaphore(3)

    async def fetch_status(row):
        if row["id"] in expired_ids:
            return row, None
        async with semaphore:
            try:
                return row, await alldebrid.magnet_status(row["alldebrid_id"])
            except Exception as exc:
                return row, exc

    torrent_errors = 0
    for row, status_result in await asyncio.gather(*(fetch_status(row) for row in rows)):
        importing = row["status"] == "ready_importing"
        try:
            if row["id"] in expired_ids:
                async with db_session() as db:
                    await manager._fail_torrent(
                        db, row, now,
                        f"No AllDebrid progress for {timeout_hours} hours (timeout)",
                    )
                continue

            if isinstance(status_result, Exception):
                raise status_result
            status_data = status_result
            status_code = status_data.get("statusCode", 0)

            if status_code == 4:
                importing = True
                async with db_session() as db:
                    claim = await db.execute(
                        "UPDATE torrents SET status = 'ready_importing', status_message = ?, updated_at = ? "
                        "WHERE id = ? AND status IN ('processing', 'ready_importing')",
                        ("Ready on AllDebrid, importing files", now, row["id"]),
                    )
                    await db.commit()
                if claim.rowcount == 0:
                    continue

                links = await alldebrid.magnet_files(row["alldebrid_id"])
                if not links:
                    if row["package_id"]:
                        async with db_session() as db:
                            await db.execute("DELETE FROM torrents WHERE id = ?", (row["id"],))
                            await db.commit()
                            await manager._check_package_complete(db, row["package_id"], now)
                        continue
                    raise RuntimeError("AllDebrid returned no files for ready torrent")

                await manager.import_torrent_links(
                    row["name"] or status_data.get("filename") or "Torrent",
                    links,
                    row["destination"],
                    package_id=row["package_id"],
                )
                async with db_session() as db:
                    await db.execute("DELETE FROM torrents WHERE id = ?", (row["id"],))
                    await db.commit()
                    if row["package_id"]:
                        await manager._check_package_complete(db, row["package_id"], now)
                try:
                    await alldebrid.magnet_delete(row["alldebrid_id"])
                except Exception as exc:
                    manager._record_error("torrent_cleanup", exc)
            elif status_code >= 5:
                torrent_errors += 1
                async with db_session() as db:
                    await manager._fail_torrent(
                        db, row, now,
                        status_data.get("filename", "AllDebrid torrent error"),
                    )
            else:
                downloaded = status_data.get("downloaded", 0)
                size = status_data.get("size", 0) or row["size"]
                progress = round(downloaded / size * 100, 1) if size > 0 else 0
                progressed = downloaded > (row["downloaded"] or 0)
                last_progress_at = now if progressed else (
                    row["last_progress_at"] or row["created_at"] or now
                )
                async with db_session() as db:
                    await db.execute(
                        """UPDATE torrents SET progress = ?, speed = ?, seeders = ?,
                               size = ?, downloaded = ?, status_message = ?,
                               updated_at = ?, last_progress_at = ?
                           WHERE id = ? AND status = 'processing'""",
                        (
                            progress, status_data.get("downloadSpeed", 0),
                            status_data.get("seeders", 0), size, downloaded,
                            status_data.get("filename", ""), now,
                            last_progress_at, row["id"],
                        ),
                    )
                    await db.commit()
        except Exception as exc:
            torrent_errors += 1
            manager._record_error("torrent", exc)
            async with db_session() as db:
                if importing:
                    await db.execute(
                        "UPDATE torrents SET status = 'import_failed', status_message = ?, updated_at = ? "
                        "WHERE id = ? AND status = 'ready_importing'",
                        (str(exc)[:400], now, row["id"]),
                    )
                else:
                    await db.execute(
                        "UPDATE torrents SET status_message = ?, updated_at = ? "
                        "WHERE id = ? AND status = 'processing'",
                        (f"Temporary torrent check failed: {type(exc).__name__}", now, row["id"]),
                    )
                await db.commit()
            manager.log_torrent_failure(row["id"], exc)

    manager._health["torrent_errors"] = torrent_errors
