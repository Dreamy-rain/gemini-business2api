"""账户管理模块

负责账户配置、多账户协调和会话缓存管理
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, TYPE_CHECKING

from fastapi import HTTPException

# 导入存储层（支持数据库）
from core import storage

if TYPE_CHECKING:
    from core.jwt import JWTManager

logger = logging.getLogger(__name__)

# 配置文件路径 - 自动检测环境
if os.path.exists("/data"):
    ACCOUNTS_FILE = "/data/accounts.json"  # HF Pro 持久化
else:
    ACCOUNTS_FILE = "data/accounts.json"  # 本地存储（统一到 data 目录）


@dataclass
class AccountConfig:
    """单个账户配置"""
    account_id: str
    secure_c_ses: str
    host_c_oses: Optional[str]
    csesidx: str
    config_id: str
    expires_at: Optional[str] = None  # 账户过期时间 (格式: "2025-12-23 10:59:21")
    disabled: bool = False  # 手动禁用状态

    def get_remaining_hours(self) -> Optional[float]:
        """计算账户剩余小时数"""
        if not self.expires_at:
            return None
        try:
            # 解析过期时间（假设为北京时间）
            beijing_tz = timezone(timedelta(hours=8))
            expire_time = datetime.strptime(self.expires_at, "%Y-%m-%d %H:%M:%S")
            expire_time = expire_time.replace(tzinfo=beijing_tz)

            # 当前时间（北京时间）
            now = datetime.now(beijing_tz)

            # 计算剩余时间
            remaining = (expire_time - now).total_seconds() / 3600
            return remaining
        except Exception:
            return None

    def is_expired(self) -> bool:
        """检查账户是否已过期"""
        remaining = self.get_remaining_hours()
        if remaining is None:
            return False  # 未设置过期时间，默认不过期
        return remaining <= 0


def format_account_expiration(remaining_hours: Optional[float]) -> tuple:
    """
    格式化账户过期时间显示（基于12小时过期周期）

    Args:
        remaining_hours: 剩余小时数（None表示未设置过期时间）

    Returns:
        (status, status_color, expire_display) 元组
    """
    if remaining_hours is None:
        # 未设置过期时间时显示为"未设置"
        return ("未设置", "#9e9e9e", "未设置")
    elif remaining_hours <= 0:
        return ("已过期", "#f44336", "已过期")
    elif remaining_hours < 3:  # 少于3小时
        return ("即将过期", "#ff9800", f"{remaining_hours:.1f} 小时")
    else:  # 3小时及以上，统一显示小时
        return ("正常", "#4caf50", f"{remaining_hours:.1f} 小时")


class AccountManager:
    """单个账户管理器"""
    def __init__(self, config: AccountConfig, http_client, user_agent: str, account_failure_threshold: int, rate_limit_cooldown_seconds: int):
        self.config = config
        self.http_client = http_client
        self.user_agent = user_agent
        self.account_failure_threshold = account_failure_threshold
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.jwt_manager: Optional['JWTManager'] = None  # 延迟初始化
        self.is_available = True
        self.last_error_time = 0.0
        self.last_429_time = 0.0  # 429错误专属时间戳
        self.error_count = 0
        self.conversation_count = 0  # 累计对话次数

    async def get_jwt(self, request_id: str = "") -> str:
        """获取 JWT token (带错误处理)"""
        # 检查账户是否过期
        if self.config.is_expired():
            self.is_available = False
            logger.warning(f"[ACCOUNT] [{self.config.account_id}] 账户已过期，已自动禁用")
            raise HTTPException(403, f"Account {self.config.account_id} has expired")

        try:
            if self.jwt_manager is None:
                # 延迟初始化 JWTManager (避免循环依赖)
                from core.jwt import JWTManager
                self.jwt_manager = JWTManager(self.config, self.http_client, self.user_agent)
            jwt = await self.jwt_manager.get(request_id)
            self.is_available = True
            self.error_count = 0
            return jwt
        except Exception as e:
            self.last_error_time = time.time()
            self.error_count += 1
            # 使用配置的失败阈值
            if self.error_count >= self.account_failure_threshold:
                self.is_available = False
                logger.error(f"[ACCOUNT] [{self.config.account_id}] JWT获取连续失败{self.error_count}次，账户已永久禁用")
            else:
                # 安全：只记录异常类型，不记录详细信息
                logger.warning(f"[ACCOUNT] [{self.config.account_id}] JWT获取失败({self.error_count}/{self.account_failure_threshold}): {type(e).__name__}")
            raise

    def should_retry(self) -> bool:
        """检查账户是否可重试（429错误冷却期后自动恢复，普通错误永久禁用）"""
        if self.is_available:
            return True

        current_time = time.time()

        # 检查429冷却期（冷却期后自动恢复）
        if self.last_429_time > 0:
            if current_time - self.last_429_time > self.rate_limit_cooldown_seconds:
                # 冷却期已过，自动恢复账户可用性
                self.is_available = True
                self.last_429_time = 0.0
                self.error_count = 0  # 重置错误计数
                logger.info(f"[ACCOUNT] [{self.config.account_id}] 429冷却期已过，账户已自动恢复")
                return True
            return False  # 仍在冷却期

        # 普通错误永久禁用
        return False

    def get_cooldown_info(self) -> tuple[int, str | None]:
        """
        获取账户冷却信息

        Returns:
            (cooldown_seconds, cooldown_reason) 元组
            - cooldown_seconds: 剩余冷却秒数，0表示无冷却，-1表示永久禁用
            - cooldown_reason: 冷却原因，None表示无冷却
        """
        current_time = time.time()

        # 优先检查429冷却期（无论账户是否可用）
        if self.last_429_time > 0:
            remaining_429 = self.rate_limit_cooldown_seconds - (current_time - self.last_429_time)
            if remaining_429 > 0:
                return (int(remaining_429), "429限流")
            # 429冷却期已过

        # 如果账户可用且没有429冷却，返回正常状态
        if self.is_available:
            return (0, None)

        # 普通错误永久禁用
        return (-1, "错误禁用")


class MultiAccountManager:
    """多账户协调器"""
    def __init__(self, session_cache_ttl_seconds: int):
        self.accounts: Dict[str, AccountManager] = {}
        self.account_list: List[str] = []  # 账户ID列表 (用于轮询)
        self.current_index = 0
        self._cache_lock = asyncio.Lock()  # 缓存操作专用锁
        self._index_lock = asyncio.Lock()  # 索引更新专用锁
        # 全局会话缓存：{conv_key: {"account_id": str, "session_id": str, "updated_at": float}}
        self.global_session_cache: Dict[str, dict] = {}
        self.cache_max_size = 1000  # 最大缓存条目数
        self.cache_ttl = session_cache_ttl_seconds  # 缓存过期时间（秒）
        # Session级别锁：防止同一对话的并发请求冲突
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks_lock = asyncio.Lock()  # 保护锁字典的锁
        self._session_locks_max_size = 2000  # 最大锁数量

    def _clean_expired_cache(self):
        """清理过期的缓存条目"""
        current_time = time.time()
        expired_keys = [
            key for key, value in self.global_session_cache.items()
            if current_time - value["updated_at"] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.global_session_cache[key]
        if expired_keys:
            logger.info(f"[CACHE] 清理 {len(expired_keys)} 个过期会话缓存")

    def _ensure_cache_size(self):
        """确保缓存不超过最大大小（LRU策略）"""
        if len(self.global_session_cache) > self.cache_max_size:
            # 按更新时间排序，删除最旧的20%
            sorted_items = sorted(
                self.global_session_cache.items(),
                key=lambda x: x[1]["updated_at"]
            )
            remove_count = len(sorted_items) - int(self.cache_max_size * 0.8)
            for key, _ in sorted_items[:remove_count]:
                del self.global_session_cache[key]
            logger.info(f"[CACHE] LRU清理 {remove_count} 个最旧会话缓存")

    async def start_background_cleanup(self):
        """启动后台缓存清理任务（每5分钟执行一次）"""
        try:
            while True:
                await asyncio.sleep(300)  # 5分钟
                async with self._cache_lock:
                    self._clean_expired_cache()
                    self._ensure_cache_size()
        except asyncio.CancelledError:
            logger.info("[CACHE] 后台清理任务已停止")
        except Exception as e:
            logger.error(f"[CACHE] 后台清理任务异常: {e}")

    async def set_session_cache(self, conv_key: str, account_id: str, session_id: str):
        """线程安全地设置会话缓存"""
        async with self._cache_lock:
            self.global_session_cache[conv_key] = {
                "account_id": account_id,
                "session_id": session_id,
                "updated_at": time.time()
            }
            # 检查缓存大小
            self._ensure_cache_size()

    async def update_session_time(self, conv_key: str):
        """线程安全地更新会话时间戳"""
        async with self._cache_lock:
            if conv_key in self.global_session_cache:
                self.global_session_cache[conv_key]["updated_at"] = time.time()

    async def acquire_session_lock(self, conv_key: str) -> asyncio.Lock:
        """获取指定对话的锁（用于防止同一对话的并发请求冲突）"""
        async with self._session_locks_lock:
            # 清理过多的锁（LRU策略：删除不在缓存中的锁）
            if len(self._session_locks) > self._session_locks_max_size:
                # 只保留当前缓存中存在的锁
                valid_keys = set(self.global_session_cache.keys())
                keys_to_remove = [k for k in self._session_locks if k not in valid_keys]
                for k in keys_to_remove[:len(keys_to_remove)//2]:  # 删除一半无效锁
                    del self._session_locks[k]

            if conv_key not in self._session_locks:
                self._session_locks[conv_key] = asyncio.Lock()
            return self._session_locks[conv_key]

    def update_http_client(self, http_client):
        """更新所有账户使用的 http_client（用于代理变更后重建客户端）"""
        for account_mgr in self.accounts.values():
            account_mgr.http_client = http_client
            if account_mgr.jwt_manager is not None:
                account_mgr.jwt_manager.http_client = http_client

    def add_account(self, config: AccountConfig, http_client, user_agent: str, account_failure_threshold: int, rate_limit_cooldown_seconds: int, global_stats: dict):
        """添加账户"""
        manager = AccountManager(config, http_client, user_agent, account_failure_threshold, rate_limit_cooldown_seconds)
        # 从统计数据加载对话次数
        if "account_conversations" in global_stats:
            manager.conversation_count = global_stats["account_conversations"].get(config.account_id, 0)
        self.accounts[config.account_id] = manager
        self.account_list.append(config.account_id)
        logger.info(f"[MULTI] [ACCOUNT] 添加账户: {config.account_id}")

    async def get_account(self, account_id: Optional[str] = None, request_id: str = "") -> AccountManager:
        """获取账户 (智能选择或指定) - 优先选择健康账户，提升响应速度"""
        req_tag = f"[req_{request_id}] " if request_id else ""

        # 如果指定了账户ID（无需锁）
        if account_id:
            if account_id not in self.accounts:
                raise HTTPException(404, f"Account {account_id} not found")
            account = self.accounts[account_id]
            if not account.should_retry():
                raise HTTPException(503, f"Account {account_id} temporarily unavailable")
            return account

        # 智能选择可用账户（优先健康账户，提升响应速度）
        available_accounts = []
        for acc_id in self.account_list:
            account = self.accounts[acc_id]
            # 检查账户是否可用（会自动恢复429冷却期后的账户）
            if (account.should_retry() and
                not account.config.is_expired() and
                not account.config.disabled):
                # 计算账户健康度（error_count越低越健康）
                health_score = -account.error_count  # 负数，越大越健康
                available_accounts.append((acc_id, health_score))

        if not available_accounts:
            raise HTTPException(503, "No available accounts")

        # 按健康度排序（优先选择error_count最低的账户）
        available_accounts.sort(key=lambda x: x[1], reverse=True)

        # 只在更新索引时加锁（最小化锁持有时间）
        async with self._index_lock:
            if not hasattr(self, '_available_index'):
                self._available_index = 0

            # 在健康账户中轮询（只在前50%健康账户中选择）
            healthy_count = max(1, len(available_accounts) // 2)
            healthy_accounts = [acc_id for acc_id, _ in available_accounts[:healthy_count]]

            account_id = healthy_accounts[self._available_index % len(healthy_accounts)]
            self._available_index = (self._available_index + 1) % len(healthy_accounts)

        account = self.accounts[account_id]
        logger.info(f"[MULTI] [ACCOUNT] {req_tag}选择账户: {account_id} (健康度: {account.error_count}错误)")
        return account


# ---------- 配置文件管理 ----------

def _save_to_file(accounts_data: list):
    """保存账户配置到本地文件"""
    os.makedirs(os.path.dirname(ACCOUNTS_FILE) or ".", exist_ok=True)
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts_data, f, ensure_ascii=False, indent=2)
    logger.info(f"[CONFIG] 配置已保存到 {ACCOUNTS_FILE}")


def _load_from_file() -> list:
    """从本地文件加载账户配置"""
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[CONFIG] 文件加载失败: {str(e)}")
    return None


def save_accounts_to_file(accounts_data: list):
    """保存账户配置（优先数据库，降级到文件）"""
    if storage.is_database_enabled():
        try:
            saved = storage.save_accounts_sync(accounts_data)
            if saved:
                return
        except Exception as e:
            logger.warning(f"[CONFIG] 数据库保存失败: {e}，降级到文件存储")

    _save_to_file(accounts_data)


def load_accounts_from_source() -> list:
    """从环境变量、数据库或文件加载账户配置"""
    # 1. 优先从环境变量加载
    env_accounts = os.environ.get('ACCOUNTS_CONFIG')
    if env_accounts:
        try:
            accounts_data = json.loads(env_accounts)
            if accounts_data:
                logger.info(f"[CONFIG] 从环境变量加载配置，共 {len(accounts_data)} 个账户")
            else:
                logger.warning(f"[CONFIG] 环境变量 ACCOUNTS_CONFIG 为空")
            return accounts_data
        except Exception as e:
            logger.error(f"[CONFIG] 环境变量加载失败: {str(e)}")

    # 2. 尝试从数据库加载
    if storage.is_database_enabled():
        try:
            accounts_data = storage.load_accounts_sync()
            if accounts_data is not None:
                if accounts_data:
                    logger.info(f"[CONFIG] 从数据库加载配置，共 {len(accounts_data)} 个账户")
                else:
                    logger.warning(f"[CONFIG] 数据库中账户配置为空")
                return accounts_data
        except Exception as e:
            logger.warning(f"[CONFIG] 数据库加载失败: {e}，降级到文件存储")

    # 3. 从文件加载
    accounts_data = _load_from_file()
    if accounts_data is not None:
        if accounts_data:
            logger.info(f"[CONFIG] 从文件加载配置: {ACCOUNTS_FILE}，共 {len(accounts_data)} 个账户")
        else:
            logger.warning(f"[CONFIG] 账户配置为空，请在管理面板添加账户或编辑 {ACCOUNTS_FILE}")
        return accounts_data

    # 4. 无配置，创建空配置
    logger.warning(f"[CONFIG] 未找到配置，已创建空配置")
    logger.info(f"[CONFIG] 💡 请在管理面板添加账户，或设置 DATABASE_URL 使用数据库存储")
    save_accounts_to_file([])
    return []


def get_account_id(acc: dict, index: int) -> str:
    """获取账户ID（有显式ID则使用，否则生成默认ID）"""
    return acc.get("id", f"account_{index}")


def load_multi_account_config(
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """从文件或环境变量加载多账户配置"""
    manager = MultiAccountManager(session_cache_ttl_seconds)

    accounts_data = load_accounts_from_source()

    for i, acc in enumerate(accounts_data, 1):
        # 验证必需字段
        required_fields = ["secure_c_ses", "csesidx", "config_id"]
        missing_fields = [f for f in required_fields if f not in acc]
        if missing_fields:
            raise ValueError(f"账户 {i} 缺少必需字段: {', '.join(missing_fields)}")

        config = AccountConfig(
            account_id=get_account_id(acc, i),
            secure_c_ses=acc["secure_c_ses"],
            host_c_oses=acc.get("host_c_oses"),
            csesidx=acc["csesidx"],
            config_id=acc["config_id"],
            expires_at=acc.get("expires_at"),
            disabled=acc.get("disabled", False)  # 读取手动禁用状态，默认为 False
        )

        # 检查账户是否已过期（已过期也加载到管理面板）
        is_expired = config.is_expired()
        if is_expired:
            logger.warning(f"[CONFIG] 账户 {config.account_id} 已过期，仍加载用于展示")

        manager.add_account(config, http_client, user_agent, account_failure_threshold, rate_limit_cooldown_seconds, global_stats)
        if is_expired:
            manager.accounts[config.account_id].is_available = False

    if not manager.accounts:
        logger.warning(f"[CONFIG] 没有有效的账户配置，服务将启动但无法处理请求，请在管理面板添加账户")
    else:
        logger.info(f"[CONFIG] 成功加载 {len(manager.accounts)} 个账户")
    return manager


def reload_accounts(
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """重新加载账户配置（保留现有账户的运行时状态）"""
    # 保存现有账户的运行时状态
    old_states = {}
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        old_states[account_id] = {
            "is_available": account_mgr.is_available,
            "last_error_time": account_mgr.last_error_time,
            "last_429_time": account_mgr.last_429_time,
            "error_count": account_mgr.error_count,
            "conversation_count": account_mgr.conversation_count
        }

    # 清空会话缓存并重新加载配置
    multi_account_mgr.global_session_cache.clear()
    new_mgr = load_multi_account_config(
        http_client,
        user_agent,
        account_failure_threshold,
        rate_limit_cooldown_seconds,
        session_cache_ttl_seconds,
        global_stats
    )

    # 恢复现有账户的运行时状态
    for account_id, state in old_states.items():
        if account_id in new_mgr.accounts:
            account_mgr = new_mgr.accounts[account_id]
            account_mgr.is_available = state["is_available"]
            account_mgr.last_error_time = state["last_error_time"]
            account_mgr.last_429_time = state["last_429_time"]
            account_mgr.error_count = state["error_count"]
            account_mgr.conversation_count = state["conversation_count"]
            logger.debug(f"[CONFIG] 账户 {account_id} 运行时状态已恢复")

    logger.info(f"[CONFIG] 配置已重载，当前账户数: {len(new_mgr.accounts)}")
    return new_mgr


def update_accounts_config(
    accounts_data: list,
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """更新账户配置（保存到文件并重新加载）"""
    save_accounts_to_file(accounts_data)
    return reload_accounts(
        multi_account_mgr,
        http_client,
        user_agent,
        account_failure_threshold,
        rate_limit_cooldown_seconds,
        session_cache_ttl_seconds,
        global_stats
    )


def delete_account(
    account_id: str,
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """删除单个账户"""
    accounts_data = load_accounts_from_source()

    # 过滤掉要删除的账户
    filtered = [
        acc for i, acc in enumerate(accounts_data, 1)
        if get_account_id(acc, i) != account_id
    ]

    if len(filtered) == len(accounts_data):
        raise ValueError(f"账户 {account_id} 不存在")

    save_accounts_to_file(filtered)
    return reload_accounts(
        multi_account_mgr,
        http_client,
        user_agent,
        account_failure_threshold,
        rate_limit_cooldown_seconds,
        session_cache_ttl_seconds,
        global_stats
    )


def update_account_disabled_status(
    account_id: str,
    disabled: bool,
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """更新账户的禁用状态"""
    accounts_data = load_accounts_from_source()

    # 查找并更新账户
    found = False
    for i, acc in enumerate(accounts_data, 1):
        if get_account_id(acc, i) == account_id:
            acc["disabled"] = disabled
            found = True
            break

    if not found:
        raise ValueError(f"账户 {account_id} 不存在")

    save_accounts_to_file(accounts_data)
    new_mgr = reload_accounts(
        multi_account_mgr,
        http_client,
        user_agent,
        account_failure_threshold,
        rate_limit_cooldown_seconds,
        session_cache_ttl_seconds,
        global_stats
    )

    status_text = "已禁用" if disabled else "已启用"
    logger.info(f"[CONFIG] 账户 {account_id} {status_text}")
    return new_mgr
