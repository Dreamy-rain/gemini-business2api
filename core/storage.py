"""
存储抽象层 - 支持文件存储和 PostgreSQL 数据库存储

通过 DATABASE_URL 环境变量自动切换：
- 未设置：使用本地文件存储（原有逻辑）
- 已设置：使用 PostgreSQL 数据库存储

示例：
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 数据库 URL（可选）
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 数据库连接池（延迟初始化）
_db_pool = None


def is_database_enabled() -> bool:
    """检查是否启用数据库存储"""
    return bool(DATABASE_URL)


async def _get_pool():
    """获取数据库连接池（延迟初始化）"""
    global _db_pool
    if _db_pool is None:
        try:
            import asyncpg
            _db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=30
            )
            # 初始化表结构
            await _init_tables()
            logger.info("[STORAGE] PostgreSQL 连接池已创建")
        except ImportError:
            logger.error("[STORAGE] 需要安装 asyncpg: pip install asyncpg")
            raise
        except Exception as e:
            logger.error(f"[STORAGE] 数据库连接失败: {e}")
            raise
    return _db_pool


async def _init_tables():
    """初始化数据库表结构"""
    pool = _db_pool
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("[STORAGE] 数据库表已初始化")


async def db_get(key: str) -> Optional[dict]:
    """从数据库获取数据"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM kv_store WHERE key = $1", key
        )
        if row:
            return json.loads(row["value"])
        return None


async def db_set(key: str, value: dict):
    """保存数据到数据库"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO kv_store (key, value, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
        """, key, json.dumps(value, ensure_ascii=False))


# ==================== 账户存储接口 ====================

async def load_accounts() -> list:
    """
    加载账户配置
    - 优先从环境变量 ACCOUNTS_CONFIG 加载
    - 其次从数据库加载（如果启用）
    - 最后从文件加载
    """
    # 1. 优先从环境变量加载
    env_accounts = os.environ.get("ACCOUNTS_CONFIG")
    if env_accounts:
        try:
            accounts = json.loads(env_accounts)
            logger.info(f"[STORAGE] 从环境变量加载 {len(accounts)} 个账户")
            return accounts
        except Exception as e:
            logger.error(f"[STORAGE] 环境变量解析失败: {e}")

    # 2. 从数据库加载（如果启用）
    if is_database_enabled():
        try:
            data = await db_get("accounts")
            if data:
                logger.info(f"[STORAGE] 从数据库加载 {len(data)} 个账户")
                return data
            logger.info("[STORAGE] 数据库中无账户数据")
            return []
        except Exception as e:
            logger.error(f"[STORAGE] 数据库读取失败: {e}")
            # 降级到文件存储
    
    # 3. 从文件加载（原有逻辑）
    return None  # 返回 None 表示使用原有文件加载逻辑


async def save_accounts(accounts: list):
    """
    保存账户配置
    - 如果启用数据库，保存到数据库
    - 否则保存到文件
    """
    if is_database_enabled():
        try:
            await db_set("accounts", accounts)
            logger.info(f"[STORAGE] 已保存 {len(accounts)} 个账户到数据库")
            return True
        except Exception as e:
            logger.error(f"[STORAGE] 数据库写入失败: {e}")
            # 降级到文件存储
    
    return False  # 返回 False 表示使用原有文件保存逻辑


# ==================== 设置存储接口 ====================

async def load_settings() -> Optional[dict]:
    """从数据库加载设置（如果启用）"""
    if is_database_enabled():
        try:
            return await db_get("settings")
        except Exception as e:
            logger.error(f"[STORAGE] 设置读取失败: {e}")
    return None


async def save_settings(settings: dict) -> bool:
    """保存设置到数据库（如果启用）"""
    if is_database_enabled():
        try:
            await db_set("settings", settings)
            logger.info("[STORAGE] 设置已保存到数据库")
            return True
        except Exception as e:
            logger.error(f"[STORAGE] 设置写入失败: {e}")
    return False


# ==================== 统计存储接口 ====================

async def load_stats() -> Optional[dict]:
    """从数据库加载统计数据（如果启用）"""
    if is_database_enabled():
        try:
            return await db_get("stats")
        except Exception as e:
            logger.error(f"[STORAGE] 统计读取失败: {e}")
    return None


async def save_stats(stats: dict) -> bool:
    """保存统计数据到数据库（如果启用）"""
    if is_database_enabled():
        try:
            await db_set("stats", stats)
            return True
        except Exception as e:
            logger.error(f"[STORAGE] 统计写入失败: {e}")
    return False
