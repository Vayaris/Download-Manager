import aiosqlite
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DM_DB", "/opt/download-manager/config/downloads.db"))


async def open_db(*, row_factory: bool = False) -> aiosqlite.Connection:
    """Open a consistently configured SQLite connection."""
    db = await aiosqlite.connect(str(DB_PATH), timeout=15)
    await db.execute("PRAGMA busy_timeout = 15000")
    await db.execute("PRAGMA foreign_keys = ON")
    if row_factory:
        db.row_factory = aiosqlite.Row
    return db


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA busy_timeout = 15000")
        await db.execute("PRAGMA foreign_keys = ON")
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
                package_id  TEXT,
                last_progress_at TEXT,
                source_key TEXT,
                target_path TEXT,
                overwrite_confirmed INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                destination TEXT NOT NULL,
                status      TEXT DEFAULT 'active',
                source_count INTEGER DEFAULT 0,
                failed_sources INTEGER DEFAULT 0,
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
                completed_at TEXT,
                source_key   TEXT,
                package_id   TEXT
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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS filebrowser_places (
                username     TEXT NOT NULL,
                path         TEXT NOT NULL,
                kind         TEXT NOT NULL CHECK(kind IN ('favorite', 'recent')),
                position     INTEGER DEFAULT 0,
                last_used_at TEXT,
                PRIMARY KEY (username, path, kind)
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_filebrowser_places_user_kind
            ON filebrowser_places (username, kind, position, last_used_at)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS torrents (
                id              TEXT PRIMARY KEY,
                alldebrid_id    INTEGER NOT NULL,
                name            TEXT,
                size            INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'processing',
                destination     TEXT NOT NULL,
                progress        REAL DEFAULT 0,
                downloaded      INTEGER DEFAULT 0,
                speed           INTEGER DEFAULT 0,
                seeders         INTEGER DEFAULT 0,
                status_message  TEXT,
                package_id      TEXT,
                created_at      TEXT,
                updated_at      TEXT,
                last_progress_at TEXT,
                source_key TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS diagnostic_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                source      TEXT NOT NULL,
                code        TEXT NOT NULL,
                message     TEXT NOT NULL,
                context_json TEXT DEFAULT '{}'
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS download_submissions (
                id           TEXT PRIMARY KEY,
                username     TEXT NOT NULL,
                destination  TEXT NOT NULL,
                package_name TEXT,
                payload_json TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                expires_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_diagnostic_events_created
            ON diagnostic_events (created_at DESC)
        """)

        # Migrations for existing databases
        columns = [row[1] for row in await (await db.execute("PRAGMA table_info(downloads)")).fetchall()]
        if "retry_count" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN retry_count INTEGER DEFAULT 0")
        if "max_retries" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN max_retries INTEGER DEFAULT 5")
        if "package_id" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN package_id TEXT")
        if "last_progress_at" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN last_progress_at TEXT")
            await db.execute(
                "UPDATE downloads SET last_progress_at = COALESCE(updated_at, created_at)"
            )
        if "source_key" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN source_key TEXT")
        if "target_path" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN target_path TEXT")
        if "overwrite_confirmed" not in columns:
            await db.execute("ALTER TABLE downloads ADD COLUMN overwrite_confirmed INTEGER DEFAULT 0")

        history_columns = [row[1] for row in await (await db.execute("PRAGMA table_info(history)")).fetchall()]
        if "source_key" not in history_columns:
            await db.execute("ALTER TABLE history ADD COLUMN source_key TEXT")
        if "package_id" not in history_columns:
            await db.execute("ALTER TABLE history ADD COLUMN package_id TEXT")

        package_columns = [row[1] for row in await (await db.execute("PRAGMA table_info(packages)")).fetchall()]
        if "source_count" not in package_columns:
            await db.execute("ALTER TABLE packages ADD COLUMN source_count INTEGER DEFAULT 0")
        if "failed_sources" not in package_columns:
            await db.execute("ALTER TABLE packages ADD COLUMN failed_sources INTEGER DEFAULT 0")

        torrent_columns = [row[1] for row in await (await db.execute("PRAGMA table_info(torrents)")).fetchall()]
        if "package_id" not in torrent_columns:
            await db.execute("ALTER TABLE torrents ADD COLUMN package_id TEXT")
        if "last_progress_at" not in torrent_columns:
            await db.execute("ALTER TABLE torrents ADD COLUMN last_progress_at TEXT")
            await db.execute(
                "UPDATE torrents SET last_progress_at = created_at"
            )
        if "downloaded" not in torrent_columns:
            await db.execute("ALTER TABLE torrents ADD COLUMN downloaded INTEGER DEFAULT 0")
        if "source_key" not in torrent_columns:
            await db.execute("ALTER TABLE torrents ADD COLUMN source_key TEXT")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_downloads_source_key ON downloads (source_key)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_source_key ON history (source_key)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_completed ON history (completed_at DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON history (status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_package ON history (package_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_torrents_source_key ON torrents (source_key)")

        await db.commit()
