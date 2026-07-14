import sys
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config import get_config
from database import init_db
from services.queue_manager import QueueManager
from services.diagnostics import record_event_nowait
from routers import downloads, settings, filebrowser, torrents, smb as smb_router
from routers import auth as auth_router

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


class _SensitiveQueryFilter(logging.Filter):
    _token = re.compile(r"([?&]token=)[^&\s\"]+")

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = self._token.sub(r"\1[redacted]", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._token.sub(r"\1[redacted]", value) if isinstance(value, str) else value
                for value in record.args
            )
        return True


for _logger_name in ("uvicorn.error", "uvicorn.access"):
    _logger = logging.getLogger(_logger_name)
    if not any(isinstance(item, _SensitiveQueryFilter) for item in _logger.filters):
        _logger.addFilter(_SensitiveQueryFilter())


# ------------------------------------------------------------------ #
#  WebSocket connection manager                                        #
# ------------------------------------------------------------------ #

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections = [c for c in self.connections if c is not ws]

    async def broadcast(self, message: dict):
        for ws in self.connections[:]:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


ws_manager = ConnectionManager()


# ------------------------------------------------------------------ #
#  App lifespan                                                        #
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Mount SMB shares marked as auto_mount
    try:
        from services.smb import mount_all_auto
        mount_all_auto()
    except Exception as exc:
        record_event_nowait("startup", "smb_automount_failed", exc, severity="warning")
    qm = QueueManager()
    qm.register_ws_manager(ws_manager)
    await qm.start()
    app.state.queue_manager = qm
    yield
    await qm.stop()


# ------------------------------------------------------------------ #
#  FastAPI app                                                         #
# ------------------------------------------------------------------ #

app = FastAPI(title="Download Manager", lifespan=lifespan)


def _normalized_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme.lower(), parsed.hostname.lower(), port
    except ValueError:
        return None


def _cross_origin_cookie_request(request: Request) -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if not request.cookies.get("dm_session"):
        return False

    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "same-origin":
        return False
    if fetch_site == "cross-site":
        return True

    origin = request.headers.get("origin")
    if not origin:
        return False
    host = request.headers.get("host", request.url.netloc)
    expected = _normalized_origin(f"{request.url.scheme}://{host}")
    return _normalized_origin(origin.rstrip("/")) != expected


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _cross_origin_cookie_request(request):
            return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected"})

        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path in ("/", "/plex-page", "/settings-page"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# CORS: only allow same-origin requests (app is served from same host)
_cfg = get_config()
_cors_origins = _cfg.get("server", {}).get("cors_origins", [])
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["settings"])
app.include_router(filebrowser.router, prefix="/api/files",   tags=["files"])
app.include_router(auth_router.router, prefix="/api/auth",    tags=["auth"])
app.include_router(torrents.router,    prefix="/api/torrents", tags=["torrents"])
app.include_router(smb_router.router,  prefix="/api/smb",      tags=["smb"])

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/settings-page")
async def settings_page():
    return FileResponse(str(FRONTEND_DIR / "settings.html"))


@app.get("/plex-page")
async def plex_page():
    return FileResponse(str(FRONTEND_DIR / "plex.html"))


@app.get("/manifest.json")
async def manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript")


@app.websocket("/ws/downloads")
async def websocket_endpoint(ws: WebSocket):
    # Browsers authenticate with the HttpOnly session cookie. Query tokens are
    # retained only for compatible non-browser clients during the v2 transition.
    from fastapi import HTTPException
    from auth import validate_access_token

    token = ws.cookies.get("dm_session") or ws.query_params.get("token", "")
    try:
        await validate_access_token(token)
    except HTTPException as exc:
        await ws.close(code=4001, reason=str(exc.detail)[:120])
        return

    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection alive / receive pings
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    cfg = get_config()
    uvicorn.run(
        "main:app",
        host=cfg["server"]["host"],
        port=cfg["server"]["port"],
        reload=False,
        # Keep access logs disabled because compatible non-browser WebSocket
        # clients may still use the transitional query-token fallback.
        access_log=False,
    )
