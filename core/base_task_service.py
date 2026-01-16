"""
基础任务服务类
提供通用的任务管理、日志记录和账户更新功能
"""
import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from core.account import update_accounts_config

logger = logging.getLogger("gemini.base_task")


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BaseTask:
    """基础任务数据类"""
    id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    logs: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "results": self.results,
            "error": self.error,
            "logs": self.logs,
        }


T = TypeVar('T', bound=BaseTask)


class BaseTaskService(Generic[T]):
    """
    基础任务服务类
    提供通用的任务管理、日志记录和账户更新功能
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
        set_multi_account_mgr: Optional[Callable[[Any], None]] = None,
        log_prefix: str = "TASK",
    ) -> None:
        """
        初始化基础任务服务

        Args:
            multi_account_mgr: 多账户管理器
            http_client: HTTP客户端
            user_agent: 用户代理
            account_failure_threshold: 账户失败阈值
            rate_limit_cooldown_seconds: 速率限制冷却秒数
            session_cache_ttl_seconds: 会话缓存TTL秒数
            global_stats_provider: 全局统计提供者
            set_multi_account_mgr: 设置多账户管理器的回调
            log_prefix: 日志前缀
        """
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._tasks: Dict[str, T] = {}
        self._current_task_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._log_lock = threading.Lock()
        self._log_prefix = log_prefix

        self.multi_account_mgr = multi_account_mgr
        self.http_client = http_client
        self.user_agent = user_agent
        self.account_failure_threshold = account_failure_threshold
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.session_cache_ttl_seconds = session_cache_ttl_seconds
        self.global_stats_provider = global_stats_provider
        self.set_multi_account_mgr = set_multi_account_mgr

    def get_task(self, task_id: str) -> Optional[T]:
        """获取指定任务"""
        return self._tasks.get(task_id)

    def get_current_task(self) -> Optional[T]:
        """获取当前任务"""
        if not self._current_task_id:
            return None
        return self._tasks.get(self._current_task_id)

    def _append_log(self, task: T, level: str, message: str) -> None:
        """
        添加日志到任务

        Args:
            task: 任务对象
            level: 日志级别 (info, warning, error)
            message: 日志消息
        """
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "level": level,
            "message": message,
        }
        with self._log_lock:
            task.logs.append(entry)
            if len(task.logs) > 200:
                task.logs = task.logs[-200:]

        log_message = f"[{self._log_prefix}] {message}"
        if level == "warning":
            logger.warning(log_message)
        elif level == "error":
            logger.error(log_message)
        else:
            logger.info(log_message)

    def _apply_accounts_update(self, accounts_data: list) -> None:
        """
        应用账户更新

        Args:
            accounts_data: 账户数据列表
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
