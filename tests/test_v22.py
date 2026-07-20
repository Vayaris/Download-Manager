import asyncio
import os
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import database
from models import MagnetUploadRequest
from routers import torrents
from services.aria2_service import Aria2RpcError, Aria2Service
from services import queue_manager, torrent_tracker, webhook


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.is_closed = False

    async def post(self, url, json):
        self.calls.append((url, json))
        return FakeResponse(self.payload)

    async def aclose(self):
        self.is_closed = True


class V22Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()

    async def test_aria2_statuses_use_one_batch_and_keep_per_gid_errors(self):
        client = FakeClient([
            {"jsonrpc": "2.0", "id": "1", "result": {"status": "active"}},
            {"jsonrpc": "2.0", "id": "2", "error": {"code": 1, "message": "GID not found"}},
        ])
        service = Aria2Service()
        service._client = client
        with patch.object(service, "_get_secret", return_value="secret"):
            result = await service.tell_status_many(["gid-a", "gid-b"])

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(client.calls[0][1]), 2)
        self.assertEqual(result["gid-a"]["status"], "active")
        self.assertIsInstance(result["gid-b"], Aria2RpcError)
        self.assertEqual(result["gid-b"].category, "missing_gid")

    async def test_snapshot_revision_only_changes_with_queue_content(self):
        manager = queue_manager.QueueManager()
        empty = {"db_revision": 0, "downloads": [], "packages": [], "torrents": []}
        changed = {"db_revision": 1, "downloads": [{"id": "one"}], "packages": [], "torrents": []}
        with patch.object(
            queue_manager,
            "load_queue_snapshot",
            AsyncMock(side_effect=[empty, changed]),
        ) as load_snapshot, patch.object(
            queue_manager,
            "load_queue_revision",
            AsyncMock(side_effect=[0, 0, 1]),
        ):
            first, first_changed = await manager.refresh_snapshot()
            second, second_changed = await manager.refresh_snapshot()
            third, third_changed = await manager.refresh_snapshot()

        self.assertTrue(first_changed)
        self.assertFalse(second_changed)
        self.assertTrue(third_changed)
        self.assertEqual((first["revision"], second["revision"], third["revision"]), (1, 1, 2))
        self.assertEqual(load_snapshot.await_count, 2)

    async def test_torrent_network_poll_runs_without_an_open_database_session(self):
        async with database.db_session() as db:
            await db.execute(
                """INSERT INTO torrents
                   (id, alldebrid_id, name, status, destination, created_at, updated_at, last_progress_at)
                   VALUES ('torrent', 42, 'Test', 'processing', '/tmp', ?, ?, ?)""",
                ("2026-07-19T12:00:00+00:00",) * 3,
            )
            await db.commit()

        open_sessions = 0
        original_session = database.db_session

        @asynccontextmanager
        async def tracked_session(*args, **kwargs):
            nonlocal open_sessions
            open_sessions += 1
            try:
                async with original_session(*args, **kwargs) as db:
                    yield db
            finally:
                open_sessions -= 1

        async def status(_):
            self.assertEqual(open_sessions, 0)
            await asyncio.sleep(0)
            return {"statusCode": 1, "downloaded": 5, "size": 10}

        manager = queue_manager.QueueManager()
        config = queue_manager.get_config()
        config["downloads"]["stalled_timeout_hours"] = 0
        with (
            patch.object(torrent_tracker, "db_session", tracked_session),
            patch.object(torrent_tracker, "get_config", return_value=config),
            patch.object(torrent_tracker.alldebrid, "magnet_status", status),
        ):
            await torrent_tracker.check_torrents(manager, "2026-07-19T12:01:00+00:00")

        async with database.db_session() as db:
            progress = (await (await db.execute(
                "SELECT progress FROM torrents WHERE id = 'torrent'"
            )).fetchone())[0]
        self.assertEqual(progress, 50)

    async def test_ready_torrent_route_resolves_without_an_open_database_session(self):
        open_sessions = 0
        original_session = database.db_session

        @asynccontextmanager
        async def tracked_session(*args, **kwargs):
            nonlocal open_sessions
            open_sessions += 1
            try:
                async with original_session(*args, **kwargs) as db:
                    yield db
            finally:
                open_sessions -= 1

        async def files(_):
            self.assertEqual(open_sessions, 0)
            return ["https://example.test/file"]

        manager = SimpleNamespace(import_torrent_links=AsyncMock(return_value={"download_ids": ["one"]}))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        with (
            patch.object(torrents, "db_session", tracked_session),
            patch.object(torrents, "_validate_destination"),
            patch.object(
                torrents.alldebrid, "magnet_upload",
                AsyncMock(return_value=[{"id": 42, "name": "Ready", "ready": True}]),
            ),
            patch.object(torrents.alldebrid, "magnet_files", files),
            patch.object(torrents.alldebrid, "magnet_delete", AsyncMock()),
        ):
            result = await torrents.submit_magnets(
                MagnetUploadRequest(magnets=["magnet:?xt=test"], destination="/tmp"),
                request,
                _={"username": "vayaris"},
            )
        self.assertEqual(result["added"], 1)

    async def test_media_refresh_request_survives_manager_restart(self):
        async with database.db_session(row_factory=True) as db:
            await db.execute(
                """INSERT INTO downloads
                   (id, url, name, status, destination, created_at, updated_at)
                   VALUES ('done', 'https://example.test/file', 'file', 'complete', '/tmp', 'now', 'now')"""
            )
            await db.commit()
            manager = queue_manager.QueueManager()
            await manager._move_to_history(db, "done", "2026-07-19T12:00:00+00:00")

        async with database.db_session() as db:
            pending = (await (await db.execute(
                "SELECT pending FROM media_refresh_state WHERE id = 1"
            )).fetchone())[0]
        restarted = queue_manager.QueueManager()
        async with database.db_session() as db:
            state = await (await db.execute(
                "SELECT pending FROM media_refresh_state WHERE id = 1"
            )).fetchone()
        restarted._media_auto_refresh_pending = bool(state[0])
        self.assertEqual(pending, 1)
        self.assertTrue(restarted._media_auto_refresh_pending)

    async def test_queue_indexes_are_created(self):
        async with database.db_session() as db:
            indexes = {
                row[1] for row in await (await db.execute("PRAGMA index_list(downloads)"))
                .fetchall()
            }
        self.assertTrue({
            "idx_downloads_status_position",
            "idx_downloads_package_status",
            "idx_downloads_gid_status",
        }.issubset(indexes))

    async def test_concurrent_package_finalizers_emit_one_notification(self):
        async with database.db_session() as db:
            await db.execute(
                """INSERT INTO packages
                   (id, name, destination, status, created_at, updated_at)
                   VALUES ('package', 'Batch', '/tmp', 'active', 'now', 'now')"""
            )
            for item_id in ("one", "two"):
                await db.execute(
                    """INSERT INTO downloads
                       (id, url, name, status, destination, package_id, created_at, updated_at)
                       VALUES (?, ?, ?, 'complete', '/tmp', 'package', 'now', 'now')""",
                    (item_id, f"https://example.test/{item_id}", item_id),
                )
            await db.commit()

        manager = queue_manager.QueueManager()

        async def finalize():
            async with database.db_session(row_factory=True) as db:
                await manager._check_package_complete(
                    db, "package", "2026-07-19T12:00:00+00:00"
                )

        notify = AsyncMock()
        with patch.object(queue_manager, "send_webhook", notify):
            await asyncio.gather(finalize(), finalize())
            await asyncio.sleep(0)

        notify.assert_awaited_once()
        async with database.db_session() as db:
            count = (await (await db.execute(
                "SELECT COUNT(*) FROM packages WHERE id = 'package'"
            )).fetchone())[0]
        self.assertEqual(count, 0)

    async def test_webhook_http_failure_is_recorded(self):
        response = MagicMock()
        response.raise_for_status.side_effect = RuntimeError("HTTP 500")
        client = AsyncMock()
        client.__aenter__.return_value.post.return_value = response
        config = {
            "webhooks": {
                "enabled": True,
                "url": "https://example.test/hook",
                "events": ["download_complete"],
                "format": "generic",
            }
        }
        with (
            patch.object(webhook, "get_config", return_value=config),
            patch.object(webhook.httpx, "AsyncClient", return_value=client),
            patch.object(webhook, "record_event_nowait") as record,
        ):
            await webhook.send_webhook("download_complete", {"name": "file"})
        record.assert_called_once()

    async def test_manager_stop_cancels_workers_and_closes_aria2_client(self):
        manager = queue_manager.QueueManager()
        manager._running = True
        manager._task = asyncio.create_task(asyncio.sleep(60))
        submission = asyncio.create_task(asyncio.sleep(60))
        manager._submission_tasks["one"] = submission
        with (
            patch.object(manager.youtube_downloads, "stop", AsyncMock()) as stop_youtube,
            patch.object(queue_manager.aria2, "close", AsyncMock()) as close_aria2,
        ):
            await manager.stop()
        self.assertTrue(submission.cancelled())
        self.assertEqual(manager._submission_tasks, {})
        stop_youtube.assert_awaited_once()
        close_aria2.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
