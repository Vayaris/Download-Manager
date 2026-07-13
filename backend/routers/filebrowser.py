import asyncio
import os
import re
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from config import get_config
from database import DB_PATH
from models import FileBrowserPathRequest, FileBrowserReorderRequest, MkdirRequest

router = APIRouter()

_BROWSE_TIMEOUT_SECONDS = 5
_CACHE_TTL_SECONDS = 10
_CACHE_MAX_ENTRIES = 128
_RECENT_MAX = 10
_FAVORITE_MAX = 50
_browse_semaphore = asyncio.Semaphore(4)
_browse_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()


def _get_allowed_roots() -> list[Path]:
    """Return browseable roots without exposing unrelated server paths."""
    cfg = get_config()
    allowed = [Path(p).resolve() for p in cfg["downloads"].get("allowed_paths", [])]
    default_dest = cfg["downloads"].get("default_destination", "")
    if default_dest:
        allowed.append(Path(default_dest).resolve())
    try:
        from services.smb import get_all_mount_points
        allowed.extend(Path(mp).resolve() for mp in get_all_mount_points())
    except Exception:
        pass

    unique = []
    seen = set()
    for root in allowed or [Path("/")]:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _is_path_allowed(target: Path, allowed_roots: list[Path]) -> bool:
    """Allow navigation inside a root and through parents leading to a root."""
    for root in allowed_roots:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            pass
        try:
            root.relative_to(target)
            return True
        except ValueError:
            pass
    return False


def _is_destination_allowed(target: Path, allowed_roots: list[Path]) -> bool:
    for root in allowed_roots:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _breadcrumbs(target: Path) -> list[dict]:
    parts = target.parts
    return [
        {"name": part, "path": str(Path(*parts[:index + 1]))}
        for index, part in enumerate(parts)
    ]


def _scan_directory(target: Path) -> dict:
    if not target.exists() or not target.is_dir():
        return {"error": "Folder not found", "directories": []}

    directories = []
    try:
        with os.scandir(target) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except (OSError, PermissionError):
                    continue
                directories.append({
                    "name": entry.name,
                    "path": os.path.join(str(target), entry.name),
                    "has_children": None,
                })
    except PermissionError:
        return {"error": "Permission denied", "directories": []}
    except OSError as exc:
        return {"error": str(exc), "directories": []}

    directories.sort(key=lambda item: item["name"].casefold())
    return {"directories": directories}


def _cache_get(key: str) -> dict | None:
    cached = _browse_cache.get(key)
    if not cached:
        return None
    expires_at, payload = cached
    if expires_at <= time.monotonic():
        _browse_cache.pop(key, None)
        return None
    _browse_cache.move_to_end(key)
    return dict(payload)


def _cache_put(key: str, payload: dict):
    _browse_cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, dict(payload))
    _browse_cache.move_to_end(key)
    while len(_browse_cache) > _CACHE_MAX_ENTRIES:
        _browse_cache.popitem(last=False)


def _invalidate_cache(path: Path):
    key = str(path)
    _browse_cache.pop(key, None)


