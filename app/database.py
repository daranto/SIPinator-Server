import logging

import aiosqlite

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None


async def init_db(db_path: str) -> None:
    global _db
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _create_tables()
    logger.info(f"Database initialized at {db_path}")


async def _create_tables() -> None:
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS push_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sip_extension TEXT NOT NULL,
            device_token TEXT NOT NULL UNIQUE,
            app_bundle_id TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tokens_extension
            ON push_tokens(sip_extension);

        CREATE TABLE IF NOT EXISTS call_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT,
            caller TEXT,
            caller_name TEXT DEFAULT '',
            callee_extension TEXT,
            push_sent INTEGER DEFAULT 0,
            push_result TEXT DEFAULT '',
            timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_calls_extension
            ON call_log(callee_extension);
    """)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


# --- Token CRUD ---

async def upsert_token(
    sip_extension: str, device_token: str, app_bundle_id: str
) -> dict:
    db = get_db()
    await db.execute(
        """
        INSERT INTO push_tokens (sip_extension, device_token, app_bundle_id)
        VALUES (?, ?, ?)
        ON CONFLICT(device_token) DO UPDATE SET
            sip_extension = excluded.sip_extension,
            app_bundle_id = excluded.app_bundle_id,
            is_active = 1,
            updated_at = datetime('now')
        """,
        (sip_extension, device_token, app_bundle_id),
    )
    await db.commit()
    async with db.execute(
        "SELECT * FROM push_tokens WHERE device_token = ?", (device_token,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)


async def delete_token(device_token: str) -> bool:
    db = get_db()
    cursor = await db.execute(
        "DELETE FROM push_tokens WHERE device_token = ?", (device_token,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def deactivate_token(device_token: str) -> None:
    db = get_db()
    await db.execute(
        "UPDATE push_tokens SET is_active = 0, updated_at = datetime('now') WHERE device_token = ?",
        (device_token,),
    )
    await db.commit()


async def get_tokens_for_extension(sip_extension: str) -> list[dict]:
    db = get_db()
    async with db.execute(
        "SELECT * FROM push_tokens WHERE sip_extension = ? AND is_active = 1",
        (sip_extension,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_tokens() -> list[dict]:
    db = get_db()
    async with db.execute(
        "SELECT * FROM push_tokens WHERE is_active = 1"
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_active_token_count() -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM push_tokens WHERE is_active = 1"
    ) as cursor:
        row = await cursor.fetchone()
        return row["cnt"]


# --- Call Log ---

async def log_call(
    call_id: str,
    caller: str,
    caller_name: str,
    callee_extension: str,
    push_sent: bool,
    push_result: str,
) -> None:
    db = get_db()
    await db.execute(
        """
        INSERT INTO call_log (call_id, caller, caller_name, callee_extension, push_sent, push_result)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (call_id, caller, caller_name, callee_extension, int(push_sent), push_result),
    )
    await db.commit()


async def get_calls_for_extension(
    extension: str, limit: int = 20, offset: int = 0
) -> tuple[list[dict], int]:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM call_log WHERE callee_extension = ?",
        (extension,),
    ) as cursor:
        total = (await cursor.fetchone())["cnt"]

    async with db.execute(
        """
        SELECT * FROM call_log WHERE callee_extension = ?
        ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """,
        (extension, limit, offset),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows], total


async def get_push_stats() -> tuple[int, int]:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM call_log WHERE push_sent = 1"
    ) as cursor:
        sent = (await cursor.fetchone())["cnt"]
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM call_log WHERE push_sent = 0"
    ) as cursor:
        failed = (await cursor.fetchone())["cnt"]
    return sent, failed
