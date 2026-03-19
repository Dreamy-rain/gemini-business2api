import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core.mail_providers import create_temp_mail_client
from core.gemini_automation import GeminiAutomation
from core.proxy_utils import parse_proxy_setting

logger = logging.getLogger("gemini.register")


@dataclass
class RegisterTask(BaseTask):
    """注册任务数据类"""
    count: int = 0
    domain: Optional[str] = None
    mail_provider: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict["count"] = self.count
        base_dict["domain"] = self.domain
        base_dict["mail_provider"] = self.mail_provider
        return base_dict


class RegisterService(BaseTaskService[RegisterTask]):
    """注册服务类"""

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
            log_prefix="REGISTER",
        )

    async def start_register(self, count: Optional[int] = None, domain: Optional[str] = None, mail_provider: Optional[str] = None) -> RegisterTask:
        """
        启动注册任务 - 统一任务管理
        - 每次请求创建独立任务
        - 所有任务统一进入串行队列执行
        """
        async with self._lock:
            if os.environ.get("ACCOUNTS_CONFIG"):
                raise ValueError("已设置 ACCOUNTS_CONFIG 环境变量，注册功能已禁用")

            # 先确定使用哪个邮箱服务提供商
            mail_provider_value = (mail_provider or "").strip().lower()
            if not mail_provider_value:
                mail_provider_value = (config.basic.temp_mail_provider or "duckmail").lower()

            # 再确定使用哪个域名（只有 DuckMail 使用 register_domain 配置）
            domain_value = (domain or "").strip()
            if not domain_value:
                if mail_provider_value == "duckmail":
                    domain_value = (config.basic.register_domain or "").strip() or None
                else:
                    domain_value = None

            register_count = count or config.basic.register_default_count
            register_count = max(1, int(register_count))

            # 每次都创建新任务，避免运行中动态修改任务目标导致执行数量不准确
            task = RegisterTask(id=str(uuid.uuid4()), count=register_count, domain=domain_value, mail_provider=mail_provider_value)
            self._tasks[task.id] = task
            self._append_log(
                task,
                "info",
                f"📝 创建注册任务并入队 (数量: {register_count}, 域名: {domain_value or 'default'}, 提供商: {mail_provider_value})"
            )
            await self._enqueue_task(task)
            return task

    def _execute_task(self, task: RegisterTask):
        return self._run_register_async(task, task.domain, task.mail_provider)

    async def _run_register_async(self, task: RegisterTask, domain: Optional[str], mail_provider: Optional[str]) -> None:
        """异步执行注册任务（支持取消）。"""
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 注册任务已启动 (共 {task.count} 个账号)")

        for idx in range(task.count):
            if task.cancel_requested:
                self._append_log(task, "warning", f"register task cancelled: {task.cancel_reason or 'cancelled'}")
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return

            try:
                self._append_log(task, "info", f"📊 进度: {idx + 1}/{task.count}")
                result = await loop.run_in_executor(self._executor, self._register_one, domain, mail_provider, task)
            except TaskCancelledError:
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                email = result.get('email', '未知')
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"✅ 注册成功: {email}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                task.fail_count += 1
                error = result.get('error', '未知错误')
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "error", f"❌ 注册失败: {error}")
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # 账号之间等待 10 秒，避免资源争抢和风控
            if idx < task.count - 1 and not task.cancel_requested:
                self._append_log(task, "info", "⏳ 等待 10 秒后处理下一个账号...")
                await asyncio.sleep(10)

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._append_log(task, "info", f"🏁 注册任务完成 (成功: {task.success_count}, 失败: {task.fail_count}, 总计: {task.count})")

    def _register_one(self, domain: Optional[str], mail_provider: Optional[str], task: RegisterTask) -> dict:
        """注册单个账户"""
        log_cb = lambda level, message: self._append_log(task, level, message)

        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", "🆕 开始注册新账户")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 使用传递的邮件提供商参数，如果未提供则从配置读取
        temp_mail_provider = (mail_provider or "").strip().lower()
        if not temp_mail_provider:
            temp_mail_provider = (config.basic.temp_mail_provider or "duckmail").lower()

        log_cb("info", f"📧 步骤 1/3: 注册临时邮箱 (提供商={temp_mail_provider})...")

        if temp_mail_provider == "freemail" and not config.basic.freemail_jwt_token:
            log_cb("error", "❌ Freemail JWT Token 未配置")
            return {"success": False, "error": "Freemail JWT Token 未配置"}

        client = create_temp_mail_client(
            temp_mail_provider,
            domain=domain,
            log_cb=log_cb,
        )

        if not client.register_account(domain=domain):
            log_cb("error", f"❌ {temp_mail_provider} 邮箱注册失败")
            return {"success": False, "error": f"{temp_mail_provider} 注册失败"}

        log_cb("info", f"✅ 邮箱注册成功: {client.email}")

        browser_mode = (config.basic.browser_mode or "normal").strip().lower()
        headless = config.basic.browser_headless
        proxy_for_auth, _ = parse_proxy_setting(config.basic.proxy_for_auth)

        log_cb("info", f"🌐 步骤 2/3: 启动浏览器 (模式={browser_mode}, 无头={headless})...")

        automation = GeminiAutomation(
            user_agent=self.user_agent,
            proxy=proxy_for_auth,
            browser_mode=browser_mode,
            log_callback=log_cb,
        )
        # 允许外部取消时立刻关闭浏览器
        self._add_cancel_hook(task.id, lambda: getattr(automation, "stop", lambda: None)())

        try:
            log_cb("info", "🔐 步骤 3/3: 执行 Gemini 自动登录...")
            result = automation.login_and_extract(client.email, client, is_new_account=True)
        except Exception as exc:
            log_cb("error", f"❌ 自动登录异常: {exc}")
            return {"success": False, "error": str(exc)}

        if not result.get("success"):
            error = result.get("error", "自动化流程失败")
            log_cb("error", f"❌ 自动登录失败: {error}")
            return {"success": False, "error": error}

        log_cb("info", "✅ Gemini 登录成功，正在保存配置...")

        config_data = result["config"]
        config_data["mail_provider"] = temp_mail_provider
        config_data["mail_address"] = client.email

        # 保存邮箱自定义配置
        if temp_mail_provider == "freemail":
            config_data["mail_password"] = ""
            config_data["mail_base_url"] = config.basic.freemail_base_url
            config_data["mail_jwt_token"] = config.basic.freemail_jwt_token
            config_data["mail_verify_ssl"] = config.basic.freemail_verify_ssl
            config_data["mail_domain"] = config.basic.freemail_domain
        elif temp_mail_provider == "gptmail":
            config_data["mail_password"] = ""
            config_data["mail_base_url"] = config.basic.gptmail_base_url
            config_data["mail_api_key"] = config.basic.gptmail_api_key
            config_data["mail_verify_ssl"] = config.basic.gptmail_verify_ssl
            config_data["mail_domain"] = config.basic.gptmail_domain
        elif temp_mail_provider == "cfmail":
            config_data["mail_password"] = getattr(client, "jwt_token", "") or getattr(client, "password", "")
            config_data["mail_base_url"] = config.basic.cfmail_base_url
            config_data["mail_api_key"] = config.basic.cfmail_api_key
            config_data["mail_verify_ssl"] = config.basic.cfmail_verify_ssl
            config_data["mail_domain"] = config.basic.cfmail_domain
        elif temp_mail_provider == "samplemail":
            config_data["mail_password"] = ""
            config_data["mail_base_url"] = config.basic.samplemail_base_url
            config_data["mail_api_key"] = ""
            config_data["mail_verify_ssl"] = config.basic.samplemail_verify_ssl
            config_data["mail_domain"] = ""
        elif temp_mail_provider == "moemail":
            config_data["mail_password"] = getattr(client, "email_id", "") or getattr(client, "password", "")
            config_data["mail_base_url"] = config.basic.moemail_base_url
            config_data["mail_api_key"] = config.basic.moemail_api_key
            config_data["mail_domain"] = config.basic.moemail_domain
        elif temp_mail_provider == "duckmail":
            config_data["mail_password"] = getattr(client, "password", "")
            config_data["mail_base_url"] = config.basic.duckmail_base_url
            config_data["mail_api_key"] = config.basic.duckmail_api_key
        else:
            config_data["mail_password"] = getattr(client, "password", "")

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
