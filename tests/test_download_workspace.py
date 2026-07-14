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

    async def test_storage_overview_includes_and_deduplicates_smb(self):
        config = {
            "storage_extra_paths": ["/mnt/disk-one", "/mnt/smb/media"],
            "smb_shares": [
                {"name": "Media NAS", "mount_point": "/mnt/smb/media"},
                {"name": "Offline NAS", "mount_point": "/mnt/smb/offline"},
            ],
        }
        with (
            patch.object(settings, "get_config", return_value=config),
            patch.object(settings, "is_mounted", side_effect=lambda path: path.endswith("/media")),
            patch.object(
                settings, "_disk_usage_with_timeout",
                AsyncMock(return_value=(1000, 400, 600, 40.0)),
            ) as disk_usage,
        ):
            result = await settings.get_storage(include_smb=True, _={"username": "vayaris"})

        self.assertEqual(len(result), 3)
        media = next(item for item in result if item["name"] == "Media NAS")
        offline = next(item for item in result if item["name"] == "Offline NAS")
        self.assertEqual(media["kind"], "smb")
        self.assertTrue(media["configured_storage"])
        self.assertTrue(media["available"])
        self.assertFalse(offline["configured_storage"])
        self.assertFalse(offline["available"])
        self.assertEqual(disk_usage.await_count, 2)

    def test_download_page_contains_workspace_components(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "frontend" / "index.html").read_text()
        app = (root / "frontend" / "static" / "js" / "app.js").read_text()

        for element_id in (
            "unified-sources",
            "download-dashboard",
            "storage-overview",
            "storage-overview-summary",
            "queue-estimate",
            "recent-activity-section",
            "recent-activity",
            "runtime-alert",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertNotIn('id="today-panel"', html)
        self.assertNotIn('id="quick-favorites"', html)
        self.assertLess(html.index('class="table-wrap dl-empty"'), html.index('id="download-dashboard"'))
        self.assertLess(html.index('id="storage-overview-panel"'), html.index('id="recent-activity-section"'))
        self.assertIn('/api/settings/runtime-status', app)
        self.assertIn('/api/settings/storage?include_smb=true', app)
        self.assertIn('WorkspaceUtils.parseGlobalPasteLinks', app)
        self.assertIn('WorkspaceUtils.computeStoragePressure', app)
        self.assertIn('/static/js/workspace-utils.js', html)
        self.assertIn('setInterval(loadStorageOverview, 60000)', app)
        self.assertNotIn('renderTodayMetrics', app)
        self.assertIn('data.groups.slice(0, 5)', app)
        self.assertIn('consecutiveAria2Failures >= 2', app)
        self.assertIn('status.aria2_ok ? 0 : consecutiveAria2Failures + 1', app)

    def test_v2_interface_is_default_and_v1_fallback_is_reversible(self):
        root = Path(__file__).resolve().parents[1]
        account = (root / "frontend" / "static" / "js" / "account.js").read_text()
        theme = (root / "frontend" / "static" / "js" / "theme.js").read_text()
        modern_css = root / "frontend" / "static" / "css" / "style-modern.css"

        self.assertTrue(modern_css.is_file())
        modern_styles = modern_css.read_text()
        self.assertIn('html[data-ui-style="modern"]', modern_styles)
        self.assertIn("persistent navigation rail", modern_styles)
        self.assertIn("position: fixed", modern_styles)
        self.assertIn("max-width: none", modern_styles)
        self.assertIn("min-aspect-ratio: 2/1", modern_styles)
        self.assertIn("column-count: 3", modern_styles)
        self.assertIn("#account-modal .modal-box", modern_styles)
        self.assertIn('id="acct-ui-style-select"', account)
        self.assertIn("Interface v2", account)
        self.assertIn("Old look v1", account)
        self.assertIn('localStorage.setItem("dm_ui_style", next)', theme)
        self.assertIn('/api/auth/preferences', theme)

        for page in ("index.html", "settings.html", "plex.html"):
            html = (root / "frontend" / page).read_text()
            self.assertIn('data-ui-style="modern"', html)
            self.assertIn('/static/css/style-modern.css', html)
            self.assertIn("params.get('ui')", html)
            self.assertIn("localStorage.getItem('dm_ui_style') || 'modern'", html)
            self.assertIn("localStorage.getItem('dm_ui_generation') !== '2'", html)


if __name__ == "__main__":
    unittest.main()
