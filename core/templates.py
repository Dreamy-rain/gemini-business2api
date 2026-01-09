"""
模板生成模块
此模块包含 HTML 页面生成函数，用于管理界面和日志查看器

注意：
- 这些函数需要通过 import main 动态获取全局变量
- 避免在模块顶层导入 main，防止循环依赖
"""

from fastapi import Request, Header, HTTPException
from fastapi.responses import HTMLResponse


def generate_admin_html(request: Request, multi_account_mgr, show_hide_tip: bool = False) -> str:
    """生成管理页面HTML - 端点带Key参数完整版"""
    # 动态导入 main 模块的变量（避免循环依赖）
    import main

    # 获取当前页面的完整URL
    current_url = main.get_base_url(request)

    # 获取错误统计
    error_count = 0
    with main.log_lock:
        for log in main.log_buffer:
            if log.get("level") in ["ERROR", "CRITICAL"]:
                error_count += 1

    # --- 1. 构建提示信息 ---
    api_key_status = ""
    if main.API_KEY:
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
    # 生成正确的API端点URL和管理端点URL
    # admin_path_segment: 有PATH_PREFIX时为 secret123，无时为 admin
    # 管理端点示例：/{admin_path_segment}/accounts
    admin_path_segment = f"{main.PATH_PREFIX}" if main.PATH_PREFIX else "admin"
    api_path_segment = f"{main.PATH_PREFIX}/" if main.PATH_PREFIX else ""

    # 构建不同客户端需要的接口
    api_base_url = f"{current_url}/{api_path_segment.rstrip('/')}" if api_path_segment else current_url
    api_base_v1 = f"{current_url}/{api_path_segment}v1"
    api_endpoint = f"{current_url}/{api_path_segment}v1/chat/completions"
    api_key_display = main.API_KEY if main.API_KEY else '<span style="color: #ff9500;">未设置（公开访问）</span>'

    api_info_tip = f"""
    <div class="alert alert-primary">
        <div class="alert-icon">🔗</div>
        <div class="alert-content">
            <strong>API 接口信息</strong>
            <div style="margin-top: 10px;">
                <div style="margin-bottom: 12px;">
                    <div style="color: #86868b; font-size: 11px; margin-bottom: 4px;">基础端点（部分客户端）</div>
                    <code style="font-size: 11px; background: rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; display: inline-block; word-break: break-all;">{api_base_url}</code>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="color: #86868b; font-size: 11px; margin-bottom: 4px;">API Base（OpenAI SDK 等）</div>
                    <code style="font-size: 11px; background: rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; display: inline-block; word-break: break-all;">{api_base_v1}</code>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="color: #86868b; font-size: 11px; margin-bottom: 4px;">完整聊天接口（直接调用）</div>
                    <code style="font-size: 11px; background: rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; display: inline-block; word-break: break-all;">{api_endpoint}</code>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="color: #86868b; font-size: 11px; margin-bottom: 4px;">API 密钥</div>
                    <code style="font-size: 11px; background: rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; display: inline-block;">{api_key_display}</code>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="color: #86868b; font-size: 11px; margin-bottom: 6px;">支持的模型</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                        <span style="background: #f0f0f2; color: #1d1d1f; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;">gemini-auto</span>
                        <span style="background: #f0f0f2; color: #1d1d1f; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;">gemini-2.5-flash</span>
                        <span style="background: #f0f0f2; color: #1d1d1f; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;">gemini-2.5-pro</span>
                        <span style="background: #f0f0f2; color: #1d1d1f; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;">gemini-3-flash-preview</span>
                        <span style="background: #f0f0f2; color: #1d1d1f; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;">gemini-3-pro-preview</span>
                    </div>
                </div>
                <div style="background: rgba(0,0,0,0.03); padding: 10px; border-radius: 6px;">
                    <div style="font-size: 11px; color: #1d1d1f; margin-bottom: 4px; font-weight: 600;">📸 图片生成</div>
                    <div style="font-size: 11px; color: #86868b; line-height: 1.6;">
                        可在"系统设置"标签页自定义配置
                    </div>
                </div>
            </div>
        </div>
    </div>
    """

    # --- 2. 构建账户表格行 ---
    accounts_rows = ""
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()
        expire_status_text, _, expire_display = main.format_account_expiration(remaining_hours)

        # 检查账户是否过期或被手动禁用
        is_expired = config.is_expired()
        is_disabled = config.disabled

        # 使用AccountManager的方法获取冷却信息
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()

        # 确定账户状态和颜色
        if is_expired:
            status_text = "过期禁用"
            status_color = "#9e9e9e"
            dot_color = "#9e9e9e"
            row_opacity = "0.5"
            action_buttons = f'<button onclick="deleteAccount(\'{config.account_id}\')" class="btn-sm btn-delete" title="删除">删除</button>'
        elif is_disabled:
            status_text = "手动禁用"
            status_color = "#9e9e9e"
            dot_color = "#9e9e9e"
            row_opacity = "0.5"
            action_buttons = f'''
                <button onclick="enableAccount('{config.account_id}')" class="btn-sm btn-enable" title="启用">启用</button>
                <button onclick="deleteAccount('{config.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
            '''
        elif cooldown_seconds == -1:
            # 错误永久禁用
            status_text = cooldown_reason  # "错误禁用"
            status_color = "#f44336"
            dot_color = "#f44336"
            row_opacity = "0.5"
            action_buttons = f'''
                <button onclick="enableAccount('{config.account_id}')" class="btn-sm btn-enable" title="启用">启用</button>
                <button onclick="deleteAccount('{config.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
            '''
        elif cooldown_seconds > 0:
            # 429限流（冷却中）
            status_text = f"{cooldown_reason} ({cooldown_seconds}s)"
            status_color = "#ff9800"
            dot_color = "#ff9800"
            row_opacity = "1"
            action_buttons = f'''
                <button onclick="disableAccount('{config.account_id}')" class="btn-sm btn-disable" title="禁用">禁用</button>
                <button onclick="deleteAccount('{config.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
            '''
        else:
            # 正常状态
            is_avail = account_manager.is_available
            if is_avail:
                status_text = expire_status_text  # "正常", "即将过期", "紧急"
                if expire_status_text == "正常":
                    status_color = "#4caf50"
                    dot_color = "#34c759"
                elif expire_status_text == "即将过期":
                    status_color = "#ff9800"
                    dot_color = "#ff9800"
                else:  # 紧急
                    status_color = "#f44336"
                    dot_color = "#f44336"
            else:
                status_text = "不可用"
                status_color = "#f44336"
                dot_color = "#ff3b30"
            row_opacity = "1"
            action_buttons = f'''
                <button onclick="disableAccount('{config.account_id}')" class="btn-sm btn-disable" title="禁用">禁用</button>
                <button onclick="deleteAccount('{config.account_id}')" class="btn-sm btn-delete" title="删除">删除</button>
            '''

        # 构建表格行
        accounts_rows += f"""
            <tr style="opacity: {row_opacity};">
                <td data-label="账号ID">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="status-dot" style="background-color: {dot_color};"></span>
                        <span style="font-weight: 600;">{config.account_id}</span>
                    </div>
                </td>
                <td data-label="状态">
                    <span style="color: {status_color}; font-weight: 600; font-size: 12px;">{status_text}</span>
                </td>
                <td data-label="过期时间">
                    <span class="font-mono" style="font-size: 11px; color: #6b6b6b;">{config.expires_at or '未设置'}</span>
                </td>
                <td data-label="剩余时长">
                    <span style="color: {status_color}; font-weight: 500; font-size: 12px;">{expire_display}</span>
                </td>
                <td data-label="累计对话">
                    <span style="color: #2563eb; font-weight: 600;">{account_manager.conversation_count}</span>
                </td>
                <td data-label="操作">
                    <div style="display: flex; gap: 6px;">
                        {action_buttons}
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

    # --- 3. 构建 HTML ---
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>系统管理 - Gemini Business API</title>
        <style>
            :root {{
                --bg-body: #f5f5f7;
                --text-main: #1d1d1f;
                --text-sec: #86868b;
                --border: #d2d2d7;
                --border-light: #e5e5ea;
                --blue: #0071e3;
                --red: #ff3b30;
                --green: #34c759;
                --orange: #ff9500;
            }}

            * {{ margin: 0; padding: 0; box-sizing: border-box; }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
                background-color: var(--bg-body);
                color: var(--text-main);
                font-size: 13px;
                line-height: 1.5;
                -webkit-font-smoothing: antialiased;
                padding: 30px 20px;
                cursor: default;
            }}

            .container {{ max-width: 1100px; margin: 0 auto; }}

            /* Header */
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 24px;
                flex-wrap: wrap;
                gap: 16px;
            }}
            .header-info h1 {{
                font-size: 24px;
                font-weight: 600;
                letter-spacing: -0.5px;
                color: var(--text-main);
                margin-bottom: 4px;
            }}
            .header-info .subtitle {{ font-size: 14px; color: var(--text-sec); }}
            .header-actions {{ display: flex; gap: 10px; }}

            /* Buttons */
            .btn {{
                display: inline-flex;
                align-items: center;
                padding: 8px 16px;
                background: #ffffff;
                border: 1px solid var(--border-light);
                border-radius: 8px;
                color: var(--text-main);
                font-weight: 500;
                text-decoration: none;
                transition: all 0.2s;
                font-size: 13px;
                cursor: pointer;
                box-shadow: 0 1px 2px rgba(0,0,0,0.03);
            }}
            .btn:hover {{ background: #fafafa; border-color: var(--border); text-decoration: none; }}
            .btn-primary {{ background: var(--blue); color: white; border: none; }}
            .btn-primary:hover {{ background: #0077ed; border: none; text-decoration: none; }}

            /* Alerts */
            .alert {{
                padding: 12px 16px;
                border-radius: 10px;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                font-size: 13px;
                border: 1px solid transparent;
                margin-bottom: 12px;
            }}
            .alert-icon {{ font-size: 16px; margin-top: 1px; flex-shrink: 0; }}
            .alert-content {{ flex: 1; }}
            .alert-desc {{ color: inherit; opacity: 0.9; margin-top: 2px; font-size: 12px; }}
            .alert-link {{ color: inherit; text-decoration: underline; margin-left: 10px; font-weight: 600; cursor: pointer; }}
            .alert-info {{ background: #eef7fe; border-color: #dcebfb; color: #1c5b96; }}
            .alert-success {{ background: #eafbf0; border-color: #d3f3dd; color: #15682e; }}
            .alert-warning {{ background: #fff8e6; border-color: #fcebc2; color: #9c6e03; }}
            .alert-error {{ background: #ffebeb; border-color: #fddddd; color: #c41e1e; }}
            .alert-primary {{ background: #f9fafb; border-color: #e5e7eb; color: #374151; }}

            /* Sections & Grids */
            .section {{ margin-bottom: 30px; }}
            .section-title {{
                font-size: 15px;
                font-weight: 600;
                color: var(--text-main);
                margin-bottom: 12px;
                padding-left: 4px;
            }}
            .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; align-items: start; }}
            .grid-env {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
            .stack-col {{ display: flex; flex-direction: column; gap: 16px; }}

            /* Cards */
            .card {{
                background: #fafaf9;
                padding: 20px;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                transition: all 0.15s ease;
            }}
            .card:hover {{ border-color: #d4d4d4; box-shadow: 0 0 8px rgba(0,0,0,0.08); }}
            .card h3 {{
                font-size: 13px;
                font-weight: 600;
                color: var(--text-sec);
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid #f5f5f5;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}

            /* Account Table */
            .account-table {{
                width: 100%;
                border-collapse: collapse;
                background: #fff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                overflow: hidden;
            }}
            .account-table thead {{
                background: #fafaf9;
                border-bottom: 2px solid #e5e5e5;
            }}
            .account-table th {{
                padding: 12px 16px;
                text-align: left;
                font-size: 12px;
                font-weight: 600;
                color: #6b6b6b;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .account-table tbody tr {{
                border-bottom: 1px solid #f5f5f5;
                transition: background 0.15s ease;
            }}
            .account-table tbody tr:last-child {{
                border-bottom: none;
            }}
            .account-table tbody tr:hover {{
                background: #fafaf9;
            }}
            .account-table td {{
                padding: 14px 16px;
                font-size: 13px;
                color: var(--text-main);
                vertical-align: middle;
            }}
            .status-dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex-shrink: 0;
            }}

            /* Tabs Navigation */
            .tabs-nav {{
                display: flex;
                gap: 4px;
                border-bottom: 1px solid #e5e5e5;
                margin-bottom: 24px;
                padding: 0 4px;
            }}
            .tab-button {{
                padding: 12px 20px;
                background: none;
                border: none;
                font-size: 14px;
                font-weight: 500;
                color: #6b6b6b;
                cursor: pointer;
                transition: all 0.2s;
                border-bottom: 2px solid transparent;
                position: relative;
                top: 1px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
                line-height: 1.5;
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .tab-button:hover {{
                color: #1d1d1f;
                background: #f5f5f5;
            }}
            .tab-button.active {{
                color: #0071e3;
                border-bottom-color: #0071e3;
                font-weight: 600;
            }}
            .tab-content {{
                display: none;
            }}
            .tab-content.active {{
                display: block;
            }}

            /* Small Buttons for Table */
            .btn-sm {{
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s;
                border: 1px solid;
            }}
            .btn-delete {{
                background: #fff;
                color: #dc2626;
                border-color: #fecaca;
            }}
            .btn-delete:hover {{
                background: #dc2626;
                color: white;
                border-color: #dc2626;
            }}
            .btn-disable {{
                background: #fff;
                color: #f59e0b;
                border-color: #fed7aa;
            }}
            .btn-disable:hover {{
                background: #f59e0b;
                color: white;
                border-color: #f59e0b;
            }}
            .btn-enable {{
                background: #fff;
                color: #10b981;
                border-color: #a7f3d0;
            }}
            .btn-enable:hover {{
                background: #10b981;
                color: white;
                border-color: #10b981;
            }}

            /* Modal */
            .modal {{
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }}
            .modal.show {{ display: flex; }}
            .modal-content {{
                background: white;
                border-radius: 12px;
                width: 90%;
                max-width: 800px;
                max-height: 90vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            .modal-header {{
                padding: 20px 24px;
                border-bottom: 1px solid #e5e5e5;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .modal-title {{ font-size: 18px; font-weight: 600; color: #1a1a1a; }}
            .modal-close {{
                background: none;
                border: none;
                font-size: 24px;
                color: #6b6b6b;
                cursor: pointer;
                padding: 0;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 6px;
                transition: all 0.2s;
            }}
            .modal-close:hover {{ background: #f5f5f5; color: #1a1a1a; }}
            .modal-body {{
                padding: 24px;
                flex: 1;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }}
            .modal-footer {{
                padding: 16px 24px;
                border-top: 1px solid #e5e5e5;
                display: flex;
                justify-content: flex-end;
                gap: 12px;
            }}

            /* JSON Editor */
            .json-editor {{
                width: 100%;
                flex: 1;
                min-height: 300px;
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                font-size: 13px;
                padding: 16px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: #fafaf9;
                color: #1a1a1a;
                line-height: 1.6;
                letter-spacing: 0.3px;
                overflow-y: auto;
                resize: none;
                scrollbar-width: thin;
                scrollbar-color: rgba(0,0,0,0.15) transparent;
            }}
            .json-editor::-webkit-scrollbar {{
                width: 4px;
            }}
            .json-editor::-webkit-scrollbar-track {{
                background: transparent;
            }}
            .json-editor::-webkit-scrollbar-thumb {{
                background: rgba(0,0,0,0.15);
                border-radius: 2px;
            }}
            .json-editor::-webkit-scrollbar-thumb:hover {{
                background: rgba(0,0,0,0.3);
            }}
            .json-editor:focus {{
                outline: none;
                border-color: #0071e3;
                box-shadow: 0 0 0 3px rgba(0,113,227,0.1);
            }}
            .json-error {{
                color: #dc2626;
                font-size: 12px;
                margin-top: 8px;
                padding: 8px 12px;
                background: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 6px;
                display: none;
            }}
            .json-error.show {{ display: block; }}

            .btn-secondary {{
                background: #f5f5f5;
                color: #1a1a1a;
                border: 1px solid #e5e5e5;
            }}
            .btn-secondary:hover {{ background: #e5e5e5; }}

            .env-var {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 0;
                border-bottom: 1px solid #f5f5f5;
            }}
            .env-var:last-child {{ border-bottom: none; }}
            .env-name {{
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                font-size: 12px;
                color: var(--text-main);
                font-weight: 600;
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}
            .env-desc {{
                font-size: 11px;
                color: var(--text-sec);
                margin-top: 3px;
                line-height: 1.4;
            }}
            .env-value {{
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                font-size: 12px;
                color: var(--text-sec);
                text-align: right;
                max-width: 50%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}

            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; vertical-align: middle; margin-left: 6px; }}
            .badge-required {{ background: #ffebeb; color: #c62828; }}
            .badge-optional {{ background: #e8f5e9; color: #2e7d32; }}

            code {{
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                background: #f5f5f7;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 12px;
                color: var(--blue);
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}
            a {{ color: var(--blue); text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .font-mono {{
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}

            /* --- Service Info Styles --- */
            .model-grid {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
            .model-tag {{
                background: #f0f0f2;
                color: #1d1d1f;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 12px;
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                border: 1px solid transparent;
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}
            .model-tag.highlight {{ background: #eef7ff; color: #0071e3; border-color: #dcebfb; font-weight: 500; }}

            .info-box {{ background: #f9f9f9; border: 1px solid #e5e5ea; border-radius: 8px; padding: 14px; }}
            .info-box-title {{ font-weight: 600; font-size: 12px; color: #1d1d1f; margin-bottom: 6px; }}
            .info-box-text {{ font-size: 12px; color: #86868b; line-height: 1.5; }}

            /* Settings Form Styles */
            .setting-item {{
                margin-bottom: 14px;
            }}
            .setting-item label {{
                display: block;
                font-size: 12px;
                font-weight: 600;
                color: #1d1d1f;
                margin-bottom: 6px;
            }}
            .setting-item input[type="text"],
            .setting-item input[type="password"],
            .setting-item input[type="number"] {{
                width: 100%;
                padding: 8px 12px;
                border: 1px solid #d4d4d4;
                border-radius: 6px;
                font-size: 13px;
                color: #1d1d1f;
                background: #fff;
                transition: border-color 0.15s;
            }}
            .setting-item input:focus {{
                outline: none;
                border-color: #0071e3;
            }}
            .setting-item input::placeholder {{
                color: #c7c7cc;
            }}

            .ep-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
                background: #fff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                overflow: hidden;
            }}
            .ep-table tr {{ border-bottom: 1px solid #f5f5f5; }}
            .ep-table tr:last-child {{ border-bottom: none; }}
            .ep-table td {{ padding: 12px 16px; vertical-align: middle; }}

            .method {{
                display: inline-block;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                min-width: 48px;
                text-align: center;
                margin-right: 8px;
            }}
            .m-post {{ background: #eafbf0; color: #166534; border: 1px solid #dcfce7; }}
            .m-get {{ background: #eff6ff; color: #1e40af; border: 1px solid #dbeafe; }}
            .m-del {{ background: #fef2f2; color: #991b1b; border: 1px solid #fee2e2; }}

            .ep-path {{
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, "Courier New", monospace;
                color: #1d1d1f;
                margin-right: 8px;
                font-size: 12px;
                letter-spacing: 0.3px;
                line-height: 1.5;
            }}
            .ep-desc {{ color: #86868b; font-size: 12px; margin-left: auto; }}

            .current-url-row {{
                display: flex;
                align-items: center;
                padding: 10px 12px;
                background: #f2f7ff;
                border-radius: 8px;
                margin-bottom: 16px;
                border: 1px solid #e1effe;
            }}

            @media (max-width: 800px) {{
                .grid-3, .grid-env {{ grid-template-columns: 1fr; }}
                .header {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
                .header-actions {{ width: 100%; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
                .header-actions .btn {{ justify-content: center; text-align: center; }}
                .ep-table td {{ display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }}
                .ep-desc {{ margin-left: 0; }}

                /* Tabs Mobile */
                .tabs-nav {{
                    overflow-x: auto;
                    padding: 0;
                    gap: 0;
                    -webkit-overflow-scrolling: touch;
                }}
                .tab-button {{
                    flex: 1;
                    min-width: 100px;
                    padding: 10px 16px;
                    font-size: 13px;
                    justify-content: center;
                }}

                /* Account Table Mobile - Card Layout */
                .account-table {{
                    display: block;
                    border: none;
                }}
                .account-table thead {{
                    display: none;
                }}
                .account-table tbody {{
                    display: block;
                }}
                .account-table tr {{
                    display: block;
                    margin-bottom: 12px;
                    border: 1px solid #e5e5e5;
                    border-radius: 10px;
                    background: #fff;
                    padding: 12px;
                    position: relative;
                }}
                .account-table td {{
                    display: block;
                    padding: 0;
                    border: none;
                }}

                /* 账号ID - 卡片头部 */
                .account-table td:nth-child(1) {{
                    margin-bottom: 10px;
                    padding-bottom: 10px;
                    padding-right: 80px;
                    border-bottom: 1px solid #f5f5f5;
                }}
                .account-table td:nth-child(1) > div {{
                    width: 100%;
                }}
                .account-table td:nth-child(1) span:last-child {{
                    word-break: break-all;
                }}

                /* 状态 - 右上角显示 */
                .account-table td:nth-child(2) {{
                    position: absolute;
                    top: 12px;
                    right: 12px;
                    padding: 0;
                }}
                .account-table td:nth-child(2)::before {{
                    display: none;
                }}
                .account-table td:nth-child(2) > span {{
                    display: inline-block;
                    padding: 4px 10px;
                    border-radius: 6px;
                    font-size: 11px;
                    white-space: nowrap;
                    font-weight: 600;
                    background: rgba(255,255,255,0.95);
                    border: 1px solid currentColor;
                    opacity: 0.9;
                }}

                /* 信息行 - 紧凑布局 */
                .account-table td:nth-child(3),
                .account-table td:nth-child(4),
                .account-table td:nth-child(5) {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 6px 0;
                    font-size: 12px;
                }}
                .account-table td:nth-child(3)::before,
                .account-table td:nth-child(4)::before,
                .account-table td:nth-child(5)::before {{
                    content: attr(data-label);
                    font-weight: 600;
                    color: #86868b;
                    font-size: 11px;
                    margin-right: 8px;
                }}

                /* 操作按钮 - 底部 */
                .account-table td:nth-child(6) {{
                    margin-top: 10px;
                    padding-top: 10px;
                    border-top: 1px solid #f5f5f5;
                }}
                .account-table td:nth-child(6)::before {{
                    display: none;
                }}
                .account-table td:nth-child(6) > div {{
                    width: 100%;
                    justify-content: flex-end;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-info">
                    <h1>Gemini-Business2api</h1>
                    <div class="subtitle">多账户代理面板</div>
                </div>
                <div class="header-actions">
                    <a href="/public/uptime/html" class="btn" target="_blank">📊 状态监控</a>
                    <a href="/public/log/html" class="btn" target="_blank">📄 公开日志</a>
                    <a href="/{admin_path_segment}/log/html" class="btn" target="_blank">🔧 管理日志</a>
                    <button class="btn" onclick="document.getElementById('fileInput').click()">📥 批量上传</button>
                    <input type="file" id="fileInput" accept=".json" multiple style="display:none" onchange="handleFileUpload(event)">
                    <button class="btn" onclick="showEditConfig()" id="edit-btn">✏️ 编辑配置</button>
                </div>
            </div>

            <!-- Tabs Navigation -->
            <div class="tabs-nav">
                <button class="tab-button active" onclick="switchTab('accounts')">📋 账户管理</button>
                <button class="tab-button" onclick="switchTab('api')">📚 API文档</button>
                <button class="tab-button" onclick="switchTab('config')">⚙️ 系统配置</button>
                <button class="tab-button" onclick="switchTab('settings')">🔧 系统设置</button>
            </div>

            <!-- Tab 1: 账户管理 -->
            <div id="tab-accounts" class="tab-content active">
                {api_key_status}
                {error_alert}
                {api_info_tip}

                <div class="section">
                    <div class="section-title">账户状态 ({len(multi_account_mgr.accounts)} 个)</div>
                    <div style="color: #6b6b6b; font-size: 12px; margin-bottom: 12px; padding-left: 4px;">
                        默认过期时间12小时，注意北京时间 • 批量上传使用 <code style="font-size: 11px; background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 4px;">script/download-config.js</code> 油猴脚本
                    </div>
                    {accounts_html}
                </div>
            </div>

            <!-- Tab 2: API文档 -->
            <div id="tab-api" class="tab-content">
                <div class="section">
                    <div class="section-title">API 端点列表</div>

                    <div class="current-url-row">
                        <span style="font-size:12px; font-weight:600; color:#0071e3; margin-right:8px;">当前页面:</span>
                        <code style="background:none; padding:0; color:#1d1d1f;">{current_url}</code>
                    </div>

                    <table class="ep-table">
                        <tr>
                            <td width="70"><span class="method m-post">POST</span></td>
                            <td><span class="ep-path">/{api_path_segment}v1/chat/completions</span></td>
                            <td><span class="ep-desc">OpenAI 兼容对话接口</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{api_path_segment}v1/models</span></td>
                            <td><span class="ep-desc">获取模型列表</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{admin_path_segment}</span></td>
                            <td><span class="ep-desc">管理首页 (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{admin_path_segment}/health</span></td>
                            <td><span class="ep-desc">健康检查 (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{admin_path_segment}/accounts</span></td>
                            <td><span class="ep-desc">账户状态 JSON (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{admin_path_segment}/log</span></td>
                            <td><span class="ep-desc">获取日志 JSON (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/{admin_path_segment}/log/html</span></td>
                            <td><span class="ep-desc">日志查看器 HTML (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-del">DEL</span></td>
                            <td><span class="ep-path">/{admin_path_segment}/log?confirm=yes</span></td>
                            <td><span class="ep-desc">清空系统日志 (需登录)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/public/stats</span></td>
                            <td><span class="ep-desc">公开统计数据</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/public/log</span></td>
                            <td><span class="ep-desc">公开日志 (JSON, 脱敏)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/public/log/html</span></td>
                            <td><span class="ep-desc">公开日志查看器 (HTML)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/public/uptime</span></td>
                            <td><span class="ep-desc">实时状态监控 (JSON)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/public/uptime/html</span></td>
                            <td><span class="ep-desc">实时状态监控页面 (HTML)</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/docs</span></td>
                            <td><span class="ep-desc">Swagger API 文档</span></td>
                        </tr>
                        <tr>
                            <td><span class="method m-get">GET</span></td>
                            <td><span class="ep-path">/redoc</span></td>
                            <td><span class="ep-desc">ReDoc API 文档</span></td>
                        </tr>
                    </table>
                </div>
            </div>

            <!-- Tab 3: 系统配置 -->
            <div id="tab-config" class="tab-content">
                <div class="section">
                    <div class="section-title">当前配置状态</div>
                    <div class="grid-env">
                        <div class="stack-col">
                            <div class="card">
                                <h3>环境变量 <span class="badge badge-required">ENV</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">ADMIN_KEY</div><div class="env-desc">管理员密钥</div></div>
                                    <div class="env-value">已设置</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">PATH_PREFIX</div><div class="env-desc">API路径前缀</div></div>
                                    <div class="env-value">{main.PATH_PREFIX or '未设置'}</div>
                                </div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>基础配置 <span class="badge badge-optional">YAML</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">API_KEY</div><div class="env-desc">API访问密钥</div></div>
                                    <div class="env-value">{'已设置' if main.API_KEY else '未设置（公开访问）'}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">BASE_URL</div><div class="env-desc">服务器URL</div></div>
                                    <div class="env-value">{'已设置' if main.BASE_URL else '自动检测'}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">PROXY</div><div class="env-desc">代理地址</div></div>
                                    <div class="env-value">{'已设置' if main.PROXY else '未设置'}</div>
                                </div>
                            </div>
                        </div>
                    </div>

                        <div class="card">
                            <h3>重试策略 <span class="badge badge-optional">YAML</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">max_new_session_tries</div><div class="env-desc">新会话尝试数</div></div>
                                    <div class="env-value">{main.MAX_NEW_SESSION_TRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">max_request_retries</div><div class="env-desc">请求重试次数</div></div>
                                    <div class="env-value">{main.MAX_REQUEST_RETRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">max_account_switch_tries</div><div class="env-desc">账户切换次数</div></div>
                                    <div class="env-value">{main.MAX_ACCOUNT_SWITCH_TRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">account_failure_threshold</div><div class="env-desc">失败阈值</div></div>
                                    <div class="env-value">{main.ACCOUNT_FAILURE_THRESHOLD} 次</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">rate_limit_cooldown_seconds</div><div class="env-desc">429冷却时间</div></div>
                                    <div class="env-value">{main.RATE_LIMIT_COOLDOWN_SECONDS} 秒</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">session_cache_ttl_seconds</div><div class="env-desc">会话缓存时间</div></div>
                                    <div class="env-value">{main.SESSION_CACHE_TTL_SECONDS} 秒</div>
                                </div>
                            </div>
                        </div>

                    <div class="card">
                        <h3>公开展示 <span class="badge badge-optional">YAML</span></h3>
                        <div style="margin-top: 12px;">
                            <div class="env-var">
                                <div><div class="env-name">LOGO_URL</div><div class="env-desc">Logo图片</div></div>
                                <div class="env-value">{'已设置' if main.LOGO_URL else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">CHAT_URL</div><div class="env-desc">对话链接</div></div>
                                <div class="env-value">{'已设置' if main.CHAT_URL else '未设置'}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tab 4: 系统设置 -->
            <div id="tab-settings" class="tab-content">
                <div class="section">
                    <div class="section-title">系统设置</div>
                    <div style="color: #6b6b6b; font-size: 12px; margin-bottom: 16px; padding-left: 4px;">
                        ✅ 所有配置修改后<strong>立即生效</strong>，无需重启服务。配置保存在 <code>data/settings.yaml</code><br>
                        ⚠️ 页面显示需要重启服务后才会更新
                    </div>

                    <div class="grid-env">
                        <div class="stack-col">
                            <!-- 基础配置 -->
                            <div class="card">
                                <h3>基础配置</h3>
                                <div style="margin-top: 12px;">
                                    <div class="setting-item">
                                        <label>API 访问密钥</label>
                                        <input type="text" id="setting-api-key" placeholder="留空则公开访问" />
                                    </div>
                                    <div class="setting-item">
                                        <label>服务器 URL</label>
                                        <input type="text" id="setting-base-url" placeholder="留空则自动检测" />
                                    </div>
                                    <div class="setting-item">
                                        <label>代理地址</label>
                                        <input type="text" id="setting-proxy" placeholder="如 http://127.0.0.1:7890" />
                                    </div>
                                </div>
                            </div>

                            <!-- 图片生成配置 -->
                            <div class="card">
                                <h3>📸 图片生成配置</h3>
                                <div style="margin-top: 12px;">
                                    <div class="setting-item">
                                        <label style="display: flex; align-items: center; gap: 8px;">
                                            <input type="checkbox" id="setting-image-enabled" style="width: auto;" />
                                            启用图片生成
                                        </label>
                                    </div>
                                    <div class="setting-item">
                                        <label>支持的模型</label>
                                        <div id="setting-image-models" style="display: flex; flex-direction: column; gap: 6px; margin-top: 6px;">
                                            <label style="display: flex; align-items: center; gap: 6px; font-weight: normal; font-size: 12px;">
                                                <input type="checkbox" value="gemini-3-pro-preview" style="width: auto;" /> gemini-3-pro-preview
                                            </label>
                                            <label style="display: flex; align-items: center; gap: 6px; font-weight: normal; font-size: 12px;">
                                                <input type="checkbox" value="gemini-2.5-pro" style="width: auto;" /> gemini-2.5-pro
                                            </label>
                                            <label style="display: flex; align-items: center; gap: 6px; font-weight: normal; font-size: 12px;">
                                                <input type="checkbox" value="gemini-2.5-flash" style="width: auto;" /> gemini-2.5-flash
                                            </label>
                                            <label style="display: flex; align-items: center; gap: 6px; font-weight: normal; font-size: 12px;">
                                                <input type="checkbox" value="gemini-3-flash-preview" style="width: auto;" /> gemini-3-flash-preview
                                            </label>
                                            <label style="display: flex; align-items: center; gap: 6px; font-weight: normal; font-size: 12px;">
                                                <input type="checkbox" value="gemini-auto" style="width: auto;" /> gemini-auto
                                            </label>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="stack-col">
                            <!-- 重试策略配置 -->
                            <div class="card">
                                <h3>🔄 重试策略配置</h3>
                                <div style="margin-top: 12px;">
                                    <div class="setting-item">
                                        <label>新会话尝试账户数</label>
                                        <input type="number" id="setting-max-new-session" min="1" max="20" />
                                    </div>
                                    <div class="setting-item">
                                        <label>请求失败重试次数</label>
                                        <input type="number" id="setting-max-retries" min="1" max="10" />
                                    </div>
                                    <div class="setting-item">
                                        <label>账户切换尝试次数</label>
                                        <input type="number" id="setting-max-switch" min="1" max="20" />
                                    </div>
                                    <div class="setting-item">
                                        <label>账户失败阈值（次）</label>
                                        <input type="number" id="setting-failure-threshold" min="1" max="10" />
                                    </div>
                                    <div class="setting-item">
                                        <label>429 冷却时间（秒）</label>
                                        <input type="number" id="setting-cooldown" min="60" max="3600" />
                                    </div>
                                    <div class="setting-item">
                                        <label>会话缓存时间（秒）</label>
                                        <input type="number" id="setting-cache-ttl" min="300" max="86400" />
                                    </div>
                                </div>
                            </div>

                            <!-- 公开展示配置 -->
                            <div class="card">
                                <h3>🎨 公开展示配置</h3>
                                <div style="margin-top: 12px;">
                                    <div class="setting-item">
                                        <label>Logo URL</label>
                                        <input type="text" id="setting-logo-url" placeholder="留空则不显示" />
                                    </div>
                                    <div class="setting-item">
                                        <label>开始对话链接</label>
                                        <input type="text" id="setting-chat-url" placeholder="留空则不显示" />
                                    </div>
                                    <div class="setting-item">
                                        <label>Session 过期时间（小时）</label>
                                        <input type="number" id="setting-session-hours" min="1" max="168" />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div style="margin-top: 20px; display: flex; gap: 12px; justify-content: flex-end;">
                        <button class="btn btn-secondary" onclick="loadSettings()">重置</button>
                        <button class="btn btn-primary" onclick="saveSettings()">保存设置</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- JSON 编辑器模态框 -->
        <div id="jsonModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">编辑账户配置</div>
                    <button class="modal-close" onclick="closeModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <textarea id="jsonEditor" class="json-editor" placeholder="在此编辑 JSON 配置..."></textarea>
                    <div id="jsonError" class="json-error"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #6b6b6b;">
                        <strong>提示：</strong>编辑完成后点击"保存"按钮。JSON 格式错误时无法保存。<br>
                        配置立即生效。重启后将从环境变量重新加载，建议同步更新 ACCOUNTS_CONFIG。
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal()">取消</button>
                    <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
                </div>
            </div>
        </div>


        <script>
            let currentConfig = null;

            // 标签页切换函数
            function switchTab(tabName) {{
                // 隐藏所有标签页内容
                document.querySelectorAll('.tab-content').forEach(content => {{
                    content.classList.remove('active');
                }});
                // 移除所有标签按钮的active状态
                document.querySelectorAll('.tab-button').forEach(button => {{
                    button.classList.remove('active');
                }});

                // 显示选中的标签页
                document.getElementById('tab-' + tabName).classList.add('active');
                // 激活对应的按钮
                event.target.classList.add('active');
            }}

            // 统一的页面刷新函数（避免缓存）
            function refreshPage() {{
                window.location.reload();
            }}

            // 统一的错误处理函数
            async function handleApiResponse(response) {{
                if (!response.ok) {{
                    const errorText = await response.text();
                    let errorMsg;
                    try {{
                        const errorJson = JSON.parse(errorText);
                        errorMsg = errorJson.detail || errorJson.message || errorText;
                    }} catch {{
                        errorMsg = errorText;
                    }}
                    throw new Error(`HTTP ${{response.status}}: ${{errorMsg}}`);
                }}
                return await response.json();
            }}

            async function showEditConfig() {{
                const config = await fetch('/{admin_path_segment}/accounts-config').then(r => r.json());
                currentConfig = config.accounts;
                const json = JSON.stringify(config.accounts, null, 2);
                document.getElementById('jsonEditor').value = json;
                document.getElementById('jsonError').classList.remove('show');
                document.getElementById('jsonModal').classList.add('show');

                // 实时验证 JSON
                document.getElementById('jsonEditor').addEventListener('input', validateJSON);
            }}

            function validateJSON() {{
                const editor = document.getElementById('jsonEditor');
                const errorDiv = document.getElementById('jsonError');
                try {{
                    JSON.parse(editor.value);
                    errorDiv.classList.remove('show');
                    errorDiv.textContent = '';
                    return true;
                }} catch (e) {{
                    errorDiv.classList.add('show');
                    errorDiv.textContent = '❌ JSON 格式错误: ' + e.message;
                    return false;
                }}
            }}

            function closeModal() {{
                document.getElementById('jsonModal').classList.remove('show');
                document.getElementById('jsonEditor').removeEventListener('input', validateJSON);
            }}

            async function saveConfig() {{
                if (!validateJSON()) {{
                    alert('JSON 格式错误，请修正后再保存');
                    return;
                }}

                const newJson = document.getElementById('jsonEditor').value;
                const originalJson = JSON.stringify(currentConfig, null, 2);

                if (newJson === originalJson) {{
                    closeModal();
                    return;
                }}

                try {{
                    const data = JSON.parse(newJson);
                    const response = await fetch('/{admin_path_segment}/accounts-config', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(data)
                    }});

                    await handleApiResponse(response);
                    closeModal();
                    refreshPage();
                }} catch (error) {{
                    console.error('保存失败:', error);
                    alert('更新失败: ' + error.message);
                }}
            }}

            async function deleteAccount(accountId) {{
                if (!confirm(`确定删除账户 ${{accountId}}？`)) return;

                try {{
                    const response = await fetch('/{admin_path_segment}/accounts/' + accountId, {{
                        method: 'DELETE'
                    }});

                    await handleApiResponse(response);
                    refreshPage();
                }} catch (error) {{
                    console.error('删除失败:', error);
                    alert('删除失败: ' + error.message);
                }}
            }}

            async function disableAccount(accountId) {{
                try {{
                    const response = await fetch('/{admin_path_segment}/accounts/' + accountId + '/disable', {{
                        method: 'PUT'
                    }});

                    await handleApiResponse(response);
                    refreshPage();
                }} catch (error) {{
                    console.error('禁用失败:', error);
                    alert('禁用失败: ' + error.message);
                }}
            }}

            async function enableAccount(accountId) {{
                try {{
                    const response = await fetch('/{admin_path_segment}/accounts/' + accountId + '/enable', {{
                        method: 'PUT'
                    }});

                    await handleApiResponse(response);
                    refreshPage();
                }} catch (error) {{
                    console.error('启用失败:', error);
                    alert('启用失败: ' + error.message);
                }}
            }}

            // 批量上传相关函数
            async function handleFileUpload(event) {{
                const files = event.target.files;
                if (!files.length) return;

                let newAccounts = [];
                for (const file of files) {{
                    try {{
                        const text = await file.text();
                        const data = JSON.parse(text);
                        if (Array.isArray(data)) {{
                            newAccounts.push(...data);
                        }} else {{
                            newAccounts.push(data);
                        }}
                    }} catch (e) {{
                        alert(`文件 ${{file.name}} 解析失败: ${{e.message}}`);
                        event.target.value = '';
                        return;
                    }}
                }}

                if (!newAccounts.length) {{
                    alert('未找到有效账户数据');
                    event.target.value = '';
                    return;
                }}

                try {{
                    // 获取现有配置
                    const configResp = await fetch('/{admin_path_segment}/accounts-config');
                    const configData = await handleApiResponse(configResp);
                    const existing = configData.accounts || [];

                    // 构建ID到索引的映射
                    const idToIndex = new Map();
                    existing.forEach((acc, idx) => {{
                        if (acc.id) idToIndex.set(acc.id, idx);
                    }});

                    // 合并：相同ID覆盖，新ID追加
                    let added = 0;
                    let updated = 0;
                    for (const acc of newAccounts) {{
                        if (!acc.secure_c_ses || !acc.csesidx || !acc.config_id) continue;
                        const accId = acc.id || `account_${{existing.length + added + 1}}`;
                        acc.id = accId;

                        if (idToIndex.has(accId)) {{
                            // 覆盖已存在的账户
                            existing[idToIndex.get(accId)] = acc;
                            updated++;
                        }} else {{
                            // 追加新账户
                            existing.push(acc);
                            idToIndex.set(accId, existing.length - 1);
                            added++;
                        }}
                    }}

                    if (added === 0 && updated === 0) {{
                        alert('没有有效账户可导入');
                        event.target.value = '';
                        return;
                    }}

                    // 保存合并后的配置
                    const response = await fetch('/{admin_path_segment}/accounts-config', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(existing)
                    }});

                    await handleApiResponse(response);
                    event.target.value = '';
                    refreshPage();
                }} catch (error) {{
                    console.error('导入失败:', error);
                    alert('导入失败: ' + error.message);
                    event.target.value = '';
                }}
            }}

            // 点击模态框外部关闭
            document.getElementById('jsonModal').addEventListener('click', function(e) {{
                if (e.target === this) {{
                    closeModal();
                }}
            }});

            // ========== 系统设置相关函数 ==========
            async function loadSettings() {{
                try {{
                    const response = await fetch('/{admin_path_segment}/settings');
                    const settings = await handleApiResponse(response);

                    // 基础配置
                    document.getElementById('setting-api-key').value = settings.basic?.api_key || '';
                    document.getElementById('setting-base-url').value = settings.basic?.base_url || '';
                    document.getElementById('setting-proxy').value = settings.basic?.proxy || '';

                    // 图片生成配置
                    document.getElementById('setting-image-enabled').checked = settings.image_generation?.enabled ?? true;
                    const supportedModels = settings.image_generation?.supported_models || [];
                    document.querySelectorAll('#setting-image-models input[type="checkbox"]').forEach(cb => {{
                        cb.checked = supportedModels.includes(cb.value);
                    }});

                    // 重试策略配置
                    document.getElementById('setting-max-new-session').value = settings.retry?.max_new_session_tries || 5;
                    document.getElementById('setting-max-retries').value = settings.retry?.max_request_retries || 3;
                    document.getElementById('setting-max-switch').value = settings.retry?.max_account_switch_tries || 5;
                    document.getElementById('setting-failure-threshold').value = settings.retry?.account_failure_threshold || 3;
                    document.getElementById('setting-cooldown').value = settings.retry?.rate_limit_cooldown_seconds || 600;
                    document.getElementById('setting-cache-ttl').value = settings.retry?.session_cache_ttl_seconds || 3600;

                    // 公开展示配置
                    document.getElementById('setting-logo-url').value = settings.public_display?.logo_url || '';
                    document.getElementById('setting-chat-url').value = settings.public_display?.chat_url || '';
                    document.getElementById('setting-session-hours').value = settings.session?.expire_hours || 24;
                }} catch (error) {{
                    console.error('加载设置失败:', error);
                    alert('加载设置失败: ' + error.message);
                }}
            }}

            async function saveSettings() {{
                try {{
                    // 收集图片生成支持的模型
                    const supportedModels = [];
                    document.querySelectorAll('#setting-image-models input[type="checkbox"]:checked').forEach(cb => {{
                        supportedModels.push(cb.value);
                    }});

                    const settings = {{
                        basic: {{
                            api_key: document.getElementById('setting-api-key').value,
                            base_url: document.getElementById('setting-base-url').value,
                            proxy: document.getElementById('setting-proxy').value
                        }},
                        image_generation: {{
                            enabled: document.getElementById('setting-image-enabled').checked,
                            supported_models: supportedModels
                        }},
                        retry: {{
                            max_new_session_tries: parseInt(document.getElementById('setting-max-new-session').value) || 5,
                            max_request_retries: parseInt(document.getElementById('setting-max-retries').value) || 3,
                            max_account_switch_tries: parseInt(document.getElementById('setting-max-switch').value) || 5,
                            account_failure_threshold: parseInt(document.getElementById('setting-failure-threshold').value) || 3,
                            rate_limit_cooldown_seconds: parseInt(document.getElementById('setting-cooldown').value) || 600,
                            session_cache_ttl_seconds: parseInt(document.getElementById('setting-cache-ttl').value) || 3600
                        }},
                        public_display: {{
                            logo_url: document.getElementById('setting-logo-url').value,
                            chat_url: document.getElementById('setting-chat-url').value
                        }},
                        session: {{
                            expire_hours: parseInt(document.getElementById('setting-session-hours').value) || 24
                        }}
                    }};

                    const response = await fetch('/{admin_path_segment}/settings', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(settings)
                    }});

                    await handleApiResponse(response);

                    // 直接刷新页面，不显示弹窗
                    window.location.reload();
                }} catch (error) {{
                    console.error('保存设置失败:', error);
                    alert('保存设置失败: ' + error.message);
                }}
            }}

            // 页面加载时自动加载设置
            document.addEventListener('DOMContentLoaded', function() {{
                loadSettings();
            }});
        </script>
    </body>
    </html>
    """
    return html_content




