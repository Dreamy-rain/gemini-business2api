"""
模板数据准备函数
用于为 Jinja2 模板准备数据
"""

from config import config_manager, config
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
    """提取账户状态判断逻辑（避免重复代码）"""
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
        action_buttons = f'<button onclick="deleteAccount(\'{config_obj.account_id}\')" class="btn-sm btn-delete" title="删除">删除</button>'
    elif is_disabled:
        status_text = "手动禁用"
        status_color = "#9e9e9e"
        dot_color = "#9e9e9e"
        row_opacity = "0.5"
        action_buttons = f'''
            <button onclick="enableAccount('{config_obj.account_id}')" class="btn-sm btn-enable" title="启用">启用</button>
            <button onclick="deleteAccount('{config_obj.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
        '''
    elif cooldown_seconds == -1:
        status_text = cooldown_reason
        status_color = "#f44336"
        dot_color = "#f44336"
        row_opacity = "0.5"
        action_buttons = f'''
            <button onclick="enableAccount('{config_obj.account_id}')" class="btn-sm btn-enable" title="启用">启用</button>
            <button onclick="deleteAccount('{config_obj.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
        '''
    elif cooldown_seconds > 0:
        status_text = f"{cooldown_reason} ({cooldown_seconds}s)"
        status_color = "#ff9800"
        dot_color = "#ff9800"
        row_opacity = "1"
        action_buttons = f'''
            <button onclick="disableAccount('{config_obj.account_id}')" class="btn-sm btn-disable" title="禁用">禁用</button>
            <button onclick="deleteAccount('{config_obj.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
        '''
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
        action_buttons = f'''
            <button onclick="disableAccount('{config_obj.account_id}')" class="btn-sm btn-disable" title="禁用">禁用</button>
            <button onclick="deleteAccount('{config_obj.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
        '''

    return {
        "status_text": status_text,
        "status_color": status_color,
        "dot_color": dot_color,
        "row_opacity": row_opacity,
        "action_buttons": action_buttons,
        "expire_display": expire_display,
        "config_obj": config_obj
    }


def prepare_admin_template_data(
    request, multi_account_mgr, log_buffer, log_lock,
    api_key, base_url, proxy, logo_url, chat_url, path_prefix,
    max_new_session_tries, max_request_retries, max_account_switch_tries,
    account_failure_threshold, rate_limit_cooldown_seconds, session_cache_ttl_seconds
) -> dict:
    """准备完整的管理页面模板数据（包含 HTML 片段）"""
    # 获取当前页面的完整URL
    current_url = get_base_url_from_request(request)

    # 获取错误统计
    error_count = 0
    with log_lock:
        for log in log_buffer:
            if log.get("level") in ["ERROR", "CRITICAL"]:
                error_count += 1

    # --- 1. 构建提示信息 ---
    api_key_status = ""
    if api_key:
        api_key_status = """
        <div class="alert alert-success">
            <div class="alert-icon">🔒</div>
            <div class="alert-content">
                <strong>API 安全模式已启用</strong>
                <div class="alert-desc">API 端点需要携带 Authorization 密钥才能访问。</div>
            </div>
        </div>
        """
    else:
        api_key_status = """
        <div class="alert alert-warning">
            <div class="alert-icon">⚠️</div>
            <div class="alert-content">
                <strong>API 密钥未设置</strong>
                <div class="alert-desc">API 端点当前允许公开访问。建议在 .env 文件中配置 <code>API_KEY</code> 环境变量以提升安全性。</div>
            </div>
        </div>
        """

    error_alert = ""
    if error_count > 0:
        error_alert = f"""
        <div class="alert alert-error">
            <div class="alert-icon">🚨</div>
            <div class="alert-content">
                <strong>检测到 {error_count} 条错误日志</strong>
                <a href="/public/log/html" class="alert-link">查看详情 &rarr;</a>
            </div>
        </div>
        """

    # API接口信息提示
    admin_path_segment = f"{path_prefix}" if path_prefix else "admin"
    api_path_segment = f"{path_prefix}/" if path_prefix else ""

    # 构建不同客户端需要的接口
    api_base_url = f"{current_url}/{api_path_segment.rstrip('/')}" if api_path_segment else current_url
    api_base_v1 = f"{current_url}/{api_path_segment}v1"
    api_endpoint = f"{current_url}/{api_path_segment}v1/chat/completions"

    # --- 2. 构建账户表格行 ---
    accounts_rows = ""
    for account_id, account_manager in multi_account_mgr.accounts.items():
        # 使用辅助函数获取账户状态
        status = _get_account_status(account_manager)
        config_obj = status["config_obj"]

        # 构建表格行
        accounts_rows += f"""
            <tr style="opacity: {status['row_opacity']};">
                <td data-label="账号ID">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="status-dot" style="background-color: {status['dot_color']};"></span>
                        <span style="font-weight: 600;">{config_obj.account_id}</span>
                    </div>
                </td>
                <td data-label="状态">
                    <span style="color: {status['status_color']}; font-weight: 600; font-size: 12px;">{status['status_text']}</span>
                </td>
                <td data-label="过期时间">
                    <span class="font-mono" style="font-size: 11px; color: #6b6b6b;">{config_obj.expires_at or '未设置'}</span>
                </td>
                <td data-label="剩余时长">
                    <span style="color: {status['status_color']}; font-weight: 500; font-size: 12px;">{status['expire_display']}</span>
                </td>
                <td data-label="累计对话">
                    <span style="color: #2563eb; font-weight: 600;">{account_manager.conversation_count}</span>
                </td>
                <td data-label="操作">
                    <div style="display: flex; gap: 6px;">
                        {status['action_buttons']}
                    </div>
                </td>
            </tr>
        """

    # 构建完整的账户表格HTML
    accounts_html = f"""
        <table class="account-table">
            <thead>
                <tr>
                    <th>账号ID</th>
                    <th>状态</th>
                    <th>过期时间</th>
                    <th>剩余时长</th>
                    <th>累计对话</th>
                    <th style="text-align: center;">操作</th>
                </tr>
            </thead>
            <tbody>
                {accounts_rows if accounts_rows else '<tr><td colspan="6" style="text-align: center; color: #6b6b6b; padding: 24px;">暂无账户</td></tr>'}
            </tbody>
        </table>
    """

    # 返回所有模板变量
    return {
        "request": request,
        "current_url": current_url,
        "api_key_status": api_key_status,
        "error_alert": error_alert,
        "api_base_url": api_base_url,
        "api_base_v1": api_base_v1,
        "api_endpoint": api_endpoint,
        "accounts_html": accounts_html,
        "admin_path_segment": admin_path_segment,
        "api_path_segment": api_path_segment,
        "multi_account_mgr": multi_account_mgr,  # 添加账户管理器
        # 添加配置变量（用于 JavaScript）
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
