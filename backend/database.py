import aiosqlite
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DM_DB", "/opt/download-manager/config/downloads.db"))


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id          TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                name        TEXT,
                status      TEXT DEFAULT 'pending',
                progress    REAL DEFAULT 0,
                speed       INTEGER DEFAULT 0,
                size        INTEGER DEFAULT 0,
                downloaded  INTEGER DEFAULT 0,
                destination TEXT NOT NULL,
                created_at  TEXT,
                updated_at  TEXT,
                error_msg   TEXT,
                position    INTEGER DEFAULT 0,
                aria2_gid   TEXT
            )
        """)
        await db.commit()
