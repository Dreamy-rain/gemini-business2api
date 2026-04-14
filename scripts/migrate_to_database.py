#!/usr/bin/env python3
"""
数据库迁移脚本

用途：将数据从 kv_store 或本地文件迁移到新的数据库表结构

迁移内容：
    - accounts (账户配置)
    - settings (系统设置)
    - stats (统计数据)

使用方法：
    python scripts/migrate_to_database.py

迁移后：
    - kv_store 数据保留（作为备份，仅 PostgreSQL）
    - 本地文件重命名为 .migrated_YYYYMMDD-HHMMSS（防止重复迁移）

支持的数据库：
    - PostgreSQL：配置 DATABASE_URL 环境变量
    - SQLite：不配置 DATABASE_URL，自动使用 data/data.db
"""

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


def rename_migrated_file(file_path: str) -> str:
    """重命名已迁移的文件，添加时间戳后缀"""
    if not os.path.exists(file_path):
        return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    new_path = f"{file_path}.migrated_{timestamp}"
    os.rename(file_path, new_path)
    return new_path


async def migrate_from_kv_store(conn):
    """从 kv_store 迁移数据到新表"""
    print("\n" + "=" * 60)
    print("从 kv_store 迁移数据")
    print("=" * 60)

    # 检查 kv_store 是否存在
    exists = await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='kv_store'
        )
        """
    )

    if not exists:
        print("❌ kv_store 表不存在，跳过")
        return False

    migrated_any = False

    # 1. 迁移 accounts
    print("\n### 迁移 accounts ###")
    row = await conn.fetchrow("SELECT value FROM kv_store WHERE key = $1", "accounts")
    if row:
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)

        if isinstance(value, list) and len(value) > 0:
            # 检查新表是否已有数据
            count = await conn.fetchval("SELECT COUNT(*) FROM accounts")
            if count > 0:
                print(f"⚠️  accounts 表已有 {count} 条记录")
                confirm = input("是否覆盖？(yes/no): ").strip().lower()
                if confirm not in ("yes", "y"):
                    print("跳过 accounts 迁移")
                else:
                    # 清空并迁移
                    await conn.execute("DELETE FROM accounts")
                    for index, acc in enumerate(value, 1):
                        account_id = acc.get("id") or f"account_{index}"
                        await conn.execute(
                            """
                            INSERT INTO accounts (account_id, position, data, updated_at)
                            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                            """,
                            account_id,
                            index,
                            json.dumps(acc, ensure_ascii=False)
                        )
                    print(f"✅ 成功迁移 {len(value)} 个账户")
                    migrated_any = True
            else:
                # 新表为空，直接迁移
                for index, acc in enumerate(value, 1):
                    account_id = acc.get("id") or f"account_{index}"
                    await conn.execute(
                        """
                        INSERT INTO accounts (account_id, position, data, updated_at)
                        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                        """,
                        account_id,
                        index,
                        json.dumps(acc, ensure_ascii=False)
                    )
                print(f"✅ 成功迁移 {len(value)} 个账户")
                migrated_any = True
        else:
            print("⚠️  kv_store 中 accounts 为空")
    else:
        print("⚠️  kv_store 中未找到 accounts")

    # 2. 迁移 settings
    print("\n### 迁移 settings ###")
    row = await conn.fetchrow("SELECT value FROM kv_store WHERE key = $1", "settings")
    if row:
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)

        if isinstance(value, dict):
            # 检查新表是否已有数据
            exists = await conn.fetchval("SELECT 1 FROM kv_settings WHERE key = $1", "settings")
            if exists:
                print("⚠️  kv_settings 表已有 settings 记录")
                confirm = input("是否覆盖？(yes/no): ").strip().lower()
                if confirm not in ("yes", "y"):
                    print("跳过 settings 迁移")
                else:
                    await conn.execute(
                        """
                        INSERT INTO kv_settings (key, value, updated_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        "settings",
                        json.dumps(value, ensure_ascii=False)
                    )
                    print("✅ 成功迁移 settings")
                    migrated_any = True
            else:
                await conn.execute(
                    """
                    INSERT INTO kv_settings (key, value, updated_at)
                    VALUES ($1, $2, CURRENT_TIMESTAMP)
                    """,
                    "settings",
                    json.dumps(value, ensure_ascii=False)
                )
                print("✅ 成功迁移 settings")
                migrated_any = True
        else:
            print("⚠️  kv_store 中 settings 格式错误")
    else:
        print("⚠️  kv_store 中未找到 settings")

    # 3. 迁移 stats
    print("\n### 迁移 stats ###")
    row = await conn.fetchrow("SELECT value FROM kv_store WHERE key = $1", "stats")
    if row:
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)

        if isinstance(value, dict):
            # 检查新表是否已有数据
            exists = await conn.fetchval("SELECT 1 FROM kv_stats WHERE key = $1", "stats")
            if exists:
                print("⚠️  kv_stats 表已有 stats 记录")
                confirm = input("是否覆盖？(yes/no): ").strip().lower()
                if confirm not in ("yes", "y"):
                    print("跳过 stats 迁移")
                else:
                    await conn.execute(
                        """
                        INSERT INTO kv_stats (key, value, updated_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        "stats",
                        json.dumps(value, ensure_ascii=False)
                    )
                    print("✅ 成功迁移 stats")
                    migrated_any = True
            else:
                await conn.execute(
                    """
                    INSERT INTO kv_stats (key, value, updated_at)
                    VALUES ($1, $2, CURRENT_TIMESTAMP)
                    """,
                    "stats",
                    json.dumps(value, ensure_ascii=False)
                )
                print("✅ 成功迁移 stats")
                migrated_any = True
        else:
            print("⚠️  kv_store 中 stats 格式错误")
    else:
        print("⚠️  kv_store 中未找到 stats")

    return migrated_any


async def migrate_from_local_files(conn):
    """从本地文件迁移数据到数据库"""
    print("\n" + "=" * 60)
    print("从本地文件迁移数据")
    print("=" * 60)

    data_dir = project_root / "data"
    accounts_file = data_dir / "accounts.json"
    settings_file = data_dir / "settings.yaml"
    stats_file = data_dir / "stats.json"

    migrated_any = False

    # 1. 迁移 accounts.json
    print("\n### 迁移 accounts.json ###")
    if accounts_file.exists():
        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                accounts_data = json.load(f)

            if isinstance(accounts_data, list) and len(accounts_data) > 0:
                # 检查新表是否已有数据
                count = await conn.fetchval("SELECT COUNT(*) FROM accounts")
                if count > 0:
                    print(f"⚠️  accounts 表已有 {count} 条记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 accounts.json 迁移")
                    else:
                        # 清空并迁移
                        await conn.execute("DELETE FROM accounts")
                        for index, acc in enumerate(accounts_data, 1):
                            account_id = acc.get("id") or f"account_{index}"
                            await conn.execute(
                                """
                                INSERT INTO accounts (account_id, position, data, updated_at)
                                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                                """,
                                account_id,
                                index,
                                json.dumps(acc, ensure_ascii=False)
                            )
                        print(f"✅ 成功迁移 {len(accounts_data)} 个账户")
                        # 重命名文件
                        new_path = rename_migrated_file(str(accounts_file))
                        print(f"✅ 文件已重命名: {new_path}")
                        migrated_any = True
                else:
                    # 新表为空，直接迁移
                    for index, acc in enumerate(accounts_data, 1):
                        account_id = acc.get("id") or f"account_{index}"
                        await conn.execute(
                            """
                            INSERT INTO accounts (account_id, position, data, updated_at)
                            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                            """,
                            account_id,
                            index,
                            json.dumps(acc, ensure_ascii=False)
                        )
                    print(f"✅ 成功迁移 {len(accounts_data)} 个账户")
                    # 重命名文件
                    new_path = rename_migrated_file(str(accounts_file))
                    print(f"✅ 文件已重命名: {new_path}")
                    migrated_any = True
            else:
                print("⚠️  accounts.json 为空")
        except Exception as e:
            print(f"❌ 迁移 accounts.json 失败: {e}")
    else:
        print("⚠️  accounts.json 不存在")

    # 2. 迁移 settings.yaml
    print("\n### 迁移 settings.yaml ###")
    if settings_file.exists():
        try:
            import yaml
            with open(settings_file, "r", encoding="utf-8") as f:
                settings_data = yaml.safe_load(f) or {}

            if isinstance(settings_data, dict):
                # 检查新表是否已有数据
                exists = await conn.fetchval("SELECT 1 FROM kv_settings WHERE key = $1", "settings")
                if exists:
                    print("⚠️  kv_settings 表已有 settings 记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 settings.yaml 迁移")
                    else:
                        await conn.execute(
                            """
                            INSERT INTO kv_settings (key, value, updated_at)
                            VALUES ($1, $2, CURRENT_TIMESTAMP)
                            ON CONFLICT(key) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            "settings",
                            json.dumps(settings_data, ensure_ascii=False)
                        )
                        print("✅ 成功迁移 settings")
                        # 重命名文件
                        new_path = rename_migrated_file(str(settings_file))
                        print(f"✅ 文件已重命名: {new_path}")
                        migrated_any = True
                else:
                    await conn.execute(
                        """
                        INSERT INTO kv_settings (key, value, updated_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        """,
                        "settings",
                        json.dumps(settings_data, ensure_ascii=False)
                    )
                    print("✅ 成功迁移 settings")
                    # 重命名文件
                    new_path = rename_migrated_file(str(settings_file))
                    print(f"✅ 文件已重命名: {new_path}")
                    migrated_any = True
            else:
                print("⚠️  settings.yaml 格式错误")
        except Exception as e:
            print(f"❌ 迁移 settings.yaml 失败: {e}")
    else:
        print("⚠️  settings.yaml 不存在")

    # 3. 迁移 stats.json
    print("\n### 迁移 stats.json ###")
    if stats_file.exists():
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                stats_data = json.load(f)

            if isinstance(stats_data, dict):
                # 检查新表是否已有数据
                exists = await conn.fetchval("SELECT 1 FROM kv_stats WHERE key = $1", "stats")
                if exists:
                    print("⚠️  kv_stats 表已有 stats 记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 stats.json 迁移")
                    else:
                        await conn.execute(
                            """
                            INSERT INTO kv_stats (key, value, updated_at)
                            VALUES ($1, $2, CURRENT_TIMESTAMP)
                            ON CONFLICT(key) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            "stats",
                            json.dumps(stats_data, ensure_ascii=False)
                        )
                        print("✅ 成功迁移 stats")
                        # 重命名文件
                        new_path = rename_migrated_file(str(stats_file))
                        print(f"✅ 文件已重命名: {new_path}")
                        migrated_any = True
                else:
                    await conn.execute(
                        """
                        INSERT INTO kv_stats (key, value, updated_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        """,
                        "stats",
                        json.dumps(stats_data, ensure_ascii=False)
                    )
                    print("✅ 成功迁移 stats")
                    # 重命名文件
                    new_path = rename_migrated_file(str(stats_file))
                    print(f"✅ 文件已重命名: {new_path}")
                    migrated_any = True
            else:
                print("⚠️  stats.json 格式错误")
        except Exception as e:
            print(f"❌ 迁移 stats.json 失败: {e}")
    else:
        print("⚠️  stats.json 不存在")

    return migrated_any


def _init_sqlite_tables(conn: sqlite3.Connection) -> None:
    """初始化 SQLite 表结构"""
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
def migrate_from_local_files_sqlite(conn: sqlite3.Connection) -> bool:
    """从本地文件迁移数据到 SQLite"""
    print("\n" + "=" * 60)
    print("从本地文件迁移数据")
    print("=" * 60)

    data_dir = project_root / "data"
    accounts_file = data_dir / "accounts.json"
    settings_file = data_dir / "settings.yaml"
    stats_file = data_dir / "stats.json"

    migrated_any = False

    # 1. 迁移 accounts
    print("\n### 迁移 accounts ###")
    if accounts_file.exists():
        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                accounts_data = json.load(f)

            if isinstance(accounts_data, list) and len(accounts_data) > 0:
                # 检查新表是否已有数据
                count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
                if count > 0:
                    print(f"⚠️  accounts 表已有 {count} 条记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 accounts 迁移")
                    else:
                        # 清空并迁移
                        with conn:
                            conn.execute("DELETE FROM accounts")
                            for index, acc in enumerate(accounts_data, 1):
                                account_id = acc.get("id") or f"account_{index}"
                                conn.execute(
                                    """
                                    INSERT INTO accounts (account_id, position, data, updated_at)
                                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                                    """,
                                    (account_id, index, json.dumps(acc, ensure_ascii=False))
                                )
                        print(f"✅ 成功迁移 {len(accounts_data)} 个账户")
                        migrated_any = True

                        # 重命名文件
                        new_path = rename_migrated_file(str(accounts_file))
                        if new_path:
                            print(f"✅ 已重命名: {accounts_file.name} → {Path(new_path).name}")
                else:
                    # 直接迁移
                    with conn:
                        for index, acc in enumerate(accounts_data, 1):
                            account_id = acc.get("id") or f"account_{index}"
                            conn.execute(
                                """
                                INSERT INTO accounts (account_id, position, data, updated_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                                """,
                                (account_id, index, json.dumps(acc, ensure_ascii=False))
                            )
                    print(f"✅ 成功迁移 {len(accounts_data)} 个账户")
                    migrated_any = True

                    # 重命名文件
                    new_path = rename_migrated_file(str(accounts_file))
                    if new_path:
                        print(f"✅ 已重命名: {accounts_file.name} → {Path(new_path).name}")
            else:
                print("⚠️  accounts.json 为空或格式错误")
        except Exception as e:
            print(f"❌ 迁移 accounts 失败: {e}")
    else:
        print("⚠️  未找到 accounts.json")

    # 2. 迁移 settings
    print("\n### 迁移 settings ###")
    if settings_file.exists():
        try:
            import yaml
            with open(settings_file, "r", encoding="utf-8") as f:
                settings_data = yaml.safe_load(f)

            if settings_data:
                # 检查新表是否已有数据
                row = conn.execute(
                    "SELECT 1 FROM kv_settings WHERE key = ?",
                    ("settings",)
                ).fetchone()
                if row:
                    print("⚠️  kv_settings 表已有 settings 记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 settings 迁移")
                    else:
                        with conn:
                            conn.execute(
                                """
                                INSERT INTO kv_settings (key, value, updated_at)
                                VALUES (?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(key) DO UPDATE SET
                                    value = excluded.value,
                                    updated_at = CURRENT_TIMESTAMP
                                """,
                                ("settings", json.dumps(settings_data, ensure_ascii=False))
                            )
                        print("✅ 成功迁移 settings")
                        migrated_any = True

                        # 重命名文件
                        new_path = rename_migrated_file(str(settings_file))
                        if new_path:
                            print(f"✅ 已重命名: {settings_file.name} → {Path(new_path).name}")
                else:
                    with conn:
                        conn.execute(
                            """
                            INSERT INTO kv_settings (key, value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            """,
                            ("settings", json.dumps(settings_data, ensure_ascii=False))
                        )
                    print("✅ 成功迁移 settings")
                    migrated_any = True

                    # 重命名文件
                    new_path = rename_migrated_file(str(settings_file))
                    if new_path:
                        print(f"✅ 已重命名: {settings_file.name} → {Path(new_path).name}")
            else:
                print("⚠️  settings.yaml 为空")
        except Exception as e:
            print(f"❌ 迁移 settings 失败: {e}")
    else:
        print("⚠️  未找到 settings.yaml")

    # 3. 迁移 stats
    print("\n### 迁移 stats ###")
    if stats_file.exists():
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                stats_data = json.load(f)

            if stats_data:
                # 检查新表是否已有数据
                row = conn.execute(
                    "SELECT 1 FROM kv_stats WHERE key = ?",
                    ("stats",)
                ).fetchone()
                if row:
                    print("⚠️  kv_stats 表已有 stats 记录")
                    confirm = input("是否覆盖？(yes/no): ").strip().lower()
                    if confirm not in ("yes", "y"):
                        print("跳过 stats 迁移")
                    else:
                        with conn:
                            conn.execute(
                                """
                                INSERT INTO kv_stats (key, value, updated_at)
                                VALUES (?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(key) DO UPDATE SET
                                    value = excluded.value,
                                    updated_at = CURRENT_TIMESTAMP
                                """,
                                ("stats", json.dumps(stats_data, ensure_ascii=False))
                            )
                        print("✅ 成功迁移 stats")
                        migrated_any = True

                        # 重命名文件
                        new_path = rename_migrated_file(str(stats_file))
                        if new_path:
                            print(f"✅ 已重命名: {stats_file.name} → {Path(new_path).name}")
                else:
                    with conn:
                        conn.execute(
                            """
                            INSERT INTO kv_stats (key, value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            """,
                            ("stats", json.dumps(stats_data, ensure_ascii=False))
                        )
                    print("✅ 成功迁移 stats")
                    migrated_any = True

                    # 重命名文件
                    new_path = rename_migrated_file(str(stats_file))
                    if new_path:
                        print(f"✅ 已重命名: {stats_file.name} → {Path(new_path).name}")
            else:
                print("⚠️  stats.json 为空")
        except Exception as e:
            print(f"❌ 迁移 stats 失败: {e}")
    else:
        print("⚠️  未找到 stats.json")

    return migrated_any


async def main():
    """主函数"""
    database_url = os.environ.get("DATABASE_URL", "").strip()

    # 判断使用哪种数据库
    if database_url:
        backend = "postgres"
        db_info = database_url.split('@')[1] if '@' in database_url else 'PostgreSQL'
    else:
        backend = "sqlite"
        db_info = "data/data.db (SQLite)"

    print("=" * 60)
    print("数据库迁移脚本")
    print("=" * 60)
    print(f"目标数据库: {db_info}")
    print()
    print("迁移内容：")
    if backend == "postgres":
        print("  1. kv_store → 新表（accounts, kv_settings, kv_stats）")
        print("  2. 本地文件 → 新表")
    else:
        print("  1. 本地文件 → SQLite 数据库")
    print()
    print("迁移后：")
    if backend == "postgres":
        print("  - kv_store 保留（作为备份）")
    print("  - 本地文件重命名为 .migrated_YYYYMMDD-HHMMSS")
    print()

    confirm = input("开始迁移？(yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("❌ 操作已取消")
        return False

    try:
        if backend == "postgres":
            # PostgreSQL 迁移
            import asyncpg
            conn = await asyncpg.connect(database_url)

            # 1. 从 kv_store 迁移
            kv_migrated = await migrate_from_kv_store(conn)

            # 2. 从本地文件迁移
            file_migrated = await migrate_from_local_files(conn)

            await conn.close()

        else:
            # SQLite 迁移
            sqlite_path = project_root / "data" / "data.db"
            os.makedirs(sqlite_path.parent, exist_ok=True)

            conn = sqlite3.connect(str(sqlite_path))
            conn.row_factory = sqlite3.Row

            # 初始化表结构
            _init_sqlite_tables(conn)

            # 从本地文件迁移
            file_migrated = migrate_from_local_files_sqlite(conn)
            kv_migrated = False

            conn.close()

        print("\n" + "=" * 60)
        if kv_migrated or file_migrated:
            print("✅ 迁移完成！")
        else:
            print("⚠️  没有数据需要迁移")
        print("=" * 60)
        print()
        print("下一步：")
        print("1. 重启应用")
        print("2. 应用会自动使用新表数据")
        print()

        return True

    except ImportError as e:
        if "asyncpg" in str(e):
            print("❌ 错误：未安装 asyncpg")
            print("   请运行: pip install asyncpg")
        else:
            print(f"❌ 错误：{e}")
        return False
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
