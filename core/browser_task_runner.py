#!/usr/bin/env python3
"""
浏览器自动化子进程入口脚本（独立进程）

通过 subprocess.Popen 启动，stdin 接收 JSON 参数，
stderr 输出日志（LOG:level:message），
stdout 输出结果（RESULT:{json}）。

所有重量级模块（DrissionPage, selenium, undetected-chromedriver）
只在此脚本中导入，主进程不加载。
"""

import atexit
import json
import os
import sys
import traceback

# 确保项目根目录在 sys.path 中（从 core/ 目录往上一级）
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.browser_process_utils import is_browser_related_process


def _final_browser_cleanup():
    """子进程退出前的最终清理：杀掉自身的所有浏览器子孙进程，防止内存泄漏。"""
    try:
        import psutil
        current = psutil.Process()
        children = current.children(recursive=True)
        for child in children:
            try:
                matched, _ = is_browser_related_process(child.name(), child.cmdline())
                if matched:
                    child.kill()
                    try:
                        child.wait(timeout=3)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # 强制垃圾回收
    try:
        import gc
        gc.collect()
    except Exception:
        pass

# 注册退出清理钩子（无论正常退出还是异常退出都会执行）
atexit.register(_final_browser_cleanup)


def _log(level: str, message: str) -> None:
    """通过 stderr 向主进程发送日志。"""
    try:
        sys.stderr.write(f"LOG:{level}:{message}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _send_result(result: dict) -> None:
    """通过 stdout 向主进程发送结果 JSON。"""
    sys.stdout.write("RESULT:" + json.dumps(result, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _create_mail_client(params: dict):
    """根据参数创建邮件客户端实例。"""
    mail_provider = params.get("mail_provider", "")
    mail_config = params.get("mail_config", {})
    action = params.get("action", "login")

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
            log_callback=_log,
        )
        mail_address = mail_config.get("mail_address", params.get("email", ""))
        client.set_credentials(mail_address)
        return client

    # 临时邮箱提供商（duckmail, freemail, gptmail, moemail）
    from core.mail_providers import create_temp_mail_client

    # 构建工厂函数参数
    factory_kwargs = {"log_cb": _log}
    for key in ("proxy", "no_proxy", "direct_fallback", "base_url",
                "api_key", "jwt_token", "verify_ssl", "domain"):
        val = mail_config.get(key)
        if val is not None:
            factory_kwargs[key] = val

    client = create_temp_mail_client(mail_provider, **factory_kwargs)

    # 刷新流程：恢复已有凭据
    if action == "login":
        mail_address = mail_config.get("mail_address", params.get("email", ""))
        mail_password = mail_config.get("mail_password", "")
        client.set_credentials(mail_address, mail_password)
        # moemail 需要设置 email_id
        if mail_provider == "moemail" and mail_password:
            client.email_id = mail_password

    # 注册流程：注册新邮箱
    if action == "register":
        _log("info", f"📧 步骤 1/3: 注册临时邮箱 (提供商={mail_provider})...")
        domain = params.get("domain")
        if not client.register_account(domain=domain):
            return None  # 注册失败，由调用方处理
        _log("info", f"✅ 邮箱注册成功: {client.email}")

    return client


def _run_task(params: dict) -> dict:
    """执行浏览器自动化任务。"""
    action = params.get("action", "login")
    email = params.get("email", "")
    browser_engine = params.get("browser_engine", "dp")
    headless = params.get("headless", True)
    proxy = params.get("proxy", "")
    user_agent = params.get("user_agent", "")

    # 1. 创建邮件客户端
    mail_client = _create_mail_client(params)

    if action == "register" and mail_client is None:
        provider = params.get("mail_provider", "unknown")
        return {"success": False, "error": f"{provider} 注册失败"}

    # 注册流程中邮箱由邮件客户端创建
    if action == "register" and mail_client is not None:
        email = mail_client.email

    # 2. 创建浏览器自动化实例
    _log("info", f"🌐 启动浏览器 (引擎={browser_engine}, 无头模式={headless}, 代理={proxy or '无'})...")

    if browser_engine == "dp":
        from core.gemini_automation import GeminiAutomation
        automation = GeminiAutomation(
            user_agent=user_agent,
            proxy=proxy,
            headless=headless,
            log_callback=_log,
        )
    else:
        from core.gemini_automation_uc import GeminiAutomationUC
        if headless:
            _log("warning", "⚠️ UC 引擎无头模式反检测能力弱，强制使用有头模式")
            headless = False
        automation = GeminiAutomationUC(
            user_agent=user_agent,
            proxy=proxy,
            headless=headless,
            log_callback=_log,
        )

    # 3. 执行登录
    _log("info", "🔐 执行 Gemini 自动登录...")
    try:
        result = automation.login_and_extract(email, mail_client)
    except Exception as exc:
        _log("error", f"❌ 自动登录异常: {exc}")
        return {"success": False, "error": str(exc)}

    # 4. 注册流程附加邮箱信息
    if action == "register" and result.get("success") and mail_client is not None:
        result["email"] = email
        result["mail_password"] = getattr(mail_client, "password", "")
        result["mail_email_id"] = getattr(mail_client, "email_id", "")

    return result


def main():
    """主入口：从 stdin 读取参数，执行任务，输出结果。"""
    try:
        # 从 stdin 读取 JSON 参数
        raw_input = sys.stdin.read()
        params = json.loads(raw_input)
    except Exception as exc:
        _send_result({"success": False, "error": f"参数解析失败: {exc}"})
        sys.exit(1)

    try:
        result = _run_task(params)
        _send_result(result)
    except Exception as exc:
        tb = traceback.format_exc()
        _log("error", f"❌ 子进程异常: {exc}")
        _send_result({"success": False, "error": str(exc), "traceback": tb})
        sys.exit(1)


if __name__ == "__main__":
    main()
