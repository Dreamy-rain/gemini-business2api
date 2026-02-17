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


def _get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def is_database_enabled() -> bool:
    """Return True when DATABASE_URL is configured."""
    return bool(_get_database_url())


_pools = {}
_locks = {}
_pools_lock = threading.Lock() # Protects access to _pools and _locks dicts

# Legacy threading support for sync wrappers
_db_loop = None
_db_thread = None
_db_loop_lock = threading.Lock()

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


def _run_in_db_loop(coro, timeout=10):
    loop = _ensure_db_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except Exception as e:
        logger.warning(f"[STORAGE] Config load timed out or failed: {e}")
        raise

async def _get_pool():
    """Get (or create) the asyncpg connection pool for the current event loop."""
    loop = asyncio.get_running_loop()
    
    # Fast path check
    if loop in _pools:
        return _pools[loop]

    # Get or create async lock for this loop
    with _pools_lock:
        if loop not in _locks:
            _locks[loop] = asyncio.Lock()
        loop_lock = _locks[loop]

    async with loop_lock:
        # Double check inside lock
        if loop in _pools:
            return _pools[loop]
        
        db_url = _get_database_url()
        if not db_url:
            raise ValueError("DATABASE_URL is not set")
        try:
            import asyncpg
            import ssl
            logger.info(f"[STORAGE] Initializing PostgreSQL pool for loop {id(loop)}...")
            
            # 兼容性修复：适配 CockroachDB 无证书环境
            ssl_ctx = None
            if "sslmode=require" in db_url or "sslmode=verify-full" in db_url:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            
            pool = await asyncpg.create_pool(
                db_url,
                min_size=0,
                max_size=5,
                command_timeout=15,
                connect_timeout=10,
                ssl=ssl_ctx
            )
            await _init_tables(pool)
            
            with _pools_lock:
                _pools[loop] = pool
                
            logger.info(f"[STORAGE] PostgreSQL pool initialized for loop {id(loop)}")
            return pool
        except ImportError:
            logger.error("[STORAGE] asyncpg is required for database storage")
            raise
        except Exception as e:
            logger.error(f"[STORAGE] Database connection failed: {e}")
            raise


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
        logger.info("[STORAGE] Database tables checked/initialized")


async def db_get(key: str) -> Optional[dict]:
    """Fetch a value from the database."""
    try:
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
    except Exception as e:
        if "connection was closed" in str(e) or "is in progress" in str(e):
            logger.warning(f"[STORAGE] Database connection issue during GET, resetting pool: {e}")
            loop = asyncio.get_running_loop()
            with _pools_lock:
                if loop in _pools:
                    del _pools[loop] # Trigger reconnect on next call
        raise


async def db_set(key: str, value: dict) -> None:
    """Persist a value to the database."""
    try:
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
    except Exception as e:
        if "connection was closed" in str(e) or "is in progress" in str(e):
            logger.warning(f"[STORAGE] Database connection issue during SET, resetting pool: {e}")
            loop = asyncio.get_running_loop()
            with _pools_lock:
                if loop in _pools:
                    del _pools[loop] # Trigger reconnect on next call
        raise


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

_stats_buffer = None
_stats_buffer_lock = threading.Lock()

async def load_stats() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await db_get("stats")
    except Exception as e:
        logger.error(f"[STORAGE] Stats read failed: {e}")
    return None


async def save_stats(stats: dict) -> bool:
    """Async version of stats saving."""
    if not is_database_enabled():
        return False
    try:
        await db_set("stats", stats)
        return True
    except Exception as e:
        logger.error(f"[STORAGE] Stats write failed: {e}")
    return False


def save_stats_sync(stats: dict) -> bool:
    """
    Optimized sync wrapper for stats saving.
    Now uses a memory buffer to avoid blocking the caller.
    The actual persistence happens in a background task.
    """
    global _stats_buffer
    with _stats_buffer_lock:
        _stats_buffer = stats
    return True


async def start_stats_persistence_task(interval: int = 300):
    """
    Background task to persist stats from buffer to database.
    This prevents every request from triggering a database write.
    """
    global _stats_buffer
    logger.info(f"[STORAGE] Stats persistence task started (interval: {interval}s)")
    while True:
        try:
            await asyncio.sleep(interval)
            current_stats = None
            with _stats_buffer_lock:
                if _stats_buffer is not None:
                    current_stats = _stats_buffer
                    _stats_buffer = None
            
            if current_stats:
                await save_stats(current_stats)
                logger.debug("[STORAGE] Background stats persistence completed")
        except asyncio.CancelledError:
            # Save one last time before exiting
            if _stats_buffer:
                await save_stats(_stats_buffer)
            break
        except Exception as e:
            logger.error(f"[STORAGE] Stats persistence task error: {e}")


def load_settings_sync() -> Optional[dict]:
    return _run_in_db_loop(load_settings())


def save_settings_sync(settings: dict) -> bool:
    return _run_in_db_loop(save_settings(settings))


def load_stats_sync() -> Optional[dict]:
    return _run_in_db_loop(load_stats())


def db_set_sync(key: str, value: dict) -> None:
    """Sync wrapper for db_set."""
    return _run_in_db_loop(db_set(key, value))


def db_get_sync(key: str) -> Optional[dict]:
    """Sync wrapper for db_get."""
    return _run_in_db_loop(db_get(key))

