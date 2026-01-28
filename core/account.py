"""账户管理模块

负责账户配置、多账户协调和会话缓存管理
"""
import asyncio
import json
import logging
import os
import random
import threading
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

# HTTP错误名称映射
HTTP_ERROR_NAMES = {
    400: "参数错误",
    401: "认证错误",
    403: "权限错误",
    429: "限流"
}

# 配额类型定义
QUOTA_TYPES = {
    "text": "对话",
    "images": "绘图",
    "videos": "视频"
}

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
    mail_provider: Optional[str] = None
    mail_address: Optional[str] = None
    mail_password: Optional[str] = None
    mail_client_id: Optional[str] = None
    mail_refresh_token: Optional[str] = None
    mail_tenant: Optional[str] = None
    # 邮箱自定义配置字段（用于账户级别的邮箱服务配置）
    mail_base_url: Optional[str] = None
    mail_jwt_token: Optional[str] = None
    mail_verify_ssl: Optional[bool] = None
    mail_domain: Optional[str] = None
    mail_api_key: Optional[str] = None

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
        self.last_cooldown_time = 0.0  # 冷却时间戳（401/403/429错误）
        self.quota_cooldowns: Dict[str, float] = {}  # 按配额类型的冷却时间戳 {"text": timestamp, "images": timestamp, "videos": timestamp}
        self.error_count = 0
        self.conversation_count = 0  # 累计对话次数（用于统计展示）
        self.session_usage_count = 0  # 本次启动后使用次数（用于均衡轮询）

    def handle_non_http_error(self, error_context: str = "", request_id: str = "") -> None:
        """
        统一处理非HTTP错误（网络错误、解析错误等）

        Args:
            error_context: 错误上下文（如"JWT获取"、"聊天请求"）
            request_id: 请求ID（用于日志）
        """
        req_tag = f"[req_{request_id}] " if request_id else ""
        self.last_error_time = time.time()
        self.error_count += 1
        if self.error_count >= self.account_failure_threshold:
            self.is_available = False
            logger.error(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"{error_context}连续失败{self.error_count}次，账户已永久禁用"
            )
        else:
            logger.warning(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"{error_context}失败({self.error_count}/{self.account_failure_threshold})"
            )

    def handle_http_error(self, status_code: int, error_detail: str = "", request_id: str = "", quota_type: Optional[str] = None) -> None:
        """
        统一处理HTTP错误（参考 business-gemini-2api-main 的 raise_for_account_response）

        Args:
            status_code: HTTP状态码
            error_detail: 错误详情
            request_id: 请求ID（用于日志）
            quota_type: 配额类型（"text", "images", "videos"），用于429错误按类型冷却

        处理逻辑：
            - 400: 参数错误，不计入失败（客户端问题）
            - 429 + quota_type: 按配额类型冷却（对话/绘图/视频独立冷却）
            - 429 无quota_type: 全局冷却（整个账户不可用）
            - 401/403: 全局冷却（认证错误）
            - 其他HTTP错误: 计入error_count，达到阈值后永久禁用
        """
        req_tag = f"[req_{request_id}] " if request_id else ""

        # 400参数错误：不计入失败（客户端问题）
        if status_code == 400:
            logger.warning(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"HTTP 400参数错误（不计入失败次数）{': ' + error_detail[:100] if error_detail else ''}"
            )
            return

        # 429限流错误：按配额类型冷却或全局冷却
        if status_code == 429:
            if quota_type and quota_type in QUOTA_TYPES:
                # 按配额类型冷却（不影响账户整体可用性）
                self.quota_cooldowns[quota_type] = time.time()
                logger.warning(
                    f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                    f"{QUOTA_TYPES[quota_type]}配额限流，将在{self.rate_limit_cooldown_seconds}秒后自动恢复"
                    f"{': ' + error_detail[:100] if error_detail else ''}"
                )
            else:
                # 全局冷却（未指定配额类型）
                self.last_cooldown_time = time.time()
                self.is_available = False
                logger.warning(
                    f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                    f"遇到429限流，账户将休息{self.rate_limit_cooldown_seconds}秒后自动恢复"
                    f"{': ' + error_detail[:100] if error_detail else ''}"
                )
            return

        # 401/403认证错误：全局冷却
        if status_code in (401, 403):
            self.last_cooldown_time = time.time()
            self.is_available = False
            error_type = HTTP_ERROR_NAMES.get(status_code, "HTTP错误")
            logger.warning(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"遇到{status_code}{error_type}，账户将休息{self.rate_limit_cooldown_seconds}秒后自动恢复"
                f"{': ' + error_detail[:100] if error_detail else ''}"
            )
            return

        # 其他HTTP错误：计入error_count
        self.last_error_time = time.time()
        self.error_count += 1
        if self.error_count >= self.account_failure_threshold:
            self.is_available = False
            logger.error(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"HTTP {status_code}错误连续失败{self.error_count}次，账户已永久禁用"
                f"{': ' + error_detail[:100] if error_detail else ''}"
            )
        else:
            logger.warning(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"HTTP {status_code}错误({self.error_count}/{self.account_failure_threshold})"
                f"{': ' + error_detail[:100] if error_detail else ''}"
            )

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
            # 使用统一的错误处理入口
            if isinstance(e, HTTPException):
                self.handle_http_error(e.status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id)
            else:
                self.handle_non_http_error("JWT获取", request_id)
            raise

    def should_retry(self) -> bool:
        """检查账户是否可重试（冷却期后自动恢复，普通错误永久禁用）"""
        if self.is_available:
            return True

        current_time = time.time()

        # 检查冷却期（401/403/429错误冷却期后自动恢复）
        if self.last_cooldown_time > 0:
            if current_time - self.last_cooldown_time > self.rate_limit_cooldown_seconds:
                # 冷却期已过，自动恢复账户可用性
                self.is_available = True
                self.last_cooldown_time = 0.0
                logger.info(f"[ACCOUNT] [{self.config.account_id}] 冷却期已过，账户已自动恢复")
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

        # 优先检查冷却期（无论账户是否可用）
        if self.last_cooldown_time > 0:
            remaining = self.rate_limit_cooldown_seconds - (current_time - self.last_cooldown_time)
            if remaining > 0:
                return (int(remaining), "限流冷却")
            # 冷却期已过

        # 如果账户可用且没有冷却，返回正常状态
        if self.is_available:
            return (0, None)

        # 普通错误永久禁用
        return (-1, "错误禁用")

    def get_quota_status(self) -> Dict[str, any]:
        """
        获取配额状态（被动检测模式）

        Returns:
            {
                "quotas": {
                    "text": {"available": bool, "remaining_seconds": int},
                    "images": {"available": bool, "remaining_seconds": int},
                    "videos": {"available": bool, "remaining_seconds": int}
                },
                "limited_count": int,  # 受限配额数量
                "total_count": int,    # 总配额数量
                "is_expired": bool     # 账户是否过期/禁用
            }
        """
        # 检查账户是否过期或被禁用
        is_expired = self.config.is_expired() or self.config.disabled
        if is_expired:
            # 账户过期或被禁用，所有配额不可用
            quotas = {quota_type: {"available": False} for quota_type in QUOTA_TYPES}
            return {
                "quotas": quotas,
                "limited_count": len(QUOTA_TYPES),
                "total_count": len(QUOTA_TYPES),
                "is_expired": True
            }

        current_time = time.time()

        quotas = {}
        limited_count = 0
        expired_quotas = []  # 收集已过期的配额类型

        for quota_type in QUOTA_TYPES:
            if quota_type in self.quota_cooldowns:
                cooldown_time = self.quota_cooldowns[quota_type]
                # 检查冷却时间是否已过（使用统一的 rate_limit_cooldown_seconds）
                elapsed = current_time - cooldown_time
                if elapsed < self.rate_limit_cooldown_seconds:
                    remaining = int(self.rate_limit_cooldown_seconds - elapsed)
                    quotas[quota_type] = {
                        "available": False,
                        "remaining_seconds": remaining
                    }
                    limited_count += 1
                else:
                    # 冷却时间已过，标记为待删除
                    expired_quotas.append(quota_type)
                    quotas[quota_type] = {"available": True}
            else:
                # 未检测到限流
                quotas[quota_type] = {"available": True}

        # 统一删除已过期的配额冷却
        for quota_type in expired_quotas:
            del self.quota_cooldowns[quota_type]

        return {
            "quotas": quotas,
            "limited_count": limited_count,
            "total_count": len(QUOTA_TYPES),
            "is_expired": False
        }


