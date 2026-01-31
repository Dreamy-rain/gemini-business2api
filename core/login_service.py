import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core import storage
from core.mail_providers import create_temp_mail_client
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC
from core.microsoft_mail_client import MicrosoftMailClient

logger = logging.getLogger("gemini.login")

# 常量定义
CONFIG_CHECK_INTERVAL_SECONDS = 60  # 配置检查间隔（秒）
# 高级自动刷新调度常量（仅在用户开启“高级自动刷新调度”时生效）
SCHEDULED_REFRESH_MIN_BATCH_SIZE = 5  # 单轮最小入队数量（不可配置，保证每轮有进展）
SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS = 60.0  # HRRN 默认服务时间（秒，历史为空时使用）
SCHEDULED_REFRESH_AVG_ALPHA = 0.2  # 平均耗时滑动系数（EMA），越大越重视最近一次
SCHEDULED_REFRESH_BACKOFF_BASE_SECONDS = 15 * 60  # 指数退避基准（15分钟）
SCHEDULED_REFRESH_BACKOFF_MAX_SECONDS = 12 * 60 * 60  # 指数退避上限（12小时）


@dataclass
class LoginTask(BaseTask):
    """登录任务数据类"""
    account_ids: List[str] = field(default_factory=list)
    trigger: str = "manual"  # 任务触发来源：manual=手动、scheduled=自动定时

    def to_dict(self) -> dict:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict["account_ids"] = self.account_ids
        base_dict["trigger"] = self.trigger
        return base_dict


