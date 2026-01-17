import imaplib
import time
from datetime import datetime, timedelta
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from core.mail_utils import extract_verification_code


class MicrosoftMailClient:
    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        tenant: str = "consumers",
        proxy: str = "",
        log_callback=None,
    ) -> None:
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.tenant = tenant or "consumers"
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.log_callback = log_callback
        self.email: Optional[str] = None

    def set_credentials(self, email: str, password: Optional[str] = None) -> None:
        self.email = email

    def _get_access_token(self) -> Optional[str]:
        url = f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        try:
            res = requests.post(url, data=data, proxies=self.proxies, timeout=15)
            if res.status_code != 200:
                self._log("error", f"Microsoft token error: {res.status_code}")
                return None
            payload = res.json() if res.content else {}
            token = payload.get("access_token")
            if not token:
                self._log("error", "Microsoft token missing")
                return None
            return token
        except Exception as exc:
            self._log("error", f"Microsoft token exception: {exc}")
            return None

    def fetch_verification_code(self, since_time: Optional[datetime] = None) -> Optional[str]:
        if not self.email:
            return None

        self._log("info", "fetching verification code")
        token = self._get_access_token()
        if not token:
            return None

        auth_string = f"user={self.email}\x01auth=Bearer {token}\x01\x01".encode()
        client = imaplib.IMAP4_SSL("outlook.office365.com", 993)
        try:
            client.authenticate("XOAUTH2", lambda _: auth_string)
        except Exception as exc:
            self._log("error", f"IMAP auth failed: {exc}")
            try:
                client.logout()
            except Exception:
                pass
            return None

        search_since = since_time or (datetime.now() - timedelta(minutes=5))

        try:
            for mailbox in ("INBOX", "Junk"):
                try:
                    status, _ = client.select(mailbox, readonly=True)
                    if status != "OK":
                        continue
                except Exception:
                    continue

                # 搜索所有邮件
                status, data = client.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    continue

                ids = data[0].split()[-5:]  # 只检查最近 5 封

                for msg_id in reversed(ids):
                    status, msg_data = client.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data:
                        continue
                    raw_bytes = None
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) > 1:
                            raw_bytes = item[1]
                            break
                    if not raw_bytes:
                        continue

                    msg = message_from_bytes(raw_bytes)
                    msg_date = self._parse_message_date(msg.get("Date"))

                    # 按时间过滤
                    if msg_date and msg_date < search_since:
                        continue

                    content = self._message_to_text(msg)
                    import re
                    match = re.search(r'[A-Z0-9]{6}', content)
                    if match:
                        code = match.group(0)
                        self._log("info", f"code found in {mailbox}: {code}")
                        return code
        finally:
            try:
                client.logout()
            except Exception:
                pass

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

        for i in range(1, max_retries + 1):
            code = self.fetch_verification_code(since_time=since_time)
            if code:
                return code
            if i < max_retries:
                time.sleep(interval)

        self._log("error", "verification code timeout")
        return None

    @staticmethod
    def _message_to_text(msg) -> str:
        if msg.is_multipart():
            parts = []
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type not in ("text/plain", "text/html"):
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                parts.append(payload.decode(charset, errors="ignore"))
            return "".join(parts)
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
        return str(payload) if payload else ""

    @staticmethod
    def _parse_message_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
            if parsed is None:
                return None
            if parsed.tzinfo:
                return parsed.astimezone(tz=None).replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass
