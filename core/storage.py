"""
Storage abstraction supporting SQLite and PostgreSQL backends.

Priority:
1) DATABASE_URL -> PostgreSQL
2) SQLITE_PATH  -> SQLite (defaults to data.db when DATABASE_URL is empty)
3) No file fallback
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


def _ensure_backend_initialized() -> None:
    backend = _get_backend()
    if backend == "postgres":
        _run_in_db_loop(_get_pool())
        return
    if backend == "sqlite":
        _get_sqlite_conn()
        return


async def has_accounts() -> Optional[bool]:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM accounts LIMIT 1")
        return bool(row)
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone()
        return bool(row)
    return None


def has_accounts_sync() -> Optional[bool]:
    return _run_in_db_loop(has_accounts())


async def has_settings() -> Optional[bool]:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM kv_settings WHERE key = $1",
                "settings",
            )
        return bool(row)
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute(
                "SELECT 1 FROM kv_settings WHERE key = ?",
                ("settings",),
            ).fetchone()
        return bool(row)
    return None


def has_settings_sync() -> Optional[bool]:
    return _run_in_db_loop(has_settings())


async def has_stats() -> Optional[bool]:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM kv_stats WHERE key = $1",
                "stats",
            )
        return bool(row)
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock:
            row = conn.execute(
                "SELECT 1 FROM kv_stats WHERE key = ?",
                ("stats",),
            ).fetchone()
        return bool(row)
    return None


def has_stats_sync() -> Optional[bool]:
    return _run_in_db_loop(has_stats())


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
            CREATE TABLE IF NOT EXISTS kv_stats (
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
            CREATE TABLE IF NOT EXISTS kv_stats (
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


# ==================== Accounts storage ====================

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
    """
    从数据库加载账户配置（如果启用）

    注意：不再自动从 kv_store 迁移
    如需迁移，请手动运行：python scripts/migrate_to_database.py

    返回 None 表示降级到文件存储
    """
    if not is_database_enabled():
        return None
    try:
        data = await _load_accounts_from_table()
        if data is None:
            return None

        if data:
            logger.info(f"[STORAGE] 从数据库加载 {len(data)} 个账户")
        else:
            logger.info("[STORAGE] 数据库中未找到账户")

        return data
    except Exception as e:
        logger.error(f"[STORAGE] 数据库读取失败: {e}")
    return None


async def get_accounts_updated_at() -> Optional[float]:
    """
    Get the accounts updated_at timestamp (epoch seconds).
    Return None if database is not enabled or failed.
    """
    if not is_database_enabled():
        return None
    backend = _get_backend()
    try:
        if backend == "postgres":
            pool = await _get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT EXTRACT(EPOCH FROM MAX(updated_at)) AS ts FROM accounts"
                )
                if not row or row["ts"] is None:
                    return None
                return float(row["ts"])
        if backend == "sqlite":
            conn = _get_sqlite_conn()
            with _sqlite_lock:
                row = conn.execute(
                    "SELECT STRFTIME('%s', MAX(updated_at)) AS ts FROM accounts"
                ).fetchone()
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
        return await _save_accounts_to_table(accounts)
    except Exception as e:
        logger.error(f"[STORAGE] Database write failed: {e}")
    return False


def load_accounts_sync() -> Optional[list]:
    """Sync wrapper for load_accounts (safe in sync/async call sites)."""
    return _run_in_db_loop(load_accounts())


def save_accounts_sync(accounts: list) -> bool:
    """Sync wrapper for save_accounts (safe in sync/async call sites)."""
    return _run_in_db_loop(save_accounts(accounts))

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

async def load_account_data(account_id: str) -> Optional[dict]:
    """
    读取单个账号的完整 data 字段（JSON）。

    功能说明：
    - 用于后台任务做“轻量级状态读取/更新”，避免每次都全量加载 accounts 列表。
    - 返回值为 dict（可直接修改后再写回），调用方需确保写回时仍包含账号必需字段。

    参数：
    - account_id: 账号 ID

    返回值：
    - 成功：账号 data 字典
    - 不存在：None
    """
    return await _get_account_data(account_id)


def load_account_data_sync(account_id: str) -> Optional[dict]:
    """
    load_account_data 的同步封装。

    参数：
    - account_id: 账号 ID

    返回值：
    - 成功：账号 data 字典
    - 不存在：None
    """
    return _run_in_db_loop(load_account_data(account_id))


async def update_account_scheduled_refresh_state(account_id: str, state: dict) -> bool:
    """
    更新账号的“定时刷新调度状态”（scheduled_refresh_state）。

    设计目的：
    - 为高级自动刷新调度提供可持久化状态（上次尝试/成功时间、平均耗时、连续失败、退避到期时间）。
    - 单实例场景下即使重启服务，也能继续基于历史状态做公平调度和失败退避，避免“重启=成功率更高”的假象。

    参数：
    - account_id: 账号 ID
    - state: 要写入的状态字典（建议包含 last_attempt_at/last_success_at/avg_refresh_duration_seconds/consecutive_failures/next_eligible_at）

    返回值：
    - True: 写入成功
    - False: 账号不存在或后端不可用
    """
    data = await _get_account_data(account_id)
    if data is None:
        return False
    data["scheduled_refresh_state"] = state or {}
    return await _update_account_data(account_id, data)


def update_account_scheduled_refresh_state_sync(account_id: str, state: dict) -> bool:
    """
    update_account_scheduled_refresh_state 的同步封装。

    参数：
    - account_id: 账号 ID
    - state: 调度状态字典

    返回值：
    - True/False: 是否写入成功
    """
    return _run_in_db_loop(update_account_scheduled_refresh_state(account_id, state))

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

async def update_account_disabled(account_id: str, disabled: bool) -> bool:
    data = await _get_account_data(account_id)
    if data is None:
        return False
    data["disabled"] = disabled
    return await _update_account_data(account_id, data)

async def bulk_update_accounts_disabled(account_ids: list[str], disabled: bool) -> tuple[int, list[str]]:
    if not account_ids:
        return 0, []
    backend = _get_backend()
    existing: dict[str, dict] = {}
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT account_id, data FROM accounts WHERE account_id = ANY($1)",
                account_ids,
            )
        for row in rows:
            data = _parse_account_value(row["data"])
            if data is not None:
                existing[row["account_id"]] = data
    elif backend == "sqlite":
        conn = _get_sqlite_conn()
        placeholders = ",".join(["?"] * len(account_ids))
        with _sqlite_lock:
            rows = conn.execute(
                f"SELECT account_id, data FROM accounts WHERE account_id IN ({placeholders})",
                tuple(account_ids),
            ).fetchall()
        for row in rows:
            data = _parse_account_value(row["data"])
            if data is not None:
                existing[row["account_id"]] = data
    else:
        return 0, account_ids

    missing = [account_id for account_id in account_ids if account_id not in existing]
    if not existing:
        return 0, missing

    updated = 0
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for account_id, data in existing.items():
                    data["disabled"] = disabled
                    payload = json.dumps(data, ensure_ascii=False)
                    result = await conn.execute(
                        """
                        UPDATE accounts
                        SET data = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE account_id = $1
                        """,
                        account_id,
                        payload,
                    )
                    if result.startswith("UPDATE") and not result.endswith("0"):
                        updated += 1
    elif backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock, conn:
            for account_id, data in existing.items():
                data["disabled"] = disabled
                payload = json.dumps(data, ensure_ascii=False)
                cur = conn.execute(
                    """
                    UPDATE accounts
                    SET data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = ?
                    """,
                    (payload, account_id),
                )
                if cur.rowcount > 0:
                    updated += 1
    return updated, missing

async def _renumber_account_positions() -> None:
    backend = _get_backend()
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                WITH ordered AS (
                    SELECT account_id, ROW_NUMBER() OVER (ORDER BY position ASC) AS new_pos
                    FROM accounts
                )
                UPDATE accounts AS a
                SET position = ordered.new_pos,
                    updated_at = CURRENT_TIMESTAMP
                FROM ordered
                WHERE a.account_id = ordered.account_id
                """
            )
        return
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock, conn:
            rows = conn.execute(
                "SELECT account_id FROM accounts ORDER BY position ASC"
            ).fetchall()
            for index, row in enumerate(rows, 1):
                conn.execute(
                    "UPDATE accounts SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE account_id = ?",
                    (index, row["account_id"]),
                )

