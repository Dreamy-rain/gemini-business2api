"""
Storage abstraction supporting file and PostgreSQL backends.

If DATABASE_URL is set, PostgreSQL is used.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_db_pool = None
_db_pool_lock = None
_db_loop = None
_db_thread = None
_db_loop_lock = threading.Lock()


def _get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def is_database_enabled() -> bool:
    """Return True when DATABASE_URL is configured."""
    return bool(_get_database_url())


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
                max_size=10,
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
    """Initialize database tables."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        logger.info("[STORAGE] Database tables initialized")


async def db_get(key: str) -> Optional[dict]:
    """Fetch a value from the database."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM kv_store WHERE key = $1", key
        )
        if not row:
            return None
        value = row["value"]
        if isinstance(value, str):
            return json.loads(value)
        return value


async def db_set(key: str, value: dict) -> None:
    """Persist a value to the database."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO kv_store (key, value, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            key,
            json.dumps(value, ensure_ascii=False),
        )


# ==================== Accounts storage ====================

async def load_accounts() -> Optional[list]:
    """
    Load account configuration from database when enabled.
    Return None to indicate file-based fallback.
    """
    if not is_database_enabled():
        return None
    try:
        data = await db_get("accounts")
        if data:
            logger.info(f"[STORAGE] Loaded {len(data)} accounts from database")
            return data
        logger.info("[STORAGE] No accounts found in database")
        return []
    except Exception as e:
        logger.error(f"[STORAGE] Database read failed: {e}")
    return None


async def get_accounts_updated_at() -> Optional[float]:
    """
    Get the accounts updated_at timestamp (epoch seconds).
    Return None if database is not enabled or failed.
    """
    if not is_database_enabled():
        return None
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT EXTRACT(EPOCH FROM updated_at) AS ts FROM kv_store WHERE key = $1",
                "accounts",
            )
            if not row or row["ts"] is None:
                return None
            return float(row["ts"])
    except Exception as e:
        logger.error(f"[STORAGE] Database accounts updated_at failed: {e}")
    return None


def get_accounts_updated_at_sync() -> Optional[float]:
    """Sync wrapper for get_accounts_updated_at."""
    return _run_in_db_loop(get_accounts_updated_at())


async def save_accounts(accounts: list) -> bool:
    """Save account configuration to database when enabled."""
    if not is_database_enabled():
        return False
    try:
        await db_set("accounts", accounts)
        logger.info(f"[STORAGE] Saved {len(accounts)} accounts to database")
        return True
    except Exception as e:
        logger.error(f"[STORAGE] Database write failed: {e}")
    return False


def load_accounts_sync() -> Optional[list]:
    """Sync wrapper for load_accounts (safe in sync/async call sites)."""
    return _run_in_db_loop(load_accounts())


def save_accounts_sync(accounts: list) -> bool:
    """Sync wrapper for save_accounts (safe in sync/async call sites)."""
    return _run_in_db_loop(save_accounts(accounts))


# ==================== Settings storage ====================

async def load_settings() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await db_get("settings")
    except Exception as e:
        logger.error(f"[STORAGE] Settings read failed: {e}")
    return None


async def save_settings(settings: dict) -> bool:
    if not is_database_enabled():
        return False
    try:
        await db_set("settings", settings)
        logger.info("[STORAGE] Settings saved to database")
        return True
    except Exception as e:
        logger.error(f"[STORAGE] Settings write failed: {e}")
    return False


# ==================== Stats storage ====================

async def load_stats() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await db_get("stats")
    except Exception as e:
        logger.error(f"[STORAGE] Stats read failed: {e}")
    return None


async def save_stats(stats: dict) -> bool:
    if not is_database_enabled():
        return False
    try:
        await db_set("stats", stats)
        return True
    except Exception as e:
        logger.error(f"[STORAGE] Stats write failed: {e}")
    return False


def load_settings_sync() -> Optional[dict]:
    return _run_in_db_loop(load_settings())


def save_settings_sync(settings: dict) -> bool:
    return _run_in_db_loop(save_settings(settings))


def load_stats_sync() -> Optional[dict]:
    return _run_in_db_loop(load_stats())


def save_stats_sync(stats: dict) -> bool:
    return _run_in_db_loop(save_stats(stats))
