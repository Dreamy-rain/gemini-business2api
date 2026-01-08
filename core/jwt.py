"""JWT管理模块

负责JWT token的生成、刷新和管理
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException

if TYPE_CHECKING:
    from main import AccountConfig

logger = logging.getLogger(__name__)


def urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def kq_encode(s: str) -> str:
    b = bytearray()
    for ch in s:
        v = ord(ch)
        if v > 255:
            b.append(v & 255)
            b.append(v >> 8)
        else:
            b.append(v)
    return urlsafe_b64encode(bytes(b))

def create_jwt(key_bytes: bytes, key_id: str, csesidx: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "iss": "https://business.gemini.google",
        "aud": "https://biz-discoveryengine.googleapis.com",
        "sub": f"csesidx/{csesidx}",
        "iat": now,
        "exp": now + 300,
        "nbf": now,
    }
    header_b64  = kq_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = kq_encode(json.dumps(payload, separators=(",", ":")))
    message     = f"{header_b64}.{payload_b64}"
    sig         = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
    return f"{message}.{urlsafe_b64encode(sig)}"


class JWTManager:
    """JWT token管理器

    负责JWT的获取、刷新和缓存
    """
    def __init__(self, config: "AccountConfig", http_client: httpx.AsyncClient, user_agent: str) -> None:
        self.config = config
        self.http_client = http_client
        self.user_agent = user_agent
        self.jwt: str = ""
        self.expires: float = 0
        self._lock = asyncio.Lock()

    async def get(self, request_id: str = "") -> str:
        """获取JWT token（自动刷新）"""
        async with self._lock:
            if time.time() > self.expires:
                await self._refresh(request_id)
            return self.jwt

    async def _refresh(self, request_id: str = "") -> None:
        """刷新JWT token"""
        cookie = f"__Secure-C_SES={self.config.secure_c_ses}"
        if self.config.host_c_oses:
            cookie += f"; __Host-C_OSES={self.config.host_c_oses}"

        req_tag = f"[req_{request_id}] " if request_id else ""
        r = await self.http_client.get(
            "https://business.gemini.google/auth/getoxsrf",
            params={"csesidx": self.config.csesidx},
            headers={
                "cookie": cookie,
                "user-agent": self.user_agent,
                "referer": "https://business.gemini.google/"
            },
        )
        if r.status_code != 200:
            logger.error(f"[AUTH] [{self.config.account_id}] {req_tag}JWT 刷新失败: {r.status_code}")
            raise HTTPException(r.status_code, "getoxsrf failed")

        txt = r.text[4:] if r.text.startswith(")]}'") else r.text
        data = json.loads(txt)

        key_bytes = base64.urlsafe_b64decode(data["xsrfToken"] + "==")
        self.jwt      = create_jwt(key_bytes, data["keyId"], self.config.csesidx)
        self.expires = time.time() + 270
        logger.info(f"[AUTH] [{self.config.account_id}] {req_tag}JWT 刷新成功")
