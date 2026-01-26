"""
Gemini自动化登录模块（用于新账号注册）
"""
import os
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
            self._log("info", f"using browser: {chromium_path}")

        # 避免 Linux/WSL 下弹出系统 Keyring 解锁对话框（会阻塞自动化）。
        options.set_argument("--password-store=basic")
        options.set_argument("--use-mock-keychain")
        options.set_pref("credentials_enable_service", False)
        options.set_pref("profile.password_manager_enabled", False)

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

        # 记录开始时间，用于邮件时间过滤
        from datetime import datetime
        send_time = datetime.now()

        # Step 1: 导航到首页并设置 Cookie
        self._log("info", f"🌐 正在打开登录页面: {email}")

        page.get(AUTH_HOME_URL, timeout=self.timeout)
        time.sleep(2)

        # 设置两个关键 Cookie
        try:
            self._log("info", "🍪 正在设置认证 Cookies...")
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
            self._log("info", "✅ Cookies 设置成功")
        except Exception as e:
            self._log("warning", f"⚠️ 设置 Cookies 失败: {e}")

        login_hint = quote(email, safe="")
        login_url = f"https://auth.business.gemini.google/login/email?continueUrl=https%3A%2F%2Fbusiness.gemini.google%2F&loginHint={login_hint}&xsrfToken={DEFAULT_XSRF_TOKEN}"
        self._log("info", "🔗 正在访问登录链接...")
        page.get(login_url, timeout=self.timeout)
        time.sleep(5)

        # Step 2: 检查当前页面状态
        current_url = page.url
        self._log("info", f"📍 当前 URL: {current_url}")
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            self._log("info", "✅ 检测到已登录，直接提取配置")
            return self._extract_config(page, email)

        # Step 3: 点击发送验证码按钮
        self._log("info", "🔘 正在查找并点击发送验证码按钮...")
        if not self._click_send_code_button(page):
            self._log("error", "❌ 未找到发送验证码按钮")
            self._save_screenshot(page, "send_code_button_missing")
            return {"success": False, "error": "send code button not found"}

        # Step 4: 等待验证码输入框出现
        self._log("info", "⏳ 等待验证码输入框出现...")
        code_input = self._wait_for_code_input(page)
        if not code_input:
            self._log("error", "❌ 验证码输入框未出现")
            self._save_screenshot(page, "code_input_missing")
            return {"success": False, "error": "code input not found"}

        # Step 5: 轮询邮件获取验证码（传入发送时间)
        self._log("info", "📬 开始轮询邮箱获取验证码...")
        code = mail_client.poll_for_code(timeout=40, interval=4, since_time=send_time)

        if not code:
            self._log("warning", "⚠️ 验证码获取超时，尝试重新发送...")
            # 更新发送时间（在点击按钮之前记录）
            send_time = datetime.now()
            # 尝试点击重新发送按钮
            if self._click_resend_code_button(page):
                self._log("info", "🔄 已点击重新发送按钮，等待新验证码...")
                # 再次轮询验证码
                code = mail_client.poll_for_code(timeout=40, interval=4, since_time=send_time)
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
        self._log("info", "⌨️ 正在输入验证码 (模拟人类输入)...")
        if not self._simulate_human_input(code_input, code):
            self._log("warning", "⚠️ 模拟输入失败，降级为直接输入")
            code_input.input(code, clear=True)
            time.sleep(0.5)

        # 直接使用回车提交，不再查找按钮
        self._log("info", "⏎ 按下回车键提交验证码")
        code_input.input("\n")

        # Step 7: 等待页面自动重定向（提交验证码后 Google 会自动跳转）
        self._log("info", "⏳ 等待验证后自动跳转...")
        time.sleep(12)  # 增加等待时间，让页面有足够时间完成重定向（如果网络慢可以继续增加）

        # 记录当前 URL 状态
        current_url = page.url
        self._log("info", f"📍 验证后 URL: {current_url}")

        # 检查是否还停留在验证码页面（说明提交失败）
        if "verify-oob-code" in current_url:
            self._log("error", "❌ 验证码提交失败，仍停留在验证页面")
            self._save_screenshot(page, "verification_submit_failed")
            return {"success": False, "error": "verification code submission failed"}

        # Step 8: 处理协议页面（如果有）
        self._handle_agreement_page(page)

        # Step 9: 检查是否已经在正确的页面
        current_url = page.url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            # 已经在正确的页面，不需要再次导航
            self._log("info", "already on business page with parameters")
            return self._extract_config(page, email)

        # Step 10: 如果不在正确的页面，尝试导航
        if "business.gemini.google" not in current_url:
            self._log("info", "navigating to business page")
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(5)  # 增加等待时间
            current_url = page.url
            self._log("info", f"URL after navigation: {current_url}")

        # Step 11: 处理首次启用页面（admin/create）或用户名设置页面
        if "/admin/create" in page.url:
            if self._handle_agreement_page(page):
                time.sleep(5)
        elif "cid" not in page.url:
            if self._handle_username_setup(page):
                time.sleep(5)  # 增加等待时间

        # Step 12: 等待 URL 参数生成（csesidx 和 cid）
        self._log("info", "waiting for URL parameters")
        if not self._wait_for_business_params(page):
            self._log("warning", "URL parameters not generated, trying refresh")
            page.refresh()
            time.sleep(5)  # 增加等待时间
            if not self._wait_for_business_params(page):
                self._log("error", "URL parameters generation failed")
                current_url = page.url
                self._log("error", f"final URL: {current_url}")
                self._save_screenshot(page, "params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # Step 13: 提取配置
        self._log("info", "🎊 登录流程完成，正在提取配置...")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """点击发送验证码按钮（如果需要）"""
        time.sleep(2)

        # 方法1: 直接通过ID查找
        direct_btn = page.ele("#sign-in-with-email", timeout=5)
        if direct_btn:
            try:
                direct_btn.click()
                self._log("info", "✅ 找到并点击了发送验证码按钮 (ID: #sign-in-with-email)")
                time.sleep(3)  # 等待发送请求
                return True
            except Exception as e:
                self._log("warning", f"⚠️ 点击按钮失败: {e}")

        # 方法2: 通过关键词查找
        keywords = ["通过电子邮件发送验证码", "通过电子邮件发送", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            self._log("info", f"🔍 通过关键词搜索按钮: {keywords}")
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw in text for kw in keywords):
                    try:
                        self._log("info", f"✅ 找到匹配按钮: '{text}'")
                        btn.click()
                        self._log("info", "✅ 成功点击发送验证码按钮")
                        time.sleep(3)  # 等待发送请求
                        return True
                    except Exception as e:
                        self._log("warning", f"⚠️ 点击按钮失败: {e}")
        except Exception as e:
            self._log("warning", f"⚠️ 搜索按钮异常: {e}")

        # 检查是否已经在验证码输入页面
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele("css:input[name='pinInput']", timeout=1)
        if code_input:
            self._log("info", "✅ 已在验证码输入页面，无需点击按钮")
            return True

        self._log("error", "❌ 未找到发送验证码按钮")
        return False

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
            self._log("info", "simulated human input successfully")
            return True
        except Exception as e:
            self._log("warning", f"simulated input failed: {e}")
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
                        self._log("info", f"found resend button: {text}")
                        btn.click()
                        time.sleep(2)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass

        return False

    def _handle_agreement_page(self, page) -> bool:
        """处理首次启用/协议页面（Gemini Enterprise Business 30 天试用）

        典型 URL: https://business.gemini.google/admin/create?csesidx=...
        页面需要填写 full name，并点击“同意并开始使用”，之后才会跳转到带 /cid/ 的业务页。

        Args:
            page: DrissionPage 页面对象

        Returns:
            bool: 处理成功返回 True，否则返回 False
        """
        if "/admin/create" not in page.url:
            return False

        self._log("info", "on onboarding page (/admin/create), filling name and accepting terms")

        # Step 1: 查找并填写全名（必填）
        # 说明：该页面的输入框选择器可能会变动，这里做了多选择器兜底。
        name_input = (
            page.ele("css:input[formcontrolname='fullName']", timeout=6)
            or page.ele("css:input[placeholder*='全名']", timeout=2)
            or page.ele("css:input#mat-input-0", timeout=2)
        )
        if not name_input:
            self._log("warning", "full name input not found on /admin/create")
            self._save_screenshot(page, "admin_create_name_input_missing")
            return False

        # 避免全名冲突，增加随机后缀
        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=4))
        full_name = f"Test{suffix}"
        try:
            name_input.click()
            time.sleep(0.2)
            try:
                name_input.clear()
            except Exception:
                pass
            name_input.input(full_name, clear=True)
            time.sleep(0.3)
        except Exception as e:
            self._log("warning", f"failed to input full name: {e}")
            self._save_screenshot(page, "admin_create_name_input_failed")
            return False

        # Step 2: 点击「同意并开始使用」
        agree_btn = (
            page.ele("css:button.agree-button", timeout=6)
            or page.ele("xpath://button[contains(., '同意') and contains(., '开始')]", timeout=3)
            or page.ele("xpath://button[contains(., 'Agree') and contains(., 'start')]", timeout=3)
        )
        if not agree_btn:
            self._log("warning", "agree/start button not found on /admin/create")
            self._save_screenshot(page, "admin_create_agree_button_missing")
            return False

        try:
            agree_btn.click()
        except Exception:
            try:
                # 遮挡等场景下尝试 JS 点击
                agree_btn.run_js("this.click()")
            except Exception as e:
                self._log("warning", f"failed to click agree/start button: {e}")
                self._save_screenshot(page, "admin_create_agree_click_failed")
                return False

        # Step 3: 等待离开 /admin/create（提交后通常会自动跳转）
        for _ in range(30):
            if "/admin/create" not in page.url:
                break
            time.sleep(1)

        self._log("info", f"onboarding submit done, current url: {page.url}")
        return True

    def _wait_for_cid(self, page, timeout: int = 10) -> bool:
        """等待URL包含cid"""
        for _ in range(timeout):
            if "cid" in page.url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, page, timeout: int = 30) -> bool:
        """等待业务页面参数生成（csesidx 和 cid）

        Args:
            page: DrissionPage 页面对象
            timeout: 最大等待秒数

        Returns:
            bool: 参数就绪返回 True，否则返回 False
        """
        for _ in range(timeout):
            url = page.url
            # 有时会先跳到 onboarding 页面（/admin/create），需先处理协议页再继续拿到 /cid/ 参数。
            if "/admin/create" in url:
                self._handle_agreement_page(page)
                time.sleep(2)
                url = page.url
            if "csesidx=" in url and "/cid/" in url:
                self._log("info", f"business params ready: {url}")
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
                self._log("warning", "simulated username input failed, fallback to direct input")
                username_input.input(username)
                time.sleep(0.3)

            buttons = page.eles("tag:button")
            submit_btn = None
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if any(kw in text for kw in ["确认", "提交", "继续", "submit", "continue", "confirm", "save", "保存", "下一步", "next"]):
                    submit_btn = btn
                    break

            if submit_btn:
                submit_btn.click()
            else:
                username_input.input("\n")

            time.sleep(5)
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
            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_screenshot(self, page, name: str) -> None:
        """保存调试信息（截图 + HTML + 元信息）

        注意：不要静默吞掉异常，否则排查页面结构变化会非常困难。

        Args:
            page: DrissionPage 页面对象
            name: 文件名前缀（用于区分场景）
        """
        import os

        ts = int(time.time())
        debug_dir = os.path.abspath(os.path.join("data", "automation"))
        os.makedirs(debug_dir, exist_ok=True)

        # 1) 元信息
        try:
            meta_path = os.path.join(debug_dir, f"{name}_{ts}.meta.txt")
            title = getattr(page, "title", "")
            if callable(title):
                title = title()
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(f"url: {getattr(page, 'url', '')}\n")
                f.write(f"title: {title}\n")
            self._log("info", f"saved debug meta: {meta_path}")
        except Exception as e:
            self._log("warning", f"failed to save debug meta: {e}")

        # 2) 截图
        try:
            png_path = os.path.join(debug_dir, f"{name}_{ts}.png")
            page.get_screenshot(path=png_path)
            self._log("info", f"saved screenshot: {png_path}")
        except Exception as e:
            self._log("warning", f"failed to save screenshot: {e}")

        # 3) HTML
        try:
            html_val = getattr(page, "html", "")
            if callable(html_val):
                html_val = html_val()
            html_path = os.path.join(debug_dir, f"{name}_{ts}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_val or "")
            self._log("info", f"saved html: {html_path}")
        except Exception as e:
            self._log("warning", f"failed to save html: {e}")

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
