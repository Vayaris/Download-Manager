import httpx
from typing import Optional
from urllib.parse import unquote, urlparse
from config import get_config

ALLDEBRID_API = "https://api.alldebrid.com"
AGENT = "download-manager"


class AllDebridService:
    @staticmethod
    def error_message(error, default: str = "Unknown error") -> str:
        if isinstance(error, dict):
            code = str(error.get("code") or "").strip()
            message = str(error.get("message") or default).strip()
            return f"{code}: {message}" if code else message
        return str(error or default).strip()

    def _get_api_key(self) -> str:
        config = get_config()
        if not config["alldebrid"]["enabled"] or not config["alldebrid"]["api_key"]:
            raise Exception("AllDebrid not configured")
        return config["alldebrid"]["api_key"]

    async def unrestrict(self, url: str, api_key: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/v4/link/unlock",
                params={"agent": AGENT, "apikey": api_key, "link": url},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            link = data["data"]["link"]
            # API can return link as string or as dict with "link" key
            if isinstance(link, dict):
                return link["link"]
            return link

    async def test_key(self, api_key: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{ALLDEBRID_API}/v4/user",
                    params={"agent": AGENT, "apikey": api_key},
                )
                return resp.json().get("status") == "success"
        except Exception:
            return False

    async def user_hosts(self, api_key: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/v4.1/user/hosts",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"agent": AGENT},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")

            hosts = data.get("data", {}).get("hosts", {})
            normalized = []
            for key, host in hosts.items():
                if not isinstance(host, dict):
                    continue
                normalized.append({
                    "id": key,
                    "name": host.get("name") or key,
                    "type": host.get("type", ""),
                    "domains": host.get("domains", []),
                    "status": bool(host.get("status", False)),
                    "quota": host.get("quota"),
                    "quotaMax": host.get("quotaMax"),
                    "quotaType": host.get("quotaType"),
                    "limitSimuDl": host.get("limitSimuDl"),
                })

            return sorted(normalized, key=lambda h: h["name"].lower())

    async def magnet_upload(self, magnets: list[str]) -> list[dict]:
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{ALLDEBRID_API}/v4/magnet/upload",
                    params={"agent": AGENT, "apikey": api_key},
                    data={"magnets[]": magnets},
                )
                data = resp.json()
            except httpx.HTTPError as exc:
                raise Exception(f"AllDebrid request failed: {type(exc).__name__}") from exc
            except ValueError as exc:
                raise Exception("AllDebrid returned an invalid response") from exc
            if data.get("status") != "success":
                msg = self.error_message(data.get("error"))
                raise Exception(f"AllDebrid: {msg}")
            return data["data"]["magnets"]

    async def magnet_upload_file(self, file_bytes: bytes, filename: str) -> list[dict]:
        return await self.magnet_upload_files([(filename, file_bytes)])

    async def magnet_upload_files(self, files_data: list[tuple[str, bytes]]) -> list[dict]:
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ALLDEBRID_API}/v4/magnet/upload/file",
                params={"agent": AGENT, "apikey": api_key},
                files=[
                    ("files[]", (filename, file_bytes, "application/x-bittorrent"))
                    for filename, file_bytes in files_data
                ],
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            return data["data"]["files"]

    async def magnet_status(self, magnet_id: int) -> dict:
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/v4.1/magnet/status",
                params={"agent": AGENT, "apikey": api_key, "id": magnet_id},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            return data["data"]["magnets"]

    @staticmethod
    def _looks_like_nfo(value: str) -> bool:
        if not value:
            return False
        parsed = urlparse(str(value))
        path = unquote(parsed.path or str(value)).lower().rstrip("/")
        return path.rsplit("/", 1)[-1].endswith(".nfo")

    @classmethod
    def _is_nfo_node(cls, node: dict) -> bool:
        for key in ("n", "name", "filename", "file", "path", "l"):
            if cls._looks_like_nfo(str(node.get(key, ""))):
                return True
        return False

    async def magnet_files(self, magnet_id: int) -> list[str]:
        api_key = self._get_api_key()
        skip_nfo = bool(get_config()["downloads"].get("skip_nfo_files", True))
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/v4/magnet/files",
                params={"agent": AGENT, "apikey": api_key, "id[]": magnet_id},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            # Extract all download links from the file tree
            links = []
            magnets_data = data["data"]["magnets"]
            for magnet in magnets_data:
                self._extract_links(magnet.get("files", []), links, skip_nfo=skip_nfo)
            return links

    def _extract_links(self, nodes, links, skip_nfo: bool = True):
        for node in nodes:
            if isinstance(node, dict):
                if "l" in node and node["l"]:
                    if not (skip_nfo and self._is_nfo_node(node)):
                        links.append(node["l"])
                if "e" in node:
                    self._extract_links(node["e"], links, skip_nfo=skip_nfo)

    async def magnet_delete(self, magnet_id: int):
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/v4/magnet/delete",
                params={"agent": AGENT, "apikey": api_key, "id": magnet_id},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")

    async def process_url(self, url: str) -> str:
        """Return direct link if AllDebrid is enabled, otherwise return URL as-is."""
        config = get_config()
        if not config["alldebrid"]["enabled"] or not config["alldebrid"]["api_key"]:
            return url

        # Already-debrided links from AllDebrid CDN — use directly
        if "debrid.it/" in url or "debrid.link/" in url:
            return url

        # Skip unrestricting for direct download URLs (no debrid needed)
        host = urlparse(url).hostname or ""
        direct_hosts = (".cdn.", "download.", "dl.", "files.", "media.")
        if any(host.startswith(p.lstrip(".")) or p in host for p in direct_hosts):
            if url.split("?")[0].rsplit(".", 1)[-1].lower() in (
                "zip", "rar", "7z", "tar", "gz", "iso", "exe", "msi",
                "mp4", "mkv", "avi", "mov", "mp3", "flac", "pdf",
            ):
                return url

        try:
            direct = await self.unrestrict(url, config["alldebrid"]["api_key"])
            return direct or url
        except Exception:
            # For alldebrid.com links, propagate the error (let retry handle it)
            if "alldebrid.com/" in url:
                raise
            return url


alldebrid = AllDebridService()
