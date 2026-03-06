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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.websocket("/ws/downloads")
async def websocket_endpoint(ws: WebSocket):
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
