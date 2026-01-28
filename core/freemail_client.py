import random
import string
import time
from typing import Optional

import requests

from core.mail_utils import extract_verification_code
from core.proxy_utils import request_with_proxy_fallback


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
        """设置邮箱凭证（Freemail 不需要密码）"""
        self.email = email

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送请求并打印日志"""
        self._log("info", f"📤 发送 {method} 请求: {url}")
        if "params" in kwargs:
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

    def register_account(self, domain: Optional[str] = None) -> bool:
        """创建新的临时邮箱"""
        try:
            params = {"admin_token": self.jwt_token}
            if domain:
                params["domain"] = domain
                self._log("info", f"📧 使用域名: {domain}")
            else:
                self._log("info", "🔍 自动选择域名...")

            res = self._request(
                "POST",
                f"{self.base_url}/api/generate",
                params=params,
            )

            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                # Freemail API 返回的字段是 "email" 或 "mailbox"
                email = data.get("email") or data.get("mailbox")
                if email:
                    self.email = email
                    self._log("info", f"✅ Freemail 邮箱创建成功: {self.email}")
                    return True
                else:
                    self._log("error", "❌ 响应中缺少 email 字段")
                    return False
            elif res.status_code in (401, 403):
                self._log("error", "❌ Freemail 认证失败 (JWT Token 无效)")
                return False
            else:
                self._log("error", f"❌ Freemail 创建失败: HTTP {res.status_code}")
                return False

        except Exception as e:
            self._log("error", f"❌ Freemail 注册异常: {e}")
            return False

    def login(self) -> bool:
        """登录（Freemail 不需要登录，直接返回 True）"""
        return True

    def fetch_verification_code(self, since_time=None) -> Optional[str]:
        """获取验证码"""
        if not self.email:
            self._log("error", "❌ 邮箱地址未设置")
            return None

        try:
            self._log("info", "📬 正在拉取 Freemail 邮件列表...")
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
                self._log("error", "❌ Freemail 认证失败")
                return None

            if res.status_code != 200:
                self._log("error", f"❌ 获取邮件列表失败: HTTP {res.status_code}")
                return None

            emails = res.json() if res.content else []
            if not isinstance(emails, list):
                self._log("error", "❌ 响应格式错误（不是列表）")
                return None

            if not emails:
                self._log("info", "📭 邮箱为空，暂无邮件")
                return None

            self._log("info", f"📨 收到 {len(emails)} 封邮件，开始检查验证码...")

            # 从最新一封邮件开始查找
            for idx, email_data in enumerate(emails, 1):
                # 时间过滤
                if since_time:
                    created_at = email_data.get("created_at")
                    if created_at:
                        from datetime import datetime
                        try:
                            # 解析时间戳或 ISO 格式时间戳
                            if isinstance(created_at, (int, float)):
                                email_time = datetime.fromtimestamp(created_at)
                            else:
                                email_time = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)

                            if email_time < since_time:
                                self._log("info", f"⏭️ 邮件 {idx} 时间过早，跳过")
                                continue
                        except Exception:
                            pass

                # 提取验证码
                content = email_data.get("content") or ""
                subject = email_data.get("subject") or ""
                html_content = email_data.get("html_content") or ""
                preview = email_data.get("preview") or ""

                full_content = subject + " " + content + " " + html_content + " " + preview
                code = extract_verification_code(full_content)
                if code:
                    self._log("info", f"✅ 找到验证码: {code}")
                    return code
                else:
                    self._log("info", f"❌ 邮件 {idx} 中未找到验证码")

            self._log("warning", "⚠️ 所有邮件中均未找到验证码")
            return None

        except Exception as e:
            self._log("error", f"❌ 获取验证码异常: {e}")
            return None

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time=None,
    ) -> Optional[str]:
        """轮询获取验证码"""
        max_retries = timeout // interval
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
