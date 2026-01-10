"""
模板数据准备函数
用于为 Jinja2 模板准备数据（纯数据，不包含 HTML）
"""

from core.config import config_manager, config
from core.account import format_account_expiration


def get_base_url_from_request(request) -> str:
    """从请求中获取完整的base URL"""
    # 优先使用配置的 BASE_URL
    if config.basic.base_url:
        return config.basic.base_url.rstrip("/")

    # 自动从请求获取（兼容反向代理）
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host"))

    return f"{forwarded_proto}://{forwarded_host}"


def _get_account_status(account_manager):
    """提取账户状态判断逻辑（返回纯数据）"""
    config_obj = account_manager.config
    remaining_hours = config_obj.get_remaining_hours()
    expire_status_text, _, expire_display = format_account_expiration(remaining_hours)

    is_expired = config_obj.is_expired()
    is_disabled = config_obj.disabled
    cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()

    # 确定账户状态和颜色
    if is_expired:
        status_text = "过期禁用"
        status_color = "#9e9e9e"
        dot_color = "#9e9e9e"
        row_opacity = "0.5"
        is_permanently_failed = False
    elif is_disabled:
        status_text = "手动禁用"
        status_color = "#9e9e9e"
        dot_color = "#9e9e9e"
        row_opacity = "0.5"
        is_permanently_failed = False
    elif cooldown_seconds == -1:
        status_text = cooldown_reason
        status_color = "#f44336"
        dot_color = "#f44336"
        row_opacity = "0.5"
        is_permanently_failed = True
    elif cooldown_seconds > 0:
        status_text = f"{cooldown_reason} ({cooldown_seconds}s)"
        status_color = "#ff9800"
        dot_color = "#ff9800"
        row_opacity = "1"
        is_permanently_failed = False
    else:
        is_avail = account_manager.is_available
        if is_avail:
            status_text = expire_status_text
            if expire_status_text == "正常":
                status_color = "#4caf50"
                dot_color = "#34c759"
            elif expire_status_text == "即将过期":
                status_color = "#ff9800"
                dot_color = "#ff9800"
            else:
                status_color = "#f44336"
                dot_color = "#f44336"
        else:
            status_text = "不可用"
            status_color = "#f44336"
            dot_color = "#ff3b30"
        row_opacity = "1"
        is_permanently_failed = False

    return {
        "account_id": config_obj.account_id,
        "status_text": status_text,
        "status_color": status_color,
        "dot_color": dot_color,
        "row_opacity": row_opacity,
        "expire_display": expire_display,
        "expires_at": config_obj.expires_at,
        "conversation_count": account_manager.conversation_count,
        "is_expired": is_expired,
        "is_disabled": is_disabled,
        "is_permanently_failed": is_permanently_failed,
    }


def prepare_admin_template_data(
    request, multi_account_mgr, log_buffer, log_lock,
    api_key, base_url, proxy, logo_url, chat_url, path_prefix,
    max_new_session_tries, max_request_retries, max_account_switch_tries,
    account_failure_threshold, rate_limit_cooldown_seconds, session_cache_ttl_seconds
) -> dict:
    """准备完整的管理页面模板数据（纯数据，不包含 HTML）"""
    # 获取当前页面的完整URL
    current_url = get_base_url_from_request(request)

    # 获取错误统计
    error_count = 0
    with log_lock:
        for log in log_buffer:
            if log.get("level") in ["ERROR", "CRITICAL"]:
                error_count += 1

    # API接口信息
    admin_path_segment = f"{path_prefix}" if path_prefix else "admin"
    api_path_segment = f"{path_prefix}/" if path_prefix else ""

    # 构建不同客户端需要的接口
    api_base_url = f"{current_url}/{api_path_segment.rstrip('/')}" if api_path_segment else current_url
    api_base_v1 = f"{current_url}/{api_path_segment}v1"
    api_endpoint = f"{current_url}/{api_path_segment}v1/chat/completions"

    # 准备账户数据列表
    accounts_data = []
    for account_id, account_manager in multi_account_mgr.accounts.items():
        account_data = _get_account_status(account_manager)
        accounts_data.append(account_data)

    # 返回所有模板变量（纯数据）
    return {
        "request": request,
        "current_url": current_url,
        "has_api_key": bool(api_key),
        "error_count": error_count,
        "api_base_url": api_base_url,
        "api_base_v1": api_base_v1,
        "api_endpoint": api_endpoint,
        "accounts_data": accounts_data,
        "admin_path_segment": admin_path_segment,
        "api_path_segment": api_path_segment,
        "multi_account_mgr": multi_account_mgr,
        # 配置变量（用于 JavaScript）
        "main": {
            "PATH_PREFIX": path_prefix,
            "API_KEY": api_key,
            "BASE_URL": base_url,
            "PROXY": proxy,
            "LOGO_URL": logo_url,
            "CHAT_URL": chat_url,
            "MAX_NEW_SESSION_TRIES": max_new_session_tries,
            "MAX_REQUEST_RETRIES": max_request_retries,
            "MAX_ACCOUNT_SWITCH_TRIES": max_account_switch_tries,
            "ACCOUNT_FAILURE_THRESHOLD": account_failure_threshold,
            "RATE_LIMIT_COOLDOWN_SECONDS": rate_limit_cooldown_seconds,
            "SESSION_CACHE_TTL_SECONDS": session_cache_ttl_seconds,
        }
    }
