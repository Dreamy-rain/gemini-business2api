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
from typing import Any, Awaitable, Callable, Deque, Dict, Generic, List, Optional, TypeVar
from collections import deque

from core.account import update_accounts_config

logger = logging.getLogger("gemini.base_task")


class TaskCancelledError(Exception):
    """用于在线程/回调中快速中断任务执行。"""


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    cancel_requested: bool = False
    cancel_reason: Optional[str] = None

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
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
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
        self._pending_task_ids: Deque[str] = deque()
        self._worker_task: Optional[asyncio.Task] = None
        self._current_asyncio_task: Optional[asyncio.Task] = None
        self._cancel_hooks: Dict[str, List[Callable[[], None]]] = {}
        self._cancel_hooks_lock = threading.Lock()

        self.multi_account_mgr = multi_account_mgr
        self.http_client = http_client
        self.user_agent = user_agent
        self.account_failure_threshold = account_failure_threshold
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.session_cache_ttl_seconds = session_cache_ttl_seconds
        self.global_stats_provider = global_stats_provider
        self.set_multi_account_mgr = set_multi_account_mgr
        
        self._max_completed_tasks = 10  # 最大保留10个已完成的任务历史，减小内存占用

    def get_task(self, task_id: str) -> Optional[T]:
        """获取指定任务"""
        return self._tasks.get(task_id)

    def get_current_task(self) -> Optional[T]:
        """获取当前任务"""
        if self._current_task_id:
            current = self._tasks.get(self._current_task_id)
            if current:
                return current
        # 若当前无运行任务，返回队列中最早的 pending 任务（用于前端显示“等待中”）
        for task_id in list(self._pending_task_ids):
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                return task
        return None

    def get_pending_task_ids(self) -> List[str]:
        """返回待执行任务ID列表（调试/展示用）。"""
        return list(self._pending_task_ids)

    async def cancel_task(self, task_id: str, reason: str = "cancelled") -> Optional[T]:
        """请求取消任务（支持 pending/running）。"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            if task.status == TaskStatus.PENDING:
                # 从队列移除并直接标记取消
                try:
                    self._pending_task_ids.remove(task_id)
                except ValueError:
                    pass
                task.cancel_requested = True
                task.cancel_reason = reason
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                self._append_log(task, "warning", f"task cancelled while pending: {reason}")
                self._cleanup_finished_tasks()
                return task

            if task.status == TaskStatus.RUNNING:
                task.cancel_requested = True
                task.cancel_reason = reason
                self._append_log(task, "warning", f"cancel requested: {reason}")
                # 尝试立即触发取消回调（例如关闭浏览器）
                self._fire_cancel_hooks(task_id)
                # 尝试取消当前 await（例如 run_in_executor 等待点）
                if self._current_asyncio_task and not self._current_asyncio_task.done():
                    self._current_asyncio_task.cancel()
                return task

            return task

    async def _enqueue_task(self, task: T) -> None:
        """将任务加入队列并启动 worker。"""
        self._pending_task_ids.append(task.id)
        if not self._worker_task or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_worker())

    async def _run_worker(self) -> None:
        """串行执行队列任务（单线程 executor + 单 worker）。"""
        while True:
            async with self._lock:
                next_task: Optional[T] = None
                # 清理不存在/非pending的ID
                while self._pending_task_ids:
                    task_id = self._pending_task_ids[0]
                    task = self._tasks.get(task_id)
                    if not task or task.status != TaskStatus.PENDING:
                        self._pending_task_ids.popleft()
                        continue
                    next_task = task
                    self._pending_task_ids.popleft()
                    self._current_task_id = task.id
                    break

            if not next_task:
                break

            await self._run_one_task(next_task)

            async with self._lock:
                if self._current_task_id == next_task.id:
                    self._current_task_id = None

    async def _run_one_task(self, task: T) -> None:
        """执行单个任务，处理取消/异常/收尾。"""
        if task.status != TaskStatus.PENDING:
            return
        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            return

        task.status = TaskStatus.RUNNING
        self._append_log(task, "info", "task started")
        try:
            coro = self._execute_task(task)
            self._current_asyncio_task = asyncio.create_task(coro)
            await self._current_asyncio_task
        except asyncio.CancelledError:
            # 外部请求取消（或关闭时）会触发
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            self._append_log(task, "warning", f"task cancelled: {task.cancel_reason or 'cancelled'}")
        except TaskCancelledError:
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            self._append_log(task, "warning", f"task cancelled: {task.cancel_reason or 'cancelled'}")
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.finished_at = time.time()
            self._append_log(task, "error", f"task error: {type(exc).__name__}: {str(exc)[:200]}")
        finally:
            self._current_asyncio_task = None
            self._clear_cancel_hooks(task.id)
            # 任务执行结束，清理过旧的历史记录
            self._cleanup_finished_tasks()
            # 强制触发系统级物理内存回收
            asyncio.create_task(self._force_memory_release())

    def _add_cancel_hook(self, task_id: str, hook: Callable[[], None]) -> None:
        """注册取消回调（线程安全）。"""
        with self._cancel_hooks_lock:
            self._cancel_hooks.setdefault(task_id, []).append(hook)

    def _fire_cancel_hooks(self, task_id: str) -> None:
        """触发取消回调（尽力而为）。"""
        with self._cancel_hooks_lock:
            hooks = list(self._cancel_hooks.get(task_id) or [])
        for hook in hooks:
            try:
                hook()
            except Exception as exc:
                logger.warning("[%s] cancel hook error: %s", self._log_prefix, str(exc)[:120])

    def _clear_cancel_hooks(self, task_id: str) -> None:
        with self._cancel_hooks_lock:
            self._cancel_hooks.pop(task_id, None)

    # --- 子类需要实现 ---
    def _execute_task(self, task: T) -> Awaitable[None]:
        """子类实现：执行任务主体（需自行更新 progress/success/fail/finished_at 等）。"""
        raise NotImplementedError

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

        # 协作式取消：一旦请求取消，阻断后续通过 log_callback 的执行路径
        # 允许“取消请求/取消完成”相关日志正常写入
        if task.cancel_requested:
            safe_messages = (
                "cancel requested:",
                "task cancelled",
                "task cancelled while pending",
                "login task cancelled:",
                "register task cancelled:",
            )
            if not any(message.startswith(x) for x in safe_messages):
                raise TaskCancelledError(task.cancel_reason or "cancelled")

    def _apply_accounts_update(self, accounts_data: list) -> None:
        """
        应用账户更新

        Args:
            accounts_data: 账户数据列表
        """
        global_stats = self.global_stats_provider() or {}
        old_mgr = self.multi_account_mgr
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
        
        # 关闭旧管理器的后台任务
        if old_mgr:
            asyncio.create_task(old_mgr.aclose())
        # 为新配置启动后台清理任务
        asyncio.create_task(new_mgr.start_background_cleanup())

        if self.set_multi_account_mgr:
            self.set_multi_account_mgr(new_mgr)

    def _cleanup_finished_tasks(self) -> None:
        """清理已完成的任务历史（保留最近的 10 个）"""
        finished_tasks = [
            t_id for t_id, t in self._tasks.items() 
            if t.status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]
        
        if len(finished_tasks) > self._max_completed_tasks:
            # 按完成时间排序
            finished_tasks.sort(key=lambda tid: self._tasks[tid].finished_at or 0)
            # 移除最旧的
            to_remove = len(finished_tasks) - self._max_completed_tasks
            for tid in finished_tasks[:to_remove]:
                self._tasks.pop(tid, None)
                self._clear_cancel_hooks(tid)
            logger.info("[%s] 已清理 %d 个过期任务历史 (当前存余: %d)", 
                        self._log_prefix, to_remove, len(self._tasks))

    async def _force_memory_release(self) -> None:
        """任务结束后触发常规垃圾回收，清理多余的对象占用"""
        await asyncio.sleep(2)  # 等待其他异步收尾和子进程完全退出
        try:
            import gc
            
            # 第一重：强制收集所有分代的 Python 孤立对象
            gc.collect()
            
            # 记录清理情况
            logger.info("[%s] 任务历史缩减及常规 GC 垃圾回收已完成", self._log_prefix)
                    
        except Exception as e:
            logger.debug("[%s] 常规内存回收异常: %s", self._log_prefix, e)
