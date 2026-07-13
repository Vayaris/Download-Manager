import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

import httpx
from fastapi import HTTPException


if "database" not in sys.modules:
    TEST_ROOT = tempfile.TemporaryDirectory()
    os.environ["DM_DB"] = str(Path(TEST_ROOT.name) / "downloads.db")
    os.environ["DM_CONFIG"] = str(Path(TEST_ROOT.name) / "config.yml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from routers import downloads
from services import alldebrid as alldebrid_module
from services import queue_manager


class V114Tests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_multi_file_magnet_creates_one_package(self):
        manager = queue_manager.QueueManager()
        package = {"package_id": "pkg", "download_ids": ["a", "b"]}
        with (
            patch.object(manager, "add_package", AsyncMock(return_value=package)) as add_package,
            patch.object(manager, "add_downloads", AsyncMock()) as add_downloads,
        ):
            result = await manager.import_torrent_links(
                "Multi-file torrent", ["https://ad/a", "https://ad/b"], "/downloads"
            )

        self.assertEqual(result, package)
        add_package.assert_awaited_once_with(
            "Multi-file torrent", ["https://ad/a", "https://ad/b"], "/downloads"
        )
        add_downloads.assert_not_awaited()

    async def test_resolved_single_file_magnet_stays_standalone(self):
        manager = queue_manager.QueueManager()
        with (
            patch.object(manager, "add_package", AsyncMock()) as add_package,
            patch.object(manager, "add_downloads", AsyncMock(return_value=["a"])) as add_downloads,
        ):
            result = await manager.import_torrent_links(
                "Single-file torrent", ["https://ad/a"], "/downloads"
            )

        self.assertEqual(result, {"package_id": None, "download_ids": ["a"]})
        add_package.assert_not_awaited()
        add_downloads.assert_awaited_once_with(["https://ad/a"], "/downloads")

    async def test_magnet_upload_encodes_repeated_form_fields_with_httpx_028(self):
        magnets = [
            "magnet:?xt=urn:btih:AAAA&dn=one",
            "magnet:?xt=urn:btih:BBBB&dn=two",
        ]
        captured = {}

        def handler(request):
            captured["content_type"] = request.headers.get("content-type")
            captured["form"] = parse_qs(request.content.decode())
            return httpx.Response(200, json={
                "status": "success",
                "data": {"magnets": [{"id": 1}, {"id": 2}]},
            })

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            return real_client(transport=transport, timeout=kwargs.get("timeout"))

        service = alldebrid_module.AllDebridService()
        with (
            patch.object(service, "_get_api_key", return_value="secret"),
            patch.object(alldebrid_module.httpx, "AsyncClient", side_effect=client_factory),
        ):
            result = await service.magnet_upload(magnets)

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(captured["content_type"], "application/x-www-form-urlencoded")
        self.assertEqual(captured["form"]["magnets[]"], magnets)

    async def test_magnet_upload_preserves_alldebrid_error_code_and_message(self):
        def handler(_request):
            return httpx.Response(200, json={
                "status": "error",
                "error": {"code": "MAGNET_TOO_MANY_ACTIVE", "message": "Too many active magnets"},
            })

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        service = alldebrid_module.AllDebridService()
        with (
            patch.object(service, "_get_api_key", return_value="secret"),
            patch.object(
                alldebrid_module.httpx,
                "AsyncClient",
                side_effect=lambda *args, **kwargs: real_client(transport=transport, timeout=kwargs.get("timeout")),
            ),
        ):
            with self.assertRaisesRegex(Exception, "MAGNET_TOO_MANY_ACTIVE: Too many active magnets"):
                await service.magnet_upload(["magnet:?xt=urn:btih:AAAA"])

    async def test_magnet_failure_returns_502_and_records_only_source_count(self):
        manager = SimpleNamespace()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue_manager=manager)))
        magnet = "magnet:?xt=urn:btih:AAAA&dn=private-name"

        with (
            patch.object(downloads, "_validate_destination"),
            patch.object(downloads.alldebrid, "magnet_upload", AsyncMock(side_effect=TypeError("encoding failed"))),
            patch.object(downloads, "record_event_nowait") as record_event,
        ):
            with self.assertRaises(HTTPException) as raised:
                await downloads.add_automatic_batch(
                    request=request,
                    links=magnet,
                    destination="/tmp",
                    package_name="",
                    files=None,
                    _={"username": "vayaris"},
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "encoding failed")
        record_event.assert_called_once()
        self.assertEqual(record_event.call_args.kwargs["context"], {"count": 1})
        self.assertNotIn(magnet, str(record_event.call_args))


if __name__ == "__main__":
    unittest.main()
