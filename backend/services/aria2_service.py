import httpx
from typing import Optional, List, Dict, Any
from config import get_config


class Aria2Service:
    def __init__(self):
        self._id = 0

    def _get_url(self) -> str:
        config = get_config()
        return f"http://localhost:{config['aria2']['rpc_port']}/jsonrpc"

    def _get_secret(self) -> str:
        return get_config()["aria2"]["rpc_secret"]

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _call(self, method: str, params: list = None) -> Any:
        params = params or []
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._next_id()),
            "method": method,
            "params": [f"token:{self._get_secret()}"] + params,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self._get_url(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise Exception(f"aria2 RPC error: {data['error'].get('message', data['error'])}")
            return data.get("result")

    async def add_uri(self, url: str, destination: str, filename: Optional[str] = None, split: int = 1) -> str:
        options: Dict[str, str] = {"dir": destination}
        if filename:
            options["out"] = filename
        if split > 1:
            options["split"] = str(split)
            options["max-connection-per-server"] = str(split)
            options["min-split-size"] = "1M"
        return await self._call("aria2.addUri", [[url], options])

    async def pause(self, gid: str) -> str:
        return await self._call("aria2.pause", [gid])

    async def resume(self, gid: str) -> str:
        return await self._call("aria2.unpause", [gid])

    async def remove(self, gid: str):
        try:
            await self._call("aria2.remove", [gid])
        except Exception:
            pass
        try:
            await self._call("aria2.removeDownloadResult", [gid])
        except Exception:
            pass

    async def remove_result(self, gid: str):
        try:
            await self._call("aria2.removeDownloadResult", [gid])
        except Exception:
            pass

    async def tell_status(self, gid: str) -> Dict:
        return await self._call("aria2.tellStatus", [gid])

    async def change_global_option(self, options: Dict) -> str:
        return await self._call("aria2.changeGlobalOption", [options])

    async def is_alive(self) -> bool:
        try:
            await self._call("aria2.getVersion")
            return True
        except Exception:
            return False

    @staticmethod
    def parse_status(data: Dict) -> Dict:
        files = data.get("files", [{}])
        name = ""
        if files:
            path = files[0].get("path", "")
            name = path.split("/")[-1] if path else ""

        total = int(data.get("totalLength", 0))
        done = int(data.get("completedLength", 0))
        speed = int(data.get("downloadSpeed", 0))
        progress = round(done / total * 100, 1) if total > 0 else 0

        status_map = {
            "active": "downloading",
            "waiting": "pending",
            "paused": "paused",
            "complete": "complete",
            "error": "error",
            "removed": "error",
        }

        return {
            "name": name,
            "status": status_map.get(data.get("status", ""), "pending"),
            "progress": progress,
            "speed": speed,
            "size": total,
            "downloaded": done,
            "error_msg": data.get("errorMessage", ""),
        }


aria2 = Aria2Service()