class LoginService(BaseTaskService[LoginTask]):
    """登录服务类"""

    def __init__(
        self,
        multi_account_mgr,
        http_client,
        user_agent: str,
        retry_policy,
        session_cache_ttl_seconds: int,
        global_stats_provider: Callable[[], dict],
        set_multi_account_mgr: Optional[Callable[[Any], None]] = None,
    ) -> None:
        super().__init__(
            multi_account_mgr,
            http_client,
            user_agent,
            retry_policy,
            session_cache_ttl_seconds,
            global_stats_provider,
            set_multi_account_mgr,
            log_prefix="REFRESH",
        )
        self._is_polling = False
        # 记录上一次“定时调度器”决策时间，便于观测跳过原因与节奏
        self._last_scheduled_tick_at: Optional[float] = None
        self._last_scheduled_enqueue_at: Optional[float] = None

    async def start_login(self, account_ids: List[str], trigger: str = "manual") -> LoginTask:
        """
        启动登录/刷新任务（支持排队）。

        功能说明：
        - 支持两种触发来源：
          - manual：管理面板手动触发刷新（不受“高级调度开关”影响）
          - scheduled：后台定时轮询触发刷新（开启高级调度后会走公平/退避/防堆叠）
        - 去重：同一批账号的 pending/running 任务直接复用，避免重复入队。

        参数：
        - account_ids: 需要刷新登录的账号 ID 列表
        - trigger: 触发来源（manual/scheduled）

        返回值：
        - LoginTask: 创建或复用的任务对象
        """
        async with self._lock:
            return await self._start_login_locked(account_ids=account_ids, trigger=trigger)

    async def _start_login_locked(self, account_ids: List[str], trigger: str) -> LoginTask:
        """
        在已持有 self._lock 的前提下创建/复用任务（内部使用）。

        设计目的：
        - 将“判断 + 创建 + 入队”放到同一把锁内，便于高级调度器做到严格 skip-if-busy，
          避免 tick 到来时在并发窗口内重复入队。

        参数：
        - account_ids: 账号 ID 列表
        - trigger: 触发来源

        返回值：
        - LoginTask: 任务对象
        """
        # 去重：同一批账号的 pending/running 任务直接复用
        normalized = list(account_ids or [])
        for existing in self._tasks.values():
            if (
                isinstance(existing, LoginTask)
                and existing.account_ids == normalized
                and existing.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ):
                return existing

        task = LoginTask(id=str(uuid.uuid4()), account_ids=normalized, trigger=trigger)
        self._tasks[task.id] = task
        self._append_log(task, "info", f"📝 创建刷新任务 (账号数量: {len(task.account_ids)})")
        await self._enqueue_task(task)
        return task

    def _execute_task(self, task: LoginTask):
        return self._run_login_async(task)

    def _mask_account_id(self, account_id: str) -> str:
        """
        脱敏展示账号 ID（用于调度日志/面板日志）。

        参数：
        - account_id: 原始账号 ID

        返回值：
        - 脱敏后的字符串（保留后 6 位，其余用 * 遮盖）
        """
        raw = str(account_id or "")
        if len(raw) <= 6:
            return "*" * len(raw)
        return ("*" * (len(raw) - 6)) + raw[-6:]

    def _get_account_scheduled_refresh_state(self, account: dict) -> dict:
        """
        从账号配置中读取调度状态，保证返回为 dict。

        参数：
        - account: 单个账号配置 dict

        返回值：
        - 调度状态 dict（若不存在或类型异常则返回空 dict）
        """
        state = (account or {}).get("scheduled_refresh_state") or {}
        return state if isinstance(state, dict) else {}

    def _classify_refresh_failure(self, error_message: str) -> str:
        """
        对刷新失败进行粗粒度分类（用于观测与排查）。

        说明：
        - 当前系统失败原因主要来自自动化流程返回的 error 文本，缺少结构化错误码；
        - 这里基于关键字做简单归类，便于确认是否处于验证码/风控/超时等状态。

        参数：
        - error_message: 失败错误文本

        返回值：
        - 分类字符串（captcha_or_code / risk_or_rate_limit / timeout / element_not_found / network / other）
        """
        msg = str(error_message or "")
        lower = msg.lower()
        if any(k in msg for k in ("验证码", "校验码")) or any(k in lower for k in ("verification", "otp", "code")):
            return "captcha_or_code"
        if any(k in msg for k in ("风控", "限制", "封禁")) or any(k in lower for k in ("risk", "blocked", "rate limit", "429")):
            return "risk_or_rate_limit"
        if "超时" in msg or any(k in lower for k in ("timeout", "timed out")):
            return "timeout"
        if "元素" in msg or any(k in lower for k in ("element", "selector")):
            return "element_not_found"
        if "网络" in msg or any(k in lower for k in ("network", "connection", "dns")):
            return "network"
        return "other"

    def _compute_backoff_seconds(self, consecutive_failures: int) -> int:
        """
        计算指数退避时长（秒），用于失败账号的 next_eligible_at。

        策略：
        - 15m → 30m → 60m → 2h → 4h …（指数翻倍）
        - 最大上限 12h

        参数：
        - consecutive_failures: 连续失败次数（>=1）

        返回值：
        - 退避秒数（int）
        """
        n = max(int(consecutive_failures or 0), 1)
        backoff = SCHEDULED_REFRESH_BACKOFF_BASE_SECONDS * (2 ** (n - 1))
        return int(min(backoff, SCHEDULED_REFRESH_BACKOFF_MAX_SECONDS))

    def _update_scheduled_refresh_state_sync(
        self,
        account_id: str,
        success: bool,
        duration_seconds: float,
        error_message: str,
    ) -> dict:
        """
        同步更新账号调度状态（供 asyncio.to_thread 调用）。

        关键逻辑：
        - 成功：清零 consecutive_failures，清空 next_eligible_at，并记录 last_success_at
        - 失败：consecutive_failures + 1，并写入 next_eligible_at（指数退避）
        - 每次尝试都更新 last_attempt_at，并更新 avg_refresh_duration_seconds（EMA）

        参数：
        - account_id: 账号 ID
        - success: 本次是否成功
        - duration_seconds: 本次刷新耗时（秒）
        - error_message: 失败文本（成功时可为空）

        返回值：
        - 写入后的新状态 dict
        """
        now_ts = float(time.time())
        try:
            account_data = storage.load_account_data_sync(account_id) or {}
        except Exception:
            account_data = {}

        existing_state = self._get_account_scheduled_refresh_state(account_data)

        old_avg = existing_state.get("avg_refresh_duration_seconds", SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS)
        try:
            old_avg = float(old_avg)
        except Exception:
            old_avg = float(SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS)
        old_avg = max(old_avg, 1.0)

        # 更新平均耗时（EMA）
        new_avg = old_avg
        try:
            dur = float(duration_seconds)
            if dur > 0:
                new_avg = (old_avg * (1.0 - SCHEDULED_REFRESH_AVG_ALPHA)) + (dur * SCHEDULED_REFRESH_AVG_ALPHA)
        except Exception:
            pass

        if success:
            consecutive_failures = 0
            next_eligible_at = 0.0
            last_success_at = now_ts
        else:
            try:
                consecutive_failures = int(existing_state.get("consecutive_failures", 0)) + 1
            except Exception:
                consecutive_failures = 1
            next_eligible_at = now_ts + float(self._compute_backoff_seconds(consecutive_failures))
            try:
                last_success_at = float(existing_state.get("last_success_at", 0.0) or 0.0)
            except Exception:
                last_success_at = 0.0

        new_state = {
            "last_attempt_at": now_ts,
            "last_success_at": float(last_success_at),
            "avg_refresh_duration_seconds": float(round(new_avg, 3)),
            "consecutive_failures": int(consecutive_failures),
            "next_eligible_at": float(round(next_eligible_at, 3)),
            # 记录最近一次错误文本（便于排查；不参与调度计算）
            "last_error": str(error_message or "")[:500],
        }

        try:
            storage.update_account_scheduled_refresh_state_sync(account_id, new_state)
        except Exception as exc:
            logger.warning("[LOGIN][SCHED] update scheduled_refresh_state failed: %s", str(exc)[:200])

        return new_state

    async def _run_login_async(self, task: LoginTask) -> None:
        """异步执行登录任务（支持取消）。"""
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 刷新任务已启动 (共 {len(task.account_ids)} 个账号)")

        for idx, account_id in enumerate(task.account_ids, 1):
            # 检查是否请求取消
            if task.cancel_requested:
                self._append_log(task, "warning", f"login task cancelled: {task.cancel_reason or 'cancelled'}")
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return

            try:
                self._append_log(task, "info", f"📊 进度: {idx}/{len(task.account_ids)}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🔄 开始刷新账号: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                started_at = time.time()
                result = await loop.run_in_executor(self._executor, self._refresh_one, account_id, task)
                duration_seconds = max(time.time() - started_at, 0.0)
            except TaskCancelledError:
                # 线程侧已触发取消，直接结束任务
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                duration_seconds = 0.0
                result = {"success": False, "email": account_id, "error": str(exc)}
            task.progress += 1
            # 将耗时写入结果，便于前端/日志查看（兼容旧字段：新增字段不影响现有解析）
            result["duration_seconds"] = float(round(duration_seconds, 3))
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🎉 刷新成功: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                task.fail_count += 1
                error = result.get('error', '未知错误')
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "error", f"❌ 刷新失败: {account_id}")
                self._append_log(task, "error", f"❌ 失败原因: {error}")
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # --- 调度状态更新（对手动/自动刷新都记录；自动调度会基于这些状态做公平与退避） ---
            failure_category = "" if result.get("success") else self._classify_refresh_failure(result.get("error"))
            if failure_category:
                result["failure_category"] = failure_category
            new_state = await asyncio.to_thread(
                self._update_scheduled_refresh_state_sync,
                account_id,
                bool(result.get("success")),
                float(result.get("duration_seconds") or 0.0),
                str(result.get("error") or ""),
            )
            if not result.get("success") and new_state.get("next_eligible_at"):
                result["next_eligible_at"] = new_state.get("next_eligible_at")
                self._append_log(
                    task,
                    "warning",
                    f"⏳ 失败退避已更新: {account_id} "
                    f"(连续失败={new_state.get('consecutive_failures')}, "
                    f"next_eligible_at={new_state.get('next_eligible_at')})",
                )
            else:
                self._append_log(
                    task,
                    "info",
                    f"📈 调度状态已更新: {account_id} "
                    f"(avg={new_state.get('avg_refresh_duration_seconds')}s, "
                    f"consecutive_failures={new_state.get('consecutive_failures')})",
                )

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._append_log(task, "info", f"login task finished ({task.success_count}/{len(task.account_ids)})")
        self._current_task_id = None
        self._append_log(task, "info", f"🏁 刷新任务完成 (成功: {task.success_count}, 失败: {task.fail_count}, 总计: {len(task.account_ids)})")

    def _refresh_one(self, account_id: str, task: LoginTask) -> dict:
        """刷新单个账户"""
        accounts = load_accounts_from_source()
        account = next((acc for acc in accounts if acc.get("id") == account_id), None)
        if not account:
            return {"success": False, "email": account_id, "error": "账号不存在"}

        if account.get("disabled"):
            return {"success": False, "email": account_id, "error": "账号已禁用"}

        # 获取邮件提供商
        mail_provider = (account.get("mail_provider") or "").lower()
        if not mail_provider:
            if account.get("mail_client_id") or account.get("mail_refresh_token"):
                mail_provider = "microsoft"
            else:
                mail_provider = "duckmail"

        # 获取邮件配置
        mail_password = account.get("mail_password") or account.get("email_password")
        mail_client_id = account.get("mail_client_id")
        mail_refresh_token = account.get("mail_refresh_token")
        mail_tenant = account.get("mail_tenant") or "consumers"

        def log_cb(level, message):
            self._append_log(task, level, f"[{account_id}] {message}")

        log_cb("info", f"📧 邮件提供商: {mail_provider}")

        # 创建邮件客户端
        if mail_provider == "microsoft":
            if not mail_client_id or not mail_refresh_token:
                return {"success": False, "email": account_id, "error": "Microsoft OAuth 配置缺失"}
            mail_address = account.get("mail_address") or account_id
            client = MicrosoftMailClient(
                client_id=mail_client_id,
                refresh_token=mail_refresh_token,
                tenant=mail_tenant,
                proxy=config.basic.proxy_for_auth,
                log_callback=log_cb,
            )
            client.set_credentials(mail_address)
        elif mail_provider in ("duckmail", "moemail", "freemail", "gptmail"):
            if mail_provider not in ("freemail", "gptmail") and not mail_password:
                error_message = "邮箱密码缺失" if mail_provider == "duckmail" else "mail password (email_id) missing"
                return {"success": False, "email": account_id, "error": error_message}
            if mail_provider == "freemail" and not account.get("mail_jwt_token") and not config.basic.freemail_jwt_token:
                return {"success": False, "email": account_id, "error": "Freemail JWT Token 未配置"}

            # 创建邮件客户端，优先使用账户级别配置
            mail_address = account.get("mail_address") or account_id

            # 构建账户级别的配置参数
            account_config = {}
            if account.get("mail_base_url"):
                account_config["base_url"] = account["mail_base_url"]
            if account.get("mail_api_key"):
                account_config["api_key"] = account["mail_api_key"]
            if account.get("mail_jwt_token"):
                account_config["jwt_token"] = account["mail_jwt_token"]
            if account.get("mail_verify_ssl") is not None:
                account_config["verify_ssl"] = account["mail_verify_ssl"]
            if account.get("mail_domain"):
                account_config["domain"] = account["mail_domain"]

            # 创建客户端（工厂会优先使用传入的参数，其次使用全局配置）
            client = create_temp_mail_client(
                mail_provider,
                log_cb=log_cb,
                **account_config
            )
            client.set_credentials(mail_address, mail_password)
            if mail_provider == "moemail":
                client.email_id = mail_password  # 设置 email_id 用于获取邮件
        else:
            return {"success": False, "email": account_id, "error": f"不支持的邮件提供商: {mail_provider}"}

        # 根据配置选择浏览器引擎
        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless

        log_cb("info", f"🌐 启动浏览器 (引擎={browser_engine}, 无头模式={headless})...")

        if browser_engine == "dp":
            # DrissionPage 引擎：支持有头和无头模式
            automation = GeminiAutomation(
                user_agent=self.user_agent,
                proxy=config.basic.proxy_for_auth,
                headless=headless,
                log_callback=log_cb,
            )
        else:
            # undetected-chromedriver 引擎：无头模式反检测能力弱，强制使用有头模式
            if headless:
                log_cb("warning", "⚠️ UC 引擎无头模式反检测能力弱，强制使用有头模式")
                headless = False
            automation = GeminiAutomationUC(
                user_agent=self.user_agent,
                proxy=config.basic.proxy_for_auth,
                headless=headless,
                log_callback=log_cb,
            )
        # 允许外部取消时立刻关闭浏览器
        self._add_cancel_hook(task.id, lambda: getattr(automation, "stop", lambda: None)())
        try:
            log_cb("info", "🔐 执行 Gemini 自动登录...")
            result = automation.login_and_extract(account_id, client)
        except Exception as exc:
            log_cb("error", f"❌ 自动登录异常: {exc}")
            return {"success": False, "email": account_id, "error": str(exc)}
        if not result.get("success"):
            error = result.get("error", "自动化流程失败")
            log_cb("error", f"❌ 自动登录失败: {error}")
            return {"success": False, "email": account_id, "error": error}

        log_cb("info", "✅ Gemini 登录成功，正在保存配置...")

        # 更新账户配置
        config_data = result["config"]
        config_data["mail_provider"] = mail_provider
        if mail_provider in ("freemail", "gptmail"):
            config_data["mail_password"] = ""
        else:
            config_data["mail_password"] = mail_password
        if mail_provider == "microsoft":
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_client_id"] = mail_client_id
            config_data["mail_refresh_token"] = mail_refresh_token
            config_data["mail_tenant"] = mail_tenant
        config_data["disabled"] = account.get("disabled", False)

        for acc in accounts:
            if acc.get("id") == account_id:
                acc.update(config_data)
                break

        self._apply_accounts_update(accounts)
        log_cb("info", "✅ 配置已保存到数据库")
        return {"success": True, "email": account_id, "config": config_data}


    def _get_expiring_accounts(self) -> List[str]:
        accounts = load_accounts_from_source()
        expiring = []
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)

        for account in accounts:
            if account.get("disabled"):
                continue
            mail_provider = (account.get("mail_provider") or "").lower()
            if not mail_provider:
                if account.get("mail_client_id") or account.get("mail_refresh_token"):
                    mail_provider = "microsoft"
                else:
                    mail_provider = "duckmail"

            mail_password = account.get("mail_password") or account.get("email_password")
            if mail_provider == "microsoft":
                if not account.get("mail_client_id") or not account.get("mail_refresh_token"):
                    continue
            elif mail_provider in ("duckmail", "moemail"):
                if not mail_password:
                    continue
            elif mail_provider == "freemail":
                if not config.basic.freemail_jwt_token:
                    continue
            elif mail_provider == "gptmail":
                # GPTMail 不需要密码，允许直接刷新
                pass
            else:
                continue
            expires_at = account.get("expires_at")
            if not expires_at:
                continue

            try:
                expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                expire_time = expire_time.replace(tzinfo=beijing_tz)
                remaining = (expire_time - now).total_seconds() / 3600
            except Exception:
                continue

            if remaining <= config.basic.refresh_window_hours:
                expiring.append(account.get("id"))

        return expiring

    async def check_and_refresh(self, trigger: str = "manual") -> Optional[LoginTask]:
        """
        检查即将过期账号并触发刷新（用于手动触发或旧版定时逻辑）。

        说明：
        - 该方法不做“防堆叠/公平/退避”控制，属于旧逻辑；
        - 高级调度开启时，start_polling 会走 _scheduled_tick()，从而实现 skip-if-busy/HRRN/backoff。

        参数：
        - trigger: 任务触发来源（manual/scheduled）

        返回值：
        - 入队的任务对象（或 None）
        """
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping refresh")
            return None
        expiring_accounts = self._get_expiring_accounts()
        if not expiring_accounts:
            logger.debug("[LOGIN] no accounts need refresh")
            return None

        try:
            return await self.start_login(expiring_accounts, trigger=trigger)
        except Exception as exc:
            logger.warning("[LOGIN] refresh enqueue failed: %s", exc)
            return None

    def _get_queue_status_locked(self) -> dict:
        """
        获取当前刷新队列状态（需在持有 self._lock 时调用）。

        返回值字段：
        - running_ids: 正在执行的任务ID列表
        - pending_ids: 等待中的任务ID列表
        - pending_count: pending 数量
        - current_task_id: 当前任务ID（若有）
        """
        running_ids: List[str] = []
        pending_ids: List[str] = []
        for task_id, t in self._tasks.items():
            if not isinstance(t, LoginTask):
                continue
            if t.status == TaskStatus.RUNNING:
                running_ids.append(task_id)
            elif t.status == TaskStatus.PENDING:
                pending_ids.append(task_id)
        return {
            "running_ids": running_ids,
            "pending_ids": pending_ids,
            "pending_count": len(pending_ids),
            "current_task_id": self._current_task_id,
        }

    def _compute_hrrn_score(self, now_ts: float, last_attempt_at: float, service_seconds: float) -> float:
        """
        计算 HRRN 分数 R = (W + S) / S。

        参数：
        - now_ts: 当前时间戳（秒）
        - last_attempt_at: 上次尝试时间戳（秒）
        - service_seconds: 服务时间估计（秒，平均刷新耗时）

        返回值：
        - HRRN 分数（float，越大优先级越高）
        """
        s = max(float(service_seconds or SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS), 1.0)
        w = max(float(now_ts - float(last_attempt_at or 0.0)), 0.0)
        return (w + s) / s

    def _build_advanced_scheduled_candidates(self) -> tuple[List[dict], dict]:
        """
        构建高级自动刷新调度候选集合（含 HRRN 分数、退避过滤信息）。

        返回值：
        - candidates: 候选列表，每个元素包含：
          - account_id: 账号ID
          - score: HRRN 分数
          - waiting_seconds/service_seconds: 计算细节（便于日志）
          - next_eligible_at: 退避到期时间（<=now 表示可参与）
        - metrics: 统计信息（候选数、被退避过滤数等）
        """
        accounts = load_accounts_from_source()
        beijing_tz = timezone(timedelta(hours=8))
        now_dt = datetime.now(beijing_tz)
        now_ts = float(time.time())

        candidates: List[dict] = []
        skipped_backoff = 0
        considered = 0

        for account in accounts:
            account_id = account.get("id")
            if not account_id:
                continue
            if account.get("disabled"):
                continue

            # --- 复用现有“即将过期”判断逻辑（避免改变用户对定时刷新的预期） ---
            mail_provider = (account.get("mail_provider") or "").lower()
            if not mail_provider:
                if account.get("mail_client_id") or account.get("mail_refresh_token"):
                    mail_provider = "microsoft"
                else:
                    mail_provider = "duckmail"

            mail_password = account.get("mail_password") or account.get("email_password")
            if mail_provider == "microsoft":
                if not account.get("mail_client_id") or not account.get("mail_refresh_token"):
                    continue
            elif mail_provider in ("duckmail", "moemail"):
                if not mail_password:
                    continue
            elif mail_provider == "freemail":
                if not config.basic.freemail_jwt_token:
                    continue
            elif mail_provider == "gptmail":
                # GPTMail 不需要密码，允许直接刷新
                pass
            else:
                continue

            expires_at = account.get("expires_at")
            if not expires_at:
                continue

            try:
                expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                expire_time = expire_time.replace(tzinfo=beijing_tz)
                remaining_hours = (expire_time - now_dt).total_seconds() / 3600
            except Exception:
                continue

            if remaining_hours > config.basic.refresh_window_hours:
                continue

            considered += 1
            state = self._get_account_scheduled_refresh_state(account)
            next_eligible_at = float(state.get("next_eligible_at", 0.0) or 0.0)
            if next_eligible_at and next_eligible_at > now_ts:
                skipped_backoff += 1
                continue

            last_attempt_at = float(state.get("last_attempt_at", 0.0) or 0.0)
            service_seconds = float(
                state.get("avg_refresh_duration_seconds", SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS)
                or SCHEDULED_REFRESH_DEFAULT_SERVICE_SECONDS
            )
            service_seconds = max(service_seconds, 1.0)
            waiting_seconds = max(now_ts - last_attempt_at, 0.0)
            score = self._compute_hrrn_score(now_ts, last_attempt_at, service_seconds)

            candidates.append(
                {
                    "account_id": account_id,
                    "score": float(score),
                    "waiting_seconds": float(round(waiting_seconds, 3)),
                    "service_seconds": float(round(service_seconds, 3)),
                    "next_eligible_at": float(round(next_eligible_at, 3)),
                }
            )

        candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        metrics = {
            "considered": considered,
            "candidates": len(candidates),
            "skipped_backoff": skipped_backoff,
        }
        return candidates, metrics

    async def _scheduled_tick(self) -> Optional[LoginTask]:
        """
        定时轮询 tick：根据配置选择旧策略或高级策略（可选启用）。

        高级策略核心能力（启用开关后生效）：
        - skip-if-busy：已有刷新任务 RUNNING/PENDING 则跳过本次 tick，避免队列堆叠
        - HRRN：按饥饿程度 + 服务时间估计排序，保证长期公平覆盖
        - backoff：失败账号在 next_eligible_at 前不参与自动调度候选集合
        """
        self._last_scheduled_tick_at = float(time.time())

        advanced_enabled = bool(getattr(config.retry, "scheduled_refresh_advanced_enabled", False))
        max_batch = int(getattr(config.retry, "scheduled_refresh_max_batch_size", 20) or 20)

        if not advanced_enabled:
            # 旧策略：直接刷新所有即将过期账号（保持历史行为，避免影响未显式开启的用户）
            return await self.check_and_refresh(trigger="scheduled")

        # 高级策略：严格防堆叠（在同一把锁内做 busy 判断与入队）
        async with self._lock:
            status = self._get_queue_status_locked()
            if status["running_ids"] or status["pending_ids"]:
                logger.info(
                    "[LOGIN][SCHED] tick skipped (busy): running=%s pending=%s current=%s last_enqueue_at=%s",
                    status["running_ids"][:3],
                    status["pending_count"],
                    status["current_task_id"],
                    self._last_scheduled_enqueue_at,
                )
                return None

            candidates, metrics = self._build_advanced_scheduled_candidates()
            if not candidates:
                logger.info(
                    "[LOGIN][SCHED] tick no-op: candidates=0 (considered=%s, skipped_backoff=%s)",
                    metrics.get("considered"),
                    metrics.get("skipped_backoff"),
                )
                return None

            # 计算本轮入队数量（min=5 固定，max=用户配置；不足 5 时按实际候选数量）
            effective_max = max(int(max_batch), SCHEDULED_REFRESH_MIN_BATCH_SIZE)
            batch_size = min(len(candidates), effective_max)
            selected = candidates[:batch_size]
            selected_ids = [x["account_id"] for x in selected]

            masked_list = [self._mask_account_id(aid) for aid in selected_ids]
            logger.info(
                "[LOGIN][SCHED] enqueue: candidates=%s selected=%s max_batch=%s min_batch=%s skipped_backoff=%s ids=%s",
                metrics.get("candidates"),
                len(selected_ids),
                max_batch,
                SCHEDULED_REFRESH_MIN_BATCH_SIZE,
                metrics.get("skipped_backoff"),
                masked_list,
            )
            # TopN 的 W/S/R 记录到 debug，便于需要时排查调度是否公平/是否被退避过滤
            for item in selected[: min(10, len(selected))]:
                logger.debug(
                    "[LOGIN][SCHED] score: id=%s W=%ss S=%ss R=%s next_eligible_at=%s",
                    self._mask_account_id(item["account_id"]),
                    item.get("waiting_seconds"),
                    item.get("service_seconds"),
                    round(float(item.get("score") or 0.0), 6),
                    item.get("next_eligible_at"),
                )

            self._last_scheduled_enqueue_at = float(time.time())
            return await self._start_login_locked(account_ids=selected_ids, trigger="scheduled")

    async def start_polling(self) -> None:
        if self._is_polling:
            logger.warning("[LOGIN] polling already running")
            return

        self._is_polling = True
        logger.info("[LOGIN] refresh polling started")
        try:
            while self._is_polling:
                # 检查配置是否启用定时刷新
                if not config.retry.scheduled_refresh_enabled:
                    logger.debug("[LOGIN] scheduled refresh disabled, skipping check")
                    await asyncio.sleep(CONFIG_CHECK_INTERVAL_SECONDS)
                    continue

                # 执行一次 tick（高级调度开启时，会启用防堆叠/公平/退避）
                await self._scheduled_tick()

                # 使用配置的间隔时间
                interval_minutes = int(config.retry.scheduled_refresh_interval_minutes or 0)
                # 防止用户配置 0 导致忙等（0 仍允许保存，但这里按最小 60 秒 sleep）
                interval_seconds = max(interval_minutes * 60, CONFIG_CHECK_INTERVAL_SECONDS)
                logger.debug(f"[LOGIN] next check in {config.retry.scheduled_refresh_interval_minutes} minutes")
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[LOGIN] polling stopped")
        except Exception as exc:
            logger.error("[LOGIN] polling error: %s", exc)
        finally:
            self._is_polling = False

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[LOGIN] stopping polling")
