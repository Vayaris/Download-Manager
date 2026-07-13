import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import update_runner


class SystemTests(unittest.TestCase):
    def test_installer_embedded_yaml_matches_current_settings(self):
        installer = (ROOT / "install.sh").read_text()
        match = re.search(
            r'cat > "\$\{CONFIG_DIR\}/config\.yml" <<EOF\n(?P<yaml>.*?)\nEOF',
            installer,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        config_text = (
            match.group("yaml")
            .replace("${PORT}", "40320")
            .replace("${INSTALL_DIR}", "/opt/download-manager")
            .replace("${ARIA2_SECRET}", "test-secret")
        )
        config = yaml.safe_load(config_text)
        self.assertEqual(config["downloads"]["simultaneous"], 3)
        self.assertTrue(config["downloads"]["skip_nfo_files"])
        self.assertEqual(config["downloads"]["stalled_timeout_hours"], 3)
        self.assertFalse(config["plex"]["auto_refresh_enabled"])
        self.assertFalse(config["jellyfin"]["auto_refresh_enabled"])
        self.assertNotIn("enabled", config["auth"])

    def test_update_health_uses_configured_port_and_expected_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.yml"
            version = root / "VERSION"
            config.write_text("server:\n  port: 45678\n")
            version.write_text("1.12.0")
            class Response:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    return False
            response = Response()
            with (
                patch.object(update_runner, "CONFIG_FILE", config),
                patch.object(update_runner, "INSTALL_DIR", root),
                patch.object(update_runner, "run", return_value=SimpleNamespace(returncode=0)),
                patch.object(update_runner.urllib.request, "urlopen", return_value=response) as urlopen,
            ):
                self.assertTrue(update_runner.healthy("1.12.0", timeout=1))
            self.assertIn(":45678/api/auth/status", urlopen.call_args.args[0])

    def test_update_status_file_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            with (
                patch.object(update_runner, "STATE_DIR", state),
                patch.object(update_runner, "STATUS_FILE", state / "status.json"),
            ):
                update_runner.write_status("job", "success", "ok")
                status = state / "status.json"
                self.assertEqual(status.stat().st_mode & 0o777, 0o600)
                self.assertIn('"state": "success"', status.read_text())


if __name__ == "__main__":
    unittest.main()
