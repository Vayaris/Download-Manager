import asyncio
import json
import sys
from pathlib import Path

from config import get_config
from database import db_session
from services.youtube_setup import friendly_error


class YouTubeDownloadService:
    def __init__(self, queue_manager):
        self.queue_manager = queue_manager
        self.tasks: dict[str, asyncio.Task] = {}
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self.worker = Path(__file__).resolve().parents[1] / "youtube_worker.py"

    def active_count(self) -> int:
        return sum(not task.done() for task in self.tasks.values())

    def can_start(self) -> bool:
        limit = max(1, min(4, int(get_config().get("youtube", {}).get("max_concurrent", 2) or 2)))
        return self.active_count() < limit

    def start(self, item: dict):
        if item["id"] in self.tasks or not self.can_start():
            return False
        task = asyncio.create_task(self._run(item))
        self.tasks[item["id"]] = task
        task.add_done_callback(lambda done, download_id=item["id"]: self._finished(download_id, done))
        return True

    def _finished(self, download_id: str, task: asyncio.Task):
        self.tasks.pop(download_id, None)
        self.processes.pop(download_id, None)
        if not task.cancelled() and task.exception():
            self.queue_manager._record_error("youtube_worker", task.exception())

    async def _run(self, item: dict):
        cfg = get_config().get("youtube", {})
        command = [
            sys.executable, str(self.worker), "--url", item["url"],
            "--destination", item["destination"],
            "--profile", item.get("output_profile") or "mp4",
            "--speed-limit", str(max(0, int(cfg.get("speed_limit", 0) or 0))),
            "--video-id", item.get("source_id") or "unknown",
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.processes[item["id"]] = process
        await self._set_status(item["id"], "downloading")
        last_error = "YouTube worker failed"
        final_event = None
        stderr_buffer = bytearray()

        async def drain_stderr():
            while True:
                chunk = await process.stderr.read(2048)
                if not chunk:
                    return
                stderr_buffer.extend(chunk)
                if len(stderr_buffer) > 8192:
                    del stderr_buffer[:-8192]

        stderr_task = asyncio.create_task(drain_stderr())
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").strip()
                if not text.startswith("DMYT "):
                    continue
                try:
                    event = json.loads(text[5:])
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress":
                    await self._progress(item["id"], event)
                elif kind == "postprocessing":
                    await self._set_status(item["id"], "postprocessing")
                elif kind == "complete":
                    final_event = event
                elif kind == "error":
                    last_error = str(event.get("message") or last_error)
            return_code = await process.wait()
            await stderr_task
            if return_code == 0 and final_event:
                await self.queue_manager.finalize_youtube(item, final_event)
            elif return_code != 0:
                stderr = stderr_buffer.decode("utf-8", "replace").strip()
                await self.queue_manager.fail_youtube(
                    item, friendly_error(stderr[-400:] or last_error)
                )
            else:
                await self.queue_manager.fail_youtube(item, "YouTube worker returned no final file")
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)

    async def _set_status(self, download_id: str, status: str):
        async with db_session() as db:
            await db.execute(
                "UPDATE downloads SET status = ?, speed = 0, updated_at = datetime('now') WHERE id = ? AND engine = 'youtube'",
                (status, download_id),
            )
            await db.commit()

    async def _progress(self, download_id: str, event: dict):
        async with db_session() as db:
            await db.execute(
                """UPDATE downloads SET status = 'downloading', progress = ?, speed = ?, size = ?,
                       downloaded = ?, last_progress_at = datetime('now'), updated_at = datetime('now')
                   WHERE id = ? AND engine = 'youtube'""",
                (
                    float(event.get("progress") or 0), int(event.get("speed") or 0),
                    int(event.get("total") or 0), int(event.get("downloaded") or 0), download_id,
                ),
            )
            await db.commit()

    async def cancel(self, download_id: str):
        task = self.tasks.get(download_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def stop(self):
        for task in list(self.tasks.values()):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()
        self.processes.clear()
