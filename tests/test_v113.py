import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.datastructures import UploadFile


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import database
from routers import downloads
from services import history, queue_manager


class V113Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()
        self.destination = database.DB_PATH.parent / "history-media"
        self.destination.mkdir(exist_ok=True)

    async def _insert_history(self, item_id, completed_at, *, package_id=None, package_name=None, status="complete", size=10):
        db = await database.open_db()
        try:
            await db.execute(
                """INSERT INTO history
                   (id, name, url, destination, size, status, package_name,
                    package_id, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id, f"{item_id}.mkv", f"https://example.com/{item_id}.mkv",
                    str(self.destination), size, status, package_name, package_id,
                    completed_at, completed_at,
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def test_history_schema_and_indexes_are_migrated(self):
        db = await database.open_db()
        try:
            columns = [row[1] for row in await (await db.execute("PRAGMA table_info(history)")).fetchall()]
            indexes = [row[1] for row in await (await db.execute("PRAGMA index_list(history)")).fetchall()]
        finally:
            await db.close()
        self.assertIn("package_id", columns)
        self.assertIn("idx_history_completed", indexes)
        self.assertIn("idx_history_status", indexes)
        self.assertIn("idx_history_package", indexes)

    async def test_history_view_groups_packages_and_legacy_entries(self):
        await self._insert_history("new-a", "2026-07-13T10:00:00+00:00", package_id="pkg-1", package_name="New batch", size=100)
        await self._insert_history("new-b", "2026-07-13T10:01:00+00:00", package_id="pkg-1", package_name="New batch", status="failed", size=0)
        await self._insert_history("old-a", "2026-07-12T10:00:00+00:00", package_name="Legacy batch", size=50)
        await self._insert_history("old-b", "2026-07-12T10:01:00+00:00", package_name="Legacy batch", size=50)
        await self._insert_history("single", "2026-07-11T10:00:00+00:00")

        result = await history.history_view("all", 30, "", "2026-07-13T00:00:00+00:00")
        self.assertEqual(len(result["groups"]), 3)
        package = next(group for group in result["groups"] if group["name"] == "New batch")
        self.assertEqual(package["item_count"], 2)
        self.assertEqual(package["status"], "partial")
        detail = await history.history_group(package["id"])
        self.assertEqual({item["id"] for item in detail["items"]}, {"new-a", "new-b"})
        self.assertEqual(result["summary"]["completed_today"], 1)
        self.assertEqual(result["summary"]["failed"], 1)

        failed = await history.history_view("failed", 30, "", "2026-07-13T00:00:00+00:00")
        self.assertEqual([group["name"] for group in failed["groups"]], ["New batch"])

    async def test_history_cursor_does_not_repeat_groups(self):
        for index in range(35):
            await self._insert_history(f"item-{index:02d}", f"2026-07-13T{index // 2:02d}:{index % 2:02d}:00+00:00")
        first = await history.history_view("all", 30, "", "2026-07-13T00:00:00+00:00")
        second = await history.history_view("all", 30, first["next_cursor"], "2026-07-13T00:00:00+00:00")
        first_ids = {group["id"] for group in first["groups"]}
        second_ids = {group["id"] for group in second["groups"]}
        self.assertEqual(len(first_ids), 30)
        self.assertEqual(len(second_ids), 5)
        self.assertFalse(first_ids & second_ids)

    async def test_bulk_history_removal_never_deletes_files(self):
        media = self.destination / "keep.mkv"
        media.write_bytes(b"keep")
        await self._insert_history("keep", "2026-07-13T10:00:00+00:00")
        removed = await history.remove_history_entries(["keep"])
        self.assertEqual(removed, 1)
        self.assertTrue(media.exists())

    async def test_queue_preserves_package_id_in_history(self):
        manager = queue_manager.QueueManager()
        package_id = await manager.create_package("Tracked batch", str(self.destination))
        download_id = (await manager.add_downloads(["https://example.com/tracked.mkv"], str(self.destination), package_id=package_id))[0]
        db = await database.open_db(row_factory=True)
        try:
            await db.execute("UPDATE downloads SET status = 'complete', name = 'tracked.mkv' WHERE id = ?", (download_id,))
            await db.commit()
            await manager._move_to_history(db, download_id, "2026-07-13T10:00:00+00:00")
            row = await (await db.execute("SELECT package_id FROM history WHERE id = ?", (download_id,))).fetchone()
        finally:
            await db.close()
        self.assertEqual(row["package_id"], package_id)

    async def test_mixed_direct_link_and_torrent_create_one_package(self):
        manager = queue_manager.QueueManager()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        torrent = UploadFile(filename="mixed.torrent", file=BytesIO(b"torrent-data"))
        uploaded = [{"id": 9001, "name": "Mixed torrent", "ready": False, "size": 100}]
        with (
            patch.object(downloads, "_validate_destination"),
            patch.object(downloads.alldebrid, "magnet_upload_files", AsyncMock(return_value=uploaded)),
        ):
            result = await downloads.add_automatic_batch(
                request=request,
                links="https://example.com/direct.mkv",
                destination=str(self.destination),
                package_name="Mixed batch",
                files=[torrent],
                _={"username": "vayaris"},
            )
        self.assertEqual(result["added"], 2)
        db = await database.open_db()
        try:
            download_package = (await (await db.execute("SELECT package_id FROM downloads")).fetchone())[0]
            torrent_package = (await (await db.execute("SELECT package_id FROM torrents")).fetchone())[0]
        finally:
            await db.close()
        self.assertEqual(download_package, result["package_id"])
        self.assertEqual(torrent_package, result["package_id"])

    async def test_frontend_uses_one_unified_submission_form(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "frontend" / "index.html").read_text()
        self.assertIn('id="unified-add-card"', html)
        self.assertIn('id="unified-torrent-input"', html)
        self.assertNotIn('id="torrent-modal"', html)
        self.assertNotIn('id="package-modal"', html)


if __name__ == "__main__":
    unittest.main()
