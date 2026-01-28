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
            user_data_dir = getattr(page, "user_data_dir", None)
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
            options.set_argument(
                "--enable-features=NetworkService,NetworkServiceInProcess"
            )

        options.auto_port()
        page = ChromiumPage(options)
        page.set.timeouts(self.timeout)

        # 反检测：注入脚本隐藏自动化特征
        if self.headless:
            try:
                page.run_cdp(
                    "Page.addScriptToEvaluateOnNewDocument",
                    source="""
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
                """,
                )
            except Exception:
                pass

        return page

    def _run_flow(self, page, email: str, mail_client) -> dict:
        """执行登录流程"""

        # 记录开始时间，用于邮件时间过滤
        from datetime import datetime

        send_time = datetime.now()

        # Step 1: 导航到 Gemini Business 首页（会自动跳转到登录页面）
        self._log(
            "info", f"🌐 正在访问 https://business.gemini.google/ (邮箱: {email})"
        )

        # 访问首页，让 Google 自动重定向到登录页面（避免被检测为自动化）
        page.get("https://business.gemini.google/", timeout=self.timeout)
        time.sleep(8)  # 增加等待时间，确保页面完全加载和重定向

        # 输出当前 URL，用于调试
        current_url = page.url
        self._log("info", f"📍 当前 URL: {current_url}")

        # Step 1.5: 查找并填写邮箱输入框
        self._log("info", "📧 正在查找邮箱输入框...")

        # 先输出页面上所有 input 元素，用于调试
        try:
            all_inputs = page.eles("tag:input")
            self._log("info", f"📋 页面上共有 {len(all_inputs)} 个 input 元素")
            for i, inp in enumerate(all_inputs[:5]):  # 只输出前5个
                inp_type = inp.attr("type") or "unknown"
                inp_name = inp.attr("name") or "unknown"
                inp_placeholder = inp.attr("placeholder") or ""
                self._log(
                    "info",
                    f"  Input {i + 1}: type={inp_type}, name={inp_name}, placeholder={inp_placeholder}",
                )
        except Exception as e:
            self._log("warning", f"⚠️ 无法列出 input 元素: {e}")

        email_input = None

        # 尝试多种选择器
        selectors = [
            "css:input[type='email']",
            "css:input[name='email']",
            "css:input[name='identifier']",
            "css:input[placeholder*='邮箱']",
            "css:input[placeholder*='email']",
            "css:input[placeholder*='Email']",
            "css:input[autocomplete='email']",
        ]

        for selector in selectors:
            try:
                email_input = page.ele(selector, timeout=2)
                if email_input:
                    self._log("info", f"✅ 找到邮箱输入框: {selector}")
                    break
            except Exception:
                continue

        if not email_input:
            self._log("error", "❌ 未找到邮箱输入框")
            self._log("error", f"❌ 当前 URL: {current_url}")
            self._save_screenshot(page, "email_input_not_found")
            return {"success": False, "error": "email input not found"}

        # 输入邮箱地址（模拟人类输入）
        self._log("info", f"⌨️ 正在输入邮箱: {email}")
        if not self._simulate_human_input(email_input, email):
            self._log("warning", "⚠️ 模拟输入失败，使用直接输入")
            email_input.input(email, clear=True)
        time.sleep(1)

        # Step 1.6: 点击"使用邮箱继续"按钮
        self._log("info", "🔘 正在查找并点击继续按钮...")
        continue_btn = None

        # 查找按钮
        continue_keywords = ["使用邮箱继续", "继续", "Continue", "Next", "下一步"]
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = (btn.text or "").strip()
            if text and any(kw in text for kw in continue_keywords):
                continue_btn = btn
                self._log("info", f"✅ 找到继续按钮: '{text}'")
                break

        if not continue_btn:
            self._log("error", "❌ 未找到继续按钮")
            self._save_screenshot(page, "continue_button_not_found")
            return {"success": False, "error": "continue button not found"}

        # 点击按钮
        try:
            continue_btn.click()
            self._log("info", "✅ 已点击继续按钮")
            time.sleep(5)  # 等待页面跳转
        except Exception as e:
            self._log("error", f"❌ 点击继续按钮失败: {e}")
            self._save_screenshot(page, "continue_button_click_failed")
            return {"success": False, "error": f"continue button click failed: {e}"}

        # Step 2: 检查当前页面状态
        current_url = page.url
        self._log("info", f"📍 当前 URL: {current_url}")
        has_business_params = (
            "business.gemini.google" in current_url
            and "csesidx=" in current_url
            and "/cid/" in current_url
        )

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
                code = mail_client.poll_for_code(
                    timeout=40, interval=4, since_time=send_time
                )
                if not code:
                    self._log("error", "❌ 重新发送后仍未收到验证码")
                    self._save_screenshot(page, "code_timeout_after_resend")
                    return {
                        "success": False,
                        "error": "verification code timeout after resend",
                    }
            else:
                self._log("error", "❌ 验证码超时且未找到重新发送按钮")
                self._save_screenshot(page, "code_timeout")
                return {"success": False, "error": "verification code timeout"}

        self._log("info", f"✅ 收到验证码: {code}")

        # Step 6: 输入验证码并提交
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or page.ele(
            "css:input[type='tel']", timeout=2
        )

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
        time.sleep(
            12
        )  # 增加等待时间，让页面有足够时间完成重定向（如果网络慢可以继续增加）

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
        has_business_params = (
            "business.gemini.google" in current_url
            and "csesidx=" in current_url
            and "/cid/" in current_url
        )

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

        # Step 11: 检查是否需要设置用户名
        if "cid" not in page.url:
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
        time.sleep(3)  # 增加等待时间，确保页面完全加载

        # 方法1: 直接通过ID查找
        direct_btn = page.ele("#sign-in-with-email", timeout=5)
        if direct_btn:
            try:
                direct_btn.click()
                self._log(
                    "info", "✅ 找到并点击了发送验证码按钮 (ID: #sign-in-with-email)"
                )
                time.sleep(3)  # 等待发送请求
                return True
            except Exception as e:
                self._log("warning", f"⚠️ 点击按钮失败: {e}")

        # 方法2: 通过关键词查找（扩展关键词列表）
        keywords = [
            "通过电子邮件发送验证码",
            "通过电子邮件发送",
            "发送验证码",
            "发送",
            "email",
            "Email",
            "EMAIL",
            "Send code",
            "Send verification",
            "Verification code",
            "Get code",
            "Continue",
            "Next",
            "Verify",
        ]
        try:
            self._log("info", f"🔍 通过关键词搜索按钮...")

            # 先输出所有按钮的文本，用于调试
            buttons = page.eles("tag:button")
            self._log("info", f"📋 页面上共有 {len(buttons)} 个按钮")
            for i, btn in enumerate(buttons[:10]):  # 只输出前10个
                text = (btn.text or "").strip()
                if text:
                    self._log("info", f"  按钮 {i + 1}: '{text}'")

            # 查找匹配的按钮
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw.lower() in text.lower() for kw in keywords):
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

        # 方法3: 尝试查找 div 或 span 元素（可能是自定义按钮）
        try:
            self._log("info", "🔍 尝试查找非 button 标签的可点击元素...")
            clickables = page.eles("css:[role='button']") + page.eles("css:.button")
            self._log("info", f"📋 找到 {len(clickables)} 个可点击元素")
            for elem in clickables[:10]:
                text = (elem.text or "").strip()
                if text:
                    self._log("info", f"  元素: '{text}'")
                if text and any(kw.lower() in text.lower() for kw in keywords):
                    try:
                        self._log("info", f"✅ 找到匹配元素: '{text}'")
                        elem.click()
                        self._log("info", "✅ 成功点击发送验证码元素")
                        time.sleep(3)
                        return True
                    except Exception as e:
                        self._log("warning", f"⚠️ 点击元素失败: {e}")
        except Exception as e:
            self._log("warning", f"⚠️ 搜索可点击元素异常: {e}")

        # 如果所有方法都失败，记录错误
        self._log("error", "❌ 未找到发送验证码按钮")
        self._save_screenshot(page, "send_button_not_found")
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
                if (
                    text
                    and "重新" not in text
                    and "发送" not in text
                    and "resend" not in text
                    and "send" not in text
                ):
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
                self._log(
                    "warning",
                    "simulated username input failed, fallback to direct input",
                )
                username_input.input(username)
                time.sleep(0.3)

            buttons = page.eles("tag:button")
            submit_btn = None
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if any(
                    kw in text
                    for kw in [
                        "确认",
                        "提交",
                        "继续",
                        "submit",
                        "continue",
                        "confirm",
                        "save",
                        "保存",
                        "下一步",
                        "next",
                    ]
                ):
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
            csesidx = (
                url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""
            )

            cookies = page.cookies()
            ses = next(
                (c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None
            )
            host = next(
                (c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None
            )

            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            # 使用北京时区，确保时间计算正确（Cookie expiry 是 UTC 时间戳）
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                # 将 UTC 时间戳转为北京时间，再减去12小时作为刷新窗口
                cookie_expire_beijing = datetime.fromtimestamp(
                    ses_obj["expiry"], tz=beijing_tz
                )
                expires_at = (cookie_expire_beijing - timedelta(hours=12)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                expires_at = (datetime.now(beijing_tz) + timedelta(hours=12)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

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
        """保存截图"""
        try:
            import os

            screenshot_dir = os.path.join("data", "automation")
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
