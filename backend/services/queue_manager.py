import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional


def log(msg):
    print(f"[queue] {msg}", flush=True)

import aiosqlite

from config import get_config
from database import DB_PATH
from services.aria2_service import aria2
from services.alldebrid import alldebrid
from services.webhook import send_webhook


class QueueManager:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._ws_manager = None
        self._running = False
        self._last_torrent_check = 0

    def register_ws_manager(self, ws_manager):
        self._ws_manager = ws_manager

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------ #
    #  Main worker loop                                                    #
    # ------------------------------------------------------------------ #

    async def _loop(self):
        # Wait for aria2 to be ready before processing
        for attempt in range(30):
            if not self._running:
                return
            if await aria2.is_alive():
                log("aria2 RPC is ready")
                break
            log(f"Waiting for aria2 RPC... (attempt {attempt + 1}/30)")
            await asyncio.sleep(2)
        else:
            log("aria2 RPC not available after 60s, starting loop anyway")

        # Apply speed limit from config
        try:
            config = get_config()
            limit = config["downloads"].get("speed_limit", 0)
            limit_str = f"{limit}M" if limit > 0 else "0"
            await aria2.change_global_option({"max-overall-download-limit": limit_str})
        except Exception as e:
            log(f"Could not set speed limit: {e}")

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                import traceback; log(f"Queue tick error: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(1)

    async def _tick(self):
        config = get_config()
        max_concurrent = config["downloads"]["simultaneous"]
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # ---- Update status for downloads submitted to aria2 ---- #
            cursor = await db.execute(
                "SELECT * FROM downloads WHERE aria2_gid IS NOT NULL AND status NOT IN ('complete', 'error', 'failed')"
            )
            active_rows = await cursor.fetchall()

            for row in active_rows:
                try:
                    data = await aria2.tell_status(row["aria2_gid"])
                    parsed = aria2.parse_status(data)

                    name_update = parsed["name"] if parsed["name"] else row["name"]

                    if parsed["status"] == "error":
                        # Retry logic
                        retry_count = (row["retry_count"] or 0) + 1
                        max_retries = row["max_retries"] or 5

                        await aria2.remove_result(row["aria2_gid"])

                        if retry_count >= max_retries:
                            # Max retries reached — mark as failed definitively
                            await db.execute(
                                """UPDATE downloads SET
                                       name = ?, status = 'failed', progress = ?,
                                       speed = 0, size = ?, downloaded = ?,
                                       error_msg = ?, retry_count = ?,
                                       aria2_gid = NULL, updated_at = ?
                                   WHERE id = ?""",
                                (name_update, parsed["progress"], parsed["size"],
                                 parsed["downloaded"],
                                 f"Max retries ({max_retries}) reached. Last error: {parsed['error_msg']}",
                                 retry_count, now, row["id"]),
                            )
                            # Move to history and remove from active queue
                            await self._move_to_history(db, row["id"], now)
                            if not row["package_id"]:
                                await db.execute("DELETE FROM downloads WHERE id = ?", (row["id"],))
                            # Webhook
                            asyncio.create_task(send_webhook("download_failed", {
                                "name": name_update, "destination": row["destination"],
                                "size": parsed["size"], "error_msg": parsed["error_msg"],
                                "status": "failed",
                            }))
                        else:
                            # Retry: reset to pending
                            await db.execute(
                                """UPDATE downloads SET
                                       name = ?, status = 'pending',
                                       speed = 0, aria2_gid = NULL,
                                       retry_count = ?,
                                       error_msg = ?,
                                       updated_at = ?
                                   WHERE id = ?""",
                                (name_update, retry_count,
                                 f"Retry {retry_count}/{max_retries} - {parsed['error_msg']}",
                                 now, row["id"]),
                            )
                    elif parsed["status"] == "complete":
                        await db.execute(
                            """UPDATE downloads SET
                                   name = ?, status = 'complete', progress = 100,
                                   speed = 0, size = ?, downloaded = ?,
                                   updated_at = ?
                               WHERE id = ?""",
                            (name_update, parsed["size"], parsed["downloaded"],
                             now, row["id"]),
                        )
                        await aria2.remove_result(row["aria2_gid"])

                        # Move to history immediately and remove from active queue
                        await self._move_to_history(db, row["id"], now)
                        if not row["package_id"]:
                            # Standalone download — remove from downloads table
                            await db.execute("DELETE FROM downloads WHERE id = ?", (row["id"],))

                        # Webhook
                        asyncio.create_task(send_webhook("download_complete", {
                            "name": name_update, "destination": row["destination"],
                            "size": parsed["size"], "status": "complete",
                        }))

                        # Check if package is complete
                        if row["package_id"]:
                            await self._check_package_complete(db, row["package_id"], now)
                    else:
                        await db.execute(
                            """UPDATE downloads SET
                                   name = ?, status = ?, progress = ?,
                                   speed = ?, size = ?, downloaded = ?,
                                   updated_at = ?
                               WHERE id = ?""",
                            (name_update, parsed["status"], parsed["progress"],
                             parsed["speed"], parsed["size"], parsed["downloaded"],
                             now, row["id"]),
                        )

                except Exception as e:
                    log(f"aria2 status check failed for {row['id']} (gid={row['aria2_gid']}): {type(e).__name__}: {e}")
                    # aria2 doesn't know this GID anymore — reset to pending
                    await db.execute(
                        """UPDATE downloads SET
                               aria2_gid = NULL, status = 'pending', speed = 0, updated_at = ?
                           WHERE id = ? AND status NOT IN ('complete', 'error', 'failed')""",
                        (now, row["id"]),
                    )

            await db.commit()

            # ---- Submit new downloads if slots are available ---- #
            cursor = await db.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'downloading'"
            )
            (active_count,) = await cursor.fetchone()

            slots = max_concurrent - active_count
            if slots > 0:
                cursor = await db.execute(
                    """SELECT * FROM downloads
                       WHERE status = 'pending' AND aria2_gid IS NULL
                       ORDER BY position ASC, created_at ASC
                       LIMIT ?""",
                    (slots,),
                )
                pending = await cursor.fetchall()

                segments = config["downloads"].get("download_segments", 1)
                for item in pending:
                    try:
                        direct_url = await alldebrid.process_url(item["url"])
                        gid = await aria2.add_uri(direct_url, item["destination"], split=segments)
                        await db.execute(
                            "UPDATE downloads SET aria2_gid = ?, status = 'downloading', updated_at = ? WHERE id = ?",
                            (gid, now, item["id"]),
                        )
                        await db.commit()
                    except Exception as e:
                        retry_count = (item["retry_count"] or 0) + 1
                        max_retries = item["max_retries"] or 5

                        if retry_count >= max_retries:
                            await db.execute(
                                """UPDATE downloads SET status = 'failed',
                                       error_msg = ?, retry_count = ?, updated_at = ?
                                   WHERE id = ?""",
                                (f"Max retries ({max_retries}) reached. Last error: {str(e)[:400]}",
                                 retry_count, now, item["id"]),
                            )
                            await self._move_to_history(db, item["id"], now)
                            if not item["package_id"]:
                                await db.execute("DELETE FROM downloads WHERE id = ?", (item["id"],))
                            asyncio.create_task(send_webhook("download_failed", {
                                "name": item["name"] or item["url"],
                                "destination": item["destination"],
                                "error_msg": str(e)[:400], "status": "failed",
                            }))
                        else:
                            await db.execute(
                                """UPDATE downloads SET status = 'error',
                                       error_msg = ?, retry_count = ?, updated_at = ?
                                   WHERE id = ?""",
                                (f"Retry {retry_count}/{max_retries} - {str(e)[:400]}",
                                 retry_count, now, item["id"]),
                            )
                        await db.commit()

            # ---- Auto-retry errored downloads after a delay ---- #
            cursor = await db.execute(
                """SELECT id FROM downloads
                   WHERE status = 'error' AND retry_count > 0
                   AND retry_count < COALESCE(max_retries, 5)
                   AND datetime(updated_at) <= datetime('now', '-10 seconds')"""
            )
            retry_rows = await cursor.fetchall()
            for row in retry_rows:
                await db.execute(
                    "UPDATE downloads SET status = 'pending', speed = 0, updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
            if retry_rows:
                await db.commit()

            # ---- Update package statuses ---- #
            await self._update_package_statuses(db, now)

            # ---- Check torrents (every 5s) ---- #
            import time
            _now_ts = time.time()
            if _now_ts - self._last_torrent_check >= 5:
                self._last_torrent_check = _now_ts
                await self._check_torrents(db, now)

            # ---- Broadcast to WebSocket clients ---- #
            if self._ws_manager:
                cursor = await db.execute(
                    "SELECT * FROM downloads WHERE status NOT IN ('complete', 'failed') ORDER BY position ASC, created_at ASC"
                )
                active_downloads = [dict(r) for r in await cursor.fetchall()]

                cursor = await db.execute(
                    "SELECT * FROM downloads WHERE status IN ('complete', 'failed') ORDER BY updated_at DESC"
                )
                finished_downloads = [dict(r) for r in await cursor.fetchall()]

                cursor = await db.execute(
                    "SELECT * FROM packages ORDER BY created_at DESC"
                )
                packages = [dict(r) for r in await cursor.fetchall()]

                # Enrich packages with download data for frontend
                all_downloads = active_downloads + finished_downloads
                for pkg in packages:
                    pkg_downloads = [d for d in all_downloads if d.get("package_id") == pkg["id"]]
                    pkg["downloads"] = pkg_downloads
                    pkg["total_files"] = len(pkg_downloads)
                    pkg["completed_files"] = sum(1 for d in pkg_downloads if d["status"] == "complete")
                    pkg["active_files"] = sum(1 for d in pkg_downloads if d["status"] == "downloading")
                    total_size = sum(d.get("size") or 0 for d in pkg_downloads)
                    total_downloaded = sum(d.get("downloaded") or 0 for d in pkg_downloads)
                    pkg["total_size"] = total_size
                    pkg["total_downloaded"] = total_downloaded
                    pkg["progress"] = round(total_downloaded / total_size * 100, 1) if total_size > 0 else 0

                # Fetch torrents for broadcast
                cursor = await db.execute(
                    "SELECT * FROM torrents ORDER BY created_at DESC"
                )
                torrents_list = [dict(r) for r in await cursor.fetchall()]

                await self._ws_manager.broadcast({
                    "type": "downloads_update",
                    "data": active_downloads + finished_downloads,
                    "packages": packages,
                    "torrents": torrents_list,
                })

    async def _check_torrents(self, db, now: str):
        cursor = await db.execute(
            "SELECT * FROM torrents WHERE status = 'processing'"
        )
        rows = await cursor.fetchall()
        for row in rows:
            try:
                status_data = await alldebrid.magnet_status(row["alldebrid_id"])
                sc = status_data.get("statusCode", 0)

                if sc == 4:
                    # Ready — get files and create package
                    links = await alldebrid.magnet_files(row["alldebrid_id"])
                    if links:
                        await self.add_package(
                            row["name"] or "Torrent",
                            links,
                            row["destination"],
                        )
                    await db.execute("DELETE FROM torrents WHERE id = ?", (row["id"],))
                    await db.commit()
                    try:
                        await alldebrid.magnet_delete(row["alldebrid_id"])
                    except Exception:
                        pass
                elif sc >= 5:
                    # Error
                    await db.execute(
                        "UPDATE torrents SET status = 'error', status_message = ?, updated_at = ? WHERE id = ?",
                        (status_data.get("filename", "Torrent error"), now, row["id"]),
                    )
                    await db.commit()
                else:
                    # Processing — update progress
                    dl = status_data.get("downloaded", 0)
                    size = status_data.get("size", 0) or row["size"]
                    progress = round(dl / size * 100, 1) if size > 0 else 0
                    speed = status_data.get("downloadSpeed", 0)
                    seeders = status_data.get("seeders", 0)
                    await db.execute(
                        """UPDATE torrents SET progress = ?, speed = ?, seeders = ?,
                               size = ?, status_message = ?, updated_at = ?
                           WHERE id = ?""",
                        (progress, speed, seeders,
                         size, status_data.get("filename", ""), now, row["id"]),
                    )
                    await db.commit()
            except Exception as e:
                log(f"Torrent check failed for {row['id']}: {e}")

    async def _move_to_history(self, db, download_id: str, now: str):
        cursor = await db.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
        row = await cursor.fetchone()
        if not row:
            return

        pkg_name = None
        if row["package_id"]:
            pcur = await db.execute("SELECT name FROM packages WHERE id = ?", (row["package_id"],))
            prow = await pcur.fetchone()
            if prow:
                pkg_name = prow["name"]

        await db.execute(
            """INSERT OR REPLACE INTO history
               (id, name, url, destination, size, status, error_msg, package_name, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], row["name"], row["url"], row["destination"],
             row["size"], row["status"], row["error_msg"], pkg_name,
             row["created_at"], now),
        )
        await db.commit()

    async def _check_package_complete(self, db, package_id: str, now: str):
        cursor = await db.execute(
            "SELECT COUNT(*) FROM downloads WHERE package_id = ? AND status NOT IN ('complete', 'failed')",
            (package_id,),
        )
        (remaining,) = await cursor.fetchone()
        if remaining == 0:
            # All downloads in package are done
            cursor = await db.execute(
                "SELECT COUNT(*) FROM downloads WHERE package_id = ? AND status = 'failed'",
                (package_id,),
            )
            (failed,) = await cursor.fetchone()
            pkg_status = "complete" if failed == 0 else "partial"

            # Fetch package info before deleting (needed for webhook)
            pcur = await db.execute("SELECT * FROM packages WHERE id = ?", (package_id,))
            pkg = await pcur.fetchone()

            # Remove all package downloads from active table
            await db.execute("DELETE FROM downloads WHERE package_id = ?", (package_id,))
            # Delete the package itself so it disappears from the UI
            await db.execute("DELETE FROM packages WHERE id = ?", (package_id,))
            await db.commit()

            # Webhook
            if pkg:
                asyncio.create_task(send_webhook("package_complete", {
                    "name": pkg["name"], "package_name": pkg["name"],
                    "destination": pkg["destination"], "status": pkg_status,
                }))

    async def _update_package_statuses(self, db, now: str):
        cursor = await db.execute("SELECT id FROM packages WHERE status = 'active'")
        pkgs = await cursor.fetchall()
        for pkg in pkgs:
            await self._check_package_complete(db, pkg["id"], now)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def add_downloads(self, urls: list, destination: str, package_id: str = None) -> list:
        now = datetime.now(timezone.utc).isoformat()
        ids = []
        seen = set()
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COALESCE(MAX(position), 0) FROM downloads")
            (max_pos,) = await cursor.fetchone()
            pos = max_pos + 1

            for url in urls:
                url = url.strip()
                if not url or url in seen:
                    continue
                seen.add(url)

                # Skip if this URL is already pending or downloading
                cursor = await db.execute(
                    "SELECT id FROM downloads WHERE url = ? AND status IN ('pending', 'downloading', 'debrid', 'paused')",
                    (url,),
                )
                if await cursor.fetchone():
                    continue

                dl_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO downloads
                       (id, url, status, destination, created_at, updated_at, position, package_id)
                       VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)""",
                    (dl_id, url, destination, now, now, pos, package_id),
                )
                ids.append(dl_id)
                pos += 1
            await db.commit()

        # Submit to aria2 immediately in background (don't block the HTTP response)
        if ids:
            asyncio.create_task(self._submit_pending_now())

        return ids

    async def _submit_pending_now(self):
        """Submit pending downloads to aria2 immediately (called after add)."""
        try:
            config = get_config()
            max_concurrent = config["downloads"]["simultaneous"]
            segments = config["downloads"].get("download_segments", 1)
            now = datetime.now(timezone.utc).isoformat()

            async with aiosqlite.connect(str(DB_PATH)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM downloads WHERE status = 'downloading'"
                )
                (active_count,) = await cursor.fetchone()
                slots = max_concurrent - active_count
                if slots <= 0:
                    return

                cursor = await db.execute(
                    """SELECT * FROM downloads
                       WHERE status = 'pending' AND aria2_gid IS NULL
                       ORDER BY position ASC, created_at ASC
                       LIMIT ?""",
                    (slots,),
                )
                pending = await cursor.fetchall()

                for item in pending:
                    try:
                        direct_url = await alldebrid.process_url(item["url"])
                        gid = await aria2.add_uri(direct_url, item["destination"], split=segments)
                        cursor = await db.execute(
                            "UPDATE downloads SET aria2_gid = ?, status = 'downloading', updated_at = ? WHERE id = ? AND status = 'pending'",
                            (gid, now, item["id"]),
                        )
                        if cursor.rowcount == 0:
                            # Another task already picked up this download; cancel the aria2 download
                            try:
                                await aria2.remove(gid)
                            except Exception:
                                pass
                            continue
                        await db.commit()
                    except Exception as e:
                        log(f"Immediate submit failed for {item['url'][:80]}: {e}")
                        # Will be retried by the regular tick loop
        except Exception as e:
            log(f"_submit_pending_now error: {e}")

    async def add_package(self, name: str, urls: list, destination: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        pkg_id = str(uuid.uuid4())

        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "INSERT INTO packages (id, name, destination, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?)",
                (pkg_id, name, destination, now, now),
            )
            await db.commit()

        ids = await self.add_downloads(urls, destination, package_id=pkg_id)
        return {"package_id": pkg_id, "download_ids": ids}

    async def pause_download(self, download_id: str):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT aria2_gid, status FROM downloads WHERE id = ?", (download_id,)
            )
            row = await cursor.fetchone()
            if row and row["status"] == "downloading" and row["aria2_gid"]:
                try:
                    await aria2.pause(row["aria2_gid"])
                except Exception:
                    pass
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE downloads SET status = 'paused', speed = 0, updated_at = ? WHERE id = ?",
                (now, download_id),
            )
            await db.commit()

    async def resume_download(self, download_id: str):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT aria2_gid, status FROM downloads WHERE id = ?", (download_id,)
            )
            row = await cursor.fetchone()
            if not row or row["status"] not in ("paused", "error", "failed"):
                return

            new_status = "pending"
            if row["aria2_gid"]:
                try:
                    await aria2.resume(row["aria2_gid"])
                    new_status = "downloading"
                except Exception:
                    await db.execute(
                        "UPDATE downloads SET aria2_gid = NULL WHERE id = ?", (download_id,)
                    )

            now = datetime.now(timezone.utc).isoformat()
            # Reset retry count on manual resume of failed downloads
            if row["status"] == "failed":
                await db.execute(
                    "UPDATE downloads SET status = ?, retry_count = 0, error_msg = NULL, updated_at = ? WHERE id = ?",
                    (new_status, now, download_id),
                )
            else:
                await db.execute(
                    "UPDATE downloads SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now, download_id),
                )
            await db.commit()

    async def remove_download(self, download_id: str):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT aria2_gid FROM downloads WHERE id = ?", (download_id,)
            )
            row = await cursor.fetchone()
            if row and row["aria2_gid"]:
                await aria2.remove(row["aria2_gid"])
            await db.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
            await db.commit()

    async def pause_all(self):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id FROM downloads WHERE status = 'downloading'"
            )
            rows = await cursor.fetchall()
        for row in rows:
            await self.pause_download(row["id"])

    async def resume_all(self):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id FROM downloads WHERE status IN ('paused', 'error')"
            )
            rows = await cursor.fetchall()
        for row in rows:
            await self.resume_download(row["id"])

    async def remove_all(self):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT aria2_gid FROM downloads WHERE aria2_gid IS NOT NULL")
            rows = await cursor.fetchall()
            for row in rows:
                try:
                    await aria2.remove(row["aria2_gid"])
                except Exception:
                    pass
            await db.execute("DELETE FROM downloads")
            await db.execute("DELETE FROM packages")
            await db.commit()

    async def clear_completed(self):
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            # Move completed/failed to history before deleting
            cursor = await db.execute(
                "SELECT id FROM downloads WHERE status IN ('complete', 'failed')"
            )
            rows = await cursor.fetchall()
            for row in rows:
                await self._move_to_history(db, row["id"], now)

            await db.execute(
                "DELETE FROM downloads WHERE status IN ('complete', 'failed')"
            )
            await db.commit()

    async def reorder(self, ids: list):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            for i, dl_id in enumerate(ids):
                await db.execute(
                    "UPDATE downloads SET position = ? WHERE id = ?", (i, dl_id)
                )
            await db.commit()

    async def remove_package(self, package_id: str):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, aria2_gid FROM downloads WHERE package_id = ?", (package_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                if row["aria2_gid"]:
                    await aria2.remove(row["aria2_gid"])
            await db.execute("DELETE FROM downloads WHERE package_id = ?", (package_id,))
            await db.execute("DELETE FROM packages WHERE id = ?", (package_id,))
            await db.commit()
