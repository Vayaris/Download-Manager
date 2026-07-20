import asyncio
import json
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def log(msg):
    print(f"[queue] {msg}", flush=True)

from config import get_config
from database import db_session
from services.aria2_service import aria2
from services.alldebrid import AllDebridError, alldebrid
from services.media_refresh import auto_refresh_recommended_libraries
from services.diagnostics import record_event_nowait
from services.duplicates import inferred_name, source_key
from services.webhook import send_webhook
from services.youtube_download import YouTubeDownloadService
from services.youtube_setup import status as youtube_direct_status
from services.youtube import canonical_video_url, youtube_video_id
from services.queue_utils import (
    aria2_file_path as _aria2_file_path,
    file_matches_size as _file_matches_size,
    is_missing_aria2_gid_error as _is_missing_aria2_gid_error,
    is_transient_aria2_error as _is_transient_aria2_error,
    looks_like_nfo as _looks_like_nfo,
    parse_datetime as _parse_datetime,
    path_is_allowed as _path_is_allowed,
)
from services.queue_snapshot import load_queue_revision, load_queue_snapshot
from services.torrent_tracker import check_torrents


class QueueManager:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._submission_tasks: dict[str, asyncio.Task] = {}
        self.youtube_downloads = YouTubeDownloadService(self)
        self._ws_manager = None
        self._running = False
        self._last_torrent_check = 0
        self._snapshot = {"revision": 0, "downloads": [], "packages": [], "torrents": []}
        self._snapshot_db_revision = -1
        self._snapshot_lock = asyncio.Lock()
        self._media_auto_refresh_pending = False
        self._media_auto_refresh_running = False
        self._media_auto_refresh_retry_at = 0.0
        self._recent_errors = deque(maxlen=20)
        self._health = {
            "running": False,
            "last_tick_at": None,
            "last_tick_seconds": 0,
            "last_aria2_batch_seconds": 0,
            "last_tick_error": "",
            "tick_errors": 0,
            "temporary_aria2_errors": 0,
            "active_downloads": 0,
            "pending_downloads": 0,
            "torrent_errors": 0,
            "recent_errors": self._recent_errors,
        }

    def register_ws_manager(self, ws_manager):
        self._ws_manager = ws_manager

    def health_snapshot(self):
        snapshot = dict(self._health)
        snapshot["recent_errors"] = list(self._recent_errors)
        return snapshot

    def _record_error(self, source: str, message: str):
        self._recent_errors.appendleft({
            "at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "message": str(message)[:200],
        })
        record_event_nowait("queue", source, message)

    @staticmethod
    def log_torrent_failure(torrent_id: str, exc: Exception):
        log(f"Torrent check failed for {torrent_id}: {exc}")

    async def _finalize_download(self, db, row, parsed: dict, now: str):
        cursor = await db.execute(
            """UPDATE downloads SET
                   name = ?, status = 'complete', progress = 100,
                   speed = 0, size = ?, downloaded = ?,
                   error_msg = NULL, updated_at = ?, last_progress_at = ?
               WHERE id = ? AND aria2_gid = ? AND status NOT IN ('complete', 'failed')""",
            (
                parsed["name"] or row["name"],
                parsed["size"],
                parsed["downloaded"],
                now,
                now,
                row["id"],
                row["aria2_gid"],
            ),
        )
        if cursor.rowcount == 0:
            return

        await self._move_to_history(db, row["id"], now)
        if not row["package_id"]:
            await db.execute("DELETE FROM downloads WHERE id = ?", (row["id"],))
            asyncio.create_task(send_webhook("download_complete", {
                "name": parsed["name"] or row["name"],
                "destination": row["destination"],
                "size": parsed["size"],
                "status": "complete",
            }))
        else:
            await self._check_package_complete(db, row["package_id"], now)

    async def _expire_download(self, db, row, parsed: dict, raw_status: dict, now: str, timeout_hours: int):
        file_path = _aria2_file_path(raw_status)
        sidecar_was_present = False
        config = get_config()
        if file_path and _path_is_allowed(file_path, row["destination"], config):
            sidecar_was_present = Path(f"{file_path}.aria2").is_file()

        if file_path and sidecar_was_present and _path_is_allowed(file_path, row["destination"], config):
            for partial_path in (file_path, Path(f"{file_path}.aria2")):
                try:
                    if partial_path.is_file():
                        partial_path.unlink()
                except OSError as exc:
                    self._record_error("stalled_cleanup", f"{partial_path}: {exc}")

        error_msg = f"No progress for {timeout_hours} hours (timeout)"
        cursor = await db.execute(
            """UPDATE downloads SET
                   name = ?, status = 'failed', progress = ?,
                   speed = 0, size = ?, downloaded = ?,
                   error_msg = ?, aria2_gid = NULL, updated_at = ?
               WHERE id = ? AND aria2_gid = ? AND status NOT IN ('complete', 'failed')""",
            (
                parsed["name"] or row["name"],
                parsed["progress"],
                parsed["size"],
                parsed["downloaded"],
                error_msg,
                now,
                row["id"],
                row["aria2_gid"],
            ),
        )
        if cursor.rowcount == 0:
            return

        await self._move_to_history(db, row["id"], now)
        if not row["package_id"]:
            await db.execute("DELETE FROM downloads WHERE id = ?", (row["id"],))
            asyncio.create_task(send_webhook("download_failed", {
                "name": parsed["name"] or row["name"],
                "destination": row["destination"],
                "size": parsed["size"],
                "error_msg": error_msg,
                "status": "failed",
            }))
        else:
            await self._check_package_complete(db, row["package_id"], now)

    async def start(self):
        # A service restart kills in-flight resolver tasks. Requeue them immediately.
        async with db_session() as db:
            await db.execute(
                "UPDATE packages SET status = 'active' WHERE status = 'finalizing'"
            )
            await db.execute(
                "UPDATE downloads SET status = 'pending', error_msg = 'Recovered after restart' "
                "WHERE status IN ('submitting', 'postprocessing') AND aria2_gid IS NULL"
            )
            await db.execute(
                "UPDATE downloads SET status = 'pending', speed = 0, error_msg = 'Recovered after restart' "
                "WHERE engine = 'youtube' AND status = 'downloading'"
            )
            state = await (await db.execute(
                "SELECT pending, retry_at FROM media_refresh_state WHERE id = 1"
            )).fetchone()
            await db.commit()
        if state:
            self._media_auto_refresh_pending = bool(state[0])
            retry_at = _parse_datetime(state[1])
            if retry_at:
                remaining = max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
                self._media_auto_refresh_retry_at = time.monotonic() + remaining
        self._running = True
        self._health["running"] = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        self._health["running"] = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        tasks = list(self._submission_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._submission_tasks.clear()
        await self.youtube_downloads.stop()
        await aria2.close()

    async def refresh_snapshot(self, *, force: bool = False) -> tuple[dict, bool]:
        async with self._snapshot_lock:
            current_revision = await load_queue_revision()
            if not force and current_revision == self._snapshot_db_revision:
                return self._snapshot, False
            snapshot = await load_queue_snapshot()
            db_revision = snapshot.pop("db_revision")
            revision = self._snapshot["revision"] + 1
            self._snapshot = {"revision": revision, **snapshot}
            self._snapshot_db_revision = db_revision
            return self._snapshot, True

    async def get_snapshot(self) -> dict:
        if self._snapshot["revision"] == 0:
            await self.refresh_snapshot(force=True)
        return self._snapshot

    def _start_submission(self, item: dict, segments: int):
        download_id = item["id"]
        if download_id in self._submission_tasks:
            return
        task = asyncio.create_task(self._submit_to_aria2(item, segments))
        self._submission_tasks[download_id] = task

        def finished(done):
            self._submission_tasks.pop(download_id, None)
            if not done.cancelled() and done.exception():
                self._record_error("submission_task", done.exception())

        task.add_done_callback(finished)

    async def _submit_to_aria2(self, item: dict, segments: int):
        """Resolve one source without holding a SQLite connection or blocking the tick."""
        try:
            direct_url = await alldebrid.process_url(item["url"])
            resolved_name = inferred_name(direct_url) or inferred_name(item["url"])
            target_path = Path(item["destination"]) / resolved_name if resolved_name else None
            now = datetime.now(timezone.utc).isoformat()
            if target_path and target_path.is_file() and not item["overwrite_confirmed"]:
                async with db_session() as db:
                    await db.execute(
                        """UPDATE downloads SET status = 'duplicate_pending', name = ?,
                               target_path = ?, error_msg = 'A file with this name already exists', updated_at = ?
                           WHERE id = ? AND status = 'submitting'""",
                        (resolved_name, str(target_path), now, item["id"]),
                    )
                    await db.commit()
                return

            gid = await aria2.add_uri(direct_url, item["destination"], split=segments)
            async with db_session() as db:
                cursor = await db.execute(
                    """UPDATE downloads SET aria2_gid = ?, status = 'downloading', name = ?,
                           error_msg = NULL, updated_at = ? WHERE id = ? AND status = 'submitting'""",
                    (gid, resolved_name or item["name"], now, item["id"]),
                )
                await db.commit()
            if cursor.rowcount == 0:
                try:
                    await aria2.remove(gid)
                except Exception:
                    pass
        except asyncio.CancelledError:
            async with db_session() as db:
                await db.execute(
                    "UPDATE downloads SET status = 'pending', updated_at = ? WHERE id = ? AND status = 'submitting'",
                    (datetime.now(timezone.utc).isoformat(), item["id"]),
                )
                await db.commit()
            raise
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            async with db_session(row_factory=True) as db:
                current = await (await db.execute(
                    "SELECT status FROM downloads WHERE id = ?", (item["id"],)
                )).fetchone()
                if not current or current["status"] != "submitting":
                    return
                is_youtube = str(item.get("source_key") or "").startswith("youtube:")
                permanent_alldebrid_error = (
                    isinstance(exc, AllDebridError)
                    and exc.code in {"LINK_HOST_NOT_SUPPORTED", "LINK_NOT_SUPPORTED"}
                )
                if is_youtube and permanent_alldebrid_error and youtube_direct_status()["ready"]:
                    await db.execute(
                        """UPDATE downloads SET engine = 'youtube', output_profile = 'mp4',
                               status = 'pending', retry_count = 0,
                               error_msg = 'AllDebrid unavailable; automatic direct fallback', updated_at = ?
                           WHERE id = ? AND status = 'submitting' AND engine = 'aria2'""",
                        (now, item["id"]),
                    )
                    await db.commit()
                    return
                retry_count = (item["retry_count"] or 0) + 1
                max_retries = 1 if is_youtube and permanent_alldebrid_error else (item["max_retries"] or 5)
                error_detail = str(exc)
                if is_youtube and permanent_alldebrid_error:
                    error_detail += ". Install the local direct YouTube tools in Settings to enable automatic fallback"
                if retry_count >= max_retries:
                    await db.execute(
                        """UPDATE downloads SET status = 'failed', error_msg = ?, retry_count = ?, updated_at = ?
                           WHERE id = ? AND status = 'submitting'""",
                        (f"Max retries ({max_retries}) reached. Last error: {error_detail[:400]}", retry_count, now, item["id"]),
                    )
                    await self._move_to_history(db, item["id"], now)
                    if not item["package_id"]:
                        await db.execute("DELETE FROM downloads WHERE id = ? AND status = 'failed'", (item["id"],))
                        asyncio.create_task(send_webhook("download_failed", {
                            "name": item["name"] or item["url"],
                            "destination": item["destination"],
                            "error_msg": error_detail[:400], "status": "failed",
                        }))
                else:
                    await db.execute(
                        """UPDATE downloads SET status = 'error', error_msg = ?, retry_count = ?, updated_at = ?
                           WHERE id = ? AND status = 'submitting'""",
                        (f"Retry {retry_count}/{max_retries} - {error_detail[:400]}", retry_count, now, item["id"]),
                    )
                await db.commit()

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
            started = time.monotonic()
            try:
                await self._tick()
                self._health["last_tick_error"] = ""
            except Exception as e:
                self._health["tick_errors"] += 1
                self._health["last_tick_error"] = str(e)[:200]
                self._record_error("queue_tick", e)
                import traceback; log(f"Queue tick error: {e}\n{traceback.format_exc()}")
            finally:
                self._health["last_tick_at"] = datetime.now(timezone.utc).isoformat()
                self._health["last_tick_seconds"] = round(time.monotonic() - started, 3)
            await asyncio.sleep(1)

    async def _tick(self):
        config = get_config()
        max_concurrent = config["downloads"]["simultaneous"]
        now = datetime.now(timezone.utc).isoformat()
        now_dt = datetime.now(timezone.utc)
        stalled_timeout_hours = max(0, min(168, int(config["downloads"].get("stalled_timeout_hours", 3) or 0)))

        # Never hold SQLite while waiting for the local RPC engine. One JSON-RPC
        # batch keeps tick cost nearly constant as the active queue grows.
        async with db_session(row_factory=True) as db:
            cursor = await db.execute(
                "SELECT * FROM downloads WHERE aria2_gid IS NOT NULL AND status NOT IN ('complete', 'error', 'failed')"
            )
            active_rows = await cursor.fetchall()
        rpc_started = time.monotonic()
        try:
            aria2_results = await aria2.tell_status_many([row["aria2_gid"] for row in active_rows])
        except Exception as exc:
            aria2_results = {row["aria2_gid"]: exc for row in active_rows}
        self._health["last_aria2_batch_seconds"] = round(time.monotonic() - rpc_started, 3)
        aria2_cleanup: list[tuple[str, str]] = []

        async with db_session(row_factory=True) as db:

            # ---- Update status for downloads submitted to aria2 ---- #
            for row in active_rows:
                try:
                    data = aria2_results[row["aria2_gid"]]
                    if isinstance(data, Exception):
                        raise data
                    parsed = aria2.parse_status(data)

                    name_update = parsed["name"] if parsed["name"] else row["name"]
                    progressed = parsed["downloaded"] > (row["downloaded"] or 0)
                    last_progress_at = now if progressed else (
                        row["last_progress_at"] or row["created_at"] or now
                    )
                    last_progress_dt = _parse_datetime(last_progress_at) or now_dt

                    if parsed["status"] != "complete" and parsed["progress"] >= 100:
                        file_path = _aria2_file_path(data)
                        completion_grace_passed = now_dt - last_progress_dt >= timedelta(minutes=5)
                        file_is_complete = (
                            file_path is not None
                            and parsed["size"] > 0
                            and _path_is_allowed(file_path, row["destination"], config)
                            and _file_matches_size(file_path, parsed["size"])
                        )
                        if completion_grace_passed and file_is_complete:
                            parsed["status"] = "complete"

                    if (
                        stalled_timeout_hours > 0
                        and parsed["status"] == "downloading"
                        and parsed["progress"] < 100
                        and now_dt - last_progress_dt >= timedelta(hours=stalled_timeout_hours)
                    ):
                        aria2_cleanup.append(("remove", row["aria2_gid"]))
                        await self._expire_download(
                            db, row, parsed, data, now, stalled_timeout_hours
                        )
                        continue

                    if parsed["status"] == "error":
                        # Retry logic
                        retry_count = (row["retry_count"] or 0) + 1
                        max_retries = row["max_retries"] or 5

                        aria2_cleanup.append(("result", row["aria2_gid"]))

                        if retry_count >= max_retries:
                            # Max retries reached — mark as failed definitively
                            cursor = await db.execute(
                                """UPDATE downloads SET
                                       name = ?, status = 'failed', progress = ?,
                                       speed = 0, size = ?, downloaded = ?,
                                       error_msg = ?, retry_count = ?,
                                       aria2_gid = NULL, updated_at = ?
                                   WHERE id = ? AND aria2_gid = ? AND status NOT IN ('complete', 'failed')""",
                                (name_update, parsed["progress"], parsed["size"],
                                 parsed["downloaded"],
                                 f"Max retries ({max_retries}) reached. Last error: {parsed['error_msg']}",
                                 retry_count, now, row["id"], row["aria2_gid"]),
                            )
                            if cursor.rowcount == 0:
                                continue
                            # Move to history and remove from active queue
                            await self._move_to_history(db, row["id"], now)
                            if not row["package_id"]:
                                await db.execute("DELETE FROM downloads WHERE id = ?", (row["id"],))
                            if not row["package_id"]:
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
                                   WHERE id = ? AND aria2_gid = ? AND status NOT IN ('complete', 'failed')""",
                                (name_update, retry_count,
                                 f"Retry {retry_count}/{max_retries} - {parsed['error_msg']}",
                                 now, row["id"], row["aria2_gid"]),
                            )
                    elif parsed["status"] == "complete":
                        aria2_cleanup.append(("result", row["aria2_gid"]))
                        await self._finalize_download(db, row, parsed, now)
                    else:
                        await db.execute(
                            """UPDATE downloads SET
                                   name = ?, status = ?, progress = ?,
                                   speed = ?, size = ?, downloaded = ?,
                                   updated_at = ?, last_progress_at = ?
                               WHERE id = ? AND aria2_gid = ? AND status NOT IN ('complete', 'failed')""",
                            (name_update, parsed["status"], parsed["progress"],
                             parsed["speed"], parsed["size"], parsed["downloaded"],
                             now, last_progress_at, row["id"], row["aria2_gid"]),
                        )

                except Exception as e:
                    log(f"aria2 status check failed for {row['id']} (gid={row['aria2_gid']}): {type(e).__name__}: {e}")
                    if _is_transient_aria2_error(e):
                        self._health["temporary_aria2_errors"] += 1
                        self._record_error("aria2_temporary", f"{type(e).__name__}: {e}")
                        # Keep the GID: aria2 may still be downloading while RPC is slow.
                        await db.execute(
                            """UPDATE downloads SET
                                   error_msg = ?, updated_at = ?
                               WHERE id = ? AND status NOT IN ('complete', 'failed')""",
                            (f"Temporary aria2 status check failed: {type(e).__name__}", now, row["id"]),
                        )
                        continue

                    if _is_missing_aria2_gid_error(e):
                        # aria2 really doesn't know this GID anymore — reset to pending.
                        await db.execute(
                            """UPDATE downloads SET
                                   aria2_gid = NULL, status = 'pending', speed = 0, updated_at = ?
                               WHERE id = ? AND status NOT IN ('complete', 'error', 'failed')""",
                            (now, row["id"]),
                        )
                    else:
                        self._record_error("aria2_status", f"{type(e).__name__}: {e}")
                        await db.execute(
                            """UPDATE downloads SET
                                   error_msg = ?, updated_at = ?
                               WHERE id = ? AND status NOT IN ('complete', 'failed')""",
                            (f"aria2 status check failed: {type(e).__name__}", now, row["id"]),
                        )

            await db.commit()

            # Recover abandoned submissions, but never reset a live resolver task.
            stale_rows = await (await db.execute(
                """SELECT id FROM downloads
                   WHERE status = 'submitting'
                   AND datetime(updated_at) <= datetime('now', '-5 minutes')"""
            )).fetchall()
            live_submissions = set(self._submission_tasks) | set(self.youtube_downloads.tasks)
            for stale in stale_rows:
                if stale["id"] in live_submissions:
                    continue
                await db.execute(
                    """UPDATE downloads SET status = 'pending',
                           error_msg = 'Recovered stale submission', updated_at = ?
                       WHERE id = ? AND status = 'submitting'""",
                    (now, stale["id"]),
                )
            await db.commit()

            # ---- Submit new downloads if slots are available ---- #
            cursor = await db.execute(
                """SELECT COUNT(*) FROM downloads
                   WHERE status IN ('submitting', 'downloading', 'postprocessing')
                   OR (aria2_gid IS NOT NULL AND status NOT IN ('complete', 'failed'))"""
            )
            (active_count,) = await cursor.fetchone()
            self._health["active_downloads"] = active_count

            cursor = await db.execute("SELECT COUNT(*) FROM downloads WHERE status = 'pending'")
            (pending_count,) = await cursor.fetchone()
            self._health["pending_downloads"] = pending_count

            slots = max_concurrent - active_count
            if slots > 0:
                cursor = await db.execute(
                    """SELECT * FROM downloads
                       WHERE status = 'pending' AND aria2_gid IS NULL
                       ORDER BY position ASC, created_at ASC
                       LIMIT ?""",
                    (min(100, max(slots * 4, slots)),),
                )
                pending = await cursor.fetchall()

                segments = config["downloads"].get("download_segments", 1)
                started = 0
                for item in pending:
                    if started >= slots:
                        break
                    if item["engine"] == "youtube" and not self.youtube_downloads.can_start():
                        continue
                    cursor = await db.execute(
                        """UPDATE downloads SET status = 'submitting', updated_at = ?
                           WHERE id = ? AND status = 'pending' AND aria2_gid IS NULL""",
                        (now, item["id"]),
                    )
                    if cursor.rowcount == 0:
                        continue
                    await db.commit()
                    started += 1
                    if item["engine"] == "youtube":
                        if not self.youtube_downloads.start(dict(item)):
                            await db.execute(
                                "UPDATE downloads SET status = 'pending' WHERE id = ? AND status = 'submitting'",
                                (item["id"],),
                            )
                            await db.commit()
                            started -= 1
                    else:
                        self._start_submission(dict(item), segments)

            # ---- Auto-retry errored downloads after a delay ---- #
            retry_delay = max(0, min(3600, int(config["downloads"].get("retry_delay_seconds", 5) or 0)))
            cursor = await db.execute(
                """SELECT id FROM downloads
                   WHERE status = 'error' AND retry_count > 0
                   AND retry_count < COALESCE(max_retries, 5)
                   AND datetime(updated_at) <= datetime('now', ?)""",
                (f"-{retry_delay} seconds",),
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

        for action, gid in aria2_cleanup:
            try:
                if action == "remove":
                    await aria2.remove(gid)
                else:
                    await aria2.remove_result(gid)
            except Exception as exc:
                self._record_error("aria2_cleanup", exc)

        now_ts = time.time()
        if now_ts - self._last_torrent_check >= 5:
            self._last_torrent_check = now_ts
            await check_torrents(self, now)

        snapshot, changed = await self.refresh_snapshot()
        if changed and self._ws_manager:
            await self._ws_manager.broadcast({
                "type": "downloads_update",
                "revision": snapshot["revision"],
                "data": snapshot["downloads"],
                "packages": snapshot["packages"],
                "torrents": snapshot["torrents"],
            })

        await self._maybe_auto_refresh_media()

    async def _is_media_auto_refresh_idle(self) -> bool:
        async with db_session() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM downloads WHERE status NOT IN ('complete', 'failed')")
            (download_count,) = await cursor.fetchone()
            if download_count:
                return False

            cursor = await db.execute("SELECT COUNT(*) FROM packages")
            (package_count,) = await cursor.fetchone()
            if package_count:
                return False

            cursor = await db.execute(
                "SELECT COUNT(*) FROM torrents WHERE status IN ('processing', 'ready_importing')"
            )
            (torrent_count,) = await cursor.fetchone()
            return torrent_count == 0

    async def _maybe_auto_refresh_media(self):
        if (
            not self._media_auto_refresh_pending
            or self._media_auto_refresh_running
            or time.monotonic() < self._media_auto_refresh_retry_at
        ):
            return
        if not await self._is_media_auto_refresh_idle():
            return

        self._media_auto_refresh_running = True
        try:
            # Re-check immediately before the external media API calls.
            if not await self._is_media_auto_refresh_idle():
                return
            result = await auto_refresh_recommended_libraries()
            refreshed = result.get("refreshed", [])
            errors = result.get("errors", [])
            if refreshed:
                names = ", ".join(item.get("library_title") or item.get("library_key", "") for item in refreshed)
                log(f"Media auto-refresh completed for: {names}")
            if errors:
                self._media_auto_refresh_retry_at = time.monotonic() + 300
                retry_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
                async with db_session() as db:
                    await db.execute(
                        "UPDATE media_refresh_state SET pending = 1, retry_at = ?, updated_at = ? WHERE id = 1",
                        (retry_at, datetime.now(timezone.utc).isoformat()),
                    )
                    await db.commit()
                for item in errors:
                    self._record_error("media_auto_refresh", item.get("error", "Unknown media refresh error"))
                return
            self._media_auto_refresh_pending = False
            self._media_auto_refresh_retry_at = 0.0
            async with db_session() as db:
                await db.execute(
                    "UPDATE media_refresh_state SET pending = 0, retry_at = NULL, updated_at = ? WHERE id = 1",
                    (datetime.now(timezone.utc).isoformat(),),
                )
                await db.commit()
        except Exception as e:
            self._media_auto_refresh_retry_at = time.monotonic() + 300
            retry_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            async with db_session() as db:
                await db.execute(
                    "UPDATE media_refresh_state SET pending = 1, retry_at = ?, updated_at = ? WHERE id = 1",
                    (retry_at, datetime.now(timezone.utc).isoformat()),
                )
                await db.commit()
            self._record_error("media_auto_refresh", f"{type(e).__name__}: {e}")
        finally:
            self._media_auto_refresh_running = False

    async def _move_torrent_to_history(self, db, row, now: str, error_msg: str):
        pkg_name = None
        if row["package_id"]:
            cursor = await db.execute(
                "SELECT name FROM packages WHERE id = ?", (row["package_id"],)
            )
            package = await cursor.fetchone()
            if package:
                pkg_name = package["name"]

        await db.execute(
            """INSERT OR REPLACE INTO history
               (id, name, url, destination, size, status, error_msg, package_name,
                created_at, completed_at, package_id, source_key)
               VALUES (?, ?, ?, ?, ?, 'failed', ?, ?, ?, ?, ?, ?)""",
            (
                row["id"],
                row["name"],
                f"alldebrid://magnet/{row['alldebrid_id']}",
                row["destination"],
                row["size"],
                error_msg,
                pkg_name,
                row["created_at"],
                now,
                row["package_id"],
                row["source_key"],
            ),
        )

    async def _fail_torrent(self, db, row, now: str, error_msg: str):
        cursor = await db.execute(
            """UPDATE torrents SET
                   status = 'error', speed = 0,
                   status_message = ?, updated_at = ?
               WHERE id = ? AND status IN ('processing', 'ready_importing')""",
            (error_msg, now, row["id"]),
        )
        if cursor.rowcount == 0:
            return

        await self._move_torrent_to_history(db, row, now, error_msg)
        if row["package_id"]:
            await self._check_package_complete(db, row["package_id"], now)
        else:
            await db.execute("DELETE FROM torrents WHERE id = ?", (row["id"],))
            asyncio.create_task(send_webhook("download_failed", {
                "name": row["name"] or "Torrent",
                "destination": row["destination"],
                "size": row["size"],
                "error_msg": error_msg,
                "status": "failed",
            }))
        await db.commit()

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
               (id, name, url, destination, size, status, error_msg, package_name,
                created_at, completed_at, source_key, package_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], row["name"], row["url"], row["destination"],
             row["size"], row["status"], row["error_msg"], pkg_name,
             row["created_at"], now, row["source_key"], row["package_id"]),
        )
        if row["status"] == "complete":
            self._media_auto_refresh_pending = True
            await db.execute(
                "UPDATE media_refresh_state SET pending = 1, retry_at = NULL, updated_at = ? WHERE id = 1",
                (now,),
            )
        await db.commit()

    async def _check_package_complete(self, db, package_id: str, now: str):
        pcur = await db.execute("SELECT * FROM packages WHERE id = ?", (package_id,))
        pkg = await pcur.fetchone()
        if not pkg or pkg["status"] != "active":
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM torrents WHERE package_id = ? AND status IN ('processing', 'ready_importing')",
            (package_id,),
        )
        (pending_torrents,) = await cursor.fetchone()
        if pending_torrents:
            return

        cursor = await db.execute(
            "SELECT COUNT(*) FROM downloads WHERE package_id = ? AND status NOT IN ('complete', 'failed')",
            (package_id,),
        )
        (remaining,) = await cursor.fetchone()
        if remaining == 0:
            claim = await db.execute(
                """UPDATE packages SET status = 'finalizing', updated_at = ?
                   WHERE id = ? AND status = 'active'""",
                (now, package_id),
            )
            if claim.rowcount == 0:
                return
            await db.commit()

            cursor = await db.execute(
                "SELECT COUNT(*) FROM downloads WHERE package_id = ?",
                (package_id,),
            )
            (total_downloads,) = await cursor.fetchone()

            # All downloads in package are done
            cursor = await db.execute(
                "SELECT COUNT(*) FROM downloads WHERE package_id = ? AND status = 'failed'",
                (package_id,),
            )
            (failed_downloads,) = await cursor.fetchone()
            cursor = await db.execute(
                "SELECT COUNT(*) FROM torrents WHERE package_id = ? AND status IN ('error', 'import_failed')",
                (package_id,),
            )
            (failed_torrents,) = await cursor.fetchone()
            failed_sources = pkg["failed_sources"] or 0
            pkg_status = "complete" if failed_downloads == 0 and failed_torrents == 0 and failed_sources == 0 else "partial"

            # Remove all package downloads from active table
            await db.execute("DELETE FROM downloads WHERE package_id = ?", (package_id,))
            await db.execute("DELETE FROM torrents WHERE package_id = ?", (package_id,))
            # Delete the package itself so it disappears from the UI
            await db.execute("DELETE FROM packages WHERE id = ?", (package_id,))
            await db.commit()

            # Webhook
            if total_downloads > 0 or failed_torrents > 0 or failed_sources > 0:
                asyncio.create_task(send_webhook("package_complete", {
                    "name": pkg["name"], "package_name": pkg["name"],
                    "destination": pkg["destination"], "status": pkg_status,
                }))

    async def _update_package_statuses(self, db, now: str):
        cursor = await db.execute("SELECT id FROM packages WHERE status = 'active'")
        pkgs = await cursor.fetchall()
        for pkg in pkgs:
            await self._check_package_complete(db, pkg["id"], now)

    async def finalize_youtube(self, item: dict, event: dict):
        path = Path(str(event.get("path") or ""))
        try:
            path.resolve().relative_to(Path(item["destination"]).resolve())
        except (ValueError, OSError):
            await self.fail_youtube(item, "YouTube worker returned a file outside the destination")
            return
        if not path.is_file():
            await self.fail_youtube(item, "YouTube final file is missing")
            return
        now = datetime.now(timezone.utc).isoformat()
        async with db_session(row_factory=True) as db:
            cursor = await db.execute(
                """UPDATE downloads SET name = ?, status = 'complete', progress = 100, speed = 0,
                       size = ?, downloaded = ?, error_msg = NULL, updated_at = ?, last_progress_at = ?
                   WHERE id = ? AND engine = 'youtube' AND status IN ('submitting', 'downloading', 'postprocessing')""",
                (path.name, path.stat().st_size, path.stat().st_size, now, now, item["id"]),
            )
            if cursor.rowcount == 0:
                return
            await self._move_to_history(db, item["id"], now)
            if not item["package_id"]:
                await db.execute("DELETE FROM downloads WHERE id = ?", (item["id"],))
                asyncio.create_task(send_webhook("download_complete", {
                    "name": path.name, "destination": item["destination"],
                    "size": path.stat().st_size, "status": "complete",
                }))
            else:
                await self._check_package_complete(db, item["package_id"], now)
            await db.commit()

    async def fail_youtube(self, item: dict, message: str):
        now = datetime.now(timezone.utc).isoformat()
        async with db_session(row_factory=True) as db:
            current = await (await db.execute(
                "SELECT status FROM downloads WHERE id = ?", (item["id"],)
            )).fetchone()
            if not current or current["status"] in ("paused", "complete", "failed"):
                return
            retry_count = (item["retry_count"] or 0) + 1
            max_retries = item["max_retries"] or 3
            if retry_count >= max_retries:
                await db.execute(
                    """UPDATE downloads SET status = 'failed', speed = 0, error_msg = ?, retry_count = ?, updated_at = ?
                       WHERE id = ? AND engine = 'youtube'""",
                    (f"Max retries ({max_retries}) reached. Last error: {message[:400]}", retry_count, now, item["id"]),
                )
                await self._move_to_history(db, item["id"], now)
                if not item["package_id"]:
                    await db.execute("DELETE FROM downloads WHERE id = ?", (item["id"],))
                    asyncio.create_task(send_webhook("download_failed", {
                        "name": item["name"] or item["url"], "destination": item["destination"],
                        "error_msg": message[:400], "status": "failed",
                    }))
                else:
                    await self._check_package_complete(db, item["package_id"], now)
            else:
                await db.execute(
                    """UPDATE downloads SET status = 'error', speed = 0, error_msg = ?, retry_count = ?, updated_at = ?
                       WHERE id = ? AND engine = 'youtube'""",
                    (f"Retry {retry_count}/{max_retries} - {message[:400]}", retry_count, now, item["id"]),
                )
            await db.commit()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def add_downloads(
        self, urls: list, destination: str, package_id: str = None,
        allow_duplicates: bool = False,
    ) -> list:
        now = datetime.now(timezone.utc).isoformat()
        ids = []
        seen = set()
        skip_nfo = bool(get_config()["downloads"].get("skip_nfo_files", True))
        async with db_session(row_factory=True) as db:
            cursor = await db.execute("SELECT COALESCE(MAX(position), 0) FROM downloads")
            (max_pos,) = await cursor.fetchone()
            pos = max_pos + 1
            max_retries = max(0, min(20, int(get_config()["downloads"].get("max_retries", 3) or 0)))

            for url in urls:
                url = url.strip()
                if not url or (url in seen and not allow_duplicates) or (skip_nfo and _looks_like_nfo(url)):
                    continue
                seen.add(url)
                video_id = youtube_video_id(url)
                item_source_key = f"youtube:{video_id}" if video_id else source_key("url", url)
                stored_url = canonical_video_url(video_id) if video_id else url

                # Skip if this URL is already in the active queue
                if not allow_duplicates:
                    cursor = await db.execute(
                        """SELECT id FROM downloads
                           WHERE (url = ? OR source_key = ?)
                           AND status IN ('pending', 'submitting', 'downloading', 'postprocessing', 'debrid', 'paused', 'error', 'duplicate_pending')""",
                        (stored_url, item_source_key),
                    )
                    if await cursor.fetchone():
                        continue

                dl_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO downloads
                       (id, url, status, destination, created_at, updated_at, position,
                        package_id, max_retries, last_progress_at, source_key,
                        engine, source_id, output_profile)
                       VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, 'aria2', ?, ?)""",
                    (
                        dl_id, stored_url, destination, now, now, pos, package_id,
                        max_retries, now, item_source_key, video_id or None,
                        "alldebrid_mp4" if video_id else None,
                    ),
                )
                ids.append(dl_id)
                pos += 1
            await db.commit()

        return ids

    async def add_youtube_downloads(
        self, items: list[dict], destination: str, *, engine: str,
        output_profile: str = "mp4", package_id: str | None = None,
    ) -> list[str]:
        now = datetime.now(timezone.utc).isoformat()
        ids = []
        async with db_session(row_factory=True) as db:
            (position,) = await (await db.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM downloads"
            )).fetchone()
            max_retries = max(0, min(20, int(get_config()["downloads"].get("max_retries", 3) or 0)))
            for item in items:
                video_id = str(item.get("id") or "")
                key = f"youtube:{video_id}"
                exists = await (await db.execute(
                    "SELECT 1 FROM downloads WHERE source_key = ? LIMIT 1", (key,)
                )).fetchone()
                if exists:
                    continue
                dl_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO downloads
                       (id, url, name, status, destination, created_at, updated_at, position,
                        package_id, max_retries, last_progress_at, source_key, engine,
                        source_id, output_profile, source_metadata)
                       VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        dl_id, item["url"], item.get("title") or video_id, destination,
                        now, now, position, package_id, max_retries, now, key,
                        "youtube" if engine == "youtube" else "aria2", video_id,
                        output_profile if engine == "youtube" else "alldebrid_mp4",
                        json.dumps(item, ensure_ascii=True),
                    ),
                )
                ids.append(dl_id)
                position += 1
            await db.commit()
        return ids

    async def create_package(
        self,
        name: str,
        destination: str,
        status: str = "active",
        source_count: int = 0,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        pkg_id = str(uuid.uuid4())

        async with db_session() as db:
            await db.execute(
                """INSERT INTO packages
                   (id, name, destination, status, source_count, failed_sources, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
                (pkg_id, name, destination, status, source_count, now, now),
            )
            await db.commit()

        return pkg_id

    async def activate_package(self, package_id: str, failed_sources: int = 0):
        now = datetime.now(timezone.utc).isoformat()
        async with db_session(row_factory=True) as db:
            await db.execute(
                """UPDATE packages SET status = 'active', failed_sources = ?, updated_at = ?
                   WHERE id = ? AND status = 'assembling'""",
                (max(0, failed_sources), now, package_id),
            )
            await db.commit()
            await self._check_package_complete(db, package_id, now)

    async def add_package(self, name: str, urls: list, destination: str) -> dict:
        pkg_id = await self.create_package(name, destination, source_count=len(urls))
        ids = await self.add_downloads(urls, destination, package_id=pkg_id)
        return {"package_id": pkg_id, "download_ids": ids}

    async def import_torrent_links(
        self,
        name: str,
        links: list[str],
        destination: str,
        package_id: str | None = None,
    ) -> dict:
        """Import resolved torrent files, grouping multi-file contents."""
        if package_id:
            ids = await self.add_downloads(links, destination, package_id=package_id)
            return {"package_id": package_id, "download_ids": ids}
        if len(links) > 1:
            return await self.add_package(name or "Torrent", links, destination)
        ids = await self.add_downloads(links, destination)
        return {"package_id": None, "download_ids": ids}

    async def pause_download(self, download_id: str):
        async with db_session(row_factory=True) as db:
            row = await (await db.execute(
                "SELECT aria2_gid, status, engine FROM downloads WHERE id = ?", (download_id,)
            )).fetchone()
        if row and row["engine"] == "youtube":
            await self.youtube_downloads.cancel(download_id)
        elif row and row["status"] == "downloading" and row["aria2_gid"]:
            try:
                await aria2.pause(row["aria2_gid"])
            except Exception:
                pass
        async with db_session() as db:
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE downloads SET status = 'paused', speed = 0, updated_at = ?
                   WHERE id = ? AND status IN ('pending', 'submitting', 'downloading', 'postprocessing', 'error')""",
                (now, download_id),
            )
            await db.commit()

    async def resume_download(self, download_id: str):
        async with db_session(row_factory=True) as db:
            row = await (await db.execute(
                "SELECT aria2_gid, status FROM downloads WHERE id = ?", (download_id,)
            )).fetchone()
        if not row or row["status"] not in ("paused", "error", "failed"):
            return

        new_status = "pending"
        clear_gid = False
        if row["aria2_gid"]:
            try:
                await aria2.resume(row["aria2_gid"])
                new_status = "downloading"
            except Exception:
                clear_gid = True

        async with db_session() as db:
            if clear_gid:
                await db.execute(
                    "UPDATE downloads SET aria2_gid = NULL WHERE id = ?", (download_id,)
                )
            now = datetime.now(timezone.utc).isoformat()
            if row["status"] == "failed":
                await db.execute(
                    "UPDATE downloads SET status = ?, retry_count = 0, error_msg = NULL, updated_at = ? WHERE id = ?",
                    (new_status, now, download_id),
                )
            else:
                await db.execute(
                    "UPDATE downloads SET status = ?, updated_at = ? WHERE id = ? AND status IN ('paused', 'error', 'failed')",
                    (new_status, now, download_id),
                )
            await db.commit()

    async def remove_download(self, download_id: str):
        async with db_session(row_factory=True) as db:
            row = await (await db.execute(
                "SELECT aria2_gid, engine, source_id, destination FROM downloads WHERE id = ?", (download_id,)
            )).fetchone()
        if row and row["engine"] == "youtube":
            await self.youtube_downloads.cancel(download_id)
            source_id = str(row["source_id"] or "")
            destination = Path(row["destination"])
            if source_id and destination.is_dir():
                for partial in destination.glob("*.part*"):
                    if f"[{source_id}]" in partial.name:
                        try:
                            partial.unlink()
                        except OSError:
                            pass
        elif row and row["aria2_gid"]:
            await aria2.remove(row["aria2_gid"])
        async with db_session() as db:
            await db.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
            await db.commit()

    async def pause_all(self):
        async with db_session(row_factory=True) as db:
            cursor = await db.execute(
                "SELECT id FROM downloads WHERE status = 'downloading'"
            )
            rows = await cursor.fetchall()
        for row in rows:
            await self.pause_download(row["id"])

    async def resume_all(self):
        async with db_session(row_factory=True) as db:
            cursor = await db.execute(
                "SELECT id FROM downloads WHERE status IN ('paused', 'error')"
            )
            rows = await cursor.fetchall()
        for row in rows:
            await self.resume_download(row["id"])

    async def remove_all(self):
        await self.youtube_downloads.stop()
        async with db_session(row_factory=True) as db:
            rows = await (await db.execute(
                "SELECT aria2_gid FROM downloads WHERE aria2_gid IS NOT NULL"
            )).fetchall()
        for row in rows:
            try:
                await aria2.remove(row["aria2_gid"])
            except Exception:
                pass
        async with db_session() as db:
            await db.execute("DELETE FROM downloads")
            await db.execute("DELETE FROM packages")
            await db.commit()

    async def clear_completed(self):
        now = datetime.now(timezone.utc).isoformat()
        async with db_session(row_factory=True) as db:
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
        async with db_session() as db:
            for i, dl_id in enumerate(ids):
                await db.execute(
                    "UPDATE downloads SET position = ? WHERE id = ?", (i, dl_id)
                )
            await db.commit()

    async def remove_package(self, package_id: str):
        async with db_session(row_factory=True) as db:
            cursor = await db.execute(
                "SELECT id, aria2_gid, engine FROM downloads WHERE package_id = ?", (package_id,)
            )
            rows = await cursor.fetchall()
        for row in rows:
            if row["engine"] == "youtube":
                await self.youtube_downloads.cancel(row["id"])
            elif row["aria2_gid"]:
                await aria2.remove(row["aria2_gid"])
        async with db_session() as db:
            await db.execute("DELETE FROM downloads WHERE package_id = ?", (package_id,))
            await db.execute("DELETE FROM packages WHERE id = ?", (package_id,))
            await db.commit()
