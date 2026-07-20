import httpx
from typing import Optional, List, Dict, Any
from config import get_config


class Aria2RpcError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, category: str = "unknown"):
        super().__init__(message)
        self.code = code
        self.category = category


def classify_rpc_error(code: Optional[int], message: str) -> str:
    msg = (message or "").lower()
    if "gid" in msg and ("not found" in msg or "no such" in msg or "unknown" in msg):
        return "missing_gid"
    if code in (1, 2, 3, 4, 5, 6, 7, 8):
        return "download_error"
    return "unknown"


class Aria2Service:
    def __init__(self):
        self._id = 0
        self._client: httpx.AsyncClient | None = None

    def _get_url(self) -> str:
        config = get_config()
        return f"http://localhost:{config['aria2']['rpc_port']}/jsonrpc"

    def _get_secret(self) -> str:
        return get_config()["aria2"]["rpc_secret"]

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=1.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    @staticmethod
    def _rpc_error(data: dict) -> Aria2RpcError:
        error = data.get("error") or {}
        message = str(error.get("message", error))
        code = error.get("code")
        return Aria2RpcError(
            f"aria2 RPC error: {message}",
            code=code,
            category=classify_rpc_error(code, message),
        )

    async def _call(self, method: str, params: list = None) -> Any:
        params = params or []
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._next_id()),
            "method": method,
            "params": [f"token:{self._get_secret()}"] + params,
        }
        resp = await self._get_client().post(self._get_url(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise self._rpc_error(data)
        return data.get("result")

    async def tell_status_many(self, gids: List[str]) -> Dict[str, Any]:
        """Return one result or Exception per GID using a single JSON-RPC request."""
        if not gids:
            return {}
        secret = self._get_secret()
        requests = []
        request_ids = {}
        for gid in gids:
            request_id = str(self._next_id())
            request_ids[request_id] = gid
            requests.append({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "aria2.tellStatus",
                "params": [f"token:{secret}", gid],
            })
        response = await self._get_client().post(self._get_url(), json=requests)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise Aria2RpcError("aria2 returned an invalid batch response")
        results: Dict[str, Any] = {}
        for item in payload:
            gid = request_ids.get(str(item.get("id")))
            if not gid:
                continue
            results[gid] = self._rpc_error(item) if "error" in item else item.get("result")
        for gid in gids:
            results.setdefault(gid, Aria2RpcError("aria2 returned no status for this GID"))
        return results

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def add_uri(self, url: str, destination: str, filename: Optional[str] = None, split: int = 1) -> str:
        options: Dict[str, str] = {
            "dir": destination,
            "continue": "true",
            "allow-overwrite": "true",
        }
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

    async def get_global_option(self) -> Dict:
        return await self._call("aria2.getGlobalOption")

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
