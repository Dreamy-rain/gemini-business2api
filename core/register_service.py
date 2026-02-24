from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional

from core.account import load_accounts_from_source, ACCOUNTS_CONFIG_LOCK
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core.mail_providers import create_temp_mail_client
from core.proxy_utils import parse_proxy_setting

logger = logging.getLogger("gemini.register")


@dataclass
class RegisterTask(BaseTask):
    count: int = 0
    mail_provider: str = "duckmail"
    domain: Optional[str] = None

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["count"] = self.count
        data["mail_provider"] = self.mail_provider
        data["domain"] = self.domain
        return data


class RegisterService(BaseTaskService[RegisterTask]):
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
        """Queue a register task."""
        async with self._lock:
            if os.environ.get("ACCOUNTS_CONFIG"):
                raise ValueError("ACCOUNTS_CONFIG is set; register is disabled")

            if self._current_task_id:
                current = self._tasks.get(self._current_task_id)
                if current and current.status == TaskStatus.RUNNING:
                    raise ValueError("a register task is already running")

            domain_value = (domain or "").strip() or (config.basic.register_domain or "").strip() or None
            provider_value = (mail_provider or "").strip().lower() or (config.basic.temp_mail_provider or "duckmail").lower()

            register_count = count or config.basic.register_default_count
            register_count = max(1, min(30, int(register_count)))

            task = RegisterTask(
                id=str(uuid.uuid4()),
                count=register_count,
                mail_provider=provider_value,
                domain=domain_value,
            )
            self._tasks[task.id] = task
            self._append_log(
                task,
                "info",
                f"register task queued (count={register_count}, domain={domain_value or 'default'}, provider={provider_value})",
            )
            await self._enqueue_task(task)
            self._current_task_id = task.id
            return task

    def _execute_task(self, task: RegisterTask):
        return self._run_register_async(task)

    async def _run_register_async(self, task: RegisterTask) -> None:
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"register task started (count={task.count})")
        pending_account_configs: List[dict] = []

        for idx in range(task.count):
            if task.cancel_requested:
                self._append_log(task, "warning", f"register task cancelled: {task.cancel_reason or 'cancelled'}")
                break

            try:
                self._append_log(task, "info", f"progress: {idx + 1}/{task.count}")
                result = await loop.run_in_executor(self._executor, self._register_one, task)
            except TaskCancelledError:
                task.cancel_requested = True
                task.cancel_reason = task.cancel_reason or "cancelled"
                self._append_log(task, "warning", f"register task cancelled: {task.cancel_reason}")
                break
            except Exception as exc:
                result = {"success": False, "error": str(exc)}

            task.progress += 1
            self._append_result(task, result)

            if result.get("success"):
                task.success_count += 1
                self._append_log(task, "info", f"register success: {result.get('email', 'unknown')}")
                cfg = result.get("config")
                if isinstance(cfg, dict):
                    pending_account_configs.append(cfg)
            else:
                task.fail_count += 1
                self._append_log(task, "error", f"register failed: {result.get('error', 'unknown error')}")

        if pending_account_configs:
            try:
                with ACCOUNTS_CONFIG_LOCK:
                    accounts_data = load_accounts_from_source()
                    account_by_id = {
                        acc.get("id"): acc
                        for acc in accounts_data
                        if isinstance(acc, dict) and acc.get("id")
                    }

                    updated_count = 0
                    for cfg in pending_account_configs:
                        cfg_id = cfg.get("id")
                        if not cfg_id:
                            continue
                        existing = account_by_id.get(cfg_id)
                        if existing is None:
                            accounts_data.append(cfg)
                            account_by_id[cfg_id] = cfg
                        else:
                            existing.update(cfg)
                        updated_count += 1

                    if updated_count > 0:
                        self._apply_accounts_update(accounts_data)
                        self._append_log(task, "info", f"saved register configs: {updated_count}")
            except Exception as exc:
                task.error = f"save register config failed: {str(exc)[:200]}"
                task.status = TaskStatus.FAILED
                task.finished_at = time.time()
                self._append_log(task, "error", task.error)
                self._current_task_id = None
                return

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._current_task_id = None
        self._append_log(
            task,
            "info",
            f"register task finished (success={task.success_count}, fail={task.fail_count}, total={task.count})",
        )

    def _register_one(self, task: RegisterTask) -> dict:
        domain = task.domain
        task_provider = task.mail_provider
        log_cb = lambda level, message: self._append_log(task, level, message)

        temp_mail_provider = (config.basic.temp_mail_provider or "duckmail").lower()
        if task_provider in ("duckmail", "gptmail", "freemail", "moemail"):
            temp_mail_provider = task_provider

        if temp_mail_provider == "freemail" and not config.basic.freemail_jwt_token:
            return {"success": False, "error": "Freemail JWT Token missing"}

        client = create_temp_mail_client(
            temp_mail_provider,
            domain=domain,
            log_cb=log_cb,
        )

        if not client.register_account(domain=domain):
            return {"success": False, "error": f"{temp_mail_provider} register failed"}

        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless
        browser_proxy, _ = parse_proxy_setting(config.basic.proxy_for_auth)

        mail_config_for_subprocess = {
            "mail_address": client.email,
            "mail_password": getattr(client, "password", "") or "",
        }
        for attr in (
            "proxy_url",
            "no_proxy",
            "direct_fallback",
            "base_url",
            "api_key",
            "jwt_token",
            "verify_ssl",
        ):
            val = getattr(client, attr, None)
            if val is not None:
                mail_config_for_subprocess[attr.replace("proxy_url", "proxy")] = val

        if temp_mail_provider == "moemail":
            mail_config_for_subprocess["mail_password"] = getattr(client, "email_id", "") or getattr(client, "password", "")

        subprocess_params = {
            "action": "login",
            "email": client.email,
            "browser_engine": browser_engine,
            "headless": headless,
            "proxy": browser_proxy or "",
            "user_agent": self.user_agent,
            "mail_provider": temp_mail_provider,
            "mail_config": mail_config_for_subprocess,
        }

        from core.subprocess_worker import run_browser_in_subprocess

        result = run_browser_in_subprocess(
            subprocess_params,
            log_callback=log_cb,
            timeout=300,
            cancel_check=lambda: task.cancel_requested,
        )

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "automation failed")}

        config_data = result["config"]
        config_data["mail_provider"] = temp_mail_provider
        config_data["mail_address"] = client.email

        beijing_tz = timezone(timedelta(hours=8))
        if not config_data.get("account_expires_at"):
            config_data["account_expires_at"] = (
                datetime.now(beijing_tz) + timedelta(days=30)
            ).strftime("%Y-%m-%d %H:%M:%S")

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

        return {"success": True, "email": client.email, "config": config_data}
