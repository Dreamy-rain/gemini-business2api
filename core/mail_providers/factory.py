from typing import Callable, Optional

from core.config import config
from core.proxy_utils import extract_host, no_proxy_matches, parse_proxy_setting
from core.duckmail_client import DuckMailClient
from core.freemail_client import FreemailClient
from core.gptmail_client import GPTMailClient
from core.moemail_client import MoemailClient


def create_temp_mail_client(
    provider: str,
    *,
    domain: Optional[str] = None,
    proxy: Optional[str] = None,
    log_cb: Optional[Callable[[str, str], None]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    jwt_token: Optional[str] = None,
    verify_ssl: Optional[bool] = None,
):
    """
    创建临时邮箱客户端

    参数优先级：传入参数 > 全局配置
    """
    provider = (provider or "duckmail").lower()
    if proxy is None:
        proxy = config.basic.proxy_for_auth if config.basic.mail_proxy_enabled else ""
    proxy, no_proxy = parse_proxy_setting(proxy if config.basic.mail_proxy_enabled else "")

    if provider == "moemail":
        effective_base_url = base_url or config.basic.moemail_base_url
        if no_proxy_matches(extract_host(effective_base_url), no_proxy):
            proxy = ""
        return MoemailClient(
            base_url=effective_base_url,
            proxy=proxy,
            api_key=api_key or config.basic.moemail_api_key,
            domain=domain or config.basic.moemail_domain,
            log_callback=log_cb,
        )

    if provider == "freemail":
        effective_base_url = base_url or config.basic.freemail_base_url
        if no_proxy_matches(extract_host(effective_base_url), no_proxy):
            proxy = ""
        return FreemailClient(
            base_url=effective_base_url,
            jwt_token=jwt_token or config.basic.freemail_jwt_token,
            proxy=proxy,
            verify_ssl=verify_ssl if verify_ssl is not None else config.basic.freemail_verify_ssl,
            log_callback=log_cb,
        )

    if provider == "gptmail":
        effective_base_url = base_url or config.basic.gptmail_base_url
        if no_proxy_matches(extract_host(effective_base_url), no_proxy):
            proxy = ""
        return GPTMailClient(
            base_url=effective_base_url,
            api_key=api_key or config.basic.gptmail_api_key,
            proxy=proxy,
            verify_ssl=verify_ssl if verify_ssl is not None else config.basic.gptmail_verify_ssl,
            domain=domain or config.basic.gptmail_domain,
            log_callback=log_cb,
        )

    effective_base_url = base_url or config.basic.duckmail_base_url
    if no_proxy_matches(extract_host(effective_base_url), no_proxy):
        proxy = ""
    return DuckMailClient(
        base_url=effective_base_url,
        proxy=proxy,
        verify_ssl=verify_ssl if verify_ssl is not None else config.basic.duckmail_verify_ssl,
        api_key=api_key or config.basic.duckmail_api_key,
        log_callback=log_cb,
    )
