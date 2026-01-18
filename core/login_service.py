import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskStatus
from core.config import config
from core.duckmail_client import DuckMailClient
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC
from core.microsoft_mail_client import MicrosoftMailClient

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

    async def start_login(self, account_ids: List[str]) -> LoginTask:
        """启动登录任务"""
        async with self._lock:
            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current and current.status == TaskStatus.RUNNING:
                    raise ValueError("login task already running")

            task = LoginTask(id=str(uuid.uuid4()), account_ids=account_ids)
            self._tasks[task.id] = task
            self._current_task_id = task.id
            self._append_log(task, "info", f"login task created ({len(account_ids)} accounts)")
            asyncio.create_task(self._run_login_async(task))
            return task

    async def _run_login_async(self, task: LoginTask) -> None:
        """异步执行登录任务"""
        task.status = TaskStatus.RUNNING
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", "login task started")

        for account_id in task.account_ids:
            try:
                result = await loop.run_in_executor(self._executor, self._refresh_one, account_id, task)
            except Exception as exc:
                result = {"success": False, "email": account_id, "error": str(exc)}
            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                self._append_log(task, "info", f"refresh success: {account_id}")
            else:
                task.fail_count += 1
                self._append_log(task, "error", f"refresh failed: {account_id} - {result.get('error')}")

        task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._current_task_id = None
        self._append_log(task, "info", f"login task finished ({task.success_count}/{len(task.account_ids)})")

    def _refresh_one(self, account_id: str, task: LoginTask) -> dict:
        """刷新单个账户"""
        accounts = load_accounts_from_source()
        account = next((acc for acc in accounts if acc.get("id") == account_id), None)
        if not account:
            return {"success": False, "email": account_id, "error": "account not found"}

        if account.get("disabled"):
            return {"success": False, "email": account_id, "error": "account disabled"}

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

        log_cb = lambda level, message: self._append_log(task, level, f"[{account_id}] {message}")

        # 创建邮件客户端
        if mail_provider == "microsoft":
            if not mail_client_id or not mail_refresh_token:
                return {"success": False, "email": account_id, "error": "microsoft oauth missing"}
            mail_address = account.get("mail_address") or account_id
            client = MicrosoftMailClient(
                client_id=mail_client_id,
                refresh_token=mail_refresh_token,
                tenant=mail_tenant,
                proxy=config.basic.proxy,
                log_callback=log_cb,
            )
            client.set_credentials(mail_address)
        elif mail_provider == "duckmail":
            if not mail_password:
                return {"success": False, "email": account_id, "error": "mail password missing"}
            # DuckMail: account_id 就是邮箱地址
            client = DuckMailClient(
                base_url=config.basic.duckmail_base_url,
                proxy=config.basic.proxy,
                verify_ssl=config.basic.duckmail_verify_ssl,
                api_key=config.basic.duckmail_api_key,
                log_callback=log_cb,
            )
            client.set_credentials(account_id, mail_password)
        else:
            return {"success": False, "email": account_id, "error": f"unsupported mail provider: {mail_provider}"}

        # 根据配置选择浏览器引擎
        browser_engine = (config.basic.browser_engine or "dp").lower()
        if browser_engine == "dp":
            # DrissionPage 引擎：支持有头和无头模式
            automation = GeminiAutomation(
                user_agent=self.user_agent,
                proxy=config.basic.proxy,
                headless=config.basic.browser_headless,
                log_callback=log_cb,
            )
        else:
            # undetected-chromedriver 引擎：支持有头和无头
            automation = GeminiAutomationUC(
                user_agent=self.user_agent,
                proxy=config.basic.proxy,
                headless=config.basic.browser_headless,
                log_callback=log_cb,
            )
        try:
            result = automation.login_and_extract(account_id, client)
        except Exception as exc:
            return {"success": False, "email": account_id, "error": str(exc)}
        if not result.get("success"):
            return {"success": False, "email": account_id, "error": result.get("error", "automation failed")}

        # 更新账户配置
        config_data = result["config"]
        config_data["mail_provider"] = mail_provider
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
            else:
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

    async def check_and_refresh(self) -> None:
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping refresh")
            return
        expiring_accounts = self._get_expiring_accounts()
        if not expiring_accounts:
            logger.debug("[LOGIN] no accounts need refresh")
            return

        try:
            await self.start_login(expiring_accounts)
        except ValueError as exc:
            logger.warning("[LOGIN] %s", exc)

    async def start_polling(self) -> None:
        if self._is_polling:
            logger.warning("[LOGIN] polling already running")
            return

        self._is_polling = True
        logger.info("[LOGIN] refresh polling started (interval: 30 minutes)")
        try:
            while self._is_polling:
                await self.check_and_refresh()
                await asyncio.sleep(1800)
        except asyncio.CancelledError:
            logger.info("[LOGIN] polling stopped")
        except Exception as exc:
            logger.error("[LOGIN] polling error: %s", exc)
        finally:
            self._is_polling = False

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[LOGIN] stopping polling")
