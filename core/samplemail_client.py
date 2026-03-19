import time
from datetime import datetime, timezone
from typing import Optional

import requests

from core.mail_utils import extract_verification_code
from core.proxy_utils import request_with_proxy_fallback


class SampleMailClient:
    def __init__(
        self,
        base_url: str = "",
        proxy: str = "",
        verify_ssl: bool = True,
        log_callback=None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.verify_ssl = verify_ssl
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.log_callback = log_callback

        self.email: Optional[str] = None
        self.password: Optional[str] = None

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        self._log("info", f"📤 发送 {method} 请求: {url}")
        if "params" in kwargs and kwargs["params"] is not None:
            self._log("info", f"🔎 参数: {kwargs['params']}")

        try:
            res = request_with_proxy_fallback(
                requests.request,
                method,
                url,
                proxies=self.proxies,
                verify=self.verify_ssl,
                timeout=kwargs.pop("timeout", 15),
                **kwargs,
            )
            self._log("info", f"📥 收到响应: HTTP {res.status_code}")
            if res.status_code >= 400:
                try:
                    self._log("error", f"📄 响应内容: {res.text[:500]}")
                except Exception:
                    pass
            return res
        except Exception as e:
            self._log("error", f"❌ 网络请求失败: {e}")
            raise

    def set_credentials(self, email: str, password: str = "") -> None:
        self.email = email
        self.password = password or ""

    def register_account(self, domain: Optional[str] = None) -> bool:
        if not self.base_url:
            self._log("error", "❌ samplemail_base_url 未配置")
            return False

        if domain:
            self._log("warning", "⚠️ Sample Mail 不支持按请求指定域名，将忽略传入 domain")

        try:
            res = self._request("GET", f"{self.base_url}/email/create")
            if res.status_code != 200:
                self._log("error", f"❌ Sample Mail 创建失败: HTTP {res.status_code}")
                return False

            payload = res.json() if res.content else {}
            data = payload.get("data") or {}
            address = data.get("address") if isinstance(data, dict) else None

            if not payload.get("success") or not address:
                self._log("error", "❌ Sample Mail 响应中缺少邮箱地址")
                return False

            self.email = str(address).strip()
            self._log("info", f"✅ Sample Mail 邮箱创建成功: {self.email}")
            return True
        except Exception as e:
            self._log("error", f"❌ Sample Mail 注册异常: {e}")
            return False

    def login(self) -> bool:
        return True

    @staticmethod
    def _parse_message_time(message: dict) -> Optional[datetime]:
        raw_time = message.get("createdAt") or message.get("created_at")
        if raw_time is None:
            return None

        if isinstance(raw_time, (int, float)):
            timestamp = float(raw_time)
            if timestamp > 1e12:
                timestamp = timestamp / 1000.0
            return datetime.fromtimestamp(timestamp).astimezone().replace(tzinfo=None)

        if isinstance(raw_time, str):
            raw = raw_time.strip()
            if not raw:
                return None
            if raw.isdigit():
                timestamp = float(raw)
                if timestamp > 1e12:
                    timestamp = timestamp / 1000.0
                return datetime.fromtimestamp(timestamp).astimezone().replace(tzinfo=None)

            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo:
                    return parsed.astimezone().replace(tzinfo=None)
                return parsed.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
            except Exception:
                return None

        return None

    def fetch_verification_code(self, since_time: Optional[datetime] = None) -> Optional[str]:
        if not self.email:
            self._log("error", "❌ 邮箱地址未设置")
            return None

        try:
            self._log("info", "📬 正在拉取 Sample Mail 邮件列表...")
            res = self._request(
                "GET",
                f"{self.base_url}/email/{self.email}",
                params={"limit": 20},
            )

            if res.status_code != 200:
                self._log("error", f"❌ 获取邮件列表失败: HTTP {res.status_code}")
                return None

            payload = res.json() if res.content else {}
            if not payload.get("success"):
                self._log("error", "❌ Sample Mail 返回失败状态")
                return None

            messages = payload.get("data") or []
            if not isinstance(messages, list):
                self._log("error", "❌ 响应格式错误（data 不是列表）")
                return None

            if not messages:
                self._log("info", "📭 邮箱为空，暂无邮件")
                return None

            self._log("info", f"📨 收到 {len(messages)} 封邮件，开始检查验证码...")

            for index, message in enumerate(messages, 1):
                if not isinstance(message, dict):
                    continue

                if since_time:
                    message_time = self._parse_message_time(message)
                    if message_time is not None and message_time < since_time:
                        continue

                content_parts = [
                    message.get("subject") or "",
                    message.get("text") or "",
                    message.get("html") or "",
                ]
                content = "\n".join(part for part in content_parts if isinstance(part, str) and part)
                if not content:
                    self._log("info", f"ℹ️ 第 {index} 封邮件缺少可提取内容，跳过")
                    continue

                code = extract_verification_code(content)
                if code:
                    self._log("info", f"✅ 找到验证码: {code}")
                    return code

            self._log("warning", "⚠️ 所有邮件中均未找到验证码")
            return None
        except Exception as e:
            self._log("error", f"❌ 获取验证码异常: {e}")
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
                self._log("info", f"⏳ 等待 {interval} 秒后重试...")
                time.sleep(interval)

        self._log("error", f"⏰ 验证码获取超时 ({timeout}秒)")
        return None
