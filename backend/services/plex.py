import httpx
from typing import Any
from xml.etree import ElementTree


class PlexService:
    @staticmethod
    def _base_url(url: str) -> str:
        return (url or "").rstrip("/")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-Plex-Token": token,
        }

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, Any]:
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return resp.json()
        try:
            return resp.json()
        except Exception:
            root = ElementTree.fromstring(resp.text)
            return {
                "MediaContainer": {
                    **root.attrib,
                    "Directory": [child.attrib for child in root.findall("Directory")],
                }
            }

    async def server_info(self, url: str, token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                self._base_url(url),
                headers=self._headers(token),
            )
            resp.raise_for_status()
            data = self._parse_response(resp)
            media_container = data.get("MediaContainer", data)
            return {
                "friendlyName": media_container.get("friendlyName", ""),
                "machineIdentifier": media_container.get("machineIdentifier", ""),
                "version": media_container.get("version", ""),
            }

    async def libraries(self, url: str, token: str) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{self._base_url(url)}/library/sections",
                headers=self._headers(token),
            )
            resp.raise_for_status()
            data = self._parse_response(resp)
            directories = data.get("MediaContainer", {}).get("Directory", [])
            libraries = []
            for item in directories:
                key = str(item.get("key", "")).strip()
                title = str(item.get("title", "")).strip()
                if not key or not title:
                    continue
                libraries.append({
                    "key": key,
                    "title": title,
                    "type": str(item.get("type", "")).strip(),
                })
            return libraries

    async def refresh_library(self, url: str, token: str, key: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._base_url(url)}/library/sections/{key}/refresh",
                headers=self._headers(token),
            )
            resp.raise_for_status()


plex = PlexService()
