"""
浏览器自动化子进程 Worker

将 DrissionPage / undetected-chromedriver 等重量级库的 import 和执行
隔离在独立子进程中。子进程退出后 OS 自动回收所有内存（C 扩展、
Chromium 共享内存、glibc malloc 碎片），使主进程内存保持在 ~100MB。

主进程通过 multiprocessing.Queue 接收实时日志和最终结果。
"""

import glob
import logging
import multiprocessing as mp
import os
import platform
import signal
import time
import traceback
from queue import Empty
from typing import Callable, Optional

logger = logging.getLogger("gemini.browser_worker")

# 日志队列哨兵值：表示子进程结束
_LOG_SENTINEL = None
# 子进程超时默认值（秒）
_DEFAULT_TIMEOUT = 300


# ---------------------------------------------------------------------------
#  子进程入口（所有浏览器相关 import 都在这里）
# ---------------------------------------------------------------------------

def _run_browser_task(
    task_params: dict,
    result_queue: mp.Queue,
    log_queue: mp.Queue,
) -> None:
    """
    在独立子进程中执行浏览器自动化任务。

    所有重量级库（DrissionPage、selenium、undetected-chromedriver）
    只在此函数内部导入，不污染主进程的内存空间。
    """
    try:
        # ---- 子进程内部的日志回调 ----
        def log_cb(level: str, message: str) -> None:
            try:
                log_queue.put_nowait((level, message))
            except Exception:
                pass

        action = task_params.get("action", "login")
        email = task_params["email"]
        browser_engine = task_params.get("browser_engine", "dp")
        headless = task_params.get("headless", True)
        proxy = task_params.get("proxy", "")
        user_agent = task_params.get("user_agent", "")

        # ---- 创建邮件客户端（在子进程中） ----
        mail_client = _create_mail_client(task_params, log_cb)

        # ---- 注册流程：先注册邮箱 ----
        if action == "register" and mail_client is not None:
            log_cb("info", f"📧 步骤 1/3: 注册临时邮箱 (提供商={task_params.get('mail_provider', 'unknown')})...")
            if not mail_client.register_account(domain=task_params.get("domain")):
                provider = task_params.get("mail_provider", "unknown")
                result_queue.put({"success": False, "error": f"{provider} 注册失败"})
                return
            # 注册成功后更新 email
            email = mail_client.email
            log_cb("info", f"✅ 邮箱注册成功: {email}")

        # ---- 创建浏览器自动化实例 ----
        log_cb("info", f"🌐 启动浏览器 (引擎={browser_engine}, 无头模式={headless}, 代理={proxy or '无'})...")

        if browser_engine == "dp":
            from core.gemini_automation import GeminiAutomation
            automation = GeminiAutomation(
                user_agent=user_agent,
                proxy=proxy,
                headless=headless,
                log_callback=log_cb,
            )
        else:
            from core.gemini_automation_uc import GeminiAutomationUC
            if headless:
                log_cb("warning", "⚠️ UC 引擎无头模式反检测能力弱，强制使用有头模式")
                headless = False
            automation = GeminiAutomationUC(
                user_agent=user_agent,
                proxy=proxy,
                headless=headless,
                log_callback=log_cb,
            )

        # ---- 执行登录 ----
        log_cb("info", "🔐 执行 Gemini 自动登录...")
        result = automation.login_and_extract(email, mail_client)

        # 注册流程附加邮箱信息
        if action == "register" and result.get("success") and mail_client is not None:
            result["email"] = email
            result["mail_password"] = getattr(mail_client, "password", "")
            result["mail_email_id"] = getattr(mail_client, "email_id", "")

        result_queue.put(result)

    except Exception as exc:
        tb = traceback.format_exc()
        try:
            log_queue.put_nowait(("error", f"❌ 子进程异常: {exc}"))
        except Exception:
            pass
        result_queue.put({"success": False, "error": str(exc), "traceback": tb})
    finally:
        # 发送哨兵，通知主进程日志流结束
        try:
            log_queue.put_nowait(_LOG_SENTINEL)
        except Exception:
            pass


def _create_mail_client(task_params: dict, log_cb: Callable):
    """在子进程中创建邮件客户端实例。"""
    mail_provider = task_params.get("mail_provider", "")
    mail_config = task_params.get("mail_config", {})
    action = task_params.get("action", "login")

    if not mail_provider:
        return None

    if mail_provider == "microsoft":
        from core.microsoft_mail_client import MicrosoftMailClient
        client = MicrosoftMailClient(
            client_id=mail_config.get("client_id", ""),
            refresh_token=mail_config.get("refresh_token", ""),
            tenant=mail_config.get("tenant", "consumers"),
            proxy=mail_config.get("proxy", ""),
            no_proxy=mail_config.get("no_proxy", ""),
            direct_fallback=mail_config.get("direct_fallback", False),
            log_callback=log_cb,
        )
        mail_address = mail_config.get("mail_address", task_params.get("email", ""))
        client.set_credentials(mail_address)
        return client

    # 临时邮箱提供商（duckmail, freemail, gptmail, moemail）
    from core.mail_providers import create_temp_mail_client

    # 构建 create_temp_mail_client 的参数
    factory_kwargs = {
        "log_cb": log_cb,
    }
    # 透传所有邮件配置参数
    for key in ("proxy", "no_proxy", "direct_fallback", "base_url",
                "api_key", "jwt_token", "verify_ssl", "domain"):
        if key in mail_config:
            factory_kwargs[key] = mail_config[key]

    client = create_temp_mail_client(mail_provider, **factory_kwargs)

    # 刷新流程：恢复已有凭据
    if action == "login":
        mail_address = mail_config.get("mail_address", task_params.get("email", ""))
        mail_password = mail_config.get("mail_password", "")
        client.set_credentials(mail_address, mail_password)
        # moemail 需要设置 email_id
        if mail_provider == "moemail" and mail_password:
            client.email_id = mail_password

    return client


