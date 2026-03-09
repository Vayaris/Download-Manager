import httpx
from typing import Optional
from config import get_config

ALLDEBRID_API = "https://api.alldebrid.com/v4"
AGENT = "download-manager"


class AllDebridService:
    async def unrestrict(self, url: str, api_key: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{ALLDEBRID_API}/link/unlock",
                params={"agent": AGENT, "apikey": api_key, "link": url},
            )
            data = resp.json()
            if data.get("status") != "success":
                msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"AllDebrid: {msg}")
            return data["data"]["link"]["link"]

    async def test_key(self, api_key: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{ALLDEBRID_API}/user",
                    params={"agent": AGENT, "apikey": api_key},
                )
                return resp.json().get("status") == "success"
        except Exception:
            return False

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
