import os
import random
import string
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from core.mail_utils import extract_verification_code


class GPTMailClient:
    """GPTMail 客户端（临时邮箱）"""

    def __init__(
        self,
        base_url: str = "https://mail.chatgpt.org.uk",
        proxy: str = "",
        verify_ssl: bool = True,
        api_key: str = "",
        log_callback=None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.verify_ssl = verify_ssl
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.api_key = (api_key or "").strip()
        self.log_callback = log_callback

        self.email: Optional[str] = None

    def set_credentials(self, email: str, password: Optional[str] = None) -> None:
        self.email = email

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", None) or {}
        if self.api_key and "X-API-Key" not in headers:
            headers["X-API-Key"] = self.api_key
        kwargs["headers"] = headers

        self._log("info", f"📤 发送 {method} 请求: {url}")
        if "params" in kwargs and kwargs["params"]:
            self._log("info", f"🔎 Query: {kwargs['params']}")
        if "json" in kwargs and kwargs["json"] is not None:
            self._log("info", f"📦 请求体: {kwargs['json']}")

        try:
            res = requests.request(
                method,
                url,
                proxies=self.proxies,
                verify=self.verify_ssl,
                timeout=kwargs.pop("timeout", 15),
                **kwargs,
            )
            self._log("info", f"📥 收到响应: HTTP {res.status_code}")
            log_body = os.getenv("GPTMAIL_LOG_BODY", "").strip().lower() in ("1", "true", "yes", "y", "on")
            if res.content and (log_body or res.status_code >= 400):
                try:
                    self._log("info", f"📄 响应内容: {res.text[:500]}")
                except Exception:
                    pass
            return res
        except Exception as exc:
            self._log("error", f"❌ 网络请求失败: {exc}")
            raise

    def generate_email(self, domain: Optional[str] = None) -> Optional[str]:
        """生成一个新的邮箱地址。"""
        if not self.base_url:
            self._log("error", "❌ GPTMail base_url 为空")
            return None

        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        timestamp = str(int(time.time()))[-4:]
        prefix = f"t{timestamp}{rand}"

        payload: Dict[str, Any] = {"prefix": prefix}
        if domain:
            payload["domain"] = domain

        url = f"{self.base_url}/api/generate-email"
        try:
            res = self._request("POST", url, json=payload)
            if res.status_code != 200:
                self._log("error", f"❌ 生成邮箱失败: HTTP {res.status_code}")
                return None
            body = res.json() if res.content else {}
            if not body.get("success"):
                self._log("error", f"❌ 生成邮箱失败: {body.get('error') or 'unknown error'}")
                return None
            email = ((body.get("data") or {}).get("email") or "").strip()
            if not email:
                self._log("error", "❌ 生成邮箱成功但响应缺少 email")
                return None
            self.email = email
            self._log("info", f"✅ GPTMail 邮箱生成成功: {email}")
            return email
        except Exception as exc:
            self._log("error", f"❌ 生成邮箱异常: {exc}")
            return None

    def _list_emails(self, email: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/emails"
        res = self._request("GET", url, params={"email": email})
        if res.status_code != 200:
            self._log("error", f"❌ 获取邮件列表失败: HTTP {res.status_code}")
            return []
        body = res.json() if res.content else {}
        if not body.get("success"):
            self._log("error", f"❌ 获取邮件列表失败: {body.get('error') or 'unknown error'}")
            return []
        return list(((body.get("data") or {}).get("emails") or []))

    def _get_email(self, mail_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/email/{mail_id}"
        res = self._request("GET", url)
        if res.status_code != 200:
            self._log("warning", f"⚠️ 获取邮件详情失败: HTTP {res.status_code}")
            return None
        body = res.json() if res.content else {}
        if not body.get("success"):
            self._log("warning", f"⚠️ 获取邮件详情失败: {body.get('error') or 'unknown error'}")
            return None
        return body.get("data") or None

    def fetch_verification_code(self, since_time: Optional[datetime] = None) -> Optional[str]:
        """获取验证码（从邮件内容提取）。"""
        if not self.email:
            return None

        try:
            self._log("info", "📬 正在拉取 GPTMail 邮件列表...")
            emails = self._list_emails(self.email)
            if not emails:
                self._log("info", "📭 邮箱为空，暂无邮件")
                return None

            emails = sorted(emails, key=lambda item: int(item.get("timestamp") or 0), reverse=True)
            self._log("info", f"📨 收到 {len(emails)} 封邮件，开始检查验证码...")

            for idx, msg in enumerate(emails, 1):
                msg_id = str(msg.get("id") or "").strip()
                if not msg_id:
                    continue

                ts = msg.get("timestamp")
                if since_time and ts:
                    try:
                        msg_time = datetime.fromtimestamp(int(ts)).astimezone().replace(tzinfo=None)
                        if msg_time < since_time:
                            continue
                    except Exception:
                        pass

                content = (msg.get("content") or "") + (msg.get("html_content") or "")
                code = extract_verification_code(content)
                if code:
                    self._log("info", f"✅ 找到验证码: {code}")
                    return code

                detail = self._get_email(msg_id)
                if not detail:
                    continue

                detail_text = (
                    (detail.get("content") or "")
                    + (detail.get("html_content") or "")
                    + (detail.get("raw_content") or "")
                )
                code = extract_verification_code(detail_text)
                if code:
                    self._log("info", f"✅ 找到验证码: {code}")
                    return code

            self._log("warning", "⚠️ 所有邮件中均未找到验证码")
            return None
        except Exception as exc:
            self._log("error", f"❌ 获取验证码异常: {exc}")
            return None

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time: Optional[datetime] = None,
    ) -> Optional[str]:
        if not self.email:
            return None

        max_retries = max(1, timeout // interval)
        self._log("info", f"⏱️ 开始轮询验证码 (超时 {timeout}秒, 间隔 {interval}秒, 最多 {max_retries} 次)")

        for i in range(1, max_retries + 1):
            self._log("info", f"🔄 第 {i}/{max_retries} 次轮询...")
            code = self.fetch_verification_code(since_time=since_time)
            if code:
                self._log("info", f"🎉 验证码获取成功: {code}")
                return code
            if i < max_retries:
                time.sleep(interval)

        self._log("error", "❌ 验证码获取超时")
        return None

