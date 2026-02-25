"""
Gemini自动化登录模块（用于新账号注册）
"""
import os
import json
import random
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from DrissionPage import ChromiumPage, ChromiumOptions
from core.base_task_service import TaskCancelledError


# 常量
AUTH_HOME_URL = "https://auth.business.gemini.google/"
DEFAULT_XSRF_TOKEN = "KdLRzKwwBTD5wo8nUollAbY6cW0"

# Linux 下常见的 Chromium 路径
CHROMIUM_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]


def _find_chromium_path() -> Optional[str]:
    """查找可用的 Chromium/Chrome 浏览器路径"""
    for path in CHROMIUM_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class GeminiAutomation:
    """Gemini自动化登录"""

    def __init__(
        self,
        user_agent: str = "",
        proxy: str = "",
        headless: bool = True,
        timeout: int = 60,
        log_callback=None,
    ) -> None:
        self.user_agent = user_agent or self._get_ua()
        self.proxy = proxy
        self.headless = headless
        self.timeout = timeout
        self.log_callback = log_callback
        self._page = None
        self._user_data_dir = None
        self._last_send_error = ""

    def stop(self) -> None:
        """外部请求停止：尽力关闭浏览器实例。"""
        page = self._page
        if page:
            try:
                page.quit()
            except Exception:
                pass

    def login_and_extract(self, email: str, mail_client) -> dict:
        """执行登录并提取配置"""
        page = None
        user_data_dir = None
        try:
            page = self._create_page()
            user_data_dir = getattr(page, 'user_data_dir', None)
            self._page = page
            self._user_data_dir = user_data_dir
            return self._run_flow(page, email, mail_client)
        except TaskCancelledError:
            raise
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass
            self._page = None
            self._cleanup_user_data(user_data_dir)
            self._user_data_dir = None

    def _create_page(self) -> ChromiumPage:
        """创建浏览器页面"""
        options = ChromiumOptions()

        # 自动检测 Chromium 浏览器路径（Linux/Docker 环境）
        chromium_path = _find_chromium_path()
        if chromium_path:
            options.set_browser_path(chromium_path)

        options.set_argument("--incognito")
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-setuid-sandbox")
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--window-size=1280,800")
        options.set_user_agent(self.user_agent)

        # 语言设置（确保使用中文界面）
        options.set_argument("--lang=zh-CN")
        options.set_pref("intl.accept_languages", "zh-CN,zh")

        if self.proxy:
            options.set_argument(f"--proxy-server={self.proxy}")

        if self.headless:
            # 使用新版无头模式，更接近真实浏览器
            options.set_argument("--headless=new")
            options.set_argument("--disable-gpu")
            options.set_argument("--no-first-run")
            options.set_argument("--disable-extensions")
            # 反检测参数
            options.set_argument("--disable-infobars")
            options.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        options.auto_port()
        page = ChromiumPage(options)
        page.set.timeouts(self.timeout)

        # 反检测：注入脚本隐藏自动化特征
        if self.headless:
            try:
                page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source="""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    window.chrome = {runtime: {}};

                    // 额外的反检测措施
                    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 1});
                    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                    Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});

                    // 隐藏 headless 特征
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

                    // 模拟真实的 permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({state: Notification.permission}) :
                            originalQuery(parameters)
                    );
                """)
            except Exception:
                pass

        return page

    def _run_flow(self, page, email: str, mail_client) -> dict:
        """执行登录流程"""

        # 记录任务开始时间，用于邮件时间过滤（全流程固定，不随重发更新）
        from datetime import datetime
        task_start_time = datetime.now()

        # Step 1: 导航到首页并设置 Cookie
        self._log("info", f"🌐 打开登录页面: {email}")

        page.get(AUTH_HOME_URL, timeout=self.timeout)
        time.sleep(2)

        # 设置两个关键 Cookie
        try:
            self._log("info", "🍪 设置认证 Cookies...")
            page.set.cookies({
                "name": "__Host-AP_SignInXsrf",
                "value": DEFAULT_XSRF_TOKEN,
                "url": AUTH_HOME_URL,
                "path": "/",
                "secure": True,
            })
            # 添加 reCAPTCHA Cookie
            page.set.cookies({
                "name": "_GRECAPTCHA",
                "value": "09ABCL...",
                "url": "https://google.com",
                "path": "/",
                "secure": True,
            })
        except Exception as e:
            self._log("warning", f"⚠️ Cookie 设置失败: {e}")

        login_hint = quote(email, safe="")
        login_url = f"https://auth.business.gemini.google/login/email?continueUrl=https%3A%2F%2Fbusiness.gemini.google%2F&loginHint={login_hint}&xsrfToken={DEFAULT_XSRF_TOKEN}"

        # 提前启动网络监听，捕获默认发送
        try:
            page.listen.start(
                targets=["batchexecute", "browserinfo", "verify-oob-code"],
                is_regex=False,
                method=("GET", "POST"),
                res_type=("XHR", "FETCH", "DOCUMENT"),
            )
        except Exception:
            pass

        page.get(login_url, timeout=self.timeout)
        time.sleep(5)

        # Step 2: 检查当前页面状态
        current_url = page.url
        self._log("info", f"📍 当前 URL: {current_url}")
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            self._log("info", "✅ 已登录，提取配置")
            return self._extract_config(page, email)

        # Step 3: 点击发送验证码按钮（最多5次，每次间隔10秒）
        self._log("info", "📧 发送验证码...")
        max_send_rounds = 5
        send_round = 0
        while True:
            send_round += 1
            if self._click_send_code_button(page):
                break
            if send_round >= max_send_rounds:
                self._log("error", "❌ 验证码发送失败（可能触发风控），建议更换代理IP")
                self._save_screenshot(page, "send_code_button_failed")
                return {"success": False, "error": "send code failed after retries"}
            self._log("warning", f"⚠️ 发送失败，10秒后重试 ({send_round}/{max_send_rounds})")
            time.sleep(10)

        # Step 4: 等待验证码输入框出现
        code_input = self._wait_for_code_input(page)
        if not code_input:
            self._log("error", "❌ 验证码输入框未出现")
            self._save_screenshot(page, "code_input_missing")
            return {"success": False, "error": "code input not found"}

        # Step 5: 轮询邮件获取验证码（3次，每次5秒间隔）
        self._log("info", "📬 等待邮箱验证码...")
        code = mail_client.poll_for_code(timeout=15, interval=5, since_time=task_start_time)

        if not code:
            self._log("warning", "⚠️ 验证码超时，15秒后重新发送...")
            time.sleep(15)
            # 尝试点击重新发送按钮
            if self._click_resend_code_button(page):
                # 再次轮询验证码（3次，每次5秒间隔）
                code = mail_client.poll_for_code(timeout=15, interval=5, since_time=task_start_time)
                if not code:
                    self._log("error", "❌ 重新发送后仍未收到验证码")
                    self._save_screenshot(page, "code_timeout_after_resend")
                    return {"success": False, "error": "verification code timeout after resend"}
            else:
                self._log("error", "❌ 验证码超时且未找到重新发送按钮")
                self._save_screenshot(page, "code_timeout")
                return {"success": False, "error": "verification code timeout"}

        self._log("info", f"✅ 收到验证码: {code}")

        # Step 6: 输入验证码并提交
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or \
                     page.ele("css:input[type='tel']", timeout=2)

        if not code_input:
            self._log("error", "❌ 验证码输入框已失效")
            return {"success": False, "error": "code input expired"}

        # 尝试模拟人类输入，失败则降级到直接注入
        self._log("info", "⌨️ 输入验证码...")
        if not self._simulate_human_input(code_input, code):
            self._log("warning", "⚠️ 模拟输入失败，降级为直接输入")
            code_input.input(code, clear=True)
            time.sleep(0.5)

        # 直接使用回车提交，不再查找按钮
        self._log("info", "⏎ 提交验证码")
        code_input.input("\n")

        # Step 7: 等待页面自动重定向（提交验证码后 Google 会自动跳转）
        self._log("info", "⏳ 等待验证后跳转...")
        time.sleep(12)

        # 记录当前 URL 状态
        current_url = page.url
        self._log("info", f"📍 验证后 URL: {current_url}")

        # 检查是否还停留在验证码页面（说明提交失败）
        if "verify-oob-code" in current_url:
            self._log("error", "❌ 验证码提交失败")
            self._save_screenshot(page, "verification_submit_failed")
            return {"success": False, "error": "verification code submission failed"}

        # Step 8: 处理协议页面（如果有）
        self._handle_agreement_page(page)

        # Step 9: 检查是否已经在正确的页面
        current_url = page.url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            return self._extract_config(page, email)

        # Step 10: 如果不在正确的页面，尝试导航
        if "business.gemini.google" not in current_url:
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(5)

        # Step 11: 检查是否需要设置用户名
        if "cid" not in page.url:
            if self._handle_username_setup(page):
                time.sleep(5)

        # Step 12: 等待 URL 参数生成（csesidx 和 cid）
        if not self._wait_for_business_params(page):
            page.refresh()
            time.sleep(5)
            if not self._wait_for_business_params(page):
                self._log("error", "❌ URL 参数生成失败")
                self._save_screenshot(page, "params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # Step 13: 提取配置
        self._log("info", "🎊 登录成功，提取配置...")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """点击发送验证码按钮（如果需要）"""
        time.sleep(2)
        max_send_attempts = 5
        resend_delay_seconds = 10

        # 方法1: 直接通过ID查找
        direct_btn = page.ele("#sign-in-with-email", timeout=5)
        if direct_btn:
            for attempt in range(1, max_send_attempts + 1):
                try:
                    self._last_send_error = ""
                    direct_btn.click()
                    if self._verify_code_send_by_network(page) or self._verify_code_send_status(page):
                        self._stop_listen(page)
                        return True
                    if self._last_send_error == "captcha_check_failed":
                        self._log("error", f"❌ 触发风控，建议更换代理IP ({attempt}/{max_send_attempts})")
                    else:
                        self._log("warning", f"⚠️ 发送失败，{resend_delay_seconds}秒后重试 ({attempt}/{max_send_attempts})")
                    time.sleep(resend_delay_seconds)
                except Exception as e:
                    self._log("warning", f"⚠️ 点击失败: {e}")
            self._stop_listen(page)
            return False

        # 方法2: 通过关键词查找
        keywords = ["通过电子邮件发送验证码", "通过电子邮件发送", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw in text for kw in keywords):
                    for attempt in range(1, max_send_attempts + 1):
                        try:
                            self._last_send_error = ""
                            btn.click()
                            if self._verify_code_send_by_network(page) or self._verify_code_send_status(page):
                                self._stop_listen(page)
                                return True
                            if self._last_send_error == "captcha_check_failed":
                                self._log("error", f"❌ 触发风控，建议更换代理IP ({attempt}/{max_send_attempts})")
                            else:
                                self._log("warning", f"⚠️ 发送失败，{resend_delay_seconds}秒后重试 ({attempt}/{max_send_attempts})")
                            time.sleep(resend_delay_seconds)
                        except Exception as e:
                            self._log("warning", f"⚠️ 点击失败: {e}")
                    self._stop_listen(page)
                    return False
        except Exception as e:
            self._log("warning", f"⚠️ 搜索按钮异常: {e}")

        # 检查是否已经在验证码输入页面
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele("css:input[name='pinInput']", timeout=1)
        if code_input:
            self._stop_listen(page)
            self._log("info", "✅ 已在验证码输入页面")

            # 直接点击重新发送按钮（不管之前是否发送过）
            if self._click_resend_code_button(page):
                self._log("info", "✅ 已点击重新发送按钮")
                return True
            else:
                self._log("warning", "⚠️ 未找到重新发送按钮，继续流程")
                return True

        self._stop_listen(page)
        self._log("error", "❌ 未找到发送验证码按钮")
        return False

    def _stop_listen(self, page) -> None:
        """安全地停止网络监听"""
        try:
            if hasattr(page, 'listen') and page.listen:
                page.listen.stop()
        except Exception:
            pass

    def _verify_code_send_by_network(self, page) -> bool:
        """通过监听网络请求验证验证码是否成功发送"""
        try:
            time.sleep(1)

            packets = []
            max_wait_seconds = 6
            deadline = time.time() + max_wait_seconds
            try:
                while time.time() < deadline:
                    got_any = False
                    for packet in page.listen.steps(timeout=1, gap=1):
                        packets.append(packet)
                        got_any = True
                    if got_any:
                        time.sleep(0.2)
                    else:
                        break
            except Exception:
                return False

            if not packets:
                return False

            # 保存网络日志（仅用于调试）
            self._save_network_packets(packets)

            found_batchexecute = False
            found_batchexecute_error = False

            for packet in packets:
                try:
                    url = str(packet.url) if hasattr(packet, 'url') else str(packet)

                    if 'batchexecute' in url:
                        found_batchexecute = True

                        try:
                            response = packet.response if hasattr(packet, 'response') else None
                            if response and hasattr(response, 'raw_body'):
                                body = response.raw_body
                                raw_body_str = str(body)
                                if "CAPTCHA_CHECK_FAILED" in raw_body_str:
                                    found_batchexecute_error = True
                                    self._last_send_error = "captcha_check_failed"
                                elif "SendEmailOtpError" in raw_body_str:
                                    found_batchexecute_error = True
                                    self._last_send_error = "send_email_otp_error"
                        except Exception:
                            pass

                except Exception:
                    continue

            if found_batchexecute:
                if found_batchexecute_error:
                    return False
                return True
            else:
                return False

        except Exception:
            return False

    def _verify_code_send_status(self, page) -> bool:
        """检测页面提示判断是否发送成功"""
        time.sleep(2)
        try:
            success_keywords = ["验证码已发送", "code sent", "email sent", "check your email", "已发送"]
            error_keywords = [
                "出了点问题",
                "something went wrong",
                "error",
                "failed",
                "try again",
                "稍后再试",
                "选择其他登录方法"
            ]
            selectors = [
                "css:.zyTWof-gIZMF",
                "css:[role='alert']",
                "css:aside",
            ]
            for selector in selectors:
                try:
                    elements = page.eles(selector, timeout=1)
                    for elem in elements[:20]:
                        text = (elem.text or "").strip()
                        if not text:
                            continue
                        if any(kw in text for kw in error_keywords):
                            return False
                        if any(kw in text for kw in success_keywords):
                            return True
                except Exception:
                    continue
            return True
        except Exception:
            return True

    def _truncate_text(self, text: str, max_len: int = 2000) -> str:
        if text is None:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"...(truncated, total={len(text)})"

    def _save_network_packets(self, packets) -> None:
        """保存网络日志（仅用于调试）"""
        try:
            from core.storage import _data_file_path
            base_dir = _data_file_path(os.path.join("logs", "network"))
            os.makedirs(base_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_path = os.path.join(base_dir, f"network-{ts}.jsonl")

            def safe_str(value):
                try:
                    return value if isinstance(value, str) else str(value)
                except Exception:
                    return "<unprintable>"

            with open(file_path, "a", encoding="utf-8") as f:
                for packet in packets:
                    try:
                        req = packet.request if hasattr(packet, "request") else None
                        resp = packet.response if hasattr(packet, "response") else None
                        fail = packet.fail_info if hasattr(packet, "fail_info") else None

                        item = {
                            "url": safe_str(packet.url) if hasattr(packet, "url") else safe_str(packet),
                            "method": safe_str(packet.method) if hasattr(packet, "method") else "UNKNOWN",
                            "resourceType": safe_str(packet.resourceType) if hasattr(packet, "resourceType") else "",
                            "is_failed": bool(packet.is_failed) if hasattr(packet, "is_failed") else False,
                            "fail_info": safe_str(fail) if fail else "",
                            "request": {
                                "headers": req.headers if req and hasattr(req, "headers") else {},
                                "postData": req.postData if req and hasattr(req, "postData") else "",
                            },
                            "response": {
                                "status": resp.status if resp and hasattr(resp, "status") else 0,
                                "headers": resp.headers if resp and hasattr(resp, "headers") else {},
                                "raw_body": resp.raw_body if resp and hasattr(resp, "raw_body") else "",
                            },
                        }
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    except Exception as e:
                        f.write(json.dumps({"error": safe_str(e)}, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _wait_for_code_input(self, page, timeout: int = 30):
        """等待验证码输入框出现"""
        selectors = [
            "css:input[jsname='ovqh0b']",
            "css:input[type='tel']",
            "css:input[name='pinInput']",
            "css:input[autocomplete='one-time-code']",
        ]
        for _ in range(timeout // 2):
            for selector in selectors:
                try:
                    el = page.ele(selector, timeout=1)
                    if el:
                        return el
                except Exception:
                    continue
            time.sleep(2)
        return None

    def _simulate_human_input(self, element, text: str) -> bool:
        """模拟人类输入（逐字符输入，带随机延迟）

        Args:
            element: 输入框元素
            text: 要输入的文本

        Returns:
            bool: 是否成功
        """
        try:
            # 先点击输入框获取焦点
            element.click()
            time.sleep(random.uniform(0.1, 0.3))

            # 逐字符输入
            for char in text:
                element.input(char)
                # 随机延迟：模拟人类打字速度（50-150ms/字符）
                time.sleep(random.uniform(0.05, 0.15))

            # 输入完成后短暂停顿
            time.sleep(random.uniform(0.2, 0.5))
            return True
        except Exception:
            return False

    def _find_verify_button(self, page):
        """查找验证按钮（排除重新发送按钮）"""
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and "重新" not in text and "发送" not in text and "resend" not in text and "send" not in text:
                    return btn
        except Exception:
            pass
        return None

    def _click_resend_code_button(self, page) -> bool:
        """点击重新发送验证码按钮"""
        time.sleep(2)

        # 查找包含重新发送关键词的按钮（与 _find_verify_button 相反）
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and ("重新" in text or "resend" in text):
                    try:
                        self._log("info", f"🔄 点击重新发送按钮")
                        btn.click()
                        time.sleep(2)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass

        return False

    def _handle_agreement_page(self, page) -> None:
        """处理协议页面"""
        if "/admin/create" in page.url:
            agree_btn = page.ele("css:button.agree-button", timeout=5)
            if agree_btn:
                agree_btn.click()
                time.sleep(2)

    def _wait_for_cid(self, page, timeout: int = 10) -> bool:
        """等待URL包含cid"""
        for _ in range(timeout):
            if "cid" in page.url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, page, timeout: int = 30) -> bool:
        """等待业务页面参数生成（csesidx 和 cid）"""
        for _ in range(timeout):
            url = page.url
            if "csesidx=" in url and "/cid/" in url:
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self, page) -> bool:
        """处理用户名设置页面"""
        current_url = page.url

        if "auth.business.gemini.google/login" in current_url:
            return False

        selectors = [
            "css:input[type='text']",
            "css:input[name='displayName']",
            "css:input[aria-label*='用户名' i]",
            "css:input[aria-label*='display name' i]",
        ]

        username_input = None
        for selector in selectors:
            try:
                username_input = page.ele(selector, timeout=2)
                if username_input:
                    break
            except Exception:
                continue

        if not username_input:
            return False

        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"Test{suffix}"

        try:
            # 清空输入框
            username_input.click()
            time.sleep(0.2)
            username_input.clear()
            time.sleep(0.1)

            # 尝试模拟人类输入，失败则降级到直接注入
            if not self._simulate_human_input(username_input, username):
                username_input.input(username)
                time.sleep(0.3)

            # 直接回车提交
            username_input.input("\n")

            # 等待 URL 生成 cid 参数
            if not self._wait_for_cid(page, timeout=30):
                self._log("warning", "⚠️ 用户名提交后未检测到 cid 参数")
                return False

            return True
        except Exception:
            return False

    def _extract_config(self, page, email: str) -> dict:
        """提取配置"""
        try:
            if "cid/" not in page.url:
                page.get("https://business.gemini.google/", timeout=self.timeout)
                time.sleep(3)

            url = page.url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            cookies = page.cookies()
            ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
            host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)

            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            # 使用北京时区，确保时间计算正确（Cookie expiry 是 UTC 时间戳）
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                # 将 UTC 时间戳转为北京时间，再减去12小时作为刷新窗口
                cookie_expire_beijing = datetime.fromtimestamp(ses_obj["expiry"], tz=beijing_tz)
                expires_at = (cookie_expire_beijing - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires_at = (datetime.now(beijing_tz) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")

            config = {
                "id": email,
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses,
                "host_c_oses": host,
                "expires_at": expires_at,
            }

            # 提取试用期信息
            trial_end = self._extract_trial_end(page, csesidx, config_id)
            if trial_end:
                config["trial_end"] = trial_end

            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_trial_end(self, page, csesidx: str, config_id: str) -> Optional[str]:
        """从页面中提取试用期到期日期，不跳转到可能 400 的深层路径"""
        import re
        try:
            self._log("info", "📅 获取试用期信息...")

            def _days_to_end_date(days: int) -> str:
                end_date = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=days)).strftime("%Y-%m-%d")
                self._log("info", f"📅 试用期剩余 {days} 天，到期日: {end_date}")
                return end_date

            def _search_page_source(source: str) -> Optional[str]:
                """在页面源码中搜索试用期信息"""
                # 格式1: "daysLeft":29 (JSON数据)
                m = re.search(r'"daysLeft"\s*:\s*(\d+)', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                # 格式2: "trialDaysRemaining":29
                m = re.search(r'"trialDaysRemaining"\s*:\s*(\d+)', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                # 格式3: 日期数组 "[2026,3,25]" 形式 (batchexecute格式)
                m = re.search(r'\[(\d{4}),(\d{1,2}),(\d{1,2})\].*?\[(\d{4}),(\d{1,2}),(\d{1,2})\]', source)
                if m:
                    # 取第二个日期（结束日期）
                    try:
                        end_date = f"{m.group(4):0>4}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
                        # 简单校验年份合理
                        if 2025 <= int(m.group(4)) <= 2030:
                            self._log("info", f"📅 试用期到期日: {end_date}")
                            return end_date
                    except Exception:
                        pass
                # 格式4: "29 days left" 或 "还剩29天"
                m = re.search(r'(\d+)\s*days?\s*left', source, re.IGNORECASE)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                m = re.search(r'还剩\s*(\d+)\s*天', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                return None

            # ——— 方式1: 当前页面（刚登录完，不需要跳转）———
            try:
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            # ——— 方式2: 跳转到 /settings（不带 billing/plans 后缀，SPA可以处理）———
            try:
                settings_url = f"https://business.gemini.google/cid/{config_id}/settings?csesidx={csesidx}"
                page.get(settings_url, timeout=self.timeout)
                time.sleep(2)
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            # ——— 方式3: 跳转到主页（最保险）———
            try:
                main_url = f"https://business.gemini.google/cid/{config_id}?csesidx={csesidx}"
                page.get(main_url, timeout=self.timeout)
                time.sleep(2)
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            self._log("warning", "⚠️ 未能获取试用期信息（页面中未找到相关数据）")
            return None
        except Exception as e:
            self._log("warning", f"⚠️ 获取试用期失败: {e}")
            return None

    def _save_screenshot(self, page, name: str) -> None:
        """保存截图"""
        try:
            from core.storage import _data_file_path
            screenshot_dir = _data_file_path("automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            page.get_screenshot(path=path)
        except Exception:
            pass

    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except TaskCancelledError:
                raise
            except Exception:
                pass

    def _cleanup_user_data(self, user_data_dir: Optional[str]) -> None:
        """清理浏览器用户数据目录"""
        if not user_data_dir:
            return
        try:
            import shutil
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _get_ua() -> str:
        """生成随机User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
