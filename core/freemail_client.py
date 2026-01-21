import random
import string
import time
from typing import Optional

import requests

from core.mail_utils import extract_verification_code


class FreemailClient:
    """Freemail 临时邮箱客户端"""

    def __init__(
        self,
        base_url: str = "http://your-freemail-server.com",
        jwt_token: str = "",
        proxy: str = "",
        verify_ssl: bool = True,
        log_callback=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.jwt_token = jwt_token.strip()
        self.verify_ssl = verify_ssl
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.log_callback = log_callback

        self.email: Optional[str] = None

    def set_credentials(self, email: str, password: str = None) -> None:
        """设置邮箱凭据（Freemail 不需要密码）"""
        self.email = email

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送请求并打印详细日志"""
        self._log("info", f"[HTTP] {method} {url}")
        if "params" in kwargs:
            self._log("info", f"[HTTP] Params: {kwargs['params']}")

        try:
            res = requests.request(
                method,
                url,
                proxies=self.proxies,
                verify=self.verify_ssl,
                timeout=kwargs.pop("timeout", 15),
                **kwargs,
            )
            self._log("info", f"[HTTP] Response: {res.status_code}")
            if res.status_code >= 400:
                try:
                    self._log("error", f"[HTTP] Error body: {res.text[:500]}")
                except Exception:
                    pass
            return res
        except Exception as e:
            self._log("error", f"[HTTP] Request failed: {e}")
            raise

    def register_account(self, domain: Optional[str] = None) -> bool:
        """生成新的临时邮箱"""
        try:
            params = {"admin_token": self.jwt_token}
            if domain:
                params["domain"] = domain
                self._log("info", f"Freemail generating mailbox with domain: {domain}")
            else:
                self._log("info", "Freemail generating mailbox (auto-select domain)")

            res = self._request(
                "POST",
                f"{self.base_url}/api/generate",
                params=params,
            )

            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                # Freemail API 返回的字段是 "email" 而不是 "mailbox"
                email = data.get("email") or data.get("mailbox")
                if email:
                    self.email = email
                    self._log("info", f"Freemail mailbox created: {self.email}")
                    return True
                else:
                    self._log("error", "Freemail response missing email field")
                    return False
            elif res.status_code in (401, 403):
                self._log("error", "Freemail authentication failed (invalid JWT token)")
                return False
            else:
                self._log("error", f"Freemail generate failed: {res.status_code}")
                return False

        except Exception as e:
            self._log("error", f"Freemail register failed: {e}")
            return False

    def login(self) -> bool:
        """登录（Freemail 不需要登录，直接返回 True）"""
        return True

    def fetch_verification_code(self, since_time=None) -> Optional[str]:
        """获取验证码"""
        if not self.email:
            self._log("error", "Email not set")
            return None

        try:
            self._log("info", "Fetching verification code from Freemail")
            params = {
                "mailbox": self.email,
                "admin_token": self.jwt_token,
            }

            res = self._request(
                "GET",
                f"{self.base_url}/api/emails",
                params=params,
            )

            if res.status_code == 401 or res.status_code == 403:
                self._log("error", "Freemail authentication failed")
                return None

            if res.status_code != 200:
                self._log("error", f"Freemail fetch emails failed: {res.status_code}")
                return None

            emails = res.json() if res.content else []
            if not isinstance(emails, list):
                self._log("error", "Freemail response is not a list")
                return None

            if not emails:
                return None

            # 遍历邮件，过滤时间
            for email_data in emails:
                # 时间过滤
                if since_time:
                    created_at = email_data.get("created_at")
                    if created_at:
                        from datetime import datetime
                        try:
                            # 解析时间戳（假设是 ISO 格式或时间戳）
                            if isinstance(created_at, (int, float)):
                                email_time = datetime.fromtimestamp(created_at)
                            else:
                                email_time = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                            
                            if email_time < since_time:
                                continue
                        except Exception:
                            pass

                # 提取邮件内容（Freemail 使用 preview 字段）
                content = email_data.get("content") or ""
                subject = email_data.get("subject") or ""
                html_content = email_data.get("html_content") or ""
                preview = email_data.get("preview") or ""

                full_content = subject + " " + content + " " + html_content + " " + preview
                code = extract_verification_code(full_content)
                if code:
                    self._log("info", f"Verification code found: {code}")
                    return code

            return None

        except Exception as e:
            self._log("error", f"Fetch verification code failed: {e}")
            return None

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time=None,
    ) -> Optional[str]:
        """轮询获取验证码"""
        max_retries = timeout // interval

        for i in range(1, max_retries + 1):
            code = self.fetch_verification_code(since_time=since_time)
            if code:
                return code

            if i < max_retries:
                time.sleep(interval)

        self._log("error", "Verification code timeout")
        return None

    def _get_domain(self) -> str:
        """获取可用域名"""
        try:
            params = {"admin_token": self.jwt_token}
            res = self._request(
                "GET",
                f"{self.base_url}/api/domains",
                params=params,
            )
            if res.status_code == 200:
                domains = res.json() if res.content else []
                if isinstance(domains, list) and domains:
                    return domains[0]
        except Exception:
            pass
        return ""

    def _log(self, level: str, message: str) -> None:
        """日志回调"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass
