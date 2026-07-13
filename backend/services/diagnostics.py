import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

from database import open_db


_SECRET_PATTERNS = (
    re.compile(r"(?i)(apikey|api_key|token|password|secret)=([^&\s]+)"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]+"),
)


def _redact(value) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=[redacted]" if match.lastindex == 2 else "[redacted]", text)
    return text[:1000]


async def record_event(
    source: str,
    code: str,
    message,
    *,
    severity: str = "error",
    context: dict | None = None,
):
    safe_context = {str(key)[:80]: _redact(value) for key, value in (context or {}).items()}
    now = datetime.now(timezone.utc)
    db = await open_db()
    try:
        await db.execute(
            """INSERT INTO diagnostic_events
               (created_at, severity, source, code, message, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                now.isoformat(),
                severity if severity in ("info", "warning", "error") else "error",
                str(source)[:80],
                str(code)[:80],
                _redact(message),
                json.dumps(safe_context, ensure_ascii=True),
            ),
        )
        cutoff = (now - timedelta(days=30)).isoformat()
        await db.execute("DELETE FROM diagnostic_events WHERE created_at < ?", (cutoff,))
        await db.execute(
            """DELETE FROM diagnostic_events
               WHERE id NOT IN (
                   SELECT id FROM diagnostic_events ORDER BY created_at DESC, id DESC LIMIT 500
               )"""
        )
        await db.commit()
    finally:
        await db.close()


def record_event_nowait(source: str, code: str, message, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(record_event(source, code, message, **kwargs))


async def list_events(limit: int = 100) -> list[dict]:
    db = await open_db(row_factory=True)
    try:
        cursor = await db.execute(
            """SELECT id, created_at, severity, source, code, message, context_json
               FROM diagnostic_events ORDER BY created_at DESC, id DESC LIMIT ?""",
            (max(1, min(500, limit)),),
        )
        events = []
        for row in await cursor.fetchall():
            event = dict(row)
            try:
                event["context"] = json.loads(event.pop("context_json") or "{}")
            except (TypeError, ValueError):
                event["context"] = {}
                event.pop("context_json", None)
            events.append(event)
        return events
    finally:
        await db.close()


async def clear_events():
    db = await open_db()
    try:
        await db.execute("DELETE FROM diagnostic_events")
        await db.commit()
    finally:
        await db.close()
