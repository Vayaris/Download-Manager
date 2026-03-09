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
                aria2_gid   TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 5,
                package_id  TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                destination TEXT NOT NULL,
                status      TEXT DEFAULT 'active',
                created_at  TEXT,
                updated_at  TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id           TEXT PRIMARY KEY,
                name         TEXT,
                url          TEXT,
                destination  TEXT,
                size         INTEGER DEFAULT 0,
                status       TEXT,
                error_msg    TEXT,
                package_name TEXT,
                created_at   TEXT,
                completed_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                otp_secret    TEXT,
                otp_enabled   INTEGER DEFAULT 0,
                created_at    TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ip         TEXT NOT NULL,
                attempted_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocked_ips (
                ip          TEXT PRIMARY KEY,
                blocked_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                reason      TEXT
            )
        """)

        # Migrations for existing databases
        columns = [row[1] for row in await (await db.execute("PRAGMA table_info(downloads)")).fetchall()]
        if "retry_count" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN retry_count INTEGER DEFAULT 0")
        if "max_retries" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN max_retries INTEGER DEFAULT 5")
        if "package_id" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN package_id TEXT")

        await db.commit()
