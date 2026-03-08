import asyncio
import uuid
from datetime import datetime
from typing import Optional

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
        while self._running:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _tick(self):
        config = get_config()
        max_concurrent = config["downloads"]["simultaneous"]
        now = datetime.utcnow().isoformat()

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
                            # Move to history
                            await self._move_to_history(db, row["id"], now)
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

                except Exception:
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

                for item in pending:
                    try:
                        direct_url = await alldebrid.process_url(item["url"])
                        gid = await aria2.add_uri(direct_url, item["destination"])
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

                await self._ws_manager.broadcast({
                    "type": "downloads_update",
                    "data": active_downloads + finished_downloads,
                    "packages": packages,
                })

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
            await db.execute(
                "UPDATE packages SET status = ?, updated_at = ? WHERE id = ?",
                (pkg_status, now, package_id),
            )
            await db.commit()

            # Webhook
            pcur = await db.execute("SELECT * FROM packages WHERE id = ?", (package_id,))
            pkg = await pcur.fetchone()
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
        now = datetime.utcnow().isoformat()
        ids = []
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COALESCE(MAX(position), 0) FROM downloads")
            (max_pos,) = await cursor.fetchone()
            pos = max_pos + 1

            for url in urls:
                url = url.strip()
                if not url:
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
        return ids

    async def add_package(self, name: str, urls: list, destination: str) -> dict:
        now = datetime.utcnow().isoformat()
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
            now = datetime.utcnow().isoformat()
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

            now = datetime.utcnow().isoformat()
            # Reset retry count on manual resume of failed downloads
            extra = ""
            params = [new_status, now, download_id]
            if row["status"] == "failed":
                extra = ", retry_count = 0, error_msg = NULL"

            await db.execute(
                f"UPDATE downloads SET status = ?{extra}, updated_at = ? WHERE id = ?",
                params,
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

    async def clear_completed(self):
        now = datetime.utcnow().isoformat()
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
