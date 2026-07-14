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
from services import update_service


class SystemTests(unittest.TestCase):
    def test_release_candidate_sorts_before_stable_release(self):
        self.assertLess(
            update_service.parse_version_tag("2.0.0-rc.3"),
            update_service.parse_version_tag("2.0.0"),
        )
        self.assertGreater(
            update_service.parse_version_tag("2.0.0-rc.3"),
            update_service.parse_version_tag("1.14.2"),
        )

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
            version.write_text("1.13.0")
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
                self.assertTrue(update_runner.healthy("1.13.0", timeout=1))
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

    def test_update_database_backup_includes_wal_data(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.db"
            destination = Path(temp) / "backup.db"
            with sqlite3.connect(source) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE values_test (value TEXT)")
                db.execute("INSERT INTO values_test VALUES ('committed')")
                db.commit()
                update_runner.backup_database(source, destination)
            with sqlite3.connect(destination) as backup:
                self.assertEqual(backup.execute("SELECT value FROM values_test").fetchone()[0], "committed")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_update_installs_the_exact_verified_tag_commit(self):
        expected = "a" * 40
        responses = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout=expected + "\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        with patch.object(update_runner, "run", side_effect=responses) as run:
            installed = update_runner.install_target(Path("/repo"), "v2.0.0-rc.1", expected)
        self.assertEqual(installed, expected)
        self.assertEqual(run.call_args_list[0].args[0][:4], ["git", "fetch", "--force", "origin"])
        self.assertEqual(run.call_args_list[2].args[0], ["git", "reset", "--hard", expected])

    def test_update_rejects_a_tag_commit_mismatch(self):
        responses = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="b" * 40 + "\n", stderr=""),
        ]
        with patch.object(update_runner, "run", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                update_runner.install_target(Path("/repo"), "v2.0.0", "a" * 40)

    def test_update_runner_propagates_failure_exit_code(self):
        source = (ROOT / "backend" / "update_runner.py").read_text()
        self.assertIn("return 1", source)
        self.assertIn("sys.exit(main())", source)


if __name__ == "__main__":
    unittest.main()
