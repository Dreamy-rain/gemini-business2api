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
from core.duckmail_client import DuckMailClient
from core.gptmail_client import GPTMailClient
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC
from core.microsoft_mail_client import MicrosoftMailClient
from core.outbound_proxy import OutboundProxyConfig

logger = logging.getLogger("gemini.login")


@dataclass
class LoginTask(BaseTask):
    """登录任务数据类"""
    account_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict["account_ids"] = self.account_ids
        return base_dict


class LoginService(BaseTaskService[LoginTask]):
    """登录服务类"""

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
    ) -> None:
        super().__init__(
            multi_account_mgr,
            http_client,
            user_agent,
            account_failure_threshold,
            rate_limit_cooldown_seconds,
            session_cache_ttl_seconds,
            global_stats_provider,
            set_multi_account_mgr,
            log_prefix="REFRESH",
        )
        self._is_polling = False
        self._auto_refresh_paused = True  # 运行时开关：默认暂停（不自动刷新）

    def _get_active_account_ids(self) -> set:
        """获取当前正在处理中（PENDING 或 RUNNING）的所有账号 ID"""
        active_ids = set()
        for task in self._tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                for acc_id in task.account_ids:
                    active_ids.add(acc_id)
        return active_ids

    async def start_login(self, account_ids: List[str]) -> LoginTask:
        """启动登录任务（支持排队）。"""
        async with self._lock:
            # 获取当前已经在活跃任务中的账号
            active_ids = self._get_active_account_ids()
            
            # 过滤掉已经在队列或运行中的账号
            new_account_ids = [aid for aid in account_ids if aid not in active_ids]
            
            if not new_account_ids:
                # 寻找包含这些账号的现有活跃任务并返回，如果没有则返回 None
                for existing in self._tasks.values():
                    if (
                        isinstance(existing, LoginTask)
                        and any(aid in existing.account_ids for aid in account_ids)
                        and existing.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
                    ):
                        return existing
                return None

            task = LoginTask(id=str(uuid.uuid4()), account_ids=new_account_ids)
            self._tasks[task.id] = task
            self._append_log(task, "info", f"📝 创建刷新任务 (账号数量: {len(task.account_ids)})")
            await self._enqueue_task(task)
            return task

    def _execute_task(self, task: LoginTask):
        return self._run_login_async(task)

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
                result = await loop.run_in_executor(self._executor, self._refresh_one, account_id, task)
            except TaskCancelledError:
                # 线程侧已触发取消，直接结束任务
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                result = {"success": False, "email": account_id, "error": str(exc)}
            task.progress += 1
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

        outbound: OutboundProxyConfig = config.basic.outbound_proxy
        use_outbound_proxy = outbound.is_configured()
        proxy_url = outbound.to_proxy_url(config.security.admin_key) if use_outbound_proxy else (config.basic.proxy or "")
        no_proxy = outbound.no_proxy if use_outbound_proxy else ""
        direct_fallback = outbound.direct_fallback if use_outbound_proxy else False

        # 创建邮件客户端
        if mail_provider == "microsoft":
            if not mail_client_id or not mail_refresh_token:
                return {"success": False, "email": account_id, "error": "Microsoft OAuth 配置缺失"}
            mail_address = account.get("mail_address") or account_id
            client = MicrosoftMailClient(
                client_id=mail_client_id,
                refresh_token=mail_refresh_token,
                tenant=mail_tenant,
                proxy=proxy_url,
                no_proxy=no_proxy,
                direct_fallback=direct_fallback,
                log_callback=log_cb,
            )
            client.set_credentials(mail_address)
        elif mail_provider == "gptmail":
            mail_address = account.get("mail_address") or account_id
            client = GPTMailClient(
                base_url=config.basic.gptmail_base_url,
                proxy=proxy_url,
                no_proxy=no_proxy,
                direct_fallback=direct_fallback,
                verify_ssl=config.basic.gptmail_verify_ssl,
                api_key=config.basic.gptmail_api_key,
                log_callback=log_cb,
            )
            client.set_credentials(mail_address)
        elif mail_provider == "duckmail":
            if not mail_password:
                return {"success": False, "email": account_id, "error": "邮箱密码缺失"}
            # DuckMail: account_id 就是邮箱地址
            client = DuckMailClient(
                base_url=config.basic.duckmail_base_url,
                proxy=proxy_url,
                no_proxy=no_proxy,
                direct_fallback=direct_fallback,
                verify_ssl=config.basic.duckmail_verify_ssl,
                api_key=config.basic.duckmail_api_key,
                log_callback=log_cb,
            )
            client.set_credentials(account_id, mail_password)
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
                proxy=proxy_url,
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
                proxy=proxy_url,
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
        if mail_provider == "microsoft":
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_client_id"] = mail_client_id
            config_data["mail_refresh_token"] = mail_refresh_token
            config_data["mail_tenant"] = mail_tenant
            config_data["mail_password"] = mail_password or ""
        elif mail_provider == "duckmail":
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_password"] = mail_password or ""
        else:
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_password"] = ""
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
        
        # 获取当前活跃账号，在扫描阶段就排除它们
        active_ids = self._get_active_account_ids()

        for account in accounts:
            account_id = account.get("id")
            if not account_id or account.get("disabled") or account_id in active_ids:
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
            elif mail_provider == "duckmail":
                if not mail_password:
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

    async def check_and_refresh(self) -> Optional[LoginTask]:
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping refresh")
            return None
        expiring_accounts = self._get_expiring_accounts()
        if not expiring_accounts:
            logger.debug("[LOGIN] no accounts need refresh")
            return None

        try:
            return await self.start_login(expiring_accounts)
        except Exception as exc:
            logger.warning("[LOGIN] refresh enqueue failed: %s", exc)
            return None

    async def start_polling(self) -> None:
        if self._is_polling:
            logger.warning("[LOGIN] polling already running")
            return

        self._is_polling = True
        logger.info("[LOGIN] refresh polling started (interval: 30 minutes)")
        try:
            while self._is_polling:
                # 检查运行时开关
                if not self._auto_refresh_paused:
                    await self.check_and_refresh()
                else:
                    logger.debug("[LOGIN] auto-refresh paused, skipping check")
                await asyncio.sleep(1800)
        except asyncio.CancelledError:
            logger.info("[LOGIN] polling stopped")
        except Exception as exc:
            logger.error("[LOGIN] polling error: %s", exc)
        finally:
            self._is_polling = False

    def pause_auto_refresh(self) -> None:
        """暂停自动刷新（不保存到数据库，重启后恢复）"""
        self._auto_refresh_paused = True
        logger.info("[LOGIN] auto-refresh paused (runtime only)")

    def resume_auto_refresh(self) -> None:
        """恢复自动刷新"""
        was_paused = self._auto_refresh_paused
        self._auto_refresh_paused = False
        logger.info("[LOGIN] auto-refresh resumed")
        # 如果是从暂停状态恢复，返回 True 表示需要立即检查
        return was_paused

    def is_auto_refresh_paused(self) -> bool:
        """获取自动刷新暂停状态"""
        return self._auto_refresh_paused

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[LOGIN] stopping polling")
