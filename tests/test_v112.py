import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import database
from models import DuplicateCommitRequest, DuplicateDecision, MediaSettingsRequest
from routers import downloads, settings
from services import diagnostics, duplicates, media_refresh, queue_manager


class V112Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()
        self.root = database.DB_PATH.parent / "media-v112"
        self.root.mkdir(exist_ok=True)
        duplicates.STAGING_ROOT = database.DB_PATH.parent / "submissions-v112"

    async def test_preflight_detects_internal_active_history_and_disk_duplicates(self):
        existing = self.root / "movie.mkv"
        existing.write_bytes(b"existing")
        db = await database.open_db()
        try:
            await db.execute(
                """INSERT INTO downloads
                   (id, url, status, destination, created_at, updated_at, source_key)
                   VALUES ('active', ?, 'downloading', ?, 'now', 'now', ?)""",
                ("https://example.com/active.mkv", str(self.root), duplicates.source_key("url", "https://example.com/active.mkv")),
            )
            await db.execute(
                """INSERT INTO history
                   (id, name, url, destination, status, created_at, completed_at)
                   VALUES ('history', 'old.mkv', 'https://example.com/old.mkv', ?, 'complete', 'now', 'now')""",
                (str(self.root),),
            )
            await db.commit()
        finally:
            await db.close()

        result = await duplicates.create_submission(
            "vayaris", str(self.root), "Duplicates",
            [
                "https://example.com/active.mkv",
                "https://example.com/active.mkv",
                "https://example.com/old.mkv",
                "https://example.com/movie.mkv",
            ], [],
        )
        conflict_types = [{entry["type"] for entry in item["conflicts"]} for item in result["items"]]
        self.assertIn("active", conflict_types[0])
        self.assertIn("batch_duplicate", conflict_types[1])
        self.assertIn("history", conflict_types[2])
        self.assertIn("destination", conflict_types[3])

    async def test_commit_can_ignore_one_duplicate_without_creating_empty_package(self):
        staged = await duplicates.create_submission(
            "vayaris", str(self.root), "Single remaining",
            ["https://example.com/a.mkv", "https://example.com/a.mkv"], [],
        )
        manager = queue_manager.QueueManager()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        duplicate_item = staged["items"][1]
        with patch.object(downloads, "_validate_destination"):
            result = await downloads.commit_submission(
                staged["submission_id"],
                DuplicateCommitRequest(decisions=[DuplicateDecision(source_id=duplicate_item["id"], action="ignore")]),
                request,
                {"username": "vayaris"},
            )
        self.assertEqual(result["added"], 1)
        self.assertNotIn("package_id", result)

    async def test_disk_overwrite_requires_explicit_confirmation(self):
        (self.root / "same.mkv").write_bytes(b"old")
        staged = await duplicates.create_submission(
            "vayaris", str(self.root), "Overwrite", ["https://example.com/same.mkv"], [],
        )
        item = staged["items"][0]
        manager = queue_manager.QueueManager()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        with self.assertRaises(Exception):
            await downloads.commit_submission(
                staged["submission_id"],
                DuplicateCommitRequest(decisions=[DuplicateDecision(source_id=item["id"], action="download")]),
                request,
                {"username": "vayaris"},
            )

    async def test_diagnostic_events_are_persisted_and_redacted(self):
        await diagnostics.record_event(
            "tests", "secret", "request token=abc123 ghp_fakevalue", context={"url": "https://x/?apikey=secret"}
        )
        events = await diagnostics.list_events()
        self.assertEqual(events[0]["source"], "tests")
        serialized = json.dumps(events[0])
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("ghp_fakevalue", serialized)
        self.assertNotIn("apikey=secret", serialized)

    async def test_sqlite_busy_timeout_allows_concurrent_writers(self):
        async def writer(index):
            db = await database.open_db()
            try:
                await db.execute(
                    """INSERT INTO diagnostic_events
                       (created_at, severity, source, code, message) VALUES (?, 'info', 'concurrency', ?, 'ok')""",
                    (str(index), str(index)),
                )
                await db.commit()
            finally:
                await db.close()

        await asyncio.gather(*(writer(index) for index in range(20)))
        db = await database.open_db()
        try:
            cursor = await db.execute("SELECT COUNT(*) FROM diagnostic_events WHERE source = 'concurrency'")
            self.assertEqual((await cursor.fetchone())[0], 20)
        finally:
            await db.close()

    async def test_stale_submitting_download_is_recovered(self):
        db = await database.open_db()
        try:
            await db.execute(
                """INSERT INTO downloads
                   (id, url, status, destination, created_at, updated_at, position)
                   VALUES ('stale', 'https://example.com/file', 'submitting', ?,
                           datetime('now', '-10 minutes'), datetime('now', '-10 minutes'), 1)""",
                (str(self.root),),
            )
            await db.commit()
        finally:
            await db.close()
        manager = queue_manager.QueueManager()
        config = queue_manager.get_config()
        config["downloads"]["simultaneous"] = 0
        with patch.object(queue_manager, "get_config", return_value=config):
            await manager._tick()
        db = await database.open_db()
        try:
            cursor = await db.execute("SELECT status FROM downloads WHERE id = 'stale'")
            self.assertEqual((await cursor.fetchone())[0], "pending")
        finally:
            await db.close()

    async def test_media_auto_refresh_deduplicates_same_library(self):
        config = {
            "media": {"active": "plex"},
            "plex": {"enabled": True, "auto_refresh_enabled": True, "auto_refresh_enabled_at": None},
            "jellyfin": {"enabled": False},
        }
        suggestions = [
            {"library_key": "1", "library_title": "Films", "download_id": "a"},
            {"library_key": "1", "library_title": "Films", "download_id": "b"},
        ]
        refresh = AsyncMock(return_value={"status": "refreshed", "library_key": "1"})
        with (
            patch.object(media_refresh, "get_config", return_value=config),
            patch.object(
                media_refresh, "media_refresh_analysis",
                AsyncMock(return_value={"suggestions": suggestions, "unmatched": []}),
            ),
            patch.object(media_refresh, "refresh_library_from_config", refresh),
            patch.object(media_refresh, "update_config", side_effect=lambda mutate: (mutate(config), True)),
        ):
            result = await media_refresh.auto_refresh_recommended_libraries()
        self.assertTrue(result["attempted"])
        refresh.assert_awaited_once()

    async def test_jellyfin_docker_mapping_matches_download_destination(self):
        completed_at = datetime.now(timezone.utc).isoformat()
        async with database.db_session() as db:
            await db.execute(
                """INSERT INTO history
                   (id, name, url, destination, status, created_at, completed_at)
                   VALUES ('movie', 'Example.mkv', 'https://example.test/movie', ?, 'complete', ?, ?)""",
                ("/mnt/media/movies", completed_at, completed_at),
            )
            await db.commit()

        config = {
            "media": {"active": "jellyfin"},
            "plex": {"enabled": False},
            "jellyfin": {
                "enabled": True,
                "url": "http://jellyfin:8096",
                "token": "api-key",
                "last_refreshes": {},
                "path_mappings": [{
                    "download_prefix": "/mnt/media",
                    "jellyfin_prefix": "/media",
                }],
            },
        }
        libraries = AsyncMock(return_value=[{
            "key": "0123456789abcdef0123456789abcdef",
            "title": "Movies",
            "type": "movies",
            "locations": ["/media/movies"],
        }])
        with patch.object(media_refresh.jellyfin, "libraries", libraries):
            result = await media_refresh.media_refresh_analysis(config)

        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["unmatched"], [])
        suggestion = result["suggestions"][0]
        self.assertEqual(suggestion["mapped_from"], "/mnt/media")
        self.assertEqual(suggestion["matched_candidate"], "/media/movies/Example.mkv")

    async def test_plex_same_path_matching_is_unchanged(self):
        completed_at = datetime.now(timezone.utc).isoformat()
        async with database.db_session() as db:
            await db.execute(
                """INSERT INTO history
                   (id, name, url, destination, status, created_at, completed_at)
                   VALUES ('plex-movie', 'Example.mkv', 'https://example.test/plex', ?, 'complete', ?, ?)""",
                ("/mnt/media/movies", completed_at, completed_at),
            )
            await db.commit()

        config = {
            "media": {"active": "plex"},
            "plex": {
                "enabled": True,
                "url": "http://127.0.0.1:32400",
                "token": "plex-token",
                "last_refreshes": {},
            },
            "jellyfin": {"enabled": False},
        }
        libraries = AsyncMock(return_value=[{
            "key": "1",
            "title": "Films",
            "type": "movie",
            "locations": ["/mnt/media/movies"],
        }])
        with patch.object(media_refresh.plex, "libraries", libraries):
            result = await media_refresh.media_refresh_analysis(config)

        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["suggestions"][0]["mapped_from"], "")
        self.assertEqual(result["unmatched"], [])

    async def test_jellyfin_unmatched_path_is_reported_without_refresh(self):
        config = {
            "media": {"active": "jellyfin"},
            "plex": {"enabled": False},
            "jellyfin": {
                "enabled": True,
                "url": "http://jellyfin:8096",
                "token": "api-key",
                "auto_refresh_enabled": True,
                "auto_refresh_enabled_at": None,
            },
        }
        analysis = {
            "suggestions": [],
            "unmatched": [{"destination": "/mnt/media/movies", "history_id": "movie"}],
        }

        def update(mutator):
            mutator(config)
            return config, True

        diagnostic = MagicMock()
        refresh = AsyncMock()
        with (
            patch.object(media_refresh, "get_config", return_value=config),
            patch.object(media_refresh, "media_refresh_analysis", AsyncMock(return_value=analysis)),
            patch.object(media_refresh, "refresh_library_from_config", refresh),
            patch.object(media_refresh, "update_config", side_effect=update),
            patch.object(media_refresh, "record_event_nowait", diagnostic),
        ):
            result = await media_refresh.auto_refresh_recommended_libraries()

        self.assertEqual(result["status"], "unmatched")
        self.assertFalse(result["attempted"])
        refresh.assert_not_awaited()
        self.assertEqual(
            config["jellyfin"]["auto_refresh_last_result"]["unmatched_destinations"],
            ["/mnt/media/movies"],
        )
        diagnostic.assert_called_once()

    async def test_saving_jellyfin_mapping_rearms_auto_refresh(self):
        config = {
            "media": {"active": "jellyfin"},
            "plex": {"enabled": False},
            "jellyfin": {
                "enabled": True,
                "url": "http://jellyfin:8096",
                "token": "api-key",
                "auto_refresh_enabled": True,
                "path_mappings": [],
            },
        }
        manager = SimpleNamespace(schedule_media_auto_refresh=AsyncMock())
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        body = MediaSettingsRequest(
            provider="jellyfin",
            path_mappings=[{
                "download_prefix": "/mnt/media",
                "jellyfin_prefix": "/media",
            }],
        )

        def update(mutator):
            mutator(config)
            return config, True

        with (
            patch.object(settings, "get_config", return_value=config),
            patch.object(settings, "update_config", side_effect=update),
            patch.object(settings, "validate_destination"),
        ):
            result = await settings.update_media_settings(body, request, _={"username": "vayaris"})

        self.assertEqual(result["path_mappings"][0]["jellyfin_prefix"], "/media")
        manager.schedule_media_auto_refresh.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
