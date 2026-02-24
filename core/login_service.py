from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.account import bulk_delete_accounts, load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core.mail_providers import create_temp_mail_client
from core.microsoft_mail_client import MicrosoftMailClient
from core.outbound_proxy import OutboundProxyConfig

logger = logging.getLogger("gemini.login")

MIN_AVAILABLE_ACCOUNTS = 21
ACCOUNT_EXPIRY_RECYCLE_HOURS = 24


@dataclass
class LoginTask(BaseTask):
    account_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["account_ids"] = self.account_ids
        return data


class LoginService(BaseTaskService[LoginTask]):
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
        register_service: Optional[Any] = None,
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
        self._auto_refresh_paused = True
        self.register_service = register_service

    def _get_active_account_ids(self) -> set:
        active_ids = set()
        for task in self._tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                active_ids.update(task.account_ids)
        return active_ids

    async def start_login(self, account_ids: List[str]) -> Optional[LoginTask]:
        """Queue a login/refresh task."""
        async with self._lock:
            active_ids = self._get_active_account_ids()
            new_account_ids = [aid for aid in account_ids if aid not in active_ids]

            if not new_account_ids:
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
            self._append_log(task, "info", f"create refresh task (accounts={len(task.account_ids)})")
            await self._enqueue_task(task)
            return task

    def _execute_task(self, task: LoginTask):
        return self._run_login_async(task)

    async def _run_login_async(self, task: LoginTask) -> None:
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"refresh task started (accounts={len(task.account_ids)})")

        accounts_snapshot = {
            acc.get("id"): acc
            for acc in load_accounts_from_source()
            if isinstance(acc, dict) and acc.get("id")
        }
        pending_configs: Dict[str, dict] = {}

        for idx, account_id in enumerate(task.account_ids, 1):
            if idx > 1:
                await asyncio.sleep(random.uniform(2, 5))

            if task.cancel_requested:
                self._append_log(task, "warning", f"login task cancelled: {task.cancel_reason or 'cancelled'}")
                break

            try:
                self._append_log(task, "info", f"progress: {idx}/{len(task.account_ids)}")
                result = await loop.run_in_executor(
                    self._executor,
                    self._refresh_one,
                    account_id,
                    task,
                    accounts_snapshot.get(account_id),
                )
            except TaskCancelledError:
                task.cancel_requested = True
                task.cancel_reason = task.cancel_reason or "cancelled"
                self._append_log(task, "warning", f"login task cancelled: {task.cancel_reason}")
                break
            except Exception as exc:
                result = {"success": False, "email": account_id, "error": str(exc)}

            task.progress += 1
            self._append_result(task, result)

            if result.get("success"):
                task.success_count += 1
                self._append_log(task, "info", f"refresh success: {account_id}")
                cfg = result.get("config")
                if isinstance(cfg, dict):
                    pending_configs[account_id] = cfg
            else:
                task.fail_count += 1
                self._append_log(task, "error", f"refresh failed: {account_id} | {result.get('error', 'unknown error')}")

        if pending_configs:
            try:
                accounts_data = load_accounts_from_source()
                updated_count = 0
                for acc in accounts_data:
                    acc_id = acc.get("id")
                    if acc_id in pending_configs:
                        acc.update(pending_configs[acc_id])
                        updated_count += 1
                if updated_count > 0:
                    self._apply_accounts_update(accounts_data)
                    self._append_log(task, "info", f"saved refresh configs: {updated_count}")
            except Exception as exc:
                task.error = f"save refresh config failed: {str(exc)[:200]}"
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
        self._append_log(task, "info", f"login task finished ({task.success_count}/{len(task.account_ids)})")
        self._current_task_id = None

    def _refresh_one(self, account_id: str, task: LoginTask, account_snapshot: Optional[dict] = None) -> dict:
        """Refresh one account and return new config payload without persisting."""
        account = account_snapshot
        if not account:
            accounts = load_accounts_from_source()
            account = next((acc for acc in accounts if acc.get("id") == account_id), None)

        if not account:
            return {"success": False, "email": account_id, "error": "account not found"}

        if account.get("disabled"):
            return {"success": False, "email": account_id, "error": "account disabled"}

        mail_provider = (account.get("mail_provider") or "").lower()
        if not mail_provider:
            if account.get("mail_client_id") or account.get("mail_refresh_token"):
                mail_provider = "microsoft"
            else:
                mail_provider = "duckmail"

        mail_password = account.get("mail_password") or account.get("email_password")
        mail_client_id = account.get("mail_client_id")
        mail_refresh_token = account.get("mail_refresh_token")
        mail_tenant = account.get("mail_tenant") or "consumers"

        def log_cb(level: str, message: str) -> None:
            self._append_log(task, level, f"[{account_id}] {message}")

        outbound: OutboundProxyConfig = config.basic.outbound_proxy
        use_outbound_proxy = outbound.is_configured()
        proxy_url = outbound.to_proxy_url(config.security.admin_key) if use_outbound_proxy else (config.basic.proxy or "")
        no_proxy = outbound.no_proxy if use_outbound_proxy else ""
        direct_fallback = outbound.direct_fallback if use_outbound_proxy else False

        if mail_provider == "microsoft":
            if not mail_client_id or not mail_refresh_token:
                return {"success": False, "email": account_id, "error": "Microsoft OAuth config missing"}
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
        elif mail_provider in ("duckmail", "moemail", "freemail", "gptmail"):
            if mail_provider not in ("freemail", "gptmail") and not mail_password:
                return {"success": False, "email": account_id, "error": "mail password missing"}
            if mail_provider == "freemail" and not account.get("mail_jwt_token") and not config.basic.freemail_jwt_token:
                return {"success": False, "email": account_id, "error": "Freemail JWT Token missing"}

            mail_address = account.get("mail_address") or account_id
            account_config = {
                "proxy": proxy_url,
                "no_proxy": no_proxy,
                "direct_fallback": direct_fallback,
            }
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

            client = create_temp_mail_client(mail_provider, log_cb=log_cb, **account_config)
            client.set_credentials(mail_address, mail_password)
            if mail_provider == "moemail":
                client.email_id = mail_password
        else:
            return {"success": False, "email": account_id, "error": f"unsupported mail provider: {mail_provider}"}

        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless

        from core.proxy_utils import parse_proxy_setting

        browser_proxy = proxy_url if proxy_url else parse_proxy_setting(config.basic.proxy_for_auth)[0]

        mail_config_for_subprocess = {
            "mail_address": account.get("mail_address") or account_id,
            "mail_password": mail_password or "",
            "proxy": proxy_url,
            "no_proxy": no_proxy,
            "direct_fallback": direct_fallback,
        }
        if mail_provider == "microsoft":
            mail_config_for_subprocess["client_id"] = mail_client_id or ""
            mail_config_for_subprocess["refresh_token"] = mail_refresh_token or ""
            mail_config_for_subprocess["tenant"] = mail_tenant
        else:
            for cfg_key in ("mail_base_url", "mail_api_key", "mail_jwt_token", "mail_verify_ssl", "mail_domain"):
                val = account.get(cfg_key)
                if val is not None:
                    mail_config_for_subprocess[cfg_key.replace("mail_", "", 1)] = val

        subprocess_params = {
            "action": "login",
            "email": account_id,
            "browser_engine": browser_engine,
            "headless": headless,
            "proxy": browser_proxy or "",
            "user_agent": self.user_agent,
            "mail_provider": mail_provider,
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
            return {"success": False, "email": account_id, "error": result.get("error", "automation failed")}

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
            config_data["mail_password"] = mail_password or ""
        elif mail_provider == "duckmail":
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_password"] = mail_password or ""
        else:
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_password"] = ""

        config_data["disabled"] = account.get("disabled", False)
        return {"success": True, "email": account_id, "config": config_data}

    def _get_expiring_accounts(self) -> List[str]:
        accounts = load_accounts_from_source()
        expiring: List[str] = []
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)
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
            elif mail_provider in ("duckmail", "moemail"):
                if not mail_password:
                    continue
            elif mail_provider == "freemail":
                if not account.get("mail_jwt_token") and not config.basic.freemail_jwt_token:
                    continue
            elif mail_provider == "gptmail":
                pass
            else:
                continue

            expires_at = account.get("expires_at")
            if not expires_at:
                continue

            try:
                expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=beijing_tz)
                remaining = (expire_time - now).total_seconds() / 3600
            except Exception:
                continue

            if remaining <= config.basic.refresh_window_hours:
                expiring.append(account_id)

        return expiring

    def _parse_beijing_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            beijing_tz = timezone(timedelta(hours=8))
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=beijing_tz)
        except Exception:
            return None

    def _is_session_expired(self, account: dict) -> bool:
        expires_at = self._parse_beijing_datetime(account.get("expires_at"))
        if not expires_at:
            return False
        return expires_at <= datetime.now(timezone(timedelta(hours=8)))

    def _get_near_account_expiry_ids(self) -> List[str]:
        accounts = load_accounts_from_source()
        active_ids = self._get_active_account_ids()
        now = datetime.now(timezone(timedelta(hours=8)))
        near_expiry_ids: List[str] = []

        for account in accounts:
            account_id = account.get("id")
            if not account_id or account.get("disabled") or account_id in active_ids:
                continue

            account_expires_at = self._parse_beijing_datetime(account.get("account_expires_at"))
            if not account_expires_at:
                continue

            remaining_hours = (account_expires_at - now).total_seconds() / 3600
            if remaining_hours < ACCOUNT_EXPIRY_RECYCLE_HOURS:
                near_expiry_ids.append(account_id)

        return near_expiry_ids

    def _is_rate_limited_cooldown(self, account_id: str) -> bool:
        account_mgr = getattr(self.multi_account_mgr, "accounts", {}).get(account_id)
        if not account_mgr:
            return False

        try:
            cooldown_seconds, cooldown_reason = account_mgr.get_cooldown_info()
            return cooldown_seconds > 0 and cooldown_reason == "限流冷却"
        except Exception:
            return False

    def _compute_available_account_count(self) -> int:
        accounts = load_accounts_from_source()
        available = 0
        now = datetime.now(timezone(timedelta(hours=8)))
        for account in accounts:
            if account.get("disabled"):
                continue

            account_expires = self._parse_beijing_datetime(account.get("account_expires_at"))
            if account_expires:
                remaining_hours = (account_expires - now).total_seconds() / 3600
                if remaining_hours < ACCOUNT_EXPIRY_RECYCLE_HOURS:
                    continue

            available += 1
        return available

    async def check_and_recycle_expired_accounts(self) -> None:
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping recycle")
            return

        near_expiry_ids = self._get_near_account_expiry_ids()
        delete_candidates = [
            account_id for account_id in near_expiry_ids
            if not self._is_rate_limited_cooldown(account_id)
        ]

        skipped_cooldown = sorted(set(near_expiry_ids) - set(delete_candidates))
        if skipped_cooldown:
            logger.info(
                "[LOGIN] skip recycle for %d cooldown accounts: %s",
                len(skipped_cooldown),
                ", ".join(skipped_cooldown),
            )

        if delete_candidates:
            try:
                global_stats = self.global_stats_provider() or {}
                new_mgr, success_count, errors = bulk_delete_accounts(
                    delete_candidates,
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
                logger.info(
                    "[LOGIN] recycled %d/%d near-expiry accounts",
                    success_count,
                    len(delete_candidates),
                )
                if errors:
                    logger.warning("[LOGIN] recycle account errors: %s", "; ".join(errors))
            except Exception as exc:
                logger.error("[LOGIN] recycle accounts failed: %s", exc)

        available_count = self._compute_available_account_count()
        deficit = max(0, MIN_AVAILABLE_ACCOUNTS - available_count)
        if deficit <= 0:
            logger.debug("[LOGIN] available accounts=%d, no replenish needed", available_count)
            return

        if not self.register_service:
            logger.warning(
                "[LOGIN] available accounts=%d (<%d) but register service unavailable",
                available_count,
                MIN_AVAILABLE_ACCOUNTS,
            )
            return

        try:
            task = await self.register_service.start_register(count=deficit)
            logger.info(
                "[LOGIN] available accounts=%d, replenish deficit=%d queued task=%s",
                available_count,
                deficit,
                task.id,
            )
        except Exception as exc:
            logger.warning("[LOGIN] replenish enqueue failed (deficit=%d): %s", deficit, exc)

    async def check_and_refresh(self) -> Optional[LoginTask]:
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping refresh")
            return None

        expiring_accounts = self._get_expiring_accounts()
        if not expiring_accounts:
            logger.debug("[LOGIN] no accounts need refresh")
            return None

        logger.info("[LOGIN] expiring accounts=%d, enqueue refresh", len(expiring_accounts))
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
                await self.check_and_recycle_expired_accounts()
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
        self._auto_refresh_paused = True
        logger.info("[LOGIN] auto-refresh paused (runtime only)")

    def resume_auto_refresh(self) -> bool:
        was_paused = self._auto_refresh_paused
        self._auto_refresh_paused = False
        logger.info("[LOGIN] auto-refresh resumed")
        return was_paused

    def is_auto_refresh_paused(self) -> bool:
        return self._auto_refresh_paused

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[LOGIN] stopping polling")
