"""
Storage abstraction supporting SQLite and PostgreSQL backends.

Simplified version for the refresh worker — only includes functions
needed for account loading/updating, settings loading, and task history.

Priority:
1) DATABASE_URL -> PostgreSQL
2) SQLITE_PATH  -> SQLite (defaults to data.db when DATABASE_URL is empty)
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_db_pool = None
_db_pool_lock = None
_db_loop = None
_db_thread = None
_db_loop_lock = threading.Lock()

_sqlite_conn = None
_sqlite_lock = threading.Lock()


def _get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()

def _default_sqlite_path() -> str:
    return os.path.join("data", "data.db")

def _get_sqlite_path() -> str:
    env_path = os.environ.get("SQLITE_PATH", "").strip()
    if env_path:
        return env_path
    return _default_sqlite_path()

def _get_backend() -> str:
    if _get_database_url():
        return "postgres"
    if _get_sqlite_path():
        return "sqlite"
    return ""

def is_database_enabled() -> bool:
    """Return True when a database backend is configured."""
    return bool(_get_backend())


def _data_file_path(name: str) -> str:
    return os.path.join("data", name)


# ==================== Event loop bridge ====================

def _ensure_db_loop() -> asyncio.AbstractEventLoop:
    global _db_loop, _db_thread
    if _db_loop and _db_thread and _db_thread.is_alive():
        return _db_loop
    with _db_loop_lock:
        if _db_loop and _db_thread and _db_thread.is_alive():
            return _db_loop
        loop = asyncio.new_event_loop()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_runner, name="storage-db-loop", daemon=True)
        thread.start()
        _db_loop = loop
        _db_thread = thread
        return _db_loop


def _run_in_db_loop(coro):
    loop = _ensure_db_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


# ==================== SQLite ====================

def _get_sqlite_conn():
    """Get (or create) the SQLite connection."""
    global _sqlite_conn
    if _sqlite_conn is not None:
        return _sqlite_conn
    with _sqlite_lock:
        if _sqlite_conn is not None:
            return _sqlite_conn
        sqlite_path = _get_sqlite_path()
        if not sqlite_path:
            raise ValueError("SQLITE_PATH is not set")
        os.makedirs(os.path.dirname(sqlite_path) or ".", exist_ok=True)
        conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _init_sqlite_tables(conn)
        _sqlite_conn = conn
        logger.info(f"[STORAGE] SQLite initialized at {sqlite_path}")
        return _sqlite_conn


def _init_sqlite_tables(conn: sqlite3.Connection) -> None:
    """Initialize SQLite tables."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                position INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS accounts_position_idx
            ON accounts(position)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS task_history_created_at_idx
            ON task_history(created_at)
            """
        )


# ==================== PostgreSQL ====================

async def _get_pool():
    """Get (or create) the asyncpg connection pool."""
    global _db_pool, _db_pool_lock
    if _db_pool is not None:
        return _db_pool
    if _db_pool_lock is None:
        _db_pool_lock = asyncio.Lock()
    async with _db_pool_lock:
        if _db_pool is not None:
            return _db_pool
        db_url = _get_database_url()
        if not db_url:
            raise ValueError("DATABASE_URL is not set")
        try:
            import asyncpg
            _db_pool = await asyncpg.create_pool(
                db_url,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
            await _init_tables(_db_pool)
            logger.info("[STORAGE] PostgreSQL pool initialized")
        except ImportError:
            logger.error("[STORAGE] asyncpg is required for database storage")
            raise
        except Exception as e:
            logger.error(f"[STORAGE] Database connection failed: {e}")
            raise
    return _db_pool


async def _init_tables(pool) -> None:
    """Initialize PostgreSQL tables."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                position INTEGER NOT NULL,
                data JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS accounts_position_idx
            ON accounts(position)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_settings (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS task_history_created_at_idx
            ON task_history(created_at DESC)
            """
        )
        logger.info("[STORAGE] Database tables initialized")


# ==================== Account helpers ====================

def _parse_account_value(value) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    if isinstance(value, dict):
        return value
    return None


def _normalize_accounts(accounts: list) -> list:
    normalized = []
    for index, acc in enumerate(accounts, 1):
        if not isinstance(acc, dict):
            continue
        account_id = acc.get("id") or f"account_{index}"
        next_acc = dict(acc)
        next_acc.setdefault("id", account_id)
        normalized.append(next_acc)
    return normalized


# ==================== Accounts storage ====================

async def _load_accounts_from_table() -> Optional[list]:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM accounts ORDER BY position ASC"
            )
        if not rows:
            return []
        accounts = []
        for row in rows:
            value = _parse_account_value(row["data"])
            if value is not None:
                accounts.append(value)
        return accounts
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            rows = conn.execute(
                "SELECT data FROM accounts ORDER BY position ASC"
            ).fetchall()
        if not rows:
            return []
        accounts = []
        for row in rows:
            value = _parse_account_value(row["data"])
            if value is not None:
                accounts.append(value)
        return accounts
    return None


async def _save_accounts_to_table(accounts: list) -> bool:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        normalized = _normalize_accounts(accounts)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM accounts")
                for index, acc in enumerate(normalized, 1):
                    await conn.execute(
                        """
                        INSERT INTO accounts (account_id, position, data, updated_at)
                        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                        """,
                        acc["id"],
                        index,
                        json.dumps(acc, ensure_ascii=False),
                    )
        logger.info(f"[STORAGE] Saved {len(normalized)} accounts to database")
        return True
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        normalized = _normalize_accounts(accounts)
        with _sqlite_lock, conn:
            conn.execute("DELETE FROM accounts")
            for index, acc in enumerate(normalized, 1):
                conn.execute(
                    """
                    INSERT INTO accounts (account_id, position, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (acc["id"], index, json.dumps(acc, ensure_ascii=False)),
                )
        logger.info(f"[STORAGE] Saved {len(normalized)} accounts to database")
        return True
    return False


async def load_accounts() -> Optional[list]:
    """Load accounts from database."""
    if not is_database_enabled():
        return None
    try:
        data = await _load_accounts_from_table()
        if data is None:
            return None
        if data:
            logger.info(f"[STORAGE] Loaded {len(data)} accounts from database")
        else:
            logger.info("[STORAGE] No accounts found in database")
        return data
    except Exception as e:
        logger.error(f"[STORAGE] Database read failed: {e}")
    return None


async def save_accounts(accounts: list) -> bool:
    """Save account configuration to database when enabled."""
    if not is_database_enabled():
        return False
    try:
        return await _save_accounts_to_table(accounts)
    except Exception as e:
        logger.error(f"[STORAGE] Database write failed: {e}")
    return False


def load_accounts_sync() -> Optional[list]:
    """Sync wrapper for load_accounts."""
    return _run_in_db_loop(load_accounts())


def save_accounts_sync(accounts: list) -> bool:
    """Sync wrapper for save_accounts."""
    return _run_in_db_loop(save_accounts(accounts))


# ==================== Single account update ====================

async def _get_account_data(account_id: str) -> Optional[dict]:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM accounts WHERE account_id = $1",
                account_id,
            )
        if not row:
            return None
        return _parse_account_value(row["data"])
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute(
                "SELECT data FROM accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return None
        return _parse_account_value(row["data"])
    return None


async def _update_account_data(account_id: str, data: dict) -> bool:
    backend = _get_backend()
    payload = json.dumps(data, ensure_ascii=False)
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE accounts
                SET data = $2, updated_at = CURRENT_TIMESTAMP
                WHERE account_id = $1
                """,
                account_id,
                payload,
            )
        return result.startswith("UPDATE") and not result.endswith("0")
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock, conn:
            cur = conn.execute(
                """
                UPDATE accounts
                SET data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE account_id = ?
                """,
                (payload, account_id),
            )
        return cur.rowcount > 0
    return False


def update_account_data_sync(account_id: str, data: dict) -> bool:
    """Sync wrapper for _update_account_data."""
    return _run_in_db_loop(_update_account_data(account_id, data))


# ==================== Delete account ====================

async def _delete_account(account_id: str) -> bool:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM accounts WHERE account_id = $1",
                account_id,
            )
        return result.startswith("DELETE") and not result.endswith("0")
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock, conn:
            cur = conn.execute(
                "DELETE FROM accounts WHERE account_id = ?",
                (account_id,),
            )
        return cur.rowcount > 0
    return False


async def delete_accounts(account_ids: list) -> int:
    """Delete multiple accounts by IDs. Returns number deleted."""
    if not account_ids:
        return 0
    deleted = 0
    for account_id in account_ids:
        try:
            if await _delete_account(account_id):
                deleted += 1
        except Exception as e:
            logger.error(f"[STORAGE] Delete account {account_id} failed: {e}")
    if deleted:
        logger.info(f"[STORAGE] Deleted {deleted}/{len(account_ids)} accounts")
    return deleted


def delete_accounts_sync(account_ids: list) -> int:
    """Sync wrapper for delete_accounts."""
    return _run_in_db_loop(delete_accounts(account_ids))


# ==================== Add account ====================

async def _get_max_position() -> int:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COALESCE(MAX(position), 0) AS max_pos FROM accounts")
        return row["max_pos"] if row else 0
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute("SELECT COALESCE(MAX(position), 0) AS max_pos FROM accounts").fetchone()
        return row["max_pos"] if row else 0
    return 0


async def add_account(account_data: dict) -> bool:
    """Add a new account to the database."""
    if not is_database_enabled():
        return False
    account_id = account_data.get("id")
    if not account_id:
        return False
    try:
        max_pos = await _get_max_position()
        position = max_pos + 1
        payload = json.dumps(account_data, ensure_ascii=False)
        backend = _get_backend()
        if backend == "postgres":
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO accounts (account_id, position, data, updated_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                    ON CONFLICT (account_id) DO UPDATE SET
                        data = EXCLUDED.data,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    account_id,
                    position,
                    payload,
                )
            logger.info(f"[STORAGE] Added account {account_id} at position {position}")
            return True
        if backend == "sqlite":
            conn = _get_sqlite_conn()
            with _sqlite_lock, conn:
                conn.execute(
                    """
                    INSERT INTO accounts (account_id, position, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(account_id) DO UPDATE SET
                        data = excluded.data,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (account_id, position, payload),
                )
            logger.info(f"[STORAGE] Added account {account_id} at position {position}")
            return True
    except Exception as e:
        logger.error(f"[STORAGE] Add account failed: {e}")
    return False


def add_account_sync(account_data: dict) -> bool:
    """Sync wrapper for add_account."""
    return _run_in_db_loop(add_account(account_data))


# ==================== Count accounts ====================

async def count_active_accounts() -> int:
    """Count non-disabled accounts."""
    accounts = await _load_accounts_from_table()
    if not accounts:
        return 0
    return sum(1 for acc in accounts if not acc.get("disabled"))


def count_active_accounts_sync() -> int:
    """Sync wrapper for count_active_accounts."""
    return _run_in_db_loop(count_active_accounts())


# ==================== Settings storage ====================

async def _load_kv(table_name: str, key: str) -> Optional[dict]:
    """加载键值数据"""
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT value FROM {table_name} WHERE key = $1",
                key,
            )
        if not row:
            return None
        value = row["value"]
        if isinstance(value, str):
            return json.loads(value)
        return value

    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute(
                f"SELECT value FROM {table_name} WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        value = row["value"]
        if isinstance(value, str):
            return json.loads(value)
        return value
    return None


async def load_settings() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await _load_kv("kv_settings", "settings")
    except Exception as e:
        logger.error(f"[STORAGE] Settings read failed: {e}")
    return None


def load_settings_sync() -> Optional[dict]:
    return _run_in_db_loop(load_settings())


# ==================== Task history storage ====================

async def save_task_history_entry(entry: dict) -> bool:
    if not is_database_enabled():
        return False
    entry_id = entry.get("id")
    if not entry_id:
        return False
    created_at = float(entry.get("created_at", time.time()))
    payload = json.dumps(entry, ensure_ascii=False)
    backend = _get_backend()
    try:
        if backend == "postgres":
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO task_history (id, data, created_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (id) DO UPDATE SET
                        data = EXCLUDED.data,
                        created_at = EXCLUDED.created_at
                    """,
                    entry_id,
                    payload,
                    created_at,
                )
                await conn.execute(
                    """
                    DELETE FROM task_history
                    WHERE id IN (
                        SELECT id FROM task_history
                        ORDER BY created_at DESC
                        OFFSET 100
                    )
                    """
                )
            return True
        if backend == "sqlite":
            conn = _get_sqlite_conn()
            with _sqlite_lock, conn:
                conn.execute(
                    """
                    INSERT INTO task_history (id, data, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        data = excluded.data,
                        created_at = excluded.created_at
                    """,
                    (entry_id, payload, created_at),
                )
                conn.execute(
                    """
                    DELETE FROM task_history
                    WHERE id IN (
                        SELECT id FROM task_history
                        ORDER BY created_at DESC
                        LIMIT -1 OFFSET 100
                    )
                    """
                )
            return True
    except Exception as e:
        logger.error(f"[STORAGE] Task history write failed: {e}")
    return False


def save_task_history_entry_sync(entry: dict) -> bool:
    return _run_in_db_loop(save_task_history_entry(entry))
