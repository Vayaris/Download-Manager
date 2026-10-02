import asyncio
import os
import sys
import tempfile
import threading
import unittest
import subprocess
import shlex
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from routers import filebrowser
from services.interface_priority import InterfacePriority


class StartupTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "aria2 startup uses Bash on Linux")
    def test_startup_caps_resumed_transfers_and_creates_readable_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            python = root / "venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
            python.chmod(0o755)
            # Private/log directory setup is stubbed to keep /var/log untouched.
            install = binaries / "install"
            install.write_text("#!/bin/sh\nexit 0\n")
            install.chmod(0o755)
            destination = root / "media"
            result = root / "result.json"
            stub = binaries / "aria2c"
            program = (
                "import json,sys; from pathlib import Path; "
                f"media=Path({str(destination)!r}); f=media/'probe.bin'; f.write_bytes(b'test'); "
                f"Path({str(result)!r}).write_text(json.dumps({{'limit':[a for a in sys.argv if a.startswith('--max-overall-download-limit=')], 'mode':oct(f.stat().st_mode & 0o777), 'directory_mode':oct(media.stat().st_mode & 0o777), 'completed_sidecars_disabled':'--force-save=false' in sys.argv}}))"
            )
            stub.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c " + shlex.quote(program) + ' "$@"\n')
            stub.chmod(0o755)
            config = root / "config.yml"
            config.write_text(f"downloads:\n  speed_limit: 50\n  default_destination: {destination}\n")
            env = dict(os.environ, DM_INSTALL_DIR=str(root), DM_CONFIG=str(config),
                       PATH=str(binaries) + os.pathsep + os.environ["PATH"])
            script = Path(__file__).resolve().parents[1] / "start-aria2.sh"
            subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
            data = json.loads(result.read_text())
            self.assertEqual(data["limit"], ["--max-overall-download-limit=52428800"])
            self.assertEqual(data["mode"], "0o644")
            self.assertEqual(data["directory_mode"], "0o755")
            self.assertTrue(data["completed_sidecars_disabled"])


class PriorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_engine_restart_reapplies_the_configured_limit(self):
        now = [0]
        controller = InterfacePriority(lambda: now[0])
        config = {"downloads": {"speed_limit": 50}}
        with patch("services.interface_priority.get_config", return_value=config), patch(
                "services.interface_priority.aria2.change_global_option", new_callable=AsyncMock) as rpc, patch(
                "services.interface_priority.aria2.get_global_option", new_callable=AsyncMock,
                return_value={"max-overall-download-limit": "0"}):
            await controller.apply()
            now[0] = 6
            await controller.apply()
            self.assertEqual(rpc.await_count, 2)
            self.assertEqual(rpc.call_args.args[0]["max-overall-download-limit"], str(50 * 1048576))

    async def test_recovery_between_ticks_is_not_reported_as_an_error(self):
        from routers import runtime
        state = {"configured_mib_s": 50, "priority_interface_enabled": True,
                 "effective_percent": 95, "temporary_limit_bytes_s": int(47.5 * 1048576)}
        with patch("services.interface_priority.interface_priority.snapshot", return_value=state), patch(
                "services.aria2_service.aria2.get_global_option", new_callable=AsyncMock,
                return_value={"max-overall-download-limit": str(45 * 1048576)}), patch(
                "services.aria2_service.aria2._call", new_callable=AsyncMock,
                return_value={"downloadSpeed": "100"}):
            status = await runtime.get_speed_limit_status()
            self.assertTrue(status["applied"])
            self.assertTrue(status["priority_interface_active"])
            self.assertEqual(status["effective_percent"], 90)
            self.assertEqual(status["target_percent"], 95)

    async def test_reserve_and_gradual_recovery(self):
        now = [0]
        controller = InterfacePriority(lambda: now[0])
        config = {"downloads": {"speed_limit": 50, "priority_interface_enabled": True}}
        with patch("services.interface_priority.get_config", return_value=config):
            controller.begin()
            self.assertEqual(controller.snapshot()["effective_percent"], 80)
            controller.begin()
            controller.end()
            now[0] = 20
            self.assertEqual(controller.snapshot()["effective_percent"], 80)
            controller.end()
            now[0] = 24
            self.assertEqual(controller.snapshot()["effective_percent"], 80)
            for tick, expected in [(25, 85), (30, 90), (35, 95), (40, 100)]:
                now[0] = tick
                self.assertEqual(controller.snapshot()["effective_percent"], expected)
            self.assertEqual(config["downloads"]["speed_limit"], 50)

    async def test_disabled_unlimited_and_config_change_never_exceed_limit(self):
        config = {"downloads": {"speed_limit": 50, "priority_interface_enabled": False}}
        controller = InterfacePriority()
        with patch("services.interface_priority.get_config", return_value=config), patch(
                "services.interface_priority.aria2.change_global_option", new_callable=AsyncMock) as rpc:
            controller.begin()
            self.assertEqual(controller.snapshot()["effective_percent"], 100)
            config["downloads"]["priority_interface_enabled"] = True
            await controller.apply()
            self.assertEqual(rpc.call_args.args[0]["max-overall-download-limit"], str(40 * 1048576))
            config["downloads"]["speed_limit"] = 10
            await controller.apply()
            self.assertEqual(rpc.call_args.args[0]["max-overall-download-limit"], str(8 * 1048576))
            config["downloads"]["speed_limit"] = 0
            await controller.apply()
            self.assertFalse(controller.snapshot()["priority_interface_active"])
            self.assertEqual(rpc.call_args.args[0]["max-overall-download-limit"], "0")
            controller.end()


class BrowseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "child").mkdir()
        filebrowser._browse_cache.clear()

    async def asyncTearDown(self):
        if filebrowser._browse_inflight:
            await asyncio.gather(*list(filebrowser._browse_inflight.values()))
        self.temp.cleanup()

    async def test_cache_and_permissions(self):
        with patch.object(filebrowser, "_get_allowed_roots", return_value=[self.root]), patch(
                "services.interface_priority.interface_priority.apply", new_callable=AsyncMock):
            first = await filebrowser.browse(str(self.root), False)
            second = await filebrowser.browse(str(self.root), False)
            self.assertEqual(first["directories"][0]["name"], "child")
            self.assertTrue(second["cached"])
            self.assertFalse((await filebrowser.browse("/unrelated", False))["selectable"])

    async def test_changed_permissions_cannot_reuse_cached_listing(self):
        import copy
        config = {"downloads": {"allowed_paths": [str(self.root)], "default_destination": ""}, "smb_shares": []}
        with patch.object(filebrowser, "get_config", side_effect=lambda: copy.deepcopy(config)):
            first = await filebrowser.browse(str(self.root), False)
            self.assertTrue(first["selectable"])
            config["downloads"]["allowed_paths"] = []
            second = await filebrowser.browse(str(self.root), False)
            self.assertFalse(second["selectable"])
            self.assertIn("Access denied", second["error"])

    async def test_timed_out_scan_stays_occupied_and_is_coalesced(self):
        gate = threading.Event()
        calls = []
        def slow(path):
            calls.append(str(path))
            gate.wait(2)
            return {"directories": []}
        with patch.object(filebrowser, "_get_allowed_roots", return_value=[self.root]), patch.object(
                filebrowser, "_scan_directory", side_effect=slow), patch.object(
                filebrowser, "_RESPONSE_WAIT_SECONDS", .02), patch(
                "services.interface_priority.interface_priority.apply", new_callable=AsyncMock):
            try:
                results = await asyncio.gather(*[filebrowser.browse(str(self.root), False) for _ in range(5)])
                self.assertTrue(all(r["loading"] for r in results))
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(filebrowser._browse_inflight), 1)
                self.assertEqual(filebrowser.interface_priority.pending, 1)
            finally:
                gate.set()
            await asyncio.gather(*list(filebrowser._browse_inflight.values()))
            self.assertEqual(filebrowser.interface_priority.pending, 0)
            self.assertTrue((await filebrowser.browse(str(self.root), False))["cached"])

    async def test_cancellation_preserves_scan_until_completion(self):
        gate = threading.Event()
        with patch.object(filebrowser, "_get_allowed_roots", return_value=[self.root]), patch.object(
                filebrowser, "_scan_directory", side_effect=lambda _: (gate.wait(2), {"directories": []})[1]), patch(
                "services.interface_priority.interface_priority.apply", new_callable=AsyncMock):
            request = asyncio.create_task(filebrowser.browse(str(self.root), False))
            await asyncio.sleep(.03)
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
            self.assertEqual(len(filebrowser._browse_inflight), 1)
            gate.set()
            await asyncio.gather(*list(filebrowser._browse_inflight.values()))

    async def test_only_two_workers_and_bounded_pending_queue(self):
        gate = threading.Event()
        active = [0, 0]
        lock = threading.Lock()
        def slow(_):
            with lock:
                active[0] += 1
                active[1] = max(active)
            gate.wait(2)
            with lock:
                active[0] -= 1
            return {"directories": []}
        with patch.object(filebrowser, "_get_allowed_roots", return_value=[self.root]), patch.object(
                filebrowser, "_scan_directory", side_effect=slow), patch.object(
                filebrowser, "_RESPONSE_WAIT_SECONDS", .02):
            try:
                paths = [self.root / str(index) for index in range(9)]
                results = await asyncio.gather(*[filebrowser.browse(str(path), False) for path in paths])
                self.assertEqual(len(filebrowser._browse_inflight), 8)
                self.assertEqual(sum(bool(r.get("error")) for r in results), 1)
                self.assertEqual(active[1], 2)
            finally:
                gate.set()
            await asyncio.gather(*list(filebrowser._browse_inflight.values()))

    async def test_storage_resolution_does_not_block_api_loop(self):
        import time
        ticks = []
        async def ticker():
            for _ in range(10):
                await asyncio.sleep(.01)
                ticks.append(1)
        def slow_roots(*_):
            time.sleep(.1)
            return [self.root]
        with patch.object(filebrowser, "_get_allowed_roots", side_effect=slow_roots):
            await asyncio.gather(filebrowser.browse(str(self.root), False), ticker())
        self.assertEqual(len(ticks), 10)


if __name__ == "__main__":
    unittest.main()
