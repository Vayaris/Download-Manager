import httpx
from typing import Optional
from config import get_config

ALLDEBRID_API = "https://api.alldebrid.com"
AGENT = "download-manager"


class AllDebridService:
    def _get_api_key(self) -> str:
        config = get_config()
        if not config["alldebrid"]["enabled"] or not config["alldebrid"]["api_key"]:
            raise Exception("AllDebrid non configuré")
        return config["alldebrid"]["api_key"]

    async def unrestrict(self, url: str, api_key: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
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

    async def magnet_upload(self, magnets: list[str]) -> list[dict]:
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{ALLDEBRID_API}/v4/magnet/upload",
                params={"agent": AGENT, "apikey": api_key},
                data=[("magnets[]", m) for m in magnets],
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            return data["data"]["magnets"]

    async def magnet_upload_file(self, file_bytes: bytes, filename: str) -> list[dict]:
        api_key = self._get_api_key()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ALLDEBRID_API}/v4/magnet/upload/file",
                params={"agent": AGENT, "apikey": api_key},
                files=[("files[]", (filename, file_bytes, "application/x-bittorrent"))],
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

    async def magnet_files(self, magnet_id: int) -> list[str]:
        api_key = self._get_api_key()
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
                self._extract_links(magnet.get("files", []), links)
            return links

    def _extract_links(self, nodes, links):
        for node in nodes:
            if isinstance(node, dict):
                if "l" in node and node["l"]:
                    links.append(node["l"])
                if "e" in node:
                    self._extract_links(node["e"], links)

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

        try:
            direct = await self.unrestrict(url, config["alldebrid"]["api_key"])
            return direct or url
        except Exception:
            # For alldebrid.com links, propagate the error (let retry handle it)
            if "alldebrid.com/" in url:
                raise
            return url


alldebrid = AllDebridService()
