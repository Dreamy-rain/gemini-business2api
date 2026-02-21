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
from core.concurrency import BROWSER_LOCK
import psutil
from core.browser_process_utils import is_browser_related_process


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
                browser_pid = getattr(page, 'process_id', None)
                page.quit()
                if browser_pid:
                    self._kill_browser_process(browser_pid)
            except Exception:
                pass

    def login_and_extract(self, email: str, mail_client) -> dict:
        """执行登录并提取配置（加全局锁）"""
        self._log("info", "🔒 正在等待浏览器资源锁...")
        with BROWSER_LOCK:
            self._log("info", "🔓 已获取浏览器资源锁")
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
                
                # 无论 page.quit() 是否成功，都执行一次彻底的扫除
                self._kill_browser_process()
                
                self._page = None
                self._cleanup_user_data(user_data_dir)
                self._user_data_dir = None
                self._log("info", "🔓 释放浏览器资源锁")

    def _create_page(self) -> ChromiumPage:
        """创建浏览器页面"""
        import tempfile
        import shutil
        
        options = ChromiumOptions()

        # 自动检测 Chromium 浏览器路径（Linux/Docker 环境）
        chromium_path = _find_chromium_path()
        if chromium_path:
            options.set_browser_path(chromium_path)
            self._log("info", f"using browser: {chromium_path}")

        # 创建唯一的临时用户数据目录，避免与其他浏览器实例冲突
        user_data_dir = tempfile.mkdtemp(prefix="gemini_chrome_")
        options.set_user_data_path(user_data_dir)
        self._log("info", f"using temp user data dir: {user_data_dir}")

        options.set_argument("--incognito")
        options.set_argument("--no-sandbox")
        options.set_argument("--gemini-business-automation")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-setuid-sandbox")
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--window-size=1280,800")
        options.set_user_agent(self.user_agent)
        
        # 禁用不必要的功能，提高稳定性
        options.set_argument("--disable-extensions")
        options.set_argument("--disable-background-networking")
        options.set_argument("--disable-default-apps")
        options.set_argument("--disable-sync")
        options.set_argument("--no-first-run")

        # 【关键】禁用所有后台下载和更新，防止内存飙升（组件更新/SafeBrowsing 等可额外消耗 100-300MB）
        options.set_argument("--disable-component-update")
        options.set_argument("--safebrowsing-disable-auto-update")
        options.set_argument("--disable-client-side-phishing-detection")
        options.set_argument("--disable-domain-reliability")
        options.set_argument("--disable-features=OptimizationHints,TranslateUI")
        options.set_argument("--disable-component-extensions-with-background-pages")
        options.set_argument("--disable-background-timer-throttling")
        options.set_argument("--disable-backgrounding-occluded-windows")
        options.set_argument("--disable-renderer-backgrounding")
        options.set_argument("--disable-hang-monitor")
        options.set_argument("--disable-ipc-flooding-protection")
        options.set_argument("--disable-popup-blocking")
        options.set_argument("--disable-prompt-on-repost")
        options.set_argument("--metrics-recording-only")
        options.set_argument("--no-default-browser-check")
        options.set_argument("--disk-cache-size=1")
        options.set_argument("--aggressive-cache-discard")

        # Linux 稳定性参数
        if os.name != 'nt':
            options.set_argument("--disable-gpu")
            options.set_argument("--disable-software-rasterizer")
            
            # 如果检测到是在 Linux 环境但没有设置 DISPLAY，尝试默认使用虚拟显示器 :99（如果安装了 Xvfb）
            if not os.environ.get('DISPLAY'):
                # 强制设置 Python 进程的环境变量，确保 DrissionPage/Chromium 子进程能读取到
                os.environ['DISPLAY'] = ':99'
                self._log("info", "💡 未检测到 DISPLAY 变量，已强制设置为 :99 (Xvfb)")

        # 语言设置（确保使用中文界面）
        options.set_argument("--lang=zh-CN")
        options.set_pref("intl.accept_languages", "zh-CN,zh")

        if self.proxy:
            options.set_argument(f"--proxy-server={self.proxy}")

        if self.headless:
        # 使用新版无头模式，更接近真实浏览器
            options.set_argument("--headless=new")
            # 反检测参数
            options.set_argument("--disable-infobars")
            options.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        # 关键修复：强制绑定到 IPv4 本地地址，防止 Docker 环境下绑定到 IPv6
        options.set_argument("--remote-debugging-address=127.0.0.1")
        options.set_argument("--remote-debugging-host=127.0.0.1")

        # 使用自动端口避免冲突
        options.auto_port()
        
        try:
            page = ChromiumPage(options)
            page.user_data_dir = user_data_dir  # 保存引用以便清理
            page.set.timeouts(self.timeout)
        except Exception as e:
            # 如果创建失败，清理临时目录
            self._log("error", f"❌ 浏览器启动失败: {e}")
            try:
                shutil.rmtree(user_data_dir, ignore_errors=True)
            except Exception:
                pass
            raise

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

        # Step 5: 轮询邮件获取验证码（支持重试）
        self._log("info", "📬 开始轮询邮箱获取验证码...")
        
        max_retries = 2
        poll_timeout = 20
        code = None

        # 初始轮询
        self._log("info", "polling for verification code (attempt 1)...")
        code = mail_client.poll_for_code(timeout=poll_timeout, interval=4, since_time=send_time)

        # 重试循环
        if not code:
            for i in range(max_retries):
                self._log("warning", f"⚠️ 轮询超时 ({poll_timeout}s)，尝试重新发送 (重试 {i+1}/{max_retries})...")
                
                # 更新发送时间
                send_time = datetime.now()
                
                # 尝试点击重新发送按钮
                if self._click_resend_code_button(page):
                    self._log("info", "🔄 已点击重新发送按钮，等待新验证码...")
                    code = mail_client.poll_for_code(timeout=poll_timeout, interval=4, since_time=send_time)
                    if code:
                        break
                else:
                    self._log("error", "❌ 验证码超时且未找到重新发送按钮")
                    self._save_screenshot(page, "code_timeout_resend_missing")
                    return {"success": False, "error": "verification code timeout"}

        if not code:
            self._log("error", "❌ 多次重试后仍未收到验证码")
            self._save_screenshot(page, "code_timeout_final")
            return {"success": False, "error": "verification code timeout"}

        self._log("info", f"✅ 收到验证码: {code}")

        # Step 6: 输入验证码并直接按回车
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or \
                     page.ele("css:input[type='tel']", timeout=2)

        if not code_input:
            self._log("error", "❌ 验证码输入框已失效")
            return {"success": False, "error": "code input expired"}

        self._log("info", "⌨️ 正在输入验证码...")
        if not self._simulate_human_input(code_input, code):
            self._log("warning", "⚠️ 模拟输入失败，降级为直接输入")
            code_input.input(code, clear=True)

        time.sleep(1)  # 重要：等待 Google 脚本识别输入内容
        
        self._log("info", "⏎ 尝试按回车键提交...")
        code_input.input("\n")
        
        # 兜底：如果几秒后 URL 没变，尝试寻找并点击物理按钮
        time.sleep(2)
        if "verify-oob-code" in page.url:
            self._log("info", "🖱️ URL 未跳转，尝试寻找物理验证按钮进行点击...")
            verify_btn = page.ele("css:button[jsname='XooR8e']", timeout=3) or self._find_verify_button(page)
            if verify_btn:
                try:
                    verify_btn.click()
                    self._log("info", "✅ 已点击物理验证按钮")
                except Exception:
                    pass

        # Step 7: 等待页面自动重定向
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
        keywords = ["通过电子邮件发送验证码", "通过电子邮件发送", "email", "Email", "Send code", "Send verification", "Verification code", "获取验证码", "Get code"]
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



        # 增强调试：如果没有找到按钮，输出页面上所有按钮文本
        try:
            buttons = page.eles("tag:button")
            btn_texts = [b.text for b in buttons]
            self._log("warning", f"⚠️ 未找到匹配按钮。页面按钮列表: {btn_texts}")
        except Exception:
            pass

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
        for i in range(timeout):
            url = page.url
            if "csesidx=" in url and "/cid/" in url:
                self._log("info", f"business params ready: {url}")
                return True
            
            # 如果停留在 /admin/ 且有 csesidx 但没有 cid，可能是账号选择页
            if "csesidx=" in url and "/cid/" not in url and "/admin/" in url:
                if i % 3 == 0:  # 每3秒检查一次
                    try:
                        # 查找包含 /cid/ 的链接
                        links = page.eles("tag:a")
                        for link in links:
                            href = link.attr("href") or ""
                            if "/cid/" in href:
                                self._log("info", f"🔍 发现账号链接，尝试点击: {href}")
                                link.click()
                                time.sleep(2)
                                break
                    except Exception:
                        pass

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
        """幂等清理浏览器用户数据目录：允许重复调用，失败时按固定间隔重试。"""
        if not user_data_dir:
            return

        # 尝试多次清理，应对文件锁或延迟释放句柄
        for i in range(5):
            try:
                import shutil
                if os.path.exists(user_data_dir):
                    shutil.rmtree(user_data_dir, ignore_errors=True)

                # 如果目录仍然存在，说明清理尚未完成
                if os.path.exists(user_data_dir):
                    self._log(
                        "warning",
                        f"⚠️ 临时目录仍存在，准备第 {i + 1}/5 次重试: {user_data_dir}",
                    )
                    time.sleep(1)
                    continue
                self._log("info", f"🧹 已清理临时目录: {user_data_dir}")
                break
            except Exception as e:
                self._log(
                    "warning",
                    f"⚠️ 清理临时目录异常，第 {i + 1}/5 次重试: {e}",
                )
                time.sleep(1)
        else:
            self._log("warning", f"⚠️ 临时目录清理失败，已达到重试上限: {user_data_dir}")

    @staticmethod
    def _get_ua() -> str:
        """生成随机User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"

    def _kill_browser_process(self, pid: int = None) -> None:
        """强制清理当前进程下的所有浏览器子进程 (以及核弹级清理)"""
        try:
            # 0. 如果指定了 PID，先尝试精确杀死
            if pid:
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    self._log("info", f"🔪 尝试精确清理指定 PID: {pid}")
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except:
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # 1. 精确清理：扫描当前 Python 进程的所有浏览器相关子进程
            import psutil
            current_proc = psutil.Process()
            children = current_proc.children(recursive=True)
            
            for child in children:
                try:
                    name = child.name().lower()
                    matched, process_type = is_browser_related_process(name, child.cmdline())
                    if matched:
                        self._log(
                            "info",
                            f"🔪 发现残留进程，强制清理: PID={child.pid} Name={name} Type={process_type}",
                        )
                        child.kill()
                        try:
                            # 必须调用 wait() 来回收僵尸进程
                            child.wait(timeout=2)
                        except psutil.TimeoutExpired:
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # 2. 强制垃圾回收
            import gc
            gc.collect()

        except Exception as e:
            self._log("warning", f"⚠️ 进程清理异常: {e}")
