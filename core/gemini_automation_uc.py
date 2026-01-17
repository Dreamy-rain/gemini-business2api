"""
Gemini自动化登录模块（使用 undetected-chromedriver）
更强的反检测能力，支持无头模式
"""
import random
import string
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# 常量
AUTH_HOME_URL = "https://auth.business.gemini.google/"
LOGIN_URL = "https://auth.business.gemini.google/login?continueUrl=https:%2F%2Fbusiness.gemini.google%2F&wiffid=CAoSJDIwNTlhYzBjLTVlMmMtNGUxZS1hY2JkLThmOGY2ZDE0ODM1Mg"
DEFAULT_XSRF_TOKEN = "KdLRzKwwBTD5wo8nUollAbY6cW0"


class GeminiAutomationUC:
    """Gemini自动化登录（使用 undetected-chromedriver）"""

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
        self.driver = None
        self.user_data_dir = None

    def login_and_extract(self, email: str, mail_client) -> dict:
        """执行登录并提取配置"""
        try:
            self._create_driver()
            return self._run_flow(email, mail_client)
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            self._cleanup()

    def _create_driver(self):
        """创建浏览器驱动"""
        import tempfile
        options = uc.ChromeOptions()

        # 创建临时用户数据目录
        self.user_data_dir = tempfile.mkdtemp(prefix='uc-profile-')
        options.add_argument(f"--user-data-dir={self.user_data_dir}")

        # 基础参数
        options.add_argument("--incognito")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--window-size=1280,800")

        # 代理设置
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")

        # 无头模式
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-dev-shm-usage")

        # User-Agent
        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")

        # 创建驱动（undetected-chromedriver 会自动处理反检测）
        self.driver = uc.Chrome(
            options=options,
            version_main=None,  # 自动检测 Chrome 版本
            use_subprocess=True,
        )

        # 设置超时
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.implicitly_wait(10)

    def _run_flow(self, email: str, mail_client) -> dict:
        """执行登录流程"""

        self._log("info", f"navigating to login page for {email}")

        # 访问登录页面
        self.driver.get(LOGIN_URL)
        time.sleep(3)

        # 检查当前页面状态
        current_url = self.driver.current_url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            return self._extract_config(email)

        # 输入邮箱地址
        try:
            self._log("info", "entering email address")
            email_input = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[1]/div[1]/div/span[2]/input"))
            )
            email_input.click()
            email_input.clear()
            for char in email:
                email_input.send_keys(char)
                time.sleep(0.02)
            time.sleep(0.5)
        except Exception as e:
            self._log("error", f"failed to enter email: {e}")
            self._save_screenshot("email_input_failed")
            return {"success": False, "error": f"failed to enter email: {e}"}

        # 点击继续按钮
        try:
            continue_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/button"))
            )
            self.driver.execute_script("arguments[0].click();", continue_btn)
            time.sleep(2)
        except Exception as e:
            self._log("error", f"failed to click continue: {e}")
            self._save_screenshot("continue_button_failed")
            return {"success": False, "error": f"failed to click continue: {e}"}

        # 记录发送验证码的时间
        from datetime import datetime
        send_time = datetime.now()

        # 检查是否需要点击"发送验证码"按钮
        self._log("info", "clicking send verification code button")
        if not self._click_send_code_button():
            self._log("error", "send code button not found")
            self._save_screenshot("send_code_button_missing")
            return {"success": False, "error": "send code button not found"}

        # 等待验证码输入框出现
        code_input = self._wait_for_code_input()
        if not code_input:
            self._log("error", "code input not found")
            self._save_screenshot("code_input_missing")
            return {"success": False, "error": "code input not found"}

        # 获取验证码（传入发送时间）
        self._log("info", "polling for verification code")
        code = mail_client.poll_for_code(timeout=40, interval=4, since_time=send_time)

        if not code:
            self._log("error", "verification code timeout")
            self._save_screenshot("code_timeout")
            return {"success": False, "error": "verification code timeout"}

        self._log("info", f"code received: {code}")

        # 输入验证码
        time.sleep(1)
        try:
            code_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']"))
            )
            code_input.click()
            time.sleep(0.1)
            for char in code:
                code_input.send_keys(char)
                time.sleep(0.05)
        except Exception:
            try:
                span = self.driver.find_element(By.CSS_SELECTOR, "span[data-index='0']")
                span.click()
                time.sleep(0.2)
                self.driver.switch_to.active_element.send_keys(code)
            except Exception as e:
                self._log("error", f"failed to input code: {e}")
                self._save_screenshot("code_input_failed")
                return {"success": False, "error": f"failed to input code: {e}"}

        # 点击验证按钮
        time.sleep(0.5)
        try:
            verify_btn = self.driver.find_element(By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button")
            self.driver.execute_script("arguments[0].click();", verify_btn)
        except Exception:
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "验证" in btn.text:
                        self.driver.execute_script("arguments[0].click();", btn)
                        break
            except Exception as e:
                self._log("warning", f"failed to click verify button: {e}")

        time.sleep(5)

        # 处理协议页面
        self._handle_agreement_page()

        # 导航到业务页面并等待参数生成
        self._log("info", "navigating to business page")
        self.driver.get("https://business.gemini.google/")
        time.sleep(3)

        # 处理用户名设置
        if "cid" not in self.driver.current_url:
            if self._handle_username_setup():
                time.sleep(3)

        # 等待 URL 参数生成（csesidx 和 cid）
        self._log("info", "waiting for URL parameters")
        if not self._wait_for_business_params():
            self._log("warning", "URL parameters not generated, trying refresh")
            self.driver.refresh()
            time.sleep(3)
            if not self._wait_for_business_params():
                self._log("error", "URL parameters generation failed")
                self._save_screenshot("params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # 提取配置
        self._log("info", "login success")
        return self._extract_config(email)

    def _click_send_code_button(self) -> bool:
        """点击发送验证码按钮（如果需要）"""
        time.sleep(2)

        # 方法1: 直接通过ID查找
        try:
            direct_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "sign-in-with-email"))
            )
            self.driver.execute_script("arguments[0].click();", direct_btn)
            time.sleep(2)
            return True
        except TimeoutException:
            pass

        # 方法2: 通过关键词查找按钮
        keywords = ["通过电子邮件发送验证码", "通过电子邮件发送", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                text = btn.text.strip() if btn.text else ""
                if text and any(kw in text for kw in keywords):
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    return True
        except Exception:
            pass

        # 方法3: 检查是否已经在验证码输入页面
        try:
            code_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='pinInput']")
            if code_input:
                return True
        except NoSuchElementException:
            pass

        return False

    def _wait_for_code_input(self, timeout: int = 30):
        """等待验证码输入框出现"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']"))
            )
            return element
        except TimeoutException:
            return None

    def _find_code_input(self):
        """查找验证码输入框"""
        try:
            return self.driver.find_element(By.CSS_SELECTOR, "input[name='pinInput']")
        except NoSuchElementException:
            return None

    def _find_verify_button(self):
        """查找验证按钮"""
        try:
            return self.driver.find_element(By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button")
        except NoSuchElementException:
            pass

        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                text = btn.text.strip()
                if text and "验证" in text:
                    return btn
        except Exception:
            pass

        return None

    def _handle_agreement_page(self) -> None:
        """处理协议页面"""
        if "/admin/create" in self.driver.current_url:
            try:
                agree_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.agree-button"))
                )
                agree_btn.click()
                time.sleep(2)
            except TimeoutException:
                pass

    def _wait_for_cid(self, timeout: int = 10) -> bool:
        """等待URL包含cid"""
        for _ in range(timeout):
            if "cid" in self.driver.current_url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, timeout: int = 30) -> bool:
        """等待业务页面参数生成（csesidx 和 cid）"""
        for _ in range(timeout):
            url = self.driver.current_url
            if "csesidx=" in url and "/cid/" in url:
                self._log("info", f"business params ready: {url}")
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self) -> bool:
        """处理用户名设置页面"""
        current_url = self.driver.current_url

        if "auth.business.gemini.google/login" in current_url:
            return False

        selectors = [
            "input[formcontrolname='fullName']",
            "input[placeholder='全名']",
            "input[placeholder='Full name']",
            "input#mat-input-0",
            "input[type='text']",
            "input[name='displayName']",
        ]

        username_input = None
        for _ in range(30):
            for selector in selectors:
                try:
                    username_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if username_input.is_displayed():
                        break
                except Exception:
                    continue
            if username_input and username_input.is_displayed():
                break
            time.sleep(1)

        if not username_input or not username_input.is_displayed():
            return False

        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"Test{suffix}"

        try:
            username_input.click()
            time.sleep(0.2)
            username_input.clear()
            for char in username:
                username_input.send_keys(char)
                time.sleep(0.02)
            time.sleep(0.3)

            from selenium.webdriver.common.keys import Keys
            username_input.send_keys(Keys.ENTER)
            time.sleep(1)

            return True
        except Exception:
            return False

    def _extract_config(self, email: str) -> dict:
        """提取配置"""
        try:
            if "cid/" not in self.driver.current_url:
                self.driver.get("https://business.gemini.google/")
                time.sleep(3)

            url = self.driver.current_url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            # 提取参数
            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            # 提取 Cookie
            cookies = self.driver.get_cookies()
            ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
            host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)

            # 计算过期时间
            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            if ses_obj and "expiry" in ses_obj:
                expires_at = datetime.fromtimestamp(ses_obj["expiry"] - 43200).strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires_at = (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")

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

    def _save_screenshot(self, name: str) -> None:
        """保存截图"""
        try:
            import os
            screenshot_dir = os.path.join("data", "automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            self.driver.save_screenshot(path)
        except Exception:
            pass

    def _cleanup(self) -> None:
        """清理资源"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

        if self.user_data_dir:
            try:
                import shutil
                import os
                if os.path.exists(self.user_data_dir):
                    shutil.rmtree(self.user_data_dir, ignore_errors=True)
            except Exception:
                pass

    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    @staticmethod
    def _get_ua() -> str:
        """生成随机User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
