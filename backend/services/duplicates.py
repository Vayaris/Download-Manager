import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit, unquote

from fastapi import HTTPException

from config import get_config
from database import DB_PATH, open_db


STAGING_ROOT = DB_PATH.parent / "submissions"


def normalize_url(value: str) -> str:
    clean = value.strip()
    try:
        parts = urlsplit(clean)
        if parts.scheme.lower() == "magnet":
            xt = parse_qs(parts.query).get("xt", [""])[0].lower()
            return f"magnet:{xt}" if xt else clean
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))
    except ValueError:
        return clean


def source_key(kind: str, value: str | bytes) -> str:
    if kind == "torrent":
        digest = hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()
        return f"torrent:{digest}"
    return f"url:{normalize_url(str(value))}"


def inferred_name(value: str) -> str:
    try:
        name = Path(unquote(urlsplit(value).path)).name.strip()
        return name if "." in name else ""
    except ValueError:
        return ""


def _path_allowed(path: Path) -> bool:
    cfg = get_config()
    roots = list(cfg["downloads"].get("allowed_paths", []))
    roots.append(cfg["downloads"].get("default_destination", ""))
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        if not root:
            continue
        try:
            resolved.relative_to(Path(root).resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


async def cleanup_expired_submissions():
    now = datetime.now(timezone.utc).isoformat()
    db = await open_db(row_factory=True)
    try:
        cursor = await db.execute("SELECT id FROM download_submissions WHERE expires_at <= ?", (now,))
        expired = [row["id"] for row in await cursor.fetchall()]
        await db.execute("DELETE FROM download_submissions WHERE expires_at <= ?", (now,))
        await db.commit()
    finally:
        await db.close()
    for submission_id in expired:
        shutil.rmtree(STAGING_ROOT / submission_id, ignore_errors=True)


async def resume_pending_file_conflicts() -> int:
    """Resume conflicts as explicit overwrites when file protection is disabled."""
    db = await open_db()
    try:
        cursor = await db.execute(
            """UPDATE downloads SET status = 'pending', overwrite_confirmed = 1,
                   error_msg = NULL, updated_at = ?
               WHERE status = 'duplicate_pending'""",
            (datetime.now(timezone.utc).isoformat(),),
        )
        await db.commit()
        return max(0, cursor.rowcount)
    finally:
        await db.close()


async def create_submission(username: str, destination: str, package_name: str, links: list[str], files: list[tuple[str, bytes]]):
    await cleanup_expired_submissions()
    submission_id = str(uuid.uuid4())
    stage = STAGING_ROOT / submission_id
    stage.mkdir(parents=True, mode=0o700)
    items = []
    seen: dict[str, str] = {}
    check_existing_files = bool(
        get_config()["downloads"].get("existing_file_check_enabled", True)
    )

    db = await open_db(row_factory=True)
    try:
        for value in links:
            key = source_key("url", value)
            item = {
                "id": str(uuid.uuid4()), "kind": "magnet" if value.lower().startswith("magnet:") else "url",
                "value": value, "display_name": inferred_name(value) or value[:120], "source_key": key, "conflicts": [],
            }
            await _detect_conflicts(db, item, destination, seen, check_existing_files)
            seen.setdefault(key, item["id"])
            items.append(item)

        for index, (filename, content) in enumerate(files):
            key = source_key("torrent", content)
            stored = f"{index}-{uuid.uuid4().hex}.torrent"
            target = stage / stored
            target.write_bytes(content)
            os.chmod(target, 0o600)
            item = {
                "id": str(uuid.uuid4()), "kind": "torrent", "stored": stored,
                "display_name": filename, "source_key": key, "conflicts": [],
            }
            await _detect_conflicts(db, item, destination, seen, check_existing_files)
            seen.setdefault(key, item["id"])
            items.append(item)

        now = datetime.now(timezone.utc)
        await db.execute(
            """INSERT INTO download_submissions
               (id, username, destination, package_name, payload_json, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (submission_id, username, destination, package_name, json.dumps(items), now.isoformat(), (now + timedelta(minutes=30)).isoformat()),
        )
        await db.commit()
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        await db.close()
    return {"submission_id": submission_id, "items": items, "has_conflicts": any(item["conflicts"] for item in items)}


async def _detect_conflicts(
    db, item: dict, destination: str, seen: dict[str, str],
    check_existing_files: bool = True,
):
    key = item["source_key"]
    if key in seen:
        item["conflicts"].append({"type": "batch_duplicate", "message": "Duplicate inside this submission"})
    cursor = await db.execute(
        "SELECT id, name, destination, status FROM downloads WHERE source_key = ? OR url = ? LIMIT 1",
        (key, item.get("value", "")),
    )
    active = await cursor.fetchone()
    if active:
        item["conflicts"].append({"type": "active", "id": active["id"], "name": active["name"], "destination": active["destination"]})
    cursor = await db.execute(
        "SELECT id, name, destination, status FROM torrents WHERE source_key = ? LIMIT 1",
        (key,),
    )
    torrent = await cursor.fetchone()
    if torrent:
        item["conflicts"].append({"type": "active_torrent", "id": torrent["id"], "name": torrent["name"], "destination": torrent["destination"]})
    cursor = await db.execute(
        """SELECT id, name, destination FROM history
           WHERE status = 'complete' AND (source_key = ? OR url = ? OR (destination = ? AND name = ?)) LIMIT 1""",
        (key, item.get("value", ""), destination, item["display_name"]),
    )
    history = await cursor.fetchone()
    if history:
        item["conflicts"].append({"type": "history", "id": history["id"], "name": history["name"], "destination": history["destination"]})
    name = inferred_name(item.get("value", ""))
    if name and check_existing_files:
        target = Path(destination) / name
        if target.is_file():
            item["conflicts"].append({"type": "destination", "path": str(target), "name": name})


async def load_submission(submission_id: str, username: str) -> dict:
    db = await open_db(row_factory=True)
    try:
        cursor = await db.execute(
            "SELECT * FROM download_submissions WHERE id = ? AND username = ? AND expires_at > ?",
            (submission_id, username, datetime.now(timezone.utc).isoformat()),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission expired or not found")
        result = dict(row)
        result["items"] = json.loads(result.pop("payload_json"))
        return result
    finally:
        await db.close()


async def apply_replacement(item: dict, queue_manager):
    db = await open_db(row_factory=True)
    try:
        for conflict in item.get("conflicts", []):
            if conflict["type"] == "active" and conflict.get("id"):
                cursor = await db.execute("SELECT aria2_gid FROM downloads WHERE id = ?", (conflict["id"],))
                active = await cursor.fetchone()
                partial_paths = []
                if active and active["aria2_gid"]:
                    try:
                        from services.aria2_service import aria2
                        from services.queue_utils import aria2_file_path
                        status = await aria2.tell_status(active["aria2_gid"])
                        path = aria2_file_path(status)
                        if path and Path(f"{path}.aria2").is_file() and _path_allowed(path):
                            partial_paths = [path, Path(f"{path}.aria2")]
                    except Exception:
                        partial_paths = []
                await queue_manager.remove_download(conflict["id"])
                for partial in partial_paths:
                    try:
                        if partial.is_file():
                            partial.unlink()
                    except OSError:
                        pass
            elif conflict["type"] == "active_torrent" and conflict.get("id"):
                cursor = await db.execute("SELECT alldebrid_id FROM torrents WHERE id = ?", (conflict["id"],))
                torrent = await cursor.fetchone()
                if torrent:
                    from services.alldebrid import alldebrid
                    try:
                        await alldebrid.magnet_delete(torrent["alldebrid_id"])
                    except Exception:
                        pass
                    await db.execute("DELETE FROM torrents WHERE id = ?", (conflict["id"],))
            elif conflict["type"] == "history" and conflict.get("id"):
                cursor = await db.execute("SELECT destination, name FROM history WHERE id = ?", (conflict["id"],))
                row = await cursor.fetchone()
                if row:
                    target = Path(row["destination"] or "") / (row["name"] or "")
                    if target.is_file() and _path_allowed(target):
                        target.unlink()
                    await db.execute("DELETE FROM history WHERE id = ?", (conflict["id"],))
            elif conflict["type"] == "destination" and conflict.get("path"):
                target = Path(conflict["path"])
                if not target.is_file() or not _path_allowed(target):
                    raise HTTPException(status_code=403, detail="Duplicate path cannot be replaced safely")
                target.unlink()
        await db.commit()
    finally:
        await db.close()


async def finish_submission(submission_id: str):
    db = await open_db()
    try:
        await db.execute("DELETE FROM download_submissions WHERE id = ?", (submission_id,))
        await db.commit()
    finally:
        await db.close()
    shutil.rmtree(STAGING_ROOT / submission_id, ignore_errors=True)
