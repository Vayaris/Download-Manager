import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, Response


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import database
import config as config_module
from auth import create_access_token, validate_access_token
from models import AddDownloadsRequest, LoginRequest, SetupAdminRequest, UserPreferencesRequest
from routers import auth as auth_router
from main import _cross_origin_cookie_request, _normalized_origin


class V2FoundationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if database.DB_PATH == Path("/opt/download-manager/config/downloads.db"):
            self.fail("Refusing to run persistence tests against the production database")
        if database.DB_PATH.exists():
            database.DB_PATH.unlink()
        await database.init_db()
        self.request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={},
            url=SimpleNamespace(scheme="http"),
        )

    async def _insert_user(self, username="vayaris", token_version=0, ui_style="modern"):
        db = await database.open_db()
        try:
            await db.execute(
                """INSERT INTO users
                   (id, username, password_hash, token_version, ui_style, created_at)
                   VALUES (?, ?, ?, ?, ?, 'now')""",
                (username, username, "hash", token_version, ui_style),
            )
            await db.commit()
        finally:
            await db.close()

    async def test_user_security_and_ui_columns_are_migrated(self):
        db = await database.open_db()
        try:
            columns = {
                row[1]: row for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()
            }
        finally:
            await db.close()
        self.assertIn("token_version", columns)
        self.assertIn("ui_style", columns)
        self.assertEqual(columns["ui_style"][4], "'modern'")

    async def test_ui_preference_is_server_persisted(self):
        await self._insert_user()
        result = await auth_router.update_preferences(
            UserPreferencesRequest(ui_style="classic"),
            user={"username": "vayaris"},
        )
        self.assertEqual(result["ui_style"], "classic")
        info = await auth_router.user_info(user={"username": "vayaris"})
        self.assertEqual(info["ui_style"], "classic")

    async def test_token_version_revokes_existing_session(self):
        await self._insert_user(token_version=0)
        with patch("auth._get_secret", return_value="test-secret"):
            token = create_access_token({"sub": "vayaris", "ver": 0, "otp_verified": True})
            user = await validate_access_token(token)
            self.assertEqual(user["username"], "vayaris")

            db = await database.open_db()
            try:
                await db.execute("UPDATE users SET token_version = 1 WHERE username = 'vayaris'")
                await db.commit()
            finally:
                await db.close()

            with self.assertRaises(HTTPException):
                await validate_access_token(token)

    async def test_login_sets_httponly_strict_cookie(self):
        await self._insert_user()
        response = Response()
        with (
            patch.object(auth_router, "verify_password", return_value=True),
            patch("auth._get_secret", return_value="test-secret"),
        ):
            result = await auth_router.login(
                LoginRequest(username="vayaris", password="correct-password"),
                self.request,
                response,
            )
        self.assertTrue(result.token)
        cookie = response.headers["set-cookie"]
        self.assertIn("dm_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

    async def test_initial_admin_creation_is_atomic(self):
        async def create(username):
            return await auth_router.setup_admin(
                SetupAdminRequest(username=username, password="long-test-password"),
                self.request,
                Response(),
            )

        with (
            patch.object(auth_router, "get_password_hash", return_value="hash"),
            patch("auth._get_secret", return_value="test-secret"),
        ):
            results = await asyncio.gather(create("first"), create("second"), return_exceptions=True)

        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, HTTPException) for result in results), 1)
        db = await database.open_db()
        try:
            count = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        finally:
            await db.close()
        self.assertEqual(count, 1)

    def test_submission_models_reject_unbounded_batches(self):
        with self.assertRaises(ValueError):
            AddDownloadsRequest(urls=[f"https://example.com/{index}" for index in range(101)], destination="/mnt")

    def test_csrf_origin_normalization_and_browser_fetch_metadata(self):
        self.assertEqual(
            _normalized_origin("HTTP://Download.Example:80/"),
            ("http", "download.example", 80),
        )

        def request(headers):
            return SimpleNamespace(
                method="POST",
                cookies={"dm_session": "session"},
                headers=headers,
                url=SimpleNamespace(scheme="http", netloc="127.0.0.1:40320"),
            )

        self.assertFalse(_cross_origin_cookie_request(request({
            "origin": "https://downloads.example",
            "host": "127.0.0.1:40320",
            "sec-fetch-site": "same-origin",
        })))
        self.assertTrue(_cross_origin_cookie_request(request({
            "origin": "https://attacker.example",
            "host": "downloads.example",
            "sec-fetch-site": "cross-site",
        })))
        self.assertFalse(_cross_origin_cookie_request(request({
            "origin": "http://DOWNLOADS.example:80/",
            "host": "downloads.example",
        })))

    async def test_config_updates_are_atomic_and_preserve_disjoint_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.yml"
            with patch.object(config_module, "CONFIG_PATH", path):
                config_module._CONFIG_CACHE = None
                config_module._CONFIG_MTIME_NS = None

                async def write(index):
                    def mutate(cfg):
                        cfg.setdefault("concurrency_test", {})[str(index)] = index
                    await asyncio.to_thread(config_module.update_config, mutate)

                await asyncio.gather(*(write(index) for index in range(20)))
                saved = config_module.get_config()
                self.assertEqual(len(saved["concurrency_test"]), 20)
                self.assertTrue(saved["auth"]["jwt_secret"])

            config_module._CONFIG_CACHE = None
            config_module._CONFIG_MTIME_NS = None


if __name__ == "__main__":
    unittest.main()
