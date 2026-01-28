"""
代理设置工具函数

支持格式:
- http://127.0.0.1:7890
- http://user:pass@127.0.0.1:7890
- socks5h://127.0.0.1:7890
- socks5h://user:pass@127.0.0.1:7890 | no_proxy=localhost,127.0.0.1,.local

NO_PROXY 格式:
- 逗号分隔的主机名或域名后缀
- 支持通配符前缀，如 .local 匹配 *.local
"""

import re
from typing import Tuple, Callable, Any, Optional
from urllib.parse import urlparse
import functools


def parse_proxy_setting(proxy_str: str) -> Tuple[str, str]:
    """
    解析代理设置字符串，提取代理 URL 和 NO_PROXY 列表

    Args:
        proxy_str: 代理设置字符串，格式如 "http://127.0.0.1:7890 | no_proxy=localhost,127.0.0.1"

    Returns:
        Tuple[str, str]: (proxy_url, no_proxy_list)
        - proxy_url: 代理地址，如 "http://127.0.0.1:7890"
        - no_proxy_list: NO_PROXY 列表字符串，如 "localhost,127.0.0.1"
    """
    if not proxy_str:
        return "", ""

    proxy_str = proxy_str.strip()
    if not proxy_str:
        return "", ""

    # 检查是否包含 no_proxy 设置
    # 支持格式: proxy_url | no_proxy=host1,host2
    no_proxy = ""
    proxy_url = proxy_str

    # 使用 | 分隔代理和 no_proxy
    if "|" in proxy_str:
        parts = proxy_str.split("|", 1)
        proxy_url = parts[0].strip()
        no_proxy_part = parts[1].strip()

        # 解析 no_proxy=xxx 格式
        no_proxy_match = re.match(r"no_proxy\s*=\s*(.+)", no_proxy_part, re.IGNORECASE)
        if no_proxy_match:
            no_proxy = no_proxy_match.group(1).strip()

    return proxy_url, no_proxy


def extract_host(url: str) -> str:
    """
    从 URL 中提取主机名

    Args:
        url: 完整 URL，如 "https://mail.chatgpt.org.uk/api/emails"

    Returns:
        str: 主机名，如 "mail.chatgpt.org.uk"
    """
    if not url:
        return ""

    url = url.strip()
    if not url:
        return ""

    # 如果没有协议前缀，添加一个以便解析
    if not url.startswith(("http://", "https://", "socks5://", "socks5h://")):
        url = "http://" + url

    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


def no_proxy_matches(host: str, no_proxy: str) -> bool:
    """
    检查主机是否在 NO_PROXY 豁免列表中

    Args:
        host: 要检查的主机名，如 "mail.chatgpt.org.uk"
        no_proxy: NO_PROXY 列表字符串，如 "localhost,127.0.0.1,.local"

    Returns:
        bool: 如果主机在豁免列表中返回 True，否则返回 False

    匹配规则:
        - 精确匹配: "localhost" 匹配 "localhost"
        - 域名后缀匹配: ".local" 匹配 "foo.local", "bar.foo.local"
        - IP 地址匹配: "127.0.0.1" 精确匹配
    """
    if not host or not no_proxy:
        return False

    host = host.lower().strip()
    if not host:
        return False

    # 解析 no_proxy 列表
    no_proxy_list = [item.strip().lower() for item in no_proxy.split(",") if item.strip()]

    for pattern in no_proxy_list:
        if not pattern:
            continue

        # 精确匹配
        if host == pattern:
            return True

        # 域名后缀匹配 (如 .local 匹配 foo.local)
        if pattern.startswith("."):
            if host.endswith(pattern) or host == pattern[1:]:
                return True
        else:
            # 也支持不带点的后缀匹配 (如 local 匹配 foo.local)
            if host.endswith("." + pattern):
                return True

    return False


def normalize_proxy_url(proxy_str: str) -> str:
    """
    标准化代理 URL 格式

    支持的输入格式:
    - http://127.0.0.1:7890
    - http://user:pass@127.0.0.1:7890
    - socks5://127.0.0.1:7890
    - socks5h://127.0.0.1:7890
    - 127.0.0.1:7890 (自动添加 http://)
    - host:port:user:pass (旧格式，自动转换)

    Returns:
        str: 标准化的代理 URL
    """
    if not proxy_str:
        return ""

    proxy_str = proxy_str.strip()
    if not proxy_str:
        return ""

    # 如果已经是标准 URL 格式，直接返回
    if proxy_str.startswith(("http://", "https://", "socks5://", "socks5h://")):
        return proxy_str

    # 尝试解析旧格式 host:port:user:pass
    parts = proxy_str.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    elif len(parts) == 2:
        # host:port 格式
        return f"http://{proxy_str}"

    # 无法识别的格式，尝试添加 http:// 前缀
    return f"http://{proxy_str}"


def request_with_proxy_fallback(request_func: Callable, *args, **kwargs) -> Any:
    """
    带代理失败回退的请求包装器

    如果代理连接失败，自动禁用代理重试一次

    Args:
        request_func: 原始请求函数
        *args, **kwargs: 传递给请求函数的参数

    Returns:
        请求响应对象

    Raises:
        原始异常（如果直连也失败）
    """
    # 代理相关的错误类型
    PROXY_ERRORS = (
        "ProxyError",
        "ConnectTimeout",
        "ConnectionError",
        "407",  # Proxy Authentication Required
        "502",  # Bad Gateway (代理问题)
        "503",  # Service Unavailable (代理问题)
    )

    try:
        # 首次尝试（使用代理）
        return request_func(*args, **kwargs)
    except Exception as e:
        error_str = str(e)
        error_type = type(e).__name__

        # 检查是否是代理相关错误
        is_proxy_error = any(err in error_str or err in error_type for err in PROXY_ERRORS)

        if is_proxy_error and "proxies" in kwargs:
            # 禁用代理重试
            original_proxies = kwargs.get("proxies")
            kwargs["proxies"] = None

            try:
                # 直连重试
                return request_func(*args, **kwargs)
            except Exception:
                # 直连也失败，恢复原始代理设置并抛出原始异常
                kwargs["proxies"] = original_proxies
                raise e
        else:
            # 不是代理错误，直接抛出
            raise
