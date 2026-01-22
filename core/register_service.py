import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskStatus
from core.config import config
from core.duckmail_client import DuckMailClient
from core.gptmail_client import GPTMailClient
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC

logger = logging.getLogger("gemini.register")


@dataclass
class RegisterTask(BaseTask):
    """注册任务数据类"""
    count: int = 0
    mail_provider: str = "duckmail"

    def to_dict(self) -> dict:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict["count"] = self.count
        base_dict["mail_provider"] = self.mail_provider
        return base_dict


class RegisterService(BaseTaskService[RegisterTask]):
    """注册服务类"""

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
            log_prefix="REGISTER",
        )

    async def start_register(
        self,
        count: Optional[int] = None,
        domain: Optional[str] = None,
        mail_provider: Optional[str] = None,
    ) -> RegisterTask:
        """启动注册任务"""
        async with self._lock:
            if os.environ.get("ACCOUNTS_CONFIG"):
                raise ValueError("已设置 ACCOUNTS_CONFIG 环境变量，注册功能已禁用")
            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current and current.status == TaskStatus.RUNNING:
                    raise ValueError("已有注册任务正在运行中")

            domain_value = (domain or "").strip()
            if not domain_value:
                domain_value = (config.basic.register_domain or "").strip() or None

            mail_provider_value = (mail_provider or "").strip().lower() or "duckmail"
            if mail_provider_value not in ("duckmail", "gptmail"):
                mail_provider_value = "duckmail"

            register_count = count or config.basic.register_default_count
            register_count = max(1, min(30, int(register_count)))
            task = RegisterTask(id=str(uuid.uuid4()), count=register_count, mail_provider=mail_provider_value)
            self._tasks[task.id] = task
            self._current_task_id = task.id
            self._append_log(task, "info", f"📝 创建注册任务 (数量={register_count}, 邮箱={mail_provider_value})")
            asyncio.create_task(self._run_register_async(task, domain_value, mail_provider_value))
            return task

    async def _run_register_async(self, task: RegisterTask, domain: Optional[str], mail_provider: str) -> None:
        """异步执行注册任务"""
        task.status = TaskStatus.RUNNING
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 注册任务已启动 (共 {task.count} 个账号)")

        for idx in range(task.count):
            try:
                self._append_log(task, "info", f"📊 进度: {idx + 1}/{task.count}")
                result = await loop.run_in_executor(self._executor, self._register_one, domain, mail_provider, task)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                email = result.get('email', '未知')
                self._append_log(task, "info", f"✅ 注册成功: {email}")
            else:
                task.fail_count += 1
                error = result.get('error', '未知错误')
                self._append_log(task, "error", f"❌ 注册失败: {error}")

        task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._current_task_id = None
        self._append_log(task, "info", f"🏁 注册任务完成 (成功: {task.success_count}, 失败: {task.fail_count}, 总计: {task.count})")

    def _register_one(self, domain: Optional[str], mail_provider: str, task: RegisterTask) -> dict:
        """注册单个账户"""
        log_cb = lambda level, message: self._append_log(task, level, message)

        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", "🆕 开始注册新账户")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        client = None
        if mail_provider == "gptmail":
            client = GPTMailClient(
                base_url=config.basic.gptmail_base_url,
                proxy=config.basic.proxy,
                verify_ssl=config.basic.gptmail_verify_ssl,
                api_key=config.basic.gptmail_api_key or "gpt-test",
                log_callback=log_cb,
            )
            log_cb("info", "📧 步骤 1/3: 生成 GPTMail 邮箱...")
            email = client.generate_email(domain=domain)
            if not email:
                log_cb("error", "❌ GPTMail 邮箱生成失败")
                return {"success": False, "error": "GPTMail 生成邮箱失败"}
            log_cb("info", f"✅ GPTMail 邮箱生成成功: {client.email}")
        else:
            client = DuckMailClient(
                base_url=config.basic.duckmail_base_url,
                proxy=config.basic.proxy,
                verify_ssl=config.basic.duckmail_verify_ssl,
                api_key=config.basic.duckmail_api_key,
                log_callback=log_cb,
            )

            log_cb("info", "📧 步骤 1/3: 注册 DuckMail 邮箱...")
            if not client.register_account(domain=domain):
                log_cb("error", "❌ DuckMail 邮箱注册失败")
                return {"success": False, "error": "DuckMail 注册失败"}

            log_cb("info", f"✅ DuckMail 邮箱注册成功: {client.email}")

        # 根据配置选择浏览器引擎
        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless

        log_cb("info", f"🌐 步骤 2/3: 启动浏览器 (引擎={browser_engine}, 无头模式={headless})...")

        if browser_engine == "dp":
            # DrissionPage 引擎：支持有头和无头模式
            automation = GeminiAutomation(
                user_agent=self.user_agent,
                proxy=config.basic.proxy,
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
                proxy=config.basic.proxy,
                headless=headless,
                log_callback=log_cb,
            )

        try:
            log_cb("info", "🔐 步骤 3/3: 执行 Gemini 自动登录...")
            result = automation.login_and_extract(client.email, client)
        except Exception as exc:
            log_cb("error", f"❌ 自动登录异常: {exc}")
            return {"success": False, "error": str(exc)}

        if not result.get("success"):
            error = result.get("error", "自动化流程失败")
            log_cb("error", f"❌ 自动登录失败: {error}")
            return {"success": False, "error": error}

        log_cb("info", "✅ Gemini 登录成功，正在保存配置...")

        config_data = result["config"]
        config_data["mail_provider"] = mail_provider
        config_data["mail_address"] = client.email
        if mail_provider == "duckmail":
            config_data["mail_password"] = getattr(client, "password", "") or ""
        else:
            config_data["mail_password"] = ""

        accounts_data = load_accounts_from_source()
        updated = False
        for acc in accounts_data:
            if acc.get("id") == config_data["id"]:
                acc.update(config_data)
                updated = True
                break
        if not updated:
            accounts_data.append(config_data)

        self._apply_accounts_update(accounts_data)

        log_cb("info", "✅ 配置已保存到数据库")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", f"🎉 账户注册完成: {client.email}")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return {"success": True, "email": client.email, "config": config_data}