def _decode_mount_path(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _mounts() -> list[tuple[Path, str]]:
    mounts = []
    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                fields = line.rstrip().split()
                separator = fields.index("-")
                mount_point = Path(_decode_mount_path(fields[4]))
                source = _decode_mount_path(fields[separator + 2])
                label = mount_point.name or source.rsplit("/", 1)[-1] or str(mount_point)
                mounts.append((mount_point, label))
    except (OSError, ValueError, IndexError):
        pass
    mounts.sort(key=lambda item: len(str(item[0])), reverse=True)
    return mounts


def _storage_label(path: Path, mounts: list[tuple[Path, str]]) -> str:
    for mount_point, label in mounts:
        try:
            path.relative_to(mount_point)
            return label
        except ValueError:
            continue
    return path.anchor or "/"


def _enrich_places(rows: list[dict]) -> list[dict]:
    mounts = _mounts()
    enriched = []
    for row in rows:
        path = Path(row["path"])
        enriched.append({
            **row,
            "name": path.name or str(path),
            "storage_label": _storage_label(path, mounts),
            "available": path.is_dir(),
        })
    return enriched


def _normalize_place(path: str, allowed_roots: list[Path] | None = None) -> Path:
    value = path.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Path cannot be empty")
    try:
        target = Path(value).expanduser().resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not _is_destination_allowed(target, allowed_roots or _get_allowed_roots()):
        raise HTTPException(status_code=403, detail="Access denied for this path")
    return target


@router.get("/browse")
async def browse(
    path: str = Query(default="/"),
    refresh: bool = Query(default=False),
    _=Depends(get_current_user),
):
    try:
        target = Path(path).expanduser().resolve()
        allowed_roots = _get_allowed_roots()
        if not _is_path_allowed(target, allowed_roots):
            return {
                "path": str(target), "directories": [], "breadcrumbs": [],
                "parent": None, "error": "Access denied for this path",
            }

        key = str(target)
        payload = None if refresh else _cache_get(key)
        cached = payload is not None
        if payload is None:
            try:
                async with _browse_semaphore:
                    payload = await asyncio.wait_for(
                        asyncio.to_thread(_scan_directory, target),
                        timeout=_BROWSE_TIMEOUT_SECONDS,
                    )
            except asyncio.TimeoutError:
                payload = {"directories": [], "error": "Folder response timed out"}
            if not payload.get("error"):
                _cache_put(key, payload)

        return {
            "path": key,
            "parent": str(target.parent) if target != target.parent else None,
            "selectable": _is_destination_allowed(target, allowed_roots),
            "directories": payload.get("directories", []),
            "breadcrumbs": _breadcrumbs(target),
            "error": payload.get("error"),
            "cached": cached,
        }
    except Exception as exc:
        return {
            "path": path, "directories": [], "breadcrumbs": [],
            "parent": None, "error": str(exc), "cached": False,
        }


@router.get("/preferences")
async def get_preferences(user=Depends(get_current_user)):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT path, kind, position, last_used_at
               FROM filebrowser_places WHERE username = ?
               ORDER BY kind, position, last_used_at DESC""",
            (user["username"],),
        )
        rows = [dict(row) for row in await cursor.fetchall()]

    try:
        enriched = await asyncio.wait_for(
            asyncio.to_thread(_enrich_places, rows), timeout=_BROWSE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        enriched = [{
            **row,
            "name": Path(row["path"]).name or row["path"],
            "storage_label": Path(row["path"]).anchor or "/",
            "available": False,
        } for row in rows]

    return {
        "favorites": [row for row in enriched if row["kind"] == "favorite"],
        "recents": [row for row in enriched if row["kind"] == "recent"][:_RECENT_MAX],
    }


@router.post("/favorites")
async def add_favorite(body: FileBrowserPathRequest, user=Depends(get_current_user)):
    target = _normalize_place(body.path)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM filebrowser_places WHERE username = ? AND kind = 'favorite'",
            (user["username"],),
        )
        (count,) = await cursor.fetchone()
        if count >= _FAVORITE_MAX:
            raise HTTPException(status_code=400, detail="Favorite limit reached")
        await db.execute(
            """INSERT OR IGNORE INTO filebrowser_places
               (username, path, kind, position, last_used_at)
               VALUES (?, ?, 'favorite', ?, ?)""",
            (user["username"], str(target), count, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    return {"status": "added", "path": str(target)}


@router.delete("/favorites")
async def remove_favorite(
    path: str = Query(...), user=Depends(get_current_user)
):
    target = _normalize_place(path)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "DELETE FROM filebrowser_places WHERE username = ? AND path = ? AND kind = 'favorite'",
            (user["username"], str(target)),
        )
        await db.commit()
    return {"status": "removed"}


@router.put("/favorites/reorder")
async def reorder_favorites(
    body: FileBrowserReorderRequest, user=Depends(get_current_user)
):
    allowed_roots = _get_allowed_roots()
    normalized = [str(_normalize_place(path, allowed_roots)) for path in body.paths]
    if len(normalized) != len(set(normalized)):
        raise HTTPException(status_code=400, detail="Duplicate favorite path")

    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT path FROM filebrowser_places WHERE username = ? AND kind = 'favorite'",
            (user["username"],),
        )
        existing = {row[0] for row in await cursor.fetchall()}
        if existing != set(normalized):
            raise HTTPException(status_code=409, detail="Favorite list changed; reload and retry")
        for position, path in enumerate(normalized):
            await db.execute(
                """UPDATE filebrowser_places SET position = ?
                   WHERE username = ? AND path = ? AND kind = 'favorite'""",
                (position, user["username"], path),
            )
        await db.commit()
    return {"status": "reordered"}


@router.post("/recents")
async def add_recent(body: FileBrowserPathRequest, user=Depends(get_current_user)):
    target = _normalize_place(body.path)
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """INSERT INTO filebrowser_places
               (username, path, kind, position, last_used_at)
               VALUES (?, ?, 'recent', 0, ?)
               ON CONFLICT(username, path, kind)
               DO UPDATE SET last_used_at = excluded.last_used_at""",
            (user["username"], str(target), now),
        )
        await db.execute(
            """DELETE FROM filebrowser_places
               WHERE username = ? AND kind = 'recent' AND path NOT IN (
                   SELECT path FROM filebrowser_places
                   WHERE username = ? AND kind = 'recent'
                   ORDER BY last_used_at DESC LIMIT ?
               )""",
            (user["username"], user["username"], _RECENT_MAX),
        )
        await db.commit()
    return {"status": "saved", "path": str(target)}


@router.post("/mkdir")
async def mkdir(body: MkdirRequest, _=Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")
    if re.search(r'[/\\<>:"|?*\x00-\x1f]', name):
        raise HTTPException(status_code=400, detail="Name contains invalid characters")
    if name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid folder name")

    parent = Path(body.path).resolve()
    if not _is_destination_allowed(parent, _get_allowed_roots()):
        raise HTTPException(status_code=403, detail="Access denied for this path")

    def create_directory() -> Path:
        if not parent.exists() or not parent.is_dir():
            raise ValueError("Parent folder does not exist")
        new_dir = parent / name
        new_dir.mkdir(parents=False, exist_ok=False)
        return new_dir

    try:
        new_dir = await asyncio.wait_for(
            asyncio.to_thread(create_directory), timeout=_BROWSE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Folder creation timed out")
    except FileExistsError:
        raise HTTPException(status_code=400, detail="Folder already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    _invalidate_cache(parent)
    return {"status": "created", "path": str(new_dir)}
