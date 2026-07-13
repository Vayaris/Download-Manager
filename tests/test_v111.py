import asyncio
from io import BytesIO
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.datastructures import UploadFile


TEST_ROOT = tempfile.TemporaryDirectory()
os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import aiosqlite
import database
from models import FileBrowserPathRequest, FileBrowserReorderRequest
from routers import downloads, filebrowser
from services import queue_manager


class V111Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()
        self.allowed_root = Path(TEST_ROOT.name) / "media"
        self.allowed_root.mkdir(exist_ok=True)

    async def test_filebrowser_preferences_are_server_persisted_and_ordered(self):
        first = self.allowed_root / "Films"
        second = self.allowed_root / "Series"
        first.mkdir(exist_ok=True)
        second.mkdir(exist_ok=True)
        user = {"username": "vayaris"}

        with patch.object(filebrowser, "_get_allowed_roots", return_value=[self.allowed_root]):
            await filebrowser.add_favorite(FileBrowserPathRequest(path=str(first)), user)
            await filebrowser.add_favorite(FileBrowserPathRequest(path=str(second)), user)
            await filebrowser.reorder_favorites(
                FileBrowserReorderRequest(paths=[str(second), str(first)]), user
            )
            await filebrowser.add_recent(FileBrowserPathRequest(path=str(first)), user)
            preferences = await filebrowser.get_preferences(user)

        self.assertEqual([item["path"] for item in preferences["favorites"]], [str(second), str(first)])
        self.assertEqual([item["path"] for item in preferences["recents"]], [str(first)])
        self.assertTrue(all(item["available"] for item in preferences["favorites"]))

    async def test_assembling_package_cannot_close_early_and_notifies_once(self):
        manager = queue_manager.QueueManager()
        package_id = await manager.create_package(
            "Batch test", str(self.allowed_root), status="assembling", source_count=2
        )
        download_ids = await manager.add_downloads(
            ["https://example.com/a", "https://example.com/b"],
            str(self.allowed_root),
            package_id=package_id,
        )
        self.assertEqual(len(download_ids), 2)

        webhook = AsyncMock()
        with patch.object(queue_manager, "send_webhook", webhook):
            async with aiosqlite.connect(str(database.DB_PATH)) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "UPDATE downloads SET status = 'complete' WHERE package_id = ?",
                    (package_id,),
                )
                await db.commit()
                await manager._check_package_complete(
                    db, package_id, "2026-07-13T12:00:00+00:00"
                )
                cursor = await db.execute("SELECT status FROM packages WHERE id = ?", (package_id,))
                self.assertEqual((await cursor.fetchone())["status"], "assembling")

            await manager.activate_package(package_id)
            await asyncio.sleep(0)

        webhook.assert_awaited_once()
        self.assertEqual(webhook.await_args.args[0], "package_complete")
        self.assertEqual(webhook.await_args.args[1]["status"], "complete")
        async with aiosqlite.connect(str(database.DB_PATH)) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM packages WHERE id = ?", (package_id,))
            self.assertEqual((await cursor.fetchone())[0], 0)

    async def test_two_direct_links_are_automatically_grouped(self):
        manager = queue_manager.QueueManager()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        with patch.object(downloads, "_validate_destination"):
            result = await downloads.add_automatic_batch(
                request=request,
                links="https://example.com/a\nhttps://example.com/b",
                destination=str(self.allowed_root),
                package_name="Lot test",
                files=[],
                _={"username": "vayaris"},
            )

        self.assertEqual(result["added"], 2)
        self.assertEqual(result["package_name"], "Lot test")
        async with aiosqlite.connect(str(database.DB_PATH)) as db:
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT package_id), COUNT(*) FROM downloads WHERE package_id = ?",
                (result["package_id"],),
            )
            package_count, download_count = await cursor.fetchone()
        self.assertEqual(package_count, 1)
        self.assertEqual(download_count, 2)

    async def test_two_torrent_files_share_one_package(self):
        manager = queue_manager.QueueManager()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        files = [
            UploadFile(filename="first.torrent", file=BytesIO(b"torrent-one")),
            UploadFile(filename="second.torrent", file=BytesIO(b"torrent-two")),
        ]
        uploaded = [
            {"id": 101, "name": "First", "ready": False, "size": 100},
            {"id": 102, "name": "Second", "ready": False, "size": 200},
        ]
        with (
            patch.object(downloads, "_validate_destination"),
            patch.object(downloads.alldebrid, "magnet_upload_files", AsyncMock(return_value=uploaded)),
        ):
            result = await downloads.add_automatic_batch(
                request=request,
                links="",
                destination=str(self.allowed_root),
                package_name="Lot torrents",
                files=files,
                _={"username": "vayaris"},
            )

        self.assertEqual(result["added"], 2)
        async with aiosqlite.connect(str(database.DB_PATH)) as db:
            cursor = await db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT package_id) FROM torrents WHERE package_id = ?",
                (result["package_id"],),
            )
            torrent_count, package_count = await cursor.fetchone()
        self.assertEqual(torrent_count, 2)
        self.assertEqual(package_count, 1)

    async def test_failed_batch_source_produces_one_partial_notification(self):
        manager = queue_manager.QueueManager()
        package_id = await manager.create_package(
            "Partial batch", str(self.allowed_root), status="assembling", source_count=2
        )
        await manager.add_downloads(
            ["https://example.com/ok"], str(self.allowed_root), package_id=package_id
        )
        async with aiosqlite.connect(str(database.DB_PATH)) as db:
            await db.execute(
                "UPDATE downloads SET status = 'complete' WHERE package_id = ?", (package_id,)
            )
            await db.commit()

        webhook = AsyncMock()
        with patch.object(queue_manager, "send_webhook", webhook):
            await manager.activate_package(package_id, failed_sources=1)
            await asyncio.sleep(0)

        webhook.assert_awaited_once()
        self.assertEqual(webhook.await_args.args[1]["status"], "partial")


if __name__ == "__main__":
    unittest.main()
