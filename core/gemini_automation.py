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
            # 增强反检测
            options.set_argument("--disable-blink-features=AutomationControlled")
            options.set_argument("--exclude-switches=enable-automation")
            options.set_argument("--disable-web-security")
            options.set_argument("--allow-running-insecure-content")

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
        """执行登录流程 - 双通道：legacy 优先，manual 回退，共享验证码阶段"""

        send_time = datetime.now()

        legacy_result = self._try_legacy_login_hint_flow(page, email)
        if legacy_result.get("success"):
            send_time = legacy_result.get("send_time", send_time)
            self._log("info", "✅ [legacy] 已进入验证阶段，开始共享验证码流程")
            return self._complete_verification_and_extract(
                page,
                email,
                mail_client,
                send_time,
                branch="legacy",
            )

        legacy_reason = legacy_result.get("reason", "unknown")
        self._log("warning", f"⚠️ [legacy] 失败，准备回退 manual，原因: {legacy_reason}")

        manual_result = self._try_manual_input_flow(page, email)
        if manual_result.get("success"):
            send_time = manual_result.get("send_time", send_time)
            self._log("info", "✅ [manual] 已进入验证阶段，开始共享验证码流程")
            return self._complete_verification_and_extract(
                page,
                email,
                mail_client,
                send_time,
                branch="manual",
            )

        manual_reason = manual_result.get("reason", "unknown")
        self._save_screenshot(page, "dual_channel_failed")
        return {
            "success": False,
            "error": f"both login channels failed: legacy={legacy_reason}; manual={manual_reason}",
        }

    def _try_legacy_login_hint_flow(self, page, email: str) -> dict:
        """通道A：沿用上游风格的 loginHint + 发送验证码路径"""
        try:
            self._log("info", f"🌐 [legacy] 访问登录页: {AUTH_HOME_URL}login")
            page.get(f"{AUTH_HOME_URL}login", timeout=self.timeout)
            time.sleep(5)

            current_url = page.url
            self._log("info", f"📍 [legacy] 当前 URL: {current_url}")

            if self._has_business_params(current_url):
                self._log("info", "✅ [legacy] 已登录，直接提取配置")
                return {"success": True, "send_time": datetime.now()}

            email_input = self._find_email_input(page)
            if not email_input:
                return {
                    "success": False,
                    "reason": "email input not found on legacy page",
                }

            self._log("info", f"⌨️ [legacy] 输入邮箱: {email}")
            if not self._simulate_human_input(email_input, email):
                email_input.input(email, clear=True)

            time.sleep(1)
            send_time = datetime.now()

            clicked = self._click_send_code_button(page)
            if not clicked:
                try:
                    email_input.input("\n")
                    clicked = True
                    self._log("info", "✅ [legacy] 未找到发送按钮，已回车提交")
                except Exception:
                    clicked = False

            if not clicked:
                return {
                    "success": False,
                    "reason": "send-code action failed on legacy page",
                }

            time.sleep(6)
            current_url = page.url
            self._log("info", f"📍 [legacy] 发送后 URL: {current_url}")

            if "signin-error" in current_url:
                self._log("error", "❌ [legacy] 命中 signin-error")
                self._save_screenshot(page, "legacy_signin_error")
                return {"success": False, "reason": "legacy signin-error"}

            return {"success": True, "send_time": send_time}
        except Exception as e:
            self._log("warning", f"⚠️ [legacy] 流程异常: {e}")
            return {"success": False, "reason": f"legacy exception: {e}"}

    def _try_manual_input_flow(self, page, email: str) -> dict:
        """通道B：business 首页手动输入邮箱 + 点击继续"""
        try:
            self._log("info", f"🌐 [manual] 访问 Gemini Business 首页: {email}")
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(8)

            current_url = page.url
            self._log("info", f"📍 [manual] 当前 URL: {current_url}")

            if self._has_business_params(current_url):
                self._log("info", "✅ [manual] 已登录，直接提取配置")
                return {"success": True, "send_time": datetime.now()}

            email_input = self._find_email_input(page)
            if not email_input:
                self._save_screenshot(page, "manual_email_input_not_found")
                return {
                    "success": False,
                    "reason": "email input not found on manual page",
                }

            self._log("info", f"⌨️ [manual] 输入邮箱: {email}")
            if not self._simulate_human_input(email_input, email):
                self._log("warning", "⚠️ [manual] 模拟输入失败，使用直接输入")
                email_input.input(email, clear=True)
            time.sleep(1)

            continue_btn = self._find_continue_button(page)
            if not continue_btn:
                self._save_screenshot(page, "manual_continue_button_not_found")
                return {"success": False, "reason": "continue button not found"}

            send_time = datetime.now()
            continue_btn.click()
            self._log("info", "✅ [manual] 已点击继续按钮")
            time.sleep(8)

            current_url = page.url
            self._log("info", f"📍 [manual] 点击后 URL: {current_url}")
            if "signin-error" in current_url:
                self._log("error", "❌ [manual] 命中 signin-error")
                self._save_screenshot(page, "manual_signin_error")
                return {"success": False, "reason": "manual signin-error"}

            return {"success": True, "send_time": send_time}
        except Exception as e:
            self._log("warning", f"⚠️ [manual] 流程异常: {e}")
            return {"success": False, "reason": f"manual exception: {e}"}

    def _find_email_input(self, page):
        """查找邮箱输入框（兼容 legacy / manual 页面）"""
        selectors = [
            "css:input[name='loginHint']",
            "css:input[id='email-input']",
            "css:input[type='email']",
            "css:input[type='text']",
            "css:input[aria-label='邮箱']",
            "css:input[aria-label*='email']",
        ]

        for selector in selectors:
            try:
                email_input = page.ele(selector, timeout=2)
                if email_input:
                    self._log("info", f"✅ 找到邮箱输入框: {selector}")
                    return email_input
            except Exception:
                continue
        return None

    def _find_continue_button(self, page):
        """查找继续按钮"""
        continue_keywords = ["使用邮箱继续", "继续", "Continue", "Next", "下一步"]
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw in text for kw in continue_keywords):
                    self._log("info", f"✅ 找到继续按钮: '{text}'")
                    return btn
        except Exception:
            pass
        return None

    def _has_business_params(self, url: str) -> bool:
        """判断 URL 是否已包含可提取配置参数"""
        return "business.gemini.google" in url and "csesidx=" in url and "/cid/" in url

    def _complete_verification_and_extract(
        self,
        page,
        email: str,
        mail_client,
        send_time: datetime,
        branch: str,
    ) -> dict:
        """共享验证码阶段：等待输入框 -> 拉取验证码 -> 输入提交 -> 提取配置"""
        current_url = page.url
        if self._has_business_params(current_url):
            self._log("info", f"✅ [{branch}] 当前已是业务页，直接提取配置")
            return self._extract_config(page, email)

        self._log("info", f"⏳ [{branch}] 等待验证码输入框出现...")
        code_input = self._wait_for_code_input(page)
        if not code_input:
            self._save_screenshot(page, f"{branch}_code_input_missing")
            return {"success": False, "error": f"[{branch}] code input not found"}

        self._log("info", f"📬 [{branch}] 开始轮询邮箱获取验证码...")
        code = mail_client.poll_for_code(timeout=40, interval=4, since_time=send_time)

        if not code:
            self._log("warning", f"⚠️ [{branch}] 验证码超时，尝试重新发送")
            resend_time = datetime.now()
            if self._click_resend_code_button(page):
                self._log("info", f"🔄 [{branch}] 已点击重新发送按钮")
                code = mail_client.poll_for_code(
                    timeout=40, interval=4, since_time=resend_time
                )
            if not code:
                self._save_screenshot(page, f"{branch}_code_timeout")
                return {
                    "success": False,
                    "error": f"[{branch}] verification code timeout",
                }

        self._log("info", f"✅ [{branch}] 收到验证码: {code}")

        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or page.ele(
            "css:input[type='tel']", timeout=2
        )
        if not code_input:
            return {"success": False, "error": f"[{branch}] code input expired"}

        self._log("info", f"⌨️ [{branch}] 输入验证码")
        if not self._simulate_human_input(code_input, code):
            code_input.input(code, clear=True)
            time.sleep(0.5)

        self._log("info", f"⏎ [{branch}] 回车提交验证码")
        code_input.input("\n")

        self._log("info", f"⏳ [{branch}] 等待验证后自动跳转")
        time.sleep(12)

        current_url = page.url
        self._log("info", f"📍 [{branch}] 验证后 URL: {current_url}")

        if "verify-oob-code" in current_url:
            self._save_screenshot(page, f"{branch}_verification_submit_failed")
            return {
                "success": False,
                "error": f"[{branch}] verification code submission failed",
            }

        if "signin-error" in current_url:
            self._save_screenshot(page, f"{branch}_signin_error_after_verify")
            return {"success": False, "error": f"[{branch}] signin-error after verify"}

        self._handle_agreement_page(page)

        current_url = page.url
        if self._has_business_params(current_url):
            self._log("info", f"✅ [{branch}] 已在 business 参数页")
            return self._extract_config(page, email)

        if "business.gemini.google" not in current_url:
            self._log("info", f"🌐 [{branch}] 导航到 business 页面")
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(5)

        if "cid" not in page.url and self._handle_username_setup(page):
            time.sleep(5)

        self._log("info", f"⏳ [{branch}] 等待 URL 参数生成")
        if not self._wait_for_business_params(page):
            self._log("warning", f"⚠️ [{branch}] 首次等待失败，尝试刷新")
            page.refresh()
            time.sleep(5)
            if not self._wait_for_business_params(page):
                current_url = page.url
                self._log(
                    "error", f"❌ [{branch}] URL 参数生成失败，最终 URL: {current_url}"
                )
                self._save_screenshot(page, f"{branch}_params_missing")
                return {
                    "success": False,
                    "error": f"[{branch}] URL parameters not found",
                }

        self._log("info", f"🎊 [{branch}] 登录流程完成，提取配置")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """点击发送验证码按钮（如果需要）"""
        time.sleep(2)

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

        # 方法2: 通过关键词查找
        keywords = [
            "通过电子邮件发送验证码",
            "通过电子邮件发送",
            "email",
            "Email",
            "Send code",
            "Send verification",
            "Verification code",
        ]
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
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele(
            "css:input[name='pinInput']", timeout=1
        )
        if code_input:
            self._log("info", "✅ 已在验证码输入页面，无需点击按钮")
            return True

        self._log("error", "❌ 未找到发送验证码按钮")
        return False

    def _wait_for_code_input(self, page, timeout: int = 30):
        """等待验证码输入框出现（通过页面特征判断）"""
        selectors = [
            "css:input[jsname='ovqh0b']",
            "css:input[name='pinInput']",
            "css:input.J6L5wc",  # Google 的验证码输入框 class
            "css:input[type='tel']",
            "css:input[autocomplete='one-time-code']",
        ]

        for attempt in range(timeout // 2):
            # 先检查页面 URL，确保已经跳转到验证码页面
            try:
                current_url = page.url
                if attempt == 0:
                    self._log("info", f"🔍 当前页面 URL: {current_url}")

                # 如果还在登录页面，继续等待
                if "login" in current_url and "verify" not in current_url:
                    if attempt == 0:
                        self._log("info", "⏳ 页面还在登录页面，等待跳转...")
                    time.sleep(2)
                    continue
            except Exception as e:
                self._log("warning", f"⚠️ 无法获取页面 URL: {e}")

            # 检查页面特征，确认是验证码页面
            if attempt == 0:
                try:
                    # 检查页面文字特征
                    page_text = page.html[:5000]  # 获取前 5000 字符
                    has_verification_text = any(
                        keyword in page_text
                        for keyword in [
                            "验证码",
                            "verification",
                            "verify-oob-code",
                            "pinInput",
                        ]
                    )

                    if has_verification_text:
                        self._log("info", "✅ 检测到验证码页面特征")
                    else:
                        self._log(
                            "warning", "⚠️ 未检测到验证码页面特征，可能在错误的页面"
                        )

                    # 检查按钮特征
                    buttons = page.eles("tag:button")
                    button_texts = [btn.text for btn in buttons if btn.text]
                    self._log("info", f"🔘 页面按钮: {button_texts}")

                    has_verify_button = any(
                        keyword in " ".join(button_texts)
                        for keyword in ["验证", "Verify", "重新发送", "Resend"]
                    )

                    if has_verify_button:
                        self._log("info", "✅ 检测到验证/重新发送按钮")
                    else:
                        self._log("warning", "⚠️ 未检测到验证按钮")

                except Exception as e:
                    self._log("warning", f"⚠️ 无法检查页面特征: {e}")

            # 输出调试信息（仅第一次）
            if attempt == 0:
                try:
                    all_inputs = page.eles("tag:input")
                    self._log("info", f"🔍 页面上共有 {len(all_inputs)} 个 input 元素")
                    for i, inp in enumerate(all_inputs[:5]):
                        inp_type = inp.attr("type") or "unknown"
                        inp_name = inp.attr("name") or "unknown"
                        inp_jsname = inp.attr("jsname") or "unknown"
                        inp_class = inp.attr("class") or "unknown"
                        self._log(
                            "info",
                            f"  Input {i + 1}: type={inp_type}, name={inp_name}, jsname={inp_jsname}, class={inp_class}",
                        )
                except Exception as e:
                    self._log("warning", f"⚠️ 无法列出 input 元素: {e}")

            for selector in selectors:
                try:
                    # 尝试查找所有匹配的元素（包括隐藏的）
                    elements = page.eles(selector, timeout=1)
                    if elements:
                        el = elements[0]  # 取第一个
                        self._log("info", f"✅ 找到验证码输入框: {selector}")
                        return el
                except Exception:
                    continue

            time.sleep(2)

        self._log("error", "❌ 超时：未找到验证码输入框")
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
