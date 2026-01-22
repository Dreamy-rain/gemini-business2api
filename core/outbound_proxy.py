import base64
import hashlib
import ipaddress
from contextlib import asynccontextmanager
from typing import Iterable, Optional, Sequence
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field


DEFAULT_GEMINI_PROXY_HOST_SUFFIXES = (
    "biz-discoveryengine.googleapis.com",
    "business.gemini.google",
    "auth.business.gemini.google",
)


def _derive_fernet_key(secret: str, purpose: str) -> bytes:
    material = hashlib.sha256(f"{purpose}:{secret}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(material)


def encrypt_secret(plain: str, secret_key: str, *, purpose: str) -> str:
    if not plain:
        return ""
    fernet = Fernet(_derive_fernet_key(secret_key, purpose))
    return fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str, secret_key: str, *, purpose: str) -> str:
    if not token:
        return ""
    fernet = Fernet(_derive_fernet_key(secret_key, purpose))
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def _split_no_proxy(no_proxy: str) -> list[str]:
    if not no_proxy:
        return []
    items = []
    for raw in no_proxy.split(","):
        item = raw.strip()
        if item:
            items.append(item)
    return items


def no_proxy_matches(host: str, no_proxy: str) -> bool:
    if not host:
        return False
    host = host.strip().lower().strip("[]")
    if not host:
        return False

    entries = _split_no_proxy(no_proxy)
    if not entries:
        return False

    host_ip: Optional[ipaddress._BaseAddress] = None
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None

    for entry in entries:
        e = entry.lower()
        if e == "*":
            return True

        if "/" in e and host_ip is not None:
            try:
                net = ipaddress.ip_network(e, strict=False)
                if host_ip in net:
                    return True
                continue
            except ValueError:
                pass

        if e.endswith(".") and host.startswith(e):
            return True

        if e.startswith("."):
            suffix = e
            bare = e[1:]
            if host == bare or host.endswith(suffix):
                return True
            continue

        if host == e:
            return True

    return False


def _host_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def host_matches_any_suffix(host: str, suffixes: Iterable[str]) -> bool:
    host = (host or "").lower()
    if not host:
        return False
    for suffix in suffixes:
        s = (suffix or "").lower()
        if not s:
            continue
        if host == s or host.endswith(f".{s}"):
            return True
    return False


def normalize_proxy_url(raw: str, *, default_scheme: str = "http") -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    if "://" in value:
        return value

    if "@" in value:
        return f"{default_scheme}://{value}"

    parts = value.split(":")
    if len(parts) == 2:
        host, port = parts
        if port.isdigit():
            return f"{default_scheme}://{host}:{port}"
        return value

    if len(parts) >= 4:
        host = parts[0]
        port = parts[1]
        username = parts[2]
        password = ":".join(parts[3:])
        if port.isdigit():
            u = quote(username, safe="")
            p = quote(password, safe="")
            return f"{default_scheme}://{u}:{p}@{host}:{port}"

    return value


class OutboundProxyConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用出站代理")
    protocol: str = Field(default="http", description="代理协议：http/https/socks5/socks5h")
    host: str = Field(default="", description="代理主机")
    port: int = Field(default=0, ge=0, le=65535, description="代理端口")
    username: str = Field(default="", description="代理用户名（可选）")
    password_enc: str = Field(default="", description="代理密码密文（持久化）")
    no_proxy: str = Field(default="", description="NO_PROXY（逗号分隔）")
    direct_fallback: bool = Field(default=True, description="代理失败是否自动直连重试")

    def fingerprint(self) -> tuple:
        return (
            bool(self.enabled),
            (self.protocol or "").strip().lower(),
            (self.host or "").strip(),
            int(self.port or 0),
            (self.username or ""),
            (self.password_enc or ""),
            (self.no_proxy or ""),
            bool(self.direct_fallback),
        )

    def is_configured(self) -> bool:
        return bool(self.enabled and (self.host or "").strip() and int(self.port or 0) > 0)

    def decrypt_password(self, secret_key: str) -> str:
        return decrypt_secret(self.password_enc or "", secret_key, purpose="outbound-proxy-password")

    def encrypt_password(self, plain: str, secret_key: str) -> str:
        return encrypt_secret(plain or "", secret_key, purpose="outbound-proxy-password")

    def to_proxy_url(self, secret_key: str) -> str:
        if not self.is_configured():
            return ""
        protocol = (self.protocol or "http").strip().lower()
        if protocol not in ("http", "https", "socks5", "socks5h"):
            protocol = "http"

        auth = ""
        username = (self.username or "").strip()
        password = self.decrypt_password(secret_key).strip()
        if username and password:
            auth = f"{username}:{password}@"
        elif username and not password:
            auth = f"{username}@"

        return f"{protocol}://{auth}{self.host.strip()}:{int(self.port)}"


class ProxyAwareAsyncClient:
    def __init__(
        self,
        *,
        proxy_url: Optional[str],
        no_proxy: str,
        direct_fallback: bool,
        proxied_host_suffixes: Sequence[str],
        client_kwargs: dict,
    ) -> None:
        self._proxy_url = (proxy_url or "").strip() or None
        self._no_proxy = no_proxy or ""
        self._direct_fallback = bool(direct_fallback)
        self._proxied_host_suffixes = tuple(proxied_host_suffixes or ())

        direct_kwargs = dict(client_kwargs)
        direct_kwargs["proxy"] = None
        self._direct = httpx.AsyncClient(**direct_kwargs)

        if self._proxy_url:
            proxy_kwargs = dict(client_kwargs)
            proxy_kwargs["proxy"] = self._proxy_url
            self._proxy = httpx.AsyncClient(**proxy_kwargs)
        else:
            self._proxy = None

    def _should_use_proxy(self, url: str) -> bool:
        if not self._proxy:
            return False
        host = _host_from_url(url)
        if not host:
            return False
        if no_proxy_matches(host, self._no_proxy):
            return False
        if not self._proxied_host_suffixes:
            return True
        return host_matches_any_suffix(host, self._proxied_host_suffixes)

    async def aclose(self) -> None:
        if self._proxy:
            await self._proxy.aclose()
        await self._direct.aclose()

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if not self._should_use_proxy(url):
            return await self._direct.request(method, url, **kwargs)

        assert self._proxy is not None
        try:
            resp = await self._proxy.request(method, url, **kwargs)
        except httpx.HTTPError:
            if not self._direct_fallback:
                raise
            return await self._direct.request(method, url, **kwargs)

        if resp.status_code == 407 and self._direct_fallback:
            try:
                await resp.aclose()
            except Exception:
                pass
            return await self._direct.request(method, url, **kwargs)

        return resp

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    @asynccontextmanager
    async def stream(self, method: str, url: str, **kwargs):
        if not self._should_use_proxy(url):
            async with self._direct.stream(method, url, **kwargs) as resp:
                yield resp
            return

        assert self._proxy is not None
        try:
            async with self._proxy.stream(method, url, **kwargs) as resp:
                if resp.status_code == 407 and self._direct_fallback:
                    try:
                        await resp.aclose()
                    except Exception:
                        pass
                else:
                    yield resp
                    return
        except httpx.HTTPError:
            if not self._direct_fallback:
                raise

        async with self._direct.stream(method, url, **kwargs) as resp:
            yield resp

