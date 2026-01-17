import os
import random
import string
import time
from typing import Optional

import requests

from core.mail_utils import extract_verification_code


class DuckMailClient:
    """DuckMail客户端"""

    def __init__(
        self,
        base_url: str = "https://api.duckmail.sbs",
        proxy: str = "",
        verify_ssl: bool = True,
        api_key: str = "",
        log_callback=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.api_key = api_key.strip()
        self.log_callback = log_callback

        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.account_id: Optional[str] = None
        self.token: Optional[str] = None

    def set_credentials(self, email: str, password: str) -> None:
        self.email = email
        self.password = password

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送请求并打印详细日志"""
        headers = kwargs.pop("headers", None) or {}
        if self.api_key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.api_key}"
        kwargs["headers"] = headers
        self._log("info", f"[HTTP] {method} {url}")
        if "json" in kwargs:
            self._log("info", f"[HTTP] Request body: {kwargs['json']}")

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
            log_body = os.getenv("DUCKMAIL_LOG_BODY", "").strip().lower() in ("1", "true", "yes", "y", "on")
            if res.content and (log_body or res.status_code >= 400):
                try:
                    self._log("info", f"[HTTP] Response body: {res.text[:500]}")
                except Exception:
                    pass
            return res
        except Exception as e:
            self._log("error", f"[HTTP] Request failed: {e}")
            raise

    def register_account(self, domain: Optional[str] = None) -> bool:
        """注册新邮箱账号"""
        # 获取域名
        if not domain:
            domain = self._get_domain()
        self._log("info", f"DuckMail domain: {domain}")

        # 生成随机邮箱和密码
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        timestamp = str(int(time.time()))[-4:]
        self.email = f"t{timestamp}{rand}@{domain}"
        self.password = f"Pwd{rand}{timestamp}"
        self._log("info", f"DuckMail register email: {self.email}")

        try:
            res = self._request(
                "POST",
                f"{self.base_url}/accounts",
                json={"address": self.email, "password": self.password},
            )
            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                self.account_id = data.get("id")
                self._log("info", "DuckMail register success")
                return True
        except Exception as e:
            self._log("error", f"DuckMail register failed: {e}")
            return False

        self._log("error", "DuckMail register failed")
        return False

    def login(self) -> bool:
        """登录获取token"""
        if not self.email or not self.password:
            return False

        try:
            res = self._request(
                "POST",
                f"{self.base_url}/token",
                json={"address": self.email, "password": self.password},
            )
            if res.status_code == 200:
                data = res.json() if res.content else {}
                token = data.get("token")
                if token:
                    self.token = token
                    self._log("info", f"DuckMail login success, token: {token[:20]}...")
                    return True
        except Exception as e:
            self._log("error", f"DuckMail login failed: {e}")
            return False

        self._log("error", "DuckMail login failed")
        return False

    def fetch_verification_code(self, since_time=None) -> Optional[str]:
        """获取验证码"""
        if not self.token:
            if not self.login():
                return None

        try:
            self._log("info", "fetching verification code")
            # 获取邮件列表
            res = self._request(
                "GET",
                f"{self.base_url}/messages",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if res.status_code != 200:
                return None

            data = res.json() if res.content else {}
            messages = data.get("hydra:member", [])

            if not messages:
                return None

            # 只获取最新一封邮件，不做时间过滤
            msg_id = messages[0].get("id")
            if not msg_id:
                return None

            detail = self._request(
                "GET",
                f"{self.base_url}/messages/{msg_id}",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if detail.status_code != 200:
                return None

            payload = detail.json() if detail.content else {}

            # 获取邮件内容
            text_content = payload.get("text") or ""
            html_content = payload.get("html") or ""

            if isinstance(html_content, list):
                html_content = "".join(str(item) for item in html_content)
            if isinstance(text_content, list):
                text_content = "".join(str(item) for item in text_content)

            content = text_content + html_content
            code = extract_verification_code(content)
            if code:
                self._log("info", f"code found: {code}")
            return code

        except Exception as e:
            self._log("error", f"fetch code failed: {e}")
            return None

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time=None,
    ) -> Optional[str]:
        """轮询获取验证码"""
        if not self.token:
            if not self.login():
                return None

        max_retries = timeout // interval

        for i in range(1, max_retries + 1):
            code = self.fetch_verification_code(since_time=since_time)
            if code:
                return code

            if i < max_retries:
                time.sleep(interval)

        self._log("error", "verification code timeout")
        return None

    def _get_domain(self) -> str:
        """获取可用域名"""
        try:
            res = self._request("GET", f"{self.base_url}/domains")
            if res.status_code == 200:
                data = res.json() if res.content else {}
                members = data.get("hydra:member", [])
                if members:
                    return members[0].get("domain") or "duck.com"
        except Exception:
            pass
        return "duck.com"

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    @staticmethod
    def _extract_code(text: str) -> Optional[str]:
        return extract_verification_code(text)