class MultiAccountManager:
    """多账户协调器"""
    def __init__(self, session_cache_ttl_seconds: int):
        self.accounts: Dict[str, AccountManager] = {}
        self.account_list: List[str] = []  # 账户ID列表 (用于轮询)
        self.current_index = 0
        self._cache_lock = asyncio.Lock()  # 缓存操作专用锁
        self._counter_lock = threading.Lock()  # 轮询计数器锁
        self._request_counter = 0  # 请求计数器
        self._last_account_count = 0  # 可用账户数量
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
        """获取账户 - Round-Robin轮询"""
        req_tag = f"[req_{request_id}] " if request_id else ""

        # 指定账户ID时直接返回
        if account_id:
            if account_id not in self.accounts:
                raise HTTPException(404, f"Account {account_id} not found")
            account = self.accounts[account_id]
            if not account.should_retry():
                raise HTTPException(503, f"Account {account_id} temporarily unavailable")
            return account

        # 筛选可用账户
        available_accounts = [
            acc for acc in self.accounts.values()
            if (acc.should_retry() and
                not acc.config.is_expired() and
                not acc.config.disabled)
        ]

        if not available_accounts:
            raise HTTPException(503, "No available accounts")

        # 轮询选择
        with self._counter_lock:
            if len(available_accounts) != self._last_account_count:
                self._request_counter = random.randint(0, 999999)
                self._last_account_count = len(available_accounts)
            index = self._request_counter % len(available_accounts)
            self._request_counter += 1

        selected = available_accounts[index]
        selected.session_usage_count += 1

        logger.info(f"[MULTI] [ACCOUNT] {req_tag}选择账户: {selected.config.account_id} "
                    f"(索引: {index}/{len(available_accounts)}, 使用: {selected.session_usage_count})")
        return selected


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

    # 4. 无配置处理
    if storage.is_database_enabled():
        # 数据库模式：不自动创建空配置，避免覆盖数据库
        logger.error(f"[CONFIG] 数据库模式下未找到配置，请检查数据库连接或在管理面板添加账户")
        logger.error(f"[CONFIG] ⚠️ 为防止数据覆盖，不会自动创建空配置")
        return []
    else:
        # 文件模式：创建空配置文件
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
            disabled=acc.get("disabled", False),  # 读取手动禁用状态，默认为False
            mail_provider=acc.get("mail_provider"),
            mail_address=acc.get("mail_address"),
            mail_password=acc.get("mail_password") or acc.get("email_password"),
            mail_client_id=acc.get("mail_client_id"),
            mail_refresh_token=acc.get("mail_refresh_token"),
            mail_tenant=acc.get("mail_tenant"),
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
    """重新加载账户配置（重置所有错误状态，仅保留统计数据）"""
    # 仅保存统计数据（conversation_count）
    old_stats = {}
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        old_stats[account_id] = {
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

    # 仅恢复统计数据，错误状态全部重置
    for account_id, stats in old_stats.items():
        if account_id in new_mgr.accounts:
            account_mgr = new_mgr.accounts[account_id]
            account_mgr.conversation_count = stats["conversation_count"]
            # 确保错误状态已重置（虽然load_multi_account_config已经初始化，但显式确认）
            account_mgr.is_available = True
            account_mgr.last_error_time = 0.0
            account_mgr.last_cooldown_time = 0.0
            account_mgr.error_count = 0
            account_mgr.session_usage_count = 0
            logger.debug(f"[CONFIG] 账户 {account_id} 已刷新，错误状态已重置")

    logger.info(f"[CONFIG] 配置已重载，当前账户数: {len(new_mgr.accounts)}，所有错误状态已重置")
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
    """更新账户的禁用状态（优化版：直接修改内存）"""
    # 直接修改内存中的账户状态
    if account_id not in multi_account_mgr.accounts:
        raise ValueError(f"账户 {account_id} 不存在")

    account_mgr = multi_account_mgr.accounts[account_id]
    account_mgr.config.disabled = disabled

    # 保存到文件
    accounts_data = load_accounts_from_source()
    for i, acc in enumerate(accounts_data, 1):
        if get_account_id(acc, i) == account_id:
            acc["disabled"] = disabled
            break

    save_accounts_to_file(accounts_data)

    status_text = "已禁用" if disabled else "已启用"
    logger.info(f"[CONFIG] 账户 {account_id} {status_text}")
    return multi_account_mgr


def bulk_update_account_disabled_status(
    account_ids: list[str],
    disabled: bool,
    multi_account_mgr: MultiAccountManager,
) -> tuple[int, list[str]]:
    """批量更新账户禁用状态，单次最多50个，仅读写一次文件"""
    success_count = 0
    errors = []

    # 1. 更新内存状态
    for account_id in account_ids:
        if account_id not in multi_account_mgr.accounts:
            errors.append(f"{account_id}: 账户不存在")
            continue
        account_mgr = multi_account_mgr.accounts[account_id]
        account_mgr.config.disabled = disabled
        success_count += 1

    # 2. 只读取一次文件
    accounts_data = load_accounts_from_source()
    account_id_set = set(account_ids)

    # 3. 批量更新
    for i, acc in enumerate(accounts_data, 1):
        acc_id = get_account_id(acc, i)
        if acc_id in account_id_set:
            acc["disabled"] = disabled

    # 4. 只保存一次
    save_accounts_to_file(accounts_data)

    status_text = "已禁用" if disabled else "已启用"
    logger.info(f"[CONFIG] 批量{status_text} {success_count}/{len(account_ids)} 个账户")
    return success_count, errors


def bulk_delete_accounts(
    account_ids: list[str],
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    account_failure_threshold: int,
    rate_limit_cooldown_seconds: int,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> tuple[MultiAccountManager, int, list[str]]:
    """批量删除账户，单次最多50个，仅读写一次文件"""
    errors = []
    account_id_set = set(account_ids)

    accounts_data = load_accounts_from_source()
    kept: list[dict] = []
    deleted_ids: list[str] = []

    for i, acc in enumerate(accounts_data, 1):
        acc_id = get_account_id(acc, i)
        if acc_id in account_id_set:
            deleted_ids.append(acc_id)
            continue
        kept.append(acc)

    missing = account_id_set.difference(deleted_ids)
    for account_id in missing:
        errors.append(f"{account_id}: 账户不存在")

    if deleted_ids:
        save_accounts_to_file(kept)
        multi_account_mgr = reload_accounts(
            multi_account_mgr,
            http_client,
            user_agent,
            account_failure_threshold,
            rate_limit_cooldown_seconds,
            session_cache_ttl_seconds,
            global_stats
        )

    success_count = len(deleted_ids)
    logger.info(f"[CONFIG] 批量删除 {success_count}/{len(account_ids)} 个账户")
    return multi_account_mgr, success_count, errors