# ---------------------------------------------------------------------------
#  /dev/shm 清理（子进程退出后，主进程调用）
# ---------------------------------------------------------------------------

def _cleanup_shm() -> None:
    """清理 Chromium 可能残留的 /dev/shm 文件。"""
    if platform.system() != "Linux":
        return
    try:
        shm_files = glob.glob("/dev/shm/.com.google.Chrome.*") + \
                    glob.glob("/dev/shm/.org.chromium.*")
        for f in shm_files:
            try:
                os.remove(f)
            except OSError:
                pass
        if shm_files:
            logger.info(f"[BROWSER-WORKER] 清理了 {len(shm_files)} 个 /dev/shm 残留文件")
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  主进程调用入口
# ---------------------------------------------------------------------------

def run_in_subprocess(
    task_params: dict,
    log_callback: Callable[[str, str], None],
    timeout: int = _DEFAULT_TIMEOUT,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    在独立子进程中执行浏览器自动化任务（主进程调用）。

    Args:
        task_params: 任务参数字典（所有值必须可 pickle 序列化）
        log_callback: 日志回调函数 (level, message)
        timeout: 超时秒数
        cancel_check: 可选的取消检查函数，返回 True 表示应取消

    Returns:
        结果字典，至少包含 {"success": bool, ...}
    """
    result_queue = mp.Queue(maxsize=1)
    log_queue = mp.Queue()

    proc = mp.Process(
        target=_run_browser_task,
        args=(task_params, result_queue, log_queue),
        daemon=True,  # 主进程退出时自动终止子进程
    )
    proc.start()
    child_pid = proc.pid
    logger.info(f"[BROWSER-WORKER] 子进程已启动 (PID={child_pid})")

    start_time = time.monotonic()
    log_ended = False  # 是否收到日志哨兵

    try:
        while True:
            elapsed = time.monotonic() - start_time

            # ---- 检查超时 ----
            if elapsed > timeout:
                log_callback("error", f"⏰ 浏览器子进程超时 ({timeout}s)，正在终止...")
                _terminate_process(proc)
                return {"success": False, "error": f"浏览器操作超时 ({timeout}s)"}

            # ---- 检查取消 ----
            if cancel_check and cancel_check():
                log_callback("warning", "🚫 收到取消请求，正在终止浏览器子进程...")
                _terminate_process(proc)
                return {"success": False, "error": "任务已取消"}

            # ---- 转发日志 ----
            _drain_log_queue(log_queue, log_callback)

            # ---- 检查子进程是否结束 ----
            if not proc.is_alive():
                # 子进程已退出，最后再排空日志
                _drain_log_queue(log_queue, log_callback)
                break

            # 短暂等待，避免空转
            proc.join(timeout=0.3)

    except Exception as exc:
        log_callback("error", f"❌ 子进程管理异常: {exc}")
        _terminate_process(proc)
        return {"success": False, "error": f"子进程管理异常: {exc}"}
    finally:
        # 确保子进程已终止
        if proc.is_alive():
            _terminate_process(proc)
        # 清理 /dev/shm 残留
        _cleanup_shm()
        logger.info(f"[BROWSER-WORKER] 子进程已结束 (PID={child_pid}, exitcode={proc.exitcode})")

    # ---- 获取结果 ----
    try:
        result = result_queue.get_nowait()
    except Empty:
        exitcode = proc.exitcode
        if exitcode and exitcode < 0:
            sig_name = _signal_name(-exitcode)
            return {"success": False, "error": f"子进程被信号终止 ({sig_name})"}
        return {"success": False, "error": f"子进程异常退出 (exitcode={exitcode})"}

    return result


def _drain_log_queue(
    log_queue: mp.Queue,
    log_callback: Callable[[str, str], None],
) -> None:
    """排空日志队列，将所有日志转发给回调。"""
    while True:
        try:
            item = log_queue.get_nowait()
        except Empty:
            break
        if item is _LOG_SENTINEL:
            break
        level, message = item
        try:
            log_callback(level, message)
        except Exception:
            pass


def _terminate_process(proc: mp.Process, wait: float = 5.0) -> None:
    """优雅终止子进程：先 SIGTERM，超时后 SIGKILL。"""
    if not proc.is_alive():
        return

    pid = proc.pid
    try:
        if platform.system() == "Linux" and pid:
            # 先发 SIGTERM 让子进程有机会清理浏览器
            os.kill(pid, signal.SIGTERM)
            proc.join(timeout=wait)
            if proc.is_alive():
                os.kill(pid, signal.SIGKILL)
                proc.join(timeout=2)
        else:
            proc.terminate()
            proc.join(timeout=wait)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
    except (ProcessLookupError, OSError):
        pass


def _signal_name(signum: int) -> str:
    """将信号编号转换为名称。"""
    try:
        return signal.Signals(signum).name
    except (ValueError, AttributeError):
        return f"signal {signum}"