async def delete_accounts(account_ids: list[str]) -> int:
    if not account_ids:
        return 0
    backend = _get_backend()
    deleted = 0
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM accounts WHERE account_id = ANY($1)",
                account_ids,
            )
        try:
            deleted = int(result.split()[-1])
        except Exception:
            deleted = 0
    elif backend == "sqlite":
        conn = _get_sqlite_conn()
        placeholders = ",".join(["?"] * len(account_ids))
        with _sqlite_lock, conn:
            cur = conn.execute(
                f"DELETE FROM accounts WHERE account_id IN ({placeholders})",
                tuple(account_ids),
            )
            deleted = cur.rowcount or 0
    else:
        return 0

    if deleted > 0:
        await _renumber_account_positions()
    return deleted

def update_account_disabled_sync(account_id: str, disabled: bool) -> bool:
    return _run_in_db_loop(update_account_disabled(account_id, disabled))

def bulk_update_accounts_disabled_sync(account_ids: list[str], disabled: bool) -> tuple[int, list[str]]:
    return _run_in_db_loop(bulk_update_accounts_disabled(account_ids, disabled))

def delete_accounts_sync(account_ids: list[str]) -> int:
    return _run_in_db_loop(delete_accounts(account_ids))


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


async def _save_kv(table_name: str, key: str, value: dict) -> bool:
    backend = _get_backend()
    payload = json.dumps(value, ensure_ascii=False)
    if backend == "postgres":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {table_name} (key, value, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                key,
                payload,
            )
        return True
    if backend == "sqlite":
        conn = _get_sqlite_conn()
        with _sqlite_lock, conn:
            conn.execute(
                f"""
                INSERT INTO {table_name} (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, payload),
            )
        return True
    return False

async def load_settings() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await _load_kv("kv_settings", "settings")
    except Exception as e:
        logger.error(f"[STORAGE] Settings read failed: {e}")
    return None


async def save_settings(settings: dict) -> bool:
    if not is_database_enabled():
        return False
    try:
        saved = await _save_kv("kv_settings", "settings", settings)
        if saved:
            logger.info("[STORAGE] Settings saved to database")
        return saved
    except Exception as e:
        logger.error(f"[STORAGE] Settings write failed: {e}")
    return False


# ==================== Stats storage ====================

async def load_stats() -> Optional[dict]:
    if not is_database_enabled():
        return None
    try:
        return await _load_kv("kv_stats", "stats")
    except Exception as e:
        logger.error(f"[STORAGE] Stats read failed: {e}")
    return None


async def save_stats(stats: dict) -> bool:
    if not is_database_enabled():
        return False
    try:
        return await _save_kv("kv_stats", "stats", stats)
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


async def load_task_history(limit: int = 100) -> Optional[list]:
    if not is_database_enabled():
        return None
    backend = _get_backend()
    try:
        if backend == "postgres":
            pool = await _get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT data FROM task_history
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
            return [_parse_account_value(row["data"]) for row in rows if row and row["data"] is not None]
        if backend == "sqlite":
            conn = _get_sqlite_conn()
            with _sqlite_lock:
                rows = conn.execute(
                    """
                    SELECT data FROM task_history
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            results = []
            for row in rows:
                value = _parse_account_value(row["data"])
                if value is not None:
                    results.append(value)
            return results
    except Exception as e:
        logger.error(f"[STORAGE] Task history read failed: {e}")
    return None


async def clear_task_history() -> int:
    if not is_database_enabled():
        return 0
    backend = _get_backend()
    try:
        if backend == "postgres":
            pool = await _get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute("DELETE FROM task_history")
            if result.startswith("DELETE"):
                parts = result.split()
                return int(parts[-1]) if parts else 0
            return 0
        if backend == "sqlite":
            conn = _get_sqlite_conn()
            with _sqlite_lock, conn:
                cur = conn.execute("DELETE FROM task_history")
                return cur.rowcount or 0
    except Exception as e:
        logger.error(f"[STORAGE] Task history clear failed: {e}")
    return 0


def save_task_history_entry_sync(entry: dict) -> bool:
    return _run_in_db_loop(save_task_history_entry(entry))


def load_task_history_sync(limit: int = 100) -> Optional[list]:
    return _run_in_db_loop(load_task_history(limit))


def clear_task_history_sync() -> int:
    return _run_in_db_loop(clear_task_history())
