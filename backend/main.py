import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config import get_config
from database import init_db
from services.queue_manager import QueueManager
from routers import downloads, settings, filebrowser
from routers import auth as auth_router

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


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


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path in ("/", "/settings-page"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
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

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/settings-page")
async def settings_page():
    return FileResponse(str(FRONTEND_DIR / "settings.html"))


@app.get("/manifest.json")
async def manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript")


@app.websocket("/ws/downloads")
async def websocket_endpoint(ws: WebSocket):
    # Authenticate WebSocket: require token as query param or first message
    import aiosqlite
    from database import DB_PATH
    from jose import jwt as ws_jwt, JWTError as WSJWTError

    # Check if auth is required (users exist)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        (count,) = await cursor.fetchone()

    if count > 0:
        # Require token in query string: /ws/downloads?token=...
        token = ws.query_params.get("token")
        if not token:
            await ws.close(code=4001, reason="Authentication required")
            return
        try:
            from auth import _get_secret, ALGORITHM
            payload = ws_jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
            if not payload.get("sub"):
                await ws.close(code=4001, reason="Invalid token")
                return
            if payload.get("otp_required") and not payload.get("otp_verified"):
                await ws.close(code=4001, reason="OTP verification required")
                return
        except WSJWTError:
            await ws.close(code=4001, reason="Invalid token")
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
    )
