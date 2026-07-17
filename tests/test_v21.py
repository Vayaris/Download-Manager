import asyncio
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import database
from services import alldebrid as alldebrid_module
from services import youtube_cookies
from services import youtube_setup
from services import queue_manager as queue_manager_module
from services.queue_manager import QueueManager
from services.youtube import (
    YouTubeAnalysisService,
    canonical_video_url,
    is_channel_url,
    is_youtube_url,
    youtube_video_id,
)
from youtube_worker import MP4_FORMATS, download_mp4, rich_format


class AllDebridStreamingTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _client(handler):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        return patch.object(
            alldebrid_module.httpx,
            "AsyncClient",
            side_effect=lambda *args, **kwargs: real_client(
                transport=transport, timeout=kwargs.get("timeout")
            ),
        )

    async def test_unlock_returns_an_immediate_link(self):
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer secret")
            return httpx.Response(200, request=request, json={
                "status": "success", "data": {"link": "https://cdn.example/video.mp4"},
            })

        service = alldebrid_module.AllDebridService()
        with self._client(handler):
            result = await service.unrestrict("https://youtube.com/watch?v=abcdefghijk", "secret")
        self.assertEqual(result, "https://cdn.example/video.mp4")

    async def test_unlock_selects_the_best_combined_mp4_stream(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("/unlock"):
                return httpx.Response(200, request=request, json={
                    "status": "success",
                    "data": {
                        "id": "media-id",
                        "streams": [
                            {"id": "audio", "ext": "m4a", "quality": "1080p", "filesize": 100},
                            {"id": "720+audio", "ext": "mp4", "quality": "720p", "filesize": 200},
                            {"id": "1080+audio", "ext": "mp4", "quality": "1080p", "filesize": "300"},
                        ],
                    },
                })
            form = request.content.decode()
            self.assertIn("id=media-id", form)
            self.assertIn("stream=1080%2Baudio", form)
            return httpx.Response(200, request=request, json={
                "status": "success", "data": {"link": "https://cdn.example/best.mp4"},
            })

        service = alldebrid_module.AllDebridService()
        with self._client(handler):
            result = await service.unrestrict("https://youtu.be/abcdefghijk", "secret")
        self.assertEqual(result, "https://cdn.example/best.mp4")
        self.assertEqual(calls, ["/v4/link/unlock", "/v4/link/streaming"])

    async def test_unlock_polls_a_delayed_stream(self):
        polls = 0

        def handler(request):
            nonlocal polls
            if request.url.path.endswith("/unlock"):
                data = {"id": "media", "streams": [{"id": "best", "ext": "mp4", "quality": 1080}]}
            elif request.url.path.endswith("/streaming"):
                data = {"delayed": "job"}
            else:
                polls += 1
                data = {"status": 2, "link": "https://cdn.example/delayed.mp4"} if polls > 1 else {"status": 1}
            return httpx.Response(200, request=request, json={"status": "success", "data": data})

        service = alldebrid_module.AllDebridService()
        with self._client(handler), patch.object(asyncio, "sleep", AsyncMock()):
            result = await service.unrestrict("https://youtube.com/watch?v=abcdefghijk", "secret")
        self.assertEqual(result, "https://cdn.example/delayed.mp4")
        self.assertEqual(polls, 2)

    async def test_stream_errors_are_not_fed_back_to_aria2_as_raw_urls(self):
        service = alldebrid_module.AllDebridService()
        with (
            patch.object(alldebrid_module, "get_config", return_value={
                "alldebrid": {"enabled": True, "api_key": "secret"},
            }),
            patch.object(service, "is_stream_url", AsyncMock(return_value=True)),
            patch.object(
                service,
                "unrestrict",
                AsyncMock(side_effect=alldebrid_module.AllDebridError("LINK_EMPTY", "No stream")),
            ),
        ):
            with self.assertRaises(alldebrid_module.AllDebridError):
                await service.process_url("https://youtube.com/watch?v=abcdefghijk")


class YouTubeModelTests(unittest.TestCase):
    def test_url_detection_and_canonicalization(self):
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=abcdefghijk"))
        self.assertTrue(is_youtube_url("https://youtu.be/abcdefghijk"))
        self.assertFalse(is_youtube_url("ftp://youtube.com/video"))
        self.assertFalse(is_youtube_url("https://user:secret@youtube.com/video"))
        self.assertFalse(is_youtube_url("https://youtube.com:8080/video"))
        self.assertFalse(is_youtube_url("https://youtube.com.evil.example/video"))
        self.assertEqual(youtube_video_id("https://youtu.be/abcdefghijk?t=2"), "abcdefghijk")
        self.assertEqual(youtube_video_id("https://youtube.com/shorts/abcdefghijk"), "abcdefghijk")
        self.assertEqual(canonical_video_url("abcdefghijk"), "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertTrue(is_channel_url("https://youtube.com/@channel"))

    def test_single_video_analysis_uses_runtime_and_does_not_hide_extractor_errors(self):
        captured = {}

        class FakeYoutubeDL:
            def __init__(self, options):
                captured.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download=False):
                self.assert_download = download
                return {"id": "abcdefghijk", "title": "Video", "duration": 42, "formats": [{}]}

        with (
            patch("yt_dlp.YoutubeDL", FakeYoutubeDL),
            patch("services.youtube.runtime_options", return_value={
                "ffmpeg_location": "/tmp/ffmpeg",
                "js_runtimes": {"deno": {"path": "/tmp/deno"}},
            }),
            patch("services.youtube.temporary_cookie_file") as cookies,
        ):
            cookies.return_value.__enter__.return_value = "/tmp/cookies.txt"
            cookies.return_value.__exit__.return_value = False
            result = YouTubeAnalysisService._extract(
                "https://youtu.be/abcdefghijk", "videos", expand_playlist=True
            )

        self.assertEqual(result["items"][0]["id"], "abcdefghijk")
        self.assertEqual(captured["format"], "all")
        self.assertFalse(captured["ignoreerrors"])
        self.assertEqual(captured["ffmpeg_location"], "/tmp/ffmpeg")
        self.assertIn("deno", captured["js_runtimes"])
        self.assertEqual(captured["cookiefile"], "/tmp/cookies.txt")

    def test_rich_profile_keeps_best_video_and_one_audio_per_language(self):
        info = {
            "formats": [
                {"format_id": "v720", "vcodec": "avc1", "acodec": "none", "height": 720},
                {"format_id": "v1080", "vcodec": "vp9", "acodec": "none", "height": 1080},
                {"format_id": "fr-low", "vcodec": "none", "acodec": "opus", "language": "fr", "abr": 64},
                {"format_id": "fr-best", "vcodec": "none", "acodec": "opus", "language": "fr", "abr": 128},
                {"format_id": "fr-ad", "vcodec": "none", "acodec": "opus", "language": "fr", "abr": 256, "format_note": "audio description"},
                {"format_id": "en", "vcodec": "none", "acodec": "opus", "language": "en", "abr": 96},
            ],
            "subtitles": {"de": [{}], "fr": [{}]},
            "automatic_captions": {"en": [{}], "es": [{}]},
        }
        selector, subtitles = rich_format(info)
        self.assertEqual(selector.split("+")[0], "v1080")
        self.assertIn("fr-best", selector)
        self.assertIn("en", selector)
        self.assertNotIn("fr-low", selector)
        self.assertNotIn("fr-ad", selector)
        self.assertEqual(subtitles, ["de", "en", "fr"])


class YouTubeCookieTests(unittest.TestCase):
    VALID_COOKIES = (
        b"# Netscape HTTP Cookie File\n"
        b".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret-value\n"
        b"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tHSID\thttp-secret\n"
    )

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.cookie_path = Path(self.root.name) / "config" / "youtube-cookies.txt"
        self.path_patch = patch.object(youtube_cookies, "COOKIE_PATH", self.cookie_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_cookies_are_validated_stored_privately_and_copied_per_worker(self):
        exported = self.VALID_COOKIES + (
            b".example.com\tTRUE\t/\tTRUE\t2147483647\tSESSION\tunrelated-secret\n"
        )
        status = youtube_cookies.save_cookies(exported)
        self.assertTrue(status["configured"])
        self.assertEqual(status["count"], 2)
        self.assertEqual(stat.S_IMODE(self.cookie_path.stat().st_mode), 0o600)
        self.assertNotIn(b"example.com", self.cookie_path.read_bytes())
        self.assertNotIn(b"unrelated-secret", self.cookie_path.read_bytes())

        with youtube_cookies.temporary_cookie_file() as temporary:
            temporary_path = Path(temporary)
            self.assertNotEqual(temporary_path, self.cookie_path)
            self.assertEqual(temporary_path.read_bytes(), self.VALID_COOKIES)
            self.assertEqual(stat.S_IMODE(temporary_path.stat().st_mode), 0o600)
        self.assertFalse(temporary_path.exists())

        self.assertFalse(youtube_cookies.remove_cookies()["configured"])
        self.assertFalse(self.cookie_path.exists())

    def test_invalid_or_non_youtube_cookie_exports_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Netscape"):
            youtube_cookies.save_cookies(b"SID=secret")
        with self.assertRaisesRegex(ValueError, "YouTube"):
            youtube_cookies.save_cookies(
                b"# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n"
            )
        self.assertFalse(self.cookie_path.exists())

    def test_antibot_errors_are_actionable_without_exposing_cookie_data(self):
        message = youtube_setup.friendly_error(
            "Sign in to confirm you're not a bot. Use --cookies for authentication"
        )
        self.assertIn("Settings > YouTube", message)
        self.assertNotIn("--cookies", message)

    def test_mp4_profile_has_a_compatible_format_fallback(self):
        self.assertEqual(len(MP4_FORMATS), 2)
        self.assertIn("vcodec^=avc", MP4_FORMATS[0])
        self.assertNotIn("bv*", " ".join(MP4_FORMATS))

        unavailable = MagicMock()
        unavailable.__enter__.return_value = unavailable
        unavailable.extract_info.side_effect = RuntimeError("Requested format is not available")
        fallback = MagicMock()
        fallback.__enter__.return_value = fallback
        fallback.extract_info.return_value = {"id": "abcdefghijk"}
        fallback.prepare_filename.return_value = "/tmp/video.mp4"
        yt_dlp = MagicMock()
        yt_dlp.YoutubeDL.side_effect = [unavailable, fallback]
        info, filename = download_mp4(yt_dlp, {}, "https://youtu.be/abcdefghijk")
        self.assertEqual(info["id"], "abcdefghijk")
        self.assertEqual(filename, "/tmp/video.mp4")
        self.assertEqual(yt_dlp.YoutubeDL.call_count, 2)


class YouTubePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH == Path("/opt/download-manager/config/downloads.db"):
            self.fail("Refusing to run persistence tests against the production database")
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()

    async def test_migration_adds_youtube_columns(self):
        async with database.db_session() as db:
            columns = {
                row[1]: row for row in await (await db.execute("PRAGMA table_info(downloads)")).fetchall()
            }
        for column in ("engine", "source_id", "output_profile", "source_metadata"):
            self.assertIn(column, columns)
        self.assertEqual(columns["engine"][4], "'aria2'")

    async def test_multiple_videos_create_package_members_and_active_duplicates_are_skipped(self):
        manager = QueueManager()
        items = [
            {"id": "abcdefghijk", "url": canonical_video_url("abcdefghijk"), "title": "First"},
            {"id": "lmnopqrstuv", "url": canonical_video_url("lmnopqrstuv"), "title": "Second"},
        ]
        ids = await manager.add_youtube_downloads(
            items, str(database.DB_PATH.parent), engine="youtube", output_profile="mp4", package_id="pkg"
        )
        repeated = await manager.add_youtube_downloads(
            items, str(database.DB_PATH.parent), engine="youtube", output_profile="mp4", package_id="pkg"
        )
        self.assertEqual(len(ids), 2)
        self.assertEqual(repeated, [])
        async with database.db_session(row_factory=True) as db:
            rows = await (await db.execute("SELECT * FROM downloads ORDER BY position")).fetchall()
        self.assertEqual([row["source_id"] for row in rows], ["abcdefghijk", "lmnopqrstuv"])
        self.assertTrue(all(row["engine"] == "youtube" for row in rows))
        self.assertTrue(all(row["package_id"] == "pkg" for row in rows))

    async def test_alldebrid_unsupported_switches_youtube_to_direct_without_retry(self):
        manager = QueueManager()
        item = {"id": "abcdefghijk", "url": canonical_video_url("abcdefghijk"), "title": "Video"}
        ids = await manager.add_youtube_downloads(
            [item], str(database.DB_PATH.parent), engine="alldebrid", output_profile="mp4"
        )
        async with database.db_session(row_factory=True) as db:
            await db.execute("UPDATE downloads SET status = 'submitting' WHERE id = ?", (ids[0],))
            await db.commit()
            row = dict(await (await db.execute("SELECT * FROM downloads WHERE id = ?", (ids[0],))).fetchone())

        with (
            patch.object(
                queue_manager_module.alldebrid,
                "process_url",
                AsyncMock(side_effect=alldebrid_module.AllDebridError(
                    "LINK_HOST_NOT_SUPPORTED", "This host or link is not supported"
                )),
            ),
            patch.object(queue_manager_module, "youtube_direct_status", return_value={"ready": True}),
            patch.object(queue_manager_module.aria2, "add_uri", AsyncMock()) as add_uri,
        ):
            await manager._submit_to_aria2(row, 1)

        add_uri.assert_not_awaited()
        async with database.db_session(row_factory=True) as db:
            switched = await (await db.execute("SELECT * FROM downloads WHERE id = ?", (ids[0],))).fetchone()
        self.assertEqual(switched["engine"], "youtube")
        self.assertEqual(switched["status"], "pending")
        self.assertEqual(switched["retry_count"], 0)
        self.assertIn("automatic direct fallback", switched["error_msg"])

    async def test_generic_multi_link_batch_identifies_each_youtube_video(self):
        manager = QueueManager()
        ids = await manager.add_downloads(
            [
                "https://youtu.be/abcdefghijk?si=share-token",
                "https://www.youtube.com/watch?v=lmnopqrstuv&list=playlist",
            ],
            str(database.DB_PATH.parent),
            package_id="youtube-package",
        )
        self.assertEqual(len(ids), 2)
        async with database.db_session(row_factory=True) as db:
            rows = await (await db.execute(
                "SELECT * FROM downloads ORDER BY position"
            )).fetchall()
        self.assertEqual(
            [row["source_key"] for row in rows],
            ["youtube:abcdefghijk", "youtube:lmnopqrstuv"],
        )
        self.assertEqual(
            [row["url"] for row in rows],
            [canonical_video_url("abcdefghijk"), canonical_video_url("lmnopqrstuv")],
        )
        self.assertTrue(all(row["engine"] == "aria2" for row in rows))
        self.assertTrue(all(row["output_profile"] == "alldebrid_mp4" for row in rows))


if __name__ == "__main__":
    unittest.main()
