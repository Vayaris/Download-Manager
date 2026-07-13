import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


TEST_ROOT = tempfile.TemporaryDirectory()
os.environ.setdefault("DM_DB", str(Path(TEST_ROOT.name) / "downloads.db"))
os.environ.setdefault("DM_CONFIG", str(Path(TEST_ROOT.name) / "config.yml"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from routers import settings


class DownloadWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_status_reports_healthy_services(self):
        manager = SimpleNamespace(health_snapshot=lambda: {
            "running": True,
            "last_tick_error": "",
        })
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))

        with patch("services.aria2_service.aria2.get_global_option", AsyncMock(return_value={})):
            result = await settings.get_runtime_status(request, _={"username": "vayaris"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["aria2_ok"])
        self.assertTrue(result["queue_running"])

    async def test_runtime_status_stays_small_and_reports_failures(self):
        manager = SimpleNamespace(health_snapshot=lambda: {
            "running": True,
            "last_tick_error": "tick failed",
            "recent_errors": [{"message": "must not leak"}],
        })
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))

        with patch("services.aria2_service.aria2.get_global_option", AsyncMock(side_effect=TimeoutError)):
            result = await settings.get_runtime_status(request, _={"username": "vayaris"})

        self.assertFalse(result["ok"])
        self.assertFalse(result["aria2_ok"])
        self.assertEqual(result["queue_error"], "tick failed")
        self.assertNotIn("recent_errors", result)

    def test_download_page_contains_workspace_components(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "frontend" / "index.html").read_text()
        app = (root / "frontend" / "static" / "js" / "app.js").read_text()

        for element_id in (
            "unified-sources",
            "download-dashboard",
            "quick-favorites",
            "quick-recents",
            "recent-activity",
            "runtime-alert",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('/api/settings/runtime-status', app)
        self.assertIn('/api/files/preferences', app)
        self.assertIn('slice(0, 3)', app)


if __name__ == "__main__":
    unittest.main()
