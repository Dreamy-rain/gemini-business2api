"""账号池维护模块

负责自动维护账号池：
- 清理明显不可用的账号（过期/缺字段/运行时错误禁用）
- 在可用账号不足时触发自动注册补号
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from core.account import load_accounts_from_source, update_accounts_config
from core.base_task_service import TaskStatus
from core.config import config

logger = logging.getLogger("gemini.pool")


BEIJING_TZ = timezone(timedelta(hours=8))

# 账号池轮询间隔（程序内固定）：
# - 账号池未达标 / 注册进行中：快速轮询，便于首次启动快速补齐
# - 账号池已达标：慢速轮询，减少开销
POOL_POLL_FAST_SECONDS = 30
POOL_POLL_IDLE_SECONDS = 600


@dataclass
class PoolStatus:
    """账号池维护状态（用于管理端展示）"""
    running: bool = False
    last_run_at: float = 0.0
    last_result: Dict[str, object] = field(default_factory=dict)


def _beijing_now() -> datetime:
    """获取当前北京时间

    Returns:
        datetime: 带北京时区信息的当前时间
    """
    return datetime.now(BEIJING_TZ)


def _parse_expires_at(value: str) -> Optional[datetime]:
    """解析 expires_at 字段（北京时间字符串 -> datetime）

    Args:
        value: expires_at 字符串，格式为 "YYYY-MM-DD HH:MM:SS"

    Returns:
        解析成功返回带北京时区的 datetime，否则返回 None
    """
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=BEIJING_TZ)
    except Exception:
        return None


class PoolService:
    """账号池维护服务

    目标：保证可用账号数 >= pool_target_accounts。

    策略：
    - 清理明显不可用的账号（过期/缺字段/运行时错误禁用；可选删除 disabled=true）
    - 当账号池不足时，触发注册任务补齐缺口（注册任务本身有单次上限）
    """

    def __init__(
        self,
        multi_account_mgr,
        http_client,
        user_agent: str,
        account_failure_threshold: int,
        rate_limit_cooldown_seconds: int,
        session_cache_ttl_seconds: int,
        global_stats_provider: Callable[[], dict],
        set_multi_account_mgr: Optional[Callable[[object], None]] = None,
        register_service=None,
    ) -> None:
        self.multi_account_mgr = multi_account_mgr
        self.http_client = http_client
        self.user_agent = user_agent
        self.account_failure_threshold = account_failure_threshold
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.session_cache_ttl_seconds = session_cache_ttl_seconds
        self.global_stats_provider = global_stats_provider
        self.set_multi_account_mgr = set_multi_account_mgr
        self.register_service = register_service

        self._lock = asyncio.Lock()
        self._is_polling = False
        self._last_skip_reason: Optional[str] = None
        self.status = PoolStatus()

    def get_status(self) -> dict:
        """获取账号池维护状态

        Returns:
            dict: running/last_run_at/last_result
        """
        return {
            "running": bool(self.status.running),
            "last_run_at": self.status.last_run_at,
            "last_result": self.status.last_result or {},
        }

    def _apply_accounts_update(self, accounts_data: list) -> None:
        """落盘并重载账号配置（同时刷新运行时 AccountManager）

        Args:
            accounts_data: 账号配置列表（即将写入 accounts.json/数据库）
        """
        global_stats = self.global_stats_provider() or {}
        new_mgr = update_accounts_config(
            accounts_data,
            self.multi_account_mgr,
            self.http_client,
            self.user_agent,
            self.account_failure_threshold,
            self.rate_limit_cooldown_seconds,
            self.session_cache_ttl_seconds,
            global_stats,
        )
        self.multi_account_mgr = new_mgr
        if self.set_multi_account_mgr:
            self.set_multi_account_mgr(new_mgr)

    def _get_runtime_permanent_disabled(self) -> Dict[str, str]:
        """获取运行时永久禁用的账号：{account_id: reason}

        注意：AccountManager.get_cooldown_info() 对非 429 冷却且不可用的账号会返回 (-1, "错误禁用")。
        其中也可能包含“因过期导致不可用”的账号，所以 maintain_once() 里需要结合 expires_at 判断。

        Returns:
            Dict[str, str]: 账号 id 到禁用原因的映射
        """
        out: Dict[str, str] = {}
        try:
            for account_id, mgr in (self.multi_account_mgr.accounts or {}).items():
                cooldown_s, reason = mgr.get_cooldown_info()
                if cooldown_s == -1:
                    out[str(account_id)] = str(reason or "disabled")
        except Exception:
            # 尽力而为：运行时状态异常不应影响账号池维护。
            return out
        return out

    @staticmethod
    def _required_fields_ok(acc: dict) -> bool:
        """检查账号配置是否包含必需字段

        Args:
            acc: 账号配置 dict

        Returns:
            bool: 字段齐全且非空返回 True
        """
        # 与 core/account.py 的必需字段保持一致。
        return bool(acc.get("secure_c_ses")) and bool(acc.get("csesidx")) and bool(acc.get("config_id"))

    async def maintain_once(self) -> dict:
        """执行一次账号池维护

        Returns:
            dict: 本次维护的结果（删除数量、健康账号数、是否触发补号等）
        """
        async with self._lock:
            self.status.running = True
            self.status.last_run_at = time.time()
            try:
                # Step 1: 环境限制检查（通过环境变量注入账号时，不允许自动改写/删除/补号）
                if os.environ.get("ACCOUNTS_CONFIG"):
                    result = {"skipped": True, "reason": "ACCOUNTS_CONFIG is set"}
                    self.status.last_result = result
                    if self._last_skip_reason != "ACCOUNTS_CONFIG":
                        logger.info("[POOL] skipped: ACCOUNTS_CONFIG is set")
                        self._last_skip_reason = "ACCOUNTS_CONFIG"
                    return result

                # Step 2: 读取配置（target=0 表示禁用自动补号）
                target = int(getattr(config.basic, "pool_target_accounts", 0) or 0)
                if target <= 0:
                    result = {"skipped": True, "reason": "pool_target_accounts <= 0"}
                    self.status.last_result = result
                    if self._last_skip_reason != "TARGET_DISABLED":
                        logger.info("[POOL] skipped: pool_target_accounts<=0")
                        self._last_skip_reason = "TARGET_DISABLED"
                    return result

                prune_disabled = bool(getattr(config.basic, "pool_prune_disabled", False))

                # Step 3: 读取运行时状态（错误禁用）以及注册任务是否正在进行
                now = _beijing_now()
                runtime_disabled = self._get_runtime_permanent_disabled()

                register_running = False
                try:
                    if self.register_service:
                        current = self.register_service.get_current_task()
                        if current and getattr(current, "status", None) == TaskStatus.RUNNING:
                            register_running = True
                except Exception:
                    register_running = False

                # Step 4: 读取账号配置并进行清理/统计
                accounts = load_accounts_from_source()
                before_total = len(accounts)

                deleted: List[dict] = []
                kept: List[dict] = []

                healthy = 0
                for acc in accounts:
                    account_id = str(acc.get("id") or "")
                    disabled = bool(acc.get("disabled", False))
                    required_ok = self._required_fields_ok(acc)
                    exp_dt = _parse_expires_at(str(acc.get("expires_at") or ""))
                    runtime_perma_disabled = bool(account_id and account_id in runtime_disabled)
                    expired = bool(exp_dt and exp_dt <= now)

                    reasons: List[str] = []
                    should_delete = False

                    # 4.1 缺字段的账号无法用于 API 请求，直接删除
                    if not required_ok:
                        should_delete = True
                        reasons.append("missing_required_fields")

                    # 4.2 手动禁用账号是否删除由 pool_prune_disabled 控制
                    if prune_disabled and disabled:
                        should_delete = True
                        reasons.append("disabled")

                    # 过期账号立即删除（无宽限期）。
                    if expired:
                        should_delete = True
                        reasons.append("expired")

                    # 运行时永久禁用（非 429 冷却）通常表示账号已坏。
                    # 注意：过期也会导致运行时不可用；过期已在上面处理。
                    if runtime_perma_disabled and not expired:
                        should_delete = True
                        reasons.append("runtime_disabled")

                    if should_delete:
                        deleted.append({"id": account_id, "reasons": reasons})
                        continue

                    kept.append(acc)

                    # 统计当前“可用”的账号数量。
                    if disabled or not required_ok:
                        continue
                    if expired:
                        continue
                    if runtime_perma_disabled:
                        continue
                    healthy += 1

                # Step 5: 若有删除，先落盘并重载账号配置（同时重置运行时状态）
                if deleted:
                    try:
                        self._apply_accounts_update(kept)
                    except Exception as exc:
                        # 清理失败时不继续补号，避免状态不一致。
                        result = {
                            "skipped": False,
                            "error": f"prune failed: {type(exc).__name__}: {exc}",
                            "before_total": before_total,
                            "deleted": deleted,
                            "kept_total": len(kept),
                            "healthy": healthy,
                        }
                        self.status.last_result = result
                        logger.error("[POOL] prune failed: %s", exc)
                        return result

                # Step 6: 计算缺口并触发补号（注册服务自身会限制单次 count 上限）
                need = max(0, int(target) - int(healthy))
                to_register = int(need)

                started_register = False
                register_task_id: Optional[str] = None
                if to_register > 0 and not register_running:
                    if not self.register_service:
                        logger.warning("[POOL] need=%s but register service unavailable", to_register)
                    else:
                        try:
                            task = await self.register_service.start_register(count=to_register, domain=None)
                            started_register = True
                            register_task_id = task.id
                            logger.info("[POOL] started register task id=%s count=%s", register_task_id, to_register)
                        except Exception as exc:
                            logger.warning("[POOL] start_register failed: %s", exc)
                elif to_register > 0 and register_running:
                    logger.info("[POOL] register already running; need=%s", to_register)

                # Step 7: 汇总结果
                result = {
                    "skipped": False,
                    "target": target,
                    "before_total": before_total,
                    "deleted_count": len(deleted),
                    "deleted": deleted,
                    "kept_total": len(kept),
                    "healthy": healthy,
                    "need": need,
                    "register_running": register_running,
                    "register_started": started_register,
                    "register_task_id": register_task_id,
                }

                self.status.last_result = result
                self._last_skip_reason = None
                return result
            finally:
                self.status.running = False

    async def start_polling(self) -> None:
        """启动账号池维护轮询（后台任务）

        说明：
        - 首次启动会立即执行一次维护
        - 账号池不足/注册进行中时使用快速轮询，便于首次启动快速补齐
        - 账号池达标后使用慢速轮询，减少开销
        """
        if self._is_polling:
            logger.warning("[POOL] polling already running")
            return

        self._is_polling = True
        try:
            # Step 1: 启动后先立即执行一次，再按间隔轮询
            while self._is_polling:
                try:
                    # Step 2: 执行维护，并根据结果决定下一次轮询间隔
                    result = await self.maintain_once()
                    interval = POOL_POLL_IDLE_SECONDS
                    if not result.get("skipped"):
                        # 缺口存在或注册进行中时，快速轮询以便首次启动持续补齐。
                        if int(result.get("need") or 0) > 0 or bool(result.get("register_running")):
                            interval = POOL_POLL_FAST_SECONDS

                    # Step 3: 休眠等待下一轮
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("[POOL] polling error: %s", exc)
                    await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("[POOL] polling stopped")
        finally:
            self._is_polling = False

    def stop_polling(self) -> None:
        """停止账号池维护轮询"""
        self._is_polling = False
        logger.info("[POOL] stopping polling")