async def get_public_logs_html():
    """公开的脱敏日志查看器"""
    # 动态导入 main 模块的变量（避免循环依赖）
    import main

    html_content = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>服务状态</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            html, body { height: 100%; overflow: hidden; }
            body {
                font-family: 'Consolas', 'Monaco', monospace;
                background: #fafaf9;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 15px;
            }
            .container {
                width: 100%;
                max-width: 1200px;
                height: calc(100vh - 30px);
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                flex-direction: column;
            }
            h1 {
                color: #1a1a1a;
                font-size: 22px;
                font-weight: 600;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
            }
            h1 img {
                width: 32px;
                height: 32px;
                border-radius: 8px;
            }
            .info-bar {
                background: #f9f9f9;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 12px;
            }
            .info-item {
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 13px;
                color: #6b6b6b;
            }
            .info-item strong { color: #1a1a1a; }
            .info-item a {
                color: #1a73e8;
                text-decoration: none;
                font-weight: 500;
            }
            .info-item a:hover { text-decoration: underline; }
            .stats {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-bottom: 16px;
            }
            .stat {
                background: #fafaf9;
                padding: 12px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                text-align: center;
                transition: all 0.15s ease;
            }
            .stat:hover { border-color: #d4d4d4; }
            .stat-label { color: #6b6b6b; font-size: 11px; margin-bottom: 4px; }
            .stat-value { color: #1a1a1a; font-size: 18px; font-weight: 600; }
            .log-container {
                flex: 1;
                background: #fafaf9;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px;
                overflow-y: auto;
                scrollbar-width: thin;
                scrollbar-color: rgba(0,0,0,0.15) transparent;
            }
            .log-container::-webkit-scrollbar { width: 4px; }
            .log-container::-webkit-scrollbar-track { background: transparent; }
            .log-container::-webkit-scrollbar-thumb {
                background: rgba(0,0,0,0.15);
                border-radius: 2px;
            }
            .log-container::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.3); }
            .log-group {
                margin-bottom: 8px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: white;
            }
            .log-group-header {
                padding: 10px 12px;
                background: #f9f9f9;
                border-radius: 8px 8px 0 0;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: background 0.15s ease;
            }
            .log-group-header:hover { background: #f0f0f0; }
            .log-group-content { padding: 8px; }
            .log-entry {
                padding: 8px 10px;
                margin-bottom: 4px;
                background: white;
                border: 1px solid #e5e5e5;
                border-radius: 6px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 13px;
                transition: all 0.15s ease;
            }
            .log-entry:hover { border-color: #d4d4d4; }
            .log-time { color: #6b6b6b; font-size: 12px; min-width: 140px; }
            .log-status {
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                min-width: 60px;
                text-align: center;
            }
            .status-success { background: #d1fae5; color: #065f46; }
            .status-error { background: #fee2e2; color: #991b1b; }
            .status-in_progress { background: #fef3c7; color: #92400e; }
            .status-timeout { background: #fef3c7; color: #92400e; }
            .log-info { flex: 1; color: #374151; }
            .toggle-icon {
                display: inline-block;
                transition: transform 0.2s ease;
            }
            .toggle-icon.collapsed { transform: rotate(-90deg); }
            .subtitle-public {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            @media (max-width: 768px) {
                body { padding: 0; }
                .container {
                    padding: 15px;
                    height: 100vh;
                    border-radius: 0;
                    max-width: 100%;
                }
                h1 { font-size: 18px; margin-bottom: 12px; }
                .subtitle-public {
                    flex-direction: column;
                    gap: 6px;
                }
                .subtitle-public span {
                    font-size: 11px;
                    line-height: 1.6;
                }
                .subtitle-public a {
                    font-size: 12px;
                    font-weight: 600;
                }
                .info-bar {
                    padding: 10px 12px;
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }
                .info-item { font-size: 12px; }
                .stats {
                    grid-template-columns: repeat(2, 1fr);
                    gap: 8px;
                    margin-bottom: 12px;
                }
                .stat { padding: 8px; }
                .stat-label { font-size: 10px; }
                .stat-value { font-size: 16px; }
                .log-container { padding: 8px; }
                .log-group { margin-bottom: 6px; }
                .log-group-header {
                    padding: 8px 10px;
                    font-size: 11px;
                    flex-wrap: wrap;
                }
                .log-group-header span { font-size: 10px !important; }
                .log-entry {
                    padding: 6px 8px;
                    font-size: 11px;
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 4px;
                }
                .log-time {
                    min-width: auto;
                    font-size: 10px;
                }
                .log-info {
                    font-size: 11px;
                    word-break: break-word;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                """ + (f'<img src="{main.LOGO_URL}" alt="Logo">' if main.LOGO_URL else '') + r"""
                Gemini服务状态
            </h1>
            <div style="text-align: center; color: #999; font-size: 12px; margin-bottom: 16px;" class="subtitle-public">
                <span>展示最近1000条对话日志 · 每5秒自动更新</span>
                """ + (f'<a href="{main.CHAT_URL}" target="_blank" style="color: #1a73e8; text-decoration: none;">开始对话</a>' if main.CHAT_URL else '<span style="color: #999;">开始对话</span>') + r"""
            </div>
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">总访问</div>
                    <div class="stat-value" id="stat-visitors">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">每分钟请求</div>
                    <div class="stat-value" id="stat-load">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">平均响应</div>
                    <div class="stat-value" id="stat-avg-time">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">成功率</div>
                    <div class="stat-value" id="stat-success-rate" style="color: #10b981;">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">对话次数</div>
                    <div class="stat-value" id="stat-total">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">成功</div>
                    <div class="stat-value" id="stat-success" style="color: #10b981;">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">失败</div>
                    <div class="stat-value" id="stat-error" style="color: #ef4444;">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">更新时间</div>
                    <div class="stat-value" id="stat-update-time" style="font-size: 14px; color: #6b6b6b;">--:--</div>
                </div>
            </div>
            <div class="log-container" id="log-container">
                <div style="text-align: center; color: #999; padding: 20px;">加载中...</div>
            </div>
        </div>
        <script>
            async function loadData() {
                try {
                    // 并行加载日志和统计数据
                    const [logsResponse, statsResponse] = await Promise.all([
                        fetch('/public/log?limit=1000'),
                        fetch('/public/stats')
                    ]);

                    const logsData = await logsResponse.json();
                    const statsData = await statsResponse.json();

                    displayLogs(logsData.logs);
                    updateStats(logsData.logs, statsData);
                } catch (error) {
                    document.getElementById('log-container').innerHTML = '<div style="text-align: center; color: #f44336; padding: 20px;">加载失败: ' + error.message + '</div>';
                }
            }

            function displayLogs(logs) {
                const container = document.getElementById('log-container');
                if (logs.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">暂无日志</div>';
                    return;
                }

                // 读取折叠状态
                const foldState = JSON.parse(localStorage.getItem('public-log-fold-state') || '{}');

                let html = '';
                logs.forEach(log => {
                    const reqId = log.request_id;

                    // 状态图标和颜色
                    let statusColor = '#ff9800';
                    let statusText = '进行中';

                    if (log.status === 'success') {
                        statusColor = '#4caf50';
                        statusText = '成功';
                    } else if (log.status === 'error') {
                        statusColor = '#f44336';
                        statusText = '失败';
                    } else if (log.status === 'timeout') {
                        statusColor = '#ffc107';
                        statusText = '超时';
                    }

                    // 检查折叠状态
                    const isCollapsed = foldState[reqId] === true;
                    const contentStyle = isCollapsed ? 'style="display: none;"' : '';
                    const iconClass = isCollapsed ? 'class="toggle-icon collapsed"' : 'class="toggle-icon"';

                    // 构建事件列表
                    let eventsHtml = '';
                    log.events.forEach(event => {
                        let eventClass = 'log-entry';
                        let eventLabel = '';

                        if (event.type === 'start') {
                            eventLabel = '<span style="color: #2563eb; font-weight: 600;">开始对话</span>';
                        } else if (event.type === 'select') {
                            eventLabel = '<span style="color: #8b5cf6; font-weight: 600;">选择</span>';
                        } else if (event.type === 'retry') {
                            eventLabel = '<span style="color: #f59e0b; font-weight: 600;">重试</span>';
                        } else if (event.type === 'switch') {
                            eventLabel = '<span style="color: #06b6d4; font-weight: 600;">切换</span>';
                        } else if (event.type === 'complete') {
                            if (event.status === 'success') {
                                eventLabel = '<span style="color: #10b981; font-weight: 600;">完成</span>';
                            } else if (event.status === 'error') {
                                eventLabel = '<span style="color: #ef4444; font-weight: 600;">失败</span>';
                            } else if (event.status === 'timeout') {
                                eventLabel = '<span style="color: #f59e0b; font-weight: 600;">超时</span>';
                            }
                        }

                        eventsHtml += `
                            <div class="${eventClass}">
                                <div class="log-time">${event.time}</div>
                                <div style="min-width: 60px;">${eventLabel}</div>
                                <div class="log-info">${event.content}</div>
                            </div>
                        `;
                    });

                    html += `
                        <div class="log-group" data-req-id="${reqId}">
                            <div class="log-group-header" onclick="toggleGroup('${reqId}')">
                                <span style="color: ${statusColor}; font-weight: 600; font-size: 11px;">⬤ ${statusText}</span>
                                <span style="color: #666; font-size: 11px; margin-left: 8px;">req_${reqId}</span>
                                <span style="color: #999; font-size: 11px; margin-left: 8px;">${log.events.length}条事件</span>
                                <span ${iconClass} style="margin-left: auto; color: #999;">▼</span>
                            </div>
                            <div class="log-group-content" ${contentStyle}>
                                ${eventsHtml}
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = html;
            }

            function updateStats(logs, statsData) {
                const total = logs.length;
                const successLogs = logs.filter(log => log.status === 'success');
                const success = successLogs.length;
                const error = logs.filter(log => log.status === 'error').length;

                // 计算平均响应时间
                let avgTime = '-';
                if (success > 0) {
                    let totalDuration = 0;
                    let count = 0;
                    successLogs.forEach(log => {
                        log.events.forEach(event => {
                            if (event.type === 'complete' && event.content.includes('耗时')) {
                                const match = event.content.match(/([\d.]+)s/);
                                if (match) {
                                    totalDuration += parseFloat(match[1]);
                                    count++;
                                }
                            }
                        });
                    });
                    if (count > 0) {
                        avgTime = (totalDuration / count).toFixed(1) + 's';
                    }
                }

                // 计算成功率
                const totalCompleted = success + error;
                const successRate = totalCompleted > 0 ? ((success / totalCompleted) * 100).toFixed(1) + '%' : '-';

                // 更新日志统计
                document.getElementById('stat-total').textContent = total;
                document.getElementById('stat-success').textContent = success;
                document.getElementById('stat-error').textContent = error;
                document.getElementById('stat-success-rate').textContent = successRate;
                document.getElementById('stat-avg-time').textContent = avgTime;

                // 更新全局统计
                document.getElementById('stat-visitors').textContent = statsData.total_visitors;

                // 更新负载状态（带颜色）
                const loadElement = document.getElementById('stat-load');
                loadElement.textContent = statsData.requests_per_minute;
                loadElement.style.color = statsData.load_color;

                // 更新时间
                document.getElementById('stat-update-time').textContent = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
            }

            function toggleGroup(reqId) {
                const group = document.querySelector(`.log-group[data-req-id="${reqId}"]`);
                const content = group.querySelector('.log-group-content');
                const icon = group.querySelector('.toggle-icon');

                const isCollapsed = content.style.display === 'none';
                if (isCollapsed) {
                    content.style.display = 'block';
                    icon.classList.remove('collapsed');
                } else {
                    content.style.display = 'none';
                    icon.classList.add('collapsed');
                }

                // 保存折叠状态
                const foldState = JSON.parse(localStorage.getItem('public-log-fold-state') || '{}');
                foldState[reqId] = !isCollapsed;
                localStorage.setItem('public-log-fold-state', JSON.stringify(foldState));
            }

            // 初始加载
            loadData();

            // 自动刷新（每5秒）
            setInterval(loadData, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


async def get_uptime_html():
    """Uptime 实时监控页面（类似 Uptime Kuma）"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gemini Status</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f7;
                color: #1d1d1f;
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 {
                font-size: 24px;
                font-weight: 600;
                margin-bottom: 8px;
                color: #1d1d1f;
            }
            .subtitle { color: #86868b; font-size: 14px; margin-bottom: 24px; }
            .update-time { color: #86868b; font-size: 12px; margin-bottom: 16px; }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 16px;
            }
            .card {
                background: #fff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                padding: 16px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            }
            .card:hover { border-color: #d4d4d4; }
            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
            }
            .service-name { font-weight: 600; font-size: 14px; color: #1d1d1f; }
            .status-badge {
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            }
            .status-up { background: #d1fae5; color: #065f46; }
            .status-down { background: #fee2e2; color: #991b1b; }
            .status-unknown { background: #f3f4f6; color: #6b7280; }
            .stats {
                display: flex;
                gap: 16px;
                margin-bottom: 12px;
                font-size: 12px;
                color: #86868b;
            }
            .stat-value { color: #1d1d1f; font-weight: 600; }
            .heartbeat-bar {
                display: flex;
                gap: 2px;
                height: 24px;
                align-items: flex-end;
            }
            .beat {
                flex: 1;
                min-width: 4px;
                max-width: 8px;
                border-radius: 2px;
                transition: all 0.2s;
                position: relative;
            }
            .beat:hover { opacity: 0.8; transform: scaleY(1.1); }
            .beat.up { background: #34c759; height: 100%; }
            .beat.down { background: #ff3b30; height: 100%; }
            .beat.empty { background: #e5e5ea; height: 40%; }
            .beat .tooltip {
                position: absolute;
                bottom: 100%;
                left: 50%;
                transform: translateX(-50%);
                background: #1d1d1f;
                color: #fff;
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 11px;
                white-space: nowrap;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.15s;
                margin-bottom: 6px;
                z-index: 100;
            }
            .beat .tooltip::after {
                content: '';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                border: 5px solid transparent;
                border-top-color: #1d1d1f;
            }
            .beat:hover .tooltip { opacity: 1; }
            @media (max-width: 768px) {
                .grid { grid-template-columns: 1fr; }
                .beat { min-width: 3px; max-width: 6px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Gemini Status</h1>
            <p class="subtitle">服务状态监控</p>
            <p class="update-time" id="update-time">更新中...</p>
            <div class="grid" id="services"></div>
        </div>
        <script>
            async function loadStatus() {
                try {
                    const res = await fetch('/public/uptime');
                    const data = await res.json();
                    renderServices(data);
                    document.getElementById('update-time').textContent = '更新于 ' + data.updated_at;
                } catch (e) {
                    document.getElementById('services').innerHTML = '<div class="card">加载失败</div>';
                }
            }

            function renderServices(data) {
                const container = document.getElementById('services');
                let html = '';
                for (const [id, svc] of Object.entries(data.services)) {
                    const statusClass = svc.status === 'up' ? 'status-up' : svc.status === 'down' ? 'status-down' : 'status-unknown';
                    const statusText = svc.status === 'up' ? '正常' : svc.status === 'down' ? '故障' : '未知';

                    // 生成心跳条
                    let beats = '';
                    const maxBeats = 60;
                    const heartbeats = svc.heartbeats || [];
                    for (let i = 0; i < maxBeats; i++) {
                        if (i < heartbeats.length) {
                            const beat = heartbeats[i];
                            const status = beat.success ? '成功' : '失败';
                            beats += `<div class="beat ${beat.success ? 'up' : 'down'}"><span class="tooltip">${beat.time} · ${status}</span></div>`;
                        } else {
                            beats += '<div class="beat empty"></div>';
                        }
                    }

                    html += `
                        <div class="card">
                            <div class="card-header">
                                <span class="service-name">${svc.name}</span>
                                <span class="status-badge ${statusClass}">${statusText}</span>
                            </div>
                            <div class="stats">
                                <span>可用率 <span class="stat-value">${svc.uptime}%</span></span>
                                <span>请求 <span class="stat-value">${svc.total}</span></span>
                                <span>成功 <span class="stat-value">${svc.success}</span></span>
                            </div>
                            <div class="heartbeat-bar">${beats}</div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            }

            loadStatus();
            setInterval(loadStatus, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


async def get_login_html(request: Request, error: str = None) -> HTMLResponse:
    """生成登录页面"""
    import main

    # 获取当前URL（用于表单提交）
    current_path = request.url.path

    # 错误提示
    error_html = ""
    if error:
        error_html = f"""
        <div class="error-box">
            ⚠️ {error}
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>登录</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #fafaf9;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}

            .container {{
                background: #fff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                width: 100%;
                max-width: 380px;
                padding: 40px 32px;
            }}

            .header {{
                text-align: center;
                margin-bottom: 32px;
            }}

            h1 {{
                font-size: 22px;
                font-weight: 600;
                color: #1d1d1f;
                margin-bottom: 6px;
            }}

            .subtitle {{
                font-size: 14px;
                color: #86868b;
            }}

            .error-box {{
                padding: 12px 14px;
                background: #fff5f5;
                border: 1px solid #fecaca;
                border-radius: 8px;
                color: #dc2626;
                font-size: 14px;
                margin-bottom: 20px;
            }}

            label {{
                display: block;
                font-size: 14px;
                font-weight: 500;
                color: #1d1d1f;
                margin-bottom: 8px;
            }}

            input[type="password"] {{
                width: 100%;
                padding: 12px 14px;
                border: 1px solid #d4d4d4;
                border-radius: 8px;
                font-size: 15px;
                color: #1d1d1f;
                background: #fff;
                transition: border-color 0.15s;
                outline: none;
                margin-bottom: 20px;
            }}

            input[type="password"]:focus {{
                border-color: #0071e3;
            }}

            input[type="password"]::placeholder {{
                color: #c7c7cc;
            }}

            button {{
                width: 100%;
                padding: 12px;
                background: #0071e3;
                color: #fff;
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 500;
                cursor: pointer;
                transition: background 0.15s;
            }}

            button:hover {{
                background: #0077ed;
            }}

            button:active {{
                background: #006dd1;
            }}

            .hint {{
                margin-top: 20px;
                padding: 12px;
                background: #f6f6f8;
                border-radius: 8px;
                font-size: 13px;
                color: #86868b;
                line-height: 1.5;
            }}

            .iframe-hint {{
                margin-top: 16px;
                padding: 12px 14px;
                background: #fff4e6;
                border: 1px solid #ffd666;
                border-radius: 8px;
                font-size: 13px;
                color: #d46b08;
                line-height: 1.5;
                display: none;
            }}

            .iframe-hint a {{
                color: #0071e3;
                text-decoration: none;
                font-weight: 600;
            }}

            .iframe-hint a:hover {{
                text-decoration: underline;
            }}

            @media (max-width: 480px) {{
                .container {{
                    padding: 32px 24px;
                }}
            }}
        </style>
        <script>
            // 检测是否在 iframe 内
            if (window.self !== window.top) {{
                document.addEventListener('DOMContentLoaded', function() {{
                    const hint = document.getElementById('iframe-hint');
                    if (hint) {{
                        hint.style.display = 'block';
                        // 获取当前完整 URL（去掉 iframe 参数）
                        const currentUrl = window.location.href.replace(/[?&]__theme=.*?(&|$)/, '');
                        const link = document.getElementById('direct-link');
                        if (link) {{
                            link.href = currentUrl;
                        }}
                    }}
                }});
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>管理员登录</h1>
                <p class="subtitle">Gemini Business API</p>
            </div>

            {error_html}

            <form method="POST" action="{current_path}">
                <label for="admin_key">密钥</label>
                <input
                    type="password"
                    id="admin_key"
                    name="admin_key"
                    placeholder="输入 ADMIN_KEY"
                    required
                    autofocus
                >
                <button type="submit">登录</button>
            </form>

            <div class="hint">
                会话保持 24 小时
            </div>

            <div id="iframe-hint" class="iframe-hint">
                ⚠️ HuggingFace 内部无法登录，<a id="direct-link" href="#" target="_blank">点我跳转</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


async def admin_logs_html_no_auth(request):
    """返回美化的 HTML 日志查看界面（无需认证）"""
    from fastapi.responses import HTMLResponse

    html_content = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>日志查看器</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: "Consolas", "Monaco", monospace;
                background: #fafaf9;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            h1 { color: #1a1a1a; font-size: 22px; margin-bottom: 20px; }
            .log-item { padding: 10px; border-bottom: 1px solid #e5e5e5; font-size: 12px; }
            .log-time { color: #6b6b6b; margin-right: 10px; }
            .log-level { padding: 2px 6px; border-radius: 4px; margin-right: 10px; }
            .log-level.INFO { background: #e3f2fd; color: #1976d2; }
            .log-level.WARNING { background: #fff3e0; color: #f57c00; }
            .log-level.ERROR { background: #ffebee; color: #c62828; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📋 系统日志</h1>
            <div id="logs">加载中...</div>
        </div>
        <script>
            async function loadLogs() {
                try {
                    const path = window.location.pathname.replace("/log/html", "/log");
                    const res = await fetch(path);
                    const data = await res.json();
                    let html = "";
                    for (const log of data.logs.reverse()) {
                        html += `<div class="log-item">
                            <span class="log-time">${log.time}</span>
                            <span class="log-level ${log.level}">${log.level}</span>
                            <span>${log.message}</span>
                        </div>`;
                    }
                    document.getElementById("logs").innerHTML = html || "暂无日志";
                } catch (e) {
                    document.getElementById("logs").innerHTML = "加载失败";
                }
            }
            loadLogs();
            setInterval(loadLogs, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

