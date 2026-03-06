import asyncio
import uuid
from datetime import datetime
from typing import Optional

import aiosqlite

from config import get_config
from database import DB_PATH
from services.aria2_service import aria2
from services.alldebrid import alldebrid


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
                "SELECT * FROM downloads WHERE aria2_gid IS NOT NULL AND status NOT IN ('complete', 'error')"
            )
            active_rows = await cursor.fetchall()

            for row in active_rows:
                try:
                    data = await aria2.tell_status(row["aria2_gid"])
                    parsed = aria2.parse_status(data)

                    name_update = parsed["name"] if parsed["name"] else row["name"]
                    await db.execute(
                        """UPDATE downloads SET
                               name = ?,
                               status = ?,
                               progress = ?,
                               speed = ?,
                               size = ?,
                               downloaded = ?,
                               error_msg = CASE WHEN ? != '' THEN ? ELSE error_msg END,
                               updated_at = ?
                           WHERE id = ?""",
                        (
                            name_update,
                            parsed["status"],
                            parsed["progress"],
                            parsed["speed"],
                            parsed["size"],
                            parsed["downloaded"],
                            parsed["error_msg"],
                            parsed["error_msg"],
                            now,
                            row["id"],
                        ),
                    )

                    if parsed["status"] in ("complete", "error"):
                        await aria2.remove_result(row["aria2_gid"])

                except Exception:
                    # aria2 doesn't know this GID anymore (restart?) — reset to pending
                    await db.execute(
                        """UPDATE downloads SET
                               aria2_gid = NULL, status = 'pending', speed = 0, updated_at = ?
                           WHERE id = ? AND status NOT IN ('complete', 'error')""",
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
                        await db.execute(
                            "UPDATE downloads SET status = 'error', error_msg = ?, updated_at = ? WHERE id = ?",
                            (str(e)[:500], now, item["id"]),
                        )
                        await db.commit()

            # ---- Broadcast to WebSocket clients ---- #
            if self._ws_manager:
                cursor = await db.execute(
                    "SELECT * FROM downloads ORDER BY position ASC, created_at ASC"
                )
                rows = await cursor.fetchall()
                await self._ws_manager.broadcast(
                    {"type": "downloads_update", "data": [dict(r) for r in rows]}
                )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def add_downloads(self, urls: list, destination: str) -> list:
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
                    """INSERT INTO downloads (id, url, status, destination, created_at, updated_at, position)
                       VALUES (?, ?, 'pending', ?, ?, ?, ?)""",
                    (dl_id, url, destination, now, now, pos),
                )
                ids.append(dl_id)
                pos += 1
            await db.commit()
        return ids

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
            if not row or row["status"] != "paused":
                return

            new_status = "pending"
            if row["aria2_gid"]:
                try:
                    await aria2.resume(row["aria2_gid"])
                    new_status = "downloading"
                except Exception:
                    # aria2 lost track — reset GID and requeue
                    await db.execute(
                        "UPDATE downloads SET aria2_gid = NULL WHERE id = ?", (download_id,)
                    )

            now = datetime.utcnow().isoformat()
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
                "SELECT id FROM downloads WHERE status = 'paused'"
            )
            rows = await cursor.fetchall()
        for row in rows:
            await self.resume_download(row["id"])

    async def clear_completed(self):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "DELETE FROM downloads WHERE status IN ('complete', 'error')"
            )
            await db.commit()

    async def reorder(self, ids: list):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            for i, dl_id in enumerate(ids):
                await db.execute(
                    "UPDATE downloads SET position = ? WHERE id = ?", (i, dl_id)
                )
            await db.commit()
