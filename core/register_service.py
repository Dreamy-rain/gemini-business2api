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
from core.gemini_automation_uc import GeminiAutomationUC
from core.outbound_proxy import OutboundProxyConfig
from core.proxy_utils import parse_proxy_setting

logger = logging.getLogger("gemini.register")


@dataclass
class RegisterTask(BaseTask):
    """注册任务数据类"""
    count: int = 0
    mail_provider: str = "duckmail"
    domain: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        base_dict = super().to_dict()
        base_dict["count"] = self.count
        base_dict["mail_provider"] = self.mail_provider
        base_dict["domain"] = self.domain
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
        """启动注册任务（支持排队）。"""
        async with self._lock:
            if os.environ.get("ACCOUNTS_CONFIG"):
                raise ValueError("ACCOUNTS_CONFIG is set; register is disabled")
                raise ValueError("已设置 ACCOUNTS_CONFIG 环境变量，注册功能已禁用")
            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current and current.status == TaskStatus.RUNNING:
                    raise ValueError("已有注册任务正在运行中")

            domain_value = (domain or "").strip()
            if not domain_value:
                domain_value = (config.basic.register_domain or "").strip() or None

            mail_provider_value = (mail_provider or "").strip().lower()
            if not mail_provider_value:
                mail_provider_value = (config.basic.temp_mail_provider or "duckmail").lower()
            
            # 使用上游的参数校验逻辑，但保留我们的任务结构
            register_count = count or config.basic.register_default_count
            register_count = max(1, min(30, int(register_count)))
            
            task = RegisterTask(
                id=str(uuid.uuid4()), 
                count=register_count, 
                mail_provider=mail_provider_value,
                domain=domain_value
            )
            self._tasks[task.id] = task
            # 将 domain 和 mail_provider 记录在日志里，便于排查
            self._append_log(task, "info", f"register task queued (count={register_count}, domain={domain_value or 'default'}, provider={mail_provider_value})")
            await self._enqueue_task(task)
            self._current_task_id = task.id
            return task

    def _execute_task(self, task: RegisterTask):
        return self._run_register_async(task)

    async def _run_register_async(self, task: RegisterTask) -> None:
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
                result = await loop.run_in_executor(self._executor, self._register_one, task)
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
                self._append_log(task, "info", f"✅ 注册成功: {email}")
            else:
                task.fail_count += 1
                error = result.get('error', '未知错误')
                self._append_log(task, "error", f"❌ 注册失败: {error}")

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._current_task_id = None
        self._append_log(task, "info", f"🏁 注册任务完成 (成功: {task.success_count}, 失败: {task.fail_count}, 总计: {task.count})")
    def _register_one(self, task: RegisterTask) -> dict:
        """注册单个账户"""
        domain = task.domain
        mail_provider = task.mail_provider
        log_cb = lambda level, message: self._append_log(task, level, message)

        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", "🆕 开始注册新账户")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 根据配置选择邮件提供商
        temp_mail_provider = (config.basic.temp_mail_provider or "duckmail").lower()
        # 如果任务指定了 provider 且有效，优先使用任务指定的
        if mail_provider in ("duckmail", "gptmail", "freemail", "moemail"):
             temp_mail_provider = mail_provider

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

        # 根据配置选择浏览器引擎
        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless
        
        # 使用配置的账户操作代理（用于访问 Gemini 网站）
        browser_proxy, _ = parse_proxy_setting(config.basic.proxy_for_auth)

        log_cb("info", f"🌐 步骤 2/3: 浏览器自动化...")

        # ---- 构建子进程参数（所有值在主进程中读好）----

        # 邮件配置传给子进程（子进程只做浏览器登录，邮件客户端用于读取验证码）
        mail_config_for_subprocess = {
            "mail_address": client.email,
            "mail_password": getattr(client, "password", "") or "",
        }
        # 透传邮件客户端的连接参数
        for attr in ("proxy_url", "no_proxy", "direct_fallback", "base_url",
                      "api_key", "jwt_token", "verify_ssl"):
            val = getattr(client, attr, None)
            if val is not None:
                mail_config_for_subprocess[attr.replace("proxy_url", "proxy")] = val

        subprocess_params = {
            "action": "login",  # 子进程只做登录，邮件注册已在主进程完成
            "email": client.email,
            "browser_engine": browser_engine,
            "headless": headless,
            "proxy": browser_proxy or "",
            "user_agent": self.user_agent,
            "mail_provider": temp_mail_provider,
            "mail_config": mail_config_for_subprocess,
        }
        # moemail 需要额外的 email_id
        if temp_mail_provider == "moemail":
            mail_config_for_subprocess["mail_password"] = getattr(client, "email_id", "") or getattr(client, "password", "")

        # ---- 在独立子进程中执行浏览器自动化 ----
        from core.subprocess_worker import run_browser_in_subprocess
        result = run_browser_in_subprocess(
            subprocess_params,
            log_callback=log_cb,
            timeout=300,
            cancel_check=lambda: task.cancel_requested,
        )

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
                # 智能合并逻辑：如果账号已存在（比如是重新登录/注册同名账号），保留原有元数据
                old_expires_at = acc.get("expires_at")
                acc.update(config_data)
                if not acc.get("expires_at") and old_expires_at:
                    acc["expires_at"] = old_expires_at
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
