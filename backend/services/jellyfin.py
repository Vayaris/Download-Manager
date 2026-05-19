from typing import Any

import httpx


class JellyfinService:
    @staticmethod
    def _base_url(url: str) -> str:
        return (url or "").rstrip("/")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-Emby-Token": token,
        }

    async def server_info(self, url: str, token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{self._base_url(url)}/System/Info",
                headers=self._headers(token),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "friendlyName": data.get("ServerName", ""),
                "machineIdentifier": data.get("Id", ""),
                "version": data.get("Version", ""),
            }

    async def libraries(self, url: str, token: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{self._base_url(url)}/Library/VirtualFolders",
                headers=self._headers(token),
            )
            resp.raise_for_status()
            data = resp.json()

        libraries = []
        for item in data if isinstance(data, list) else []:
            key = str(item.get("ItemId") or item.get("Id") or item.get("Name") or "").strip()
            title = str(item.get("Name") or "").strip()
            if not key or not title:
                continue
            raw_locations = item.get("Locations", [])
            locations = [
                str(path).strip()
                for path in raw_locations
                if str(path or "").strip()
            ] if isinstance(raw_locations, list) else []
            libraries.append({
                "key": key,
                "title": title,
                "type": str(item.get("CollectionType") or item.get("LibraryOptions", {}).get("ContentType") or "").strip(),
                "locations": locations,
            })
        return libraries

    async def refresh_library(self, url: str, token: str, key: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base_url(url)}/Items/{key}/Refresh",
                headers=self._headers(token),
                params={
                    "Recursive": "true",
                    "MetadataRefreshMode": "Default",
                    "ImageRefreshMode": "Default",
                    "ReplaceAllMetadata": "false",
                    "ReplaceAllImages": "false",
                },
            )
            resp.raise_for_status()


jellyfin = JellyfinService()
