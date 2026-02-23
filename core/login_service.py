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
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC
from core.microsoft_mail_client import MicrosoftMailClient
from core.outbound_proxy import OutboundProxyConfig

logger = logging.getLogger("gemini.login")

MIN_AVAILABLE_ACCOUNTS = 21
ACCOUNT_EXPIRY_RECYCLE_HOURS = 24


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
        self._auto_refresh_paused = True  # 运行时开关：默认暂停（不自动刷新）
        self.register_service = register_service

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
            # 队列平滑：除第一个账号外，每个账号之间随机等待 2-5 秒
            if idx > 1:
                delay = random.uniform(2, 5)
                # self._append_log(task, "info", f"⏳ 等待 {delay:.1f} 秒...")
                await asyncio.sleep(delay)

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
        elif mail_provider in ("duckmail", "moemail", "freemail", "gptmail"):
            if mail_provider not in ("freemail", "gptmail") and not mail_password:
                error_message = "邮箱密码缺失" if mail_provider == "duckmail" else "mail password (email_id) missing"
                return {"success": False, "email": account_id, "error": error_message}
            if mail_provider == "freemail" and not account.get("mail_jwt_token") and not config.basic.freemail_jwt_token:
                return {"success": False, "email": account_id, "error": "Freemail JWT Token 未配置"}

            # 创建邮件客户端，优先使用账户级别配置
            mail_address = account.get("mail_address") or account_id

            # 构建账户级别的配置参数
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
        
        # 优先使用账户级别代理，否则使用全局配置的账户操作代理
        from core.proxy_utils import parse_proxy_setting
        browser_proxy = proxy_url if proxy_url else parse_proxy_setting(config.basic.proxy_for_auth)[0]

        # ---- 构建子进程参数（所有值在主进程中读好）----
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
            # 临时邮箱：透传账户级配置（工厂函数会自动回退到全局配置）
            for cfg_key in ("mail_base_url", "mail_api_key", "mail_jwt_token", "mail_verify_ssl", "mail_domain"):
                val = account.get(cfg_key)
                if val is not None:
                    # 去掉 mail_ 前缀映射到工厂参数名
                    factory_key = cfg_key.replace("mail_", "", 1)
                    mail_config_for_subprocess[factory_key] = val

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
        for account in accounts:
            if account.get("disabled"):
                continue
            if self._is_session_expired(account):
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

        # 优化策略：
        # 1. 显示总共过期数量
        # 2. 原限制单次10个已取消，现在一次性全部刷新
        total_expiring = len(expiring_accounts)
        
        accounts_to_refresh = expiring_accounts
        planned_count = len(accounts_to_refresh)
        
        logger.info(f"[LOGIN] 当前共有 {total_expiring} 个账号过期，本次计划刷新全部 {planned_count} 个")

        try:
            return await self.start_login(accounts_to_refresh)
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
