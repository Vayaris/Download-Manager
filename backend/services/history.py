import base64
import json
from datetime import datetime, timezone

from fastapi import HTTPException

from database import open_db


def _token(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _untoken(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid history group") from exc


def _cursor(completed_at: str, group_key: str) -> str:
    return _token(json.dumps([completed_at, group_key], separators=(",", ":")))


def _decode_cursor(value: str):
    try:
        completed_at, group_key = json.loads(_untoken(value))
        if not isinstance(completed_at, str) or not isinstance(group_key, str):
            raise ValueError
        return completed_at, group_key
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid history cursor") from exc


def _group_where(group_key: str):
    prefix, separator, value = group_key.partition(":")
    if not separator or not value:
        raise HTTPException(status_code=400, detail="Invalid history group")
    if prefix == "package":
        return "package_id = ?", value
    if prefix == "legacy":
        return "package_id IS NULL AND package_name = ?", value
    if prefix == "item":
        return "id = ?", value
    raise HTTPException(status_code=400, detail="Invalid history group")


async def history_view(scope: str, limit: int, cursor: str, today_from: str):
    if scope not in {"all", "today", "failed"}:
        raise HTTPException(status_code=400, detail="Invalid history filter")
    if not today_from:
        now = datetime.now(timezone.utc)
        today_from = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    row_where = "WHERE completed_at >= ?" if scope == "today" else ""
    row_params = [today_from] if scope == "today" else []
    group_where = "WHERE failed_count > 0" if scope == "failed" else ""
    cursor_where = ""
    cursor_params = []
    if cursor:
        completed_at, group_key = _decode_cursor(cursor)
        cursor_where = (
            (" AND " if group_where else " WHERE ")
            + "(completed_at < ? OR (completed_at = ? AND group_key < ?))"
        )
        cursor_params = [completed_at, completed_at, group_key]

    sql = f"""
        WITH source AS (
            SELECT *,
                CASE
                    WHEN package_id IS NOT NULL AND package_id != '' THEN 'package:' || package_id
                    WHEN package_name IS NOT NULL AND TRIM(package_name) != '' THEN 'legacy:' || package_name
                    ELSE 'item:' || id
                END AS group_key
            FROM history
            {row_where}
        ), grouped AS (
            SELECT group_key,
                   CASE WHEN group_key LIKE 'item:%' THEN MAX(name) ELSE MAX(package_name) END AS name,
                   COUNT(*) AS item_count,
                   SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS complete_count,
                   SUM(CASE WHEN status != 'complete' THEN 1 ELSE 0 END) AS failed_count,
                   SUM(CASE WHEN status = 'complete' THEN COALESCE(size, 0) ELSE 0 END) AS size,
                   CASE WHEN COUNT(DISTINCT destination) = 1 THEN MAX(destination) ELSE '' END AS destination,
                   MAX(COALESCE(completed_at, created_at, '')) AS completed_at
            FROM source
            GROUP BY group_key
        )
        SELECT * FROM grouped
        {group_where}{cursor_where}
        ORDER BY completed_at DESC, group_key DESC
        LIMIT ?
    """

    db = await open_db(row_factory=True)
    try:
        summary_cursor = await db.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status = 'complete' AND completed_at >= ? THEN 1 ELSE 0 END) AS completed_today,
                      SUM(CASE WHEN status = 'complete' THEN COALESCE(size, 0) ELSE 0 END) AS total_bytes,
                      SUM(CASE WHEN status != 'complete' THEN 1 ELSE 0 END) AS failed
               FROM history""",
            (today_from,),
        )
        summary = dict(await summary_cursor.fetchone())
        query_params = row_params + cursor_params + [limit + 1]
        rows = [dict(row) for row in await (await db.execute(sql, query_params)).fetchall()]
    finally:
        await db.close()

    has_more = len(rows) > limit
    rows = rows[:limit]
    groups = []
    for row in rows:
        failed = int(row["failed_count"] or 0)
        complete = int(row["complete_count"] or 0)
        status = "partial" if failed and complete else ("failed" if failed else "complete")
        groups.append({
            "id": _token(row["group_key"]),
            "kind": "item" if row["group_key"].startswith("item:") else "package",
            "name": row["name"] or "Download",
            "status": status,
            "item_count": int(row["item_count"] or 0),
            "complete_count": complete,
            "failed_count": failed,
            "size": int(row["size"] or 0),
            "destination": row["destination"] or "",
            "completed_at": row["completed_at"],
        })
    next_cursor = None
    if has_more and rows:
        next_cursor = _cursor(rows[-1]["completed_at"], rows[-1]["group_key"])
    return {
        "summary": {key: int(value or 0) for key, value in summary.items()},
        "groups": groups,
        "next_cursor": next_cursor,
    }


async def history_group(group_id: str):
    group_key = _untoken(group_id)
    where, value = _group_where(group_key)
    db = await open_db(row_factory=True)
    try:
        rows = [dict(row) for row in await (
            await db.execute(
                f"SELECT * FROM history WHERE {where} ORDER BY completed_at DESC, name COLLATE NOCASE",
                (value,),
            )
        ).fetchall()]
    finally:
        await db.close()
    if not rows:
        raise HTTPException(status_code=404, detail="History group not found")
    for row in rows:
        source = (row.get("url") or "").lower()
        row["retryable"] = source.startswith("http://") or source.startswith("https://") or source.startswith("magnet:")
    return {"id": group_id, "items": rows}


async def remove_history_entries(ids: list[str]):
    unique_ids = list(dict.fromkeys(value for value in ids if value))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="No history entries selected")
    if len(unique_ids) > 500:
        raise HTTPException(status_code=400, detail="Too many history entries selected")
    placeholders = ",".join("?" for _ in unique_ids)
    db = await open_db()
    try:
        cursor = await db.execute(f"DELETE FROM history WHERE id IN ({placeholders})", unique_ids)
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()
