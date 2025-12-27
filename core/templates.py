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
    hide_tip = ""
    if show_hide_tip:
        hide_tip = """
        <div class="alert alert-info">
            <div class="alert-icon">💡</div>
            <div class="alert-content">
                <strong>提示</strong>：此页面默认在首页显示。如需隐藏，请设置环境变量：<br>
                <code style="margin-top:4px; display:inline-block;">main.HIDE_HOME_PAGE=true</code>
            </div>
        </div>
        """

    api_key_status = ""
    if main.API_KEY:
        api_key_status = """
        <div class="alert alert-success">
            <div class="alert-icon">🔒</div>
            <div class="alert-content">
                <strong>安全模式已启用</strong>
                <div class="alert-desc">请求 Header 需携带 Authorization 密钥。</div>
            </div>
        </div>
        """
    else:
        api_key_status = """
        <div class="alert alert-warning">
            <div class="alert-icon">⚠️</div>
            <div class="alert-content">
                <strong>API Key 未设置</strong>
                <div class="alert-desc">API 当前允许公开访问，建议配置 main.API_KEY。</div>
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

    # --- 2. 构建账户卡片 ---
    accounts_html = ""
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()
        status_text, status_color, expire_display = main.format_account_expiration(remaining_hours)

        is_avail = account_manager.is_available
        dot_color = "#34c759" if is_avail else "#ff3b30"
        dot_title = "可用" if is_avail else "不可用"

        accounts_html += f"""
        <div class="card account-card">
            <div class="acc-header">
                <div class="acc-title">
                    <span class="status-dot" style="background-color: {dot_color};" title="{dot_title}"></span>
                    {config.account_id}
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="acc-status-text" style="color: {status_color}">{status_text}</span>
                    <button onclick="deleteAccount('{config.account_id}')" class="delete-btn" title="删除账户">删除</button>
                </div>
            </div>
            <div class="acc-body">
                <div class="acc-row">
                    <span>过期时间</span>
                    <span class="font-mono">{config.expires_at or '未设置'}</span>
                </div>
                <div class="acc-row">
                    <span>剩余时长</span>
                    <span style="color: {status_color}; font-weight: 600;">{expire_display}</span>
                </div>
            </div>
        </div>
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
            .account-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
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

            /* Account & Env Styles */
            .account-card .acc-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f5f5f5; }}
            .acc-title {{ font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }}
            .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
            .acc-status-text {{ font-size: 12px; font-weight: 500; }}
            .acc-row {{ display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; color: var(--text-sec); }}

            /* Delete Button */
            .delete-btn {{
                background: #fff;
                color: #dc2626;
                border: 1px solid #fecaca;
                padding: 4px 12px;
                border-radius: 6px;
                font-size: 11px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s;
            }}
            .delete-btn:hover {{
                background: #dc2626;
                color: white;
                border-color: #dc2626;
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
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace;
                font-size: 13px;
                padding: 16px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: #fafaf9;
                color: #1a1a1a;
                line-height: 1.6;
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

            .env-var {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }}
            .env-var:last-child {{ border-bottom: none; }}
            .env-name {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-main); font-weight: 600; }}
            .env-desc {{ font-size: 11px; color: var(--text-sec); margin-top: 2px; }}
            .env-value {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-sec); text-align: right; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; vertical-align: middle; margin-left: 6px; }}
            .badge-required {{ background: #ffebeb; color: #c62828; }}
            .badge-optional {{ background: #e8f5e9; color: #2e7d32; }}

            code {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; background: #f5f5f7; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--blue); }}
            a {{ color: var(--blue); text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .font-mono {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; }}

            /* --- Service Info Styles --- */
            .model-grid {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
            .model-tag {{
                background: #f0f0f2;
                color: #1d1d1f;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 12px;
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace;
                border: 1px solid transparent;
            }}
            .model-tag.highlight {{ background: #eef7ff; color: #0071e3; border-color: #dcebfb; font-weight: 500; }}

            .info-box {{ background: #f9f9f9; border: 1px solid #e5e5ea; border-radius: 8px; padding: 14px; }}
            .info-box-title {{ font-weight: 600; font-size: 12px; color: #1d1d1f; margin-bottom: 6px; }}
            .info-box-text {{ font-size: 12px; color: #86868b; line-height: 1.5; }}

            .ep-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            .ep-table tr {{ border-bottom: 1px solid #f5f5f5; }}
            .ep-table tr:last-child {{ border-bottom: none; }}
            .ep-table td {{ padding: 10px 0; vertical-align: middle; }}

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

            .ep-path {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; color: #1d1d1f; margin-right: 8px; font-size: 12px; }}
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
                .header-actions {{ width: 100%; justify-content: flex-start; }}
                .ep-table td {{ display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }}
                .ep-desc {{ margin-left: 0; }}
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
                    <a href="/public/log/html" class="btn" target="_blank">📄 公开日志</a>
                    <a href="/{main.PATH_PREFIX}/admin/log/html?key={main.ADMIN_KEY}" class="btn" target="_blank">🔧 管理日志</a>
                    <button class="btn" onclick="showEditConfig()" id="edit-btn">✏️ 编辑配置</button>
                </div>
            </div>

            {hide_tip}
            {api_key_status}
            {error_alert}

            <div class="section">
                <div class="section-title">账户状态 ({len(multi_account_mgr.accounts)} 个)</div>
                <div style="color: #6b6b6b; font-size: 12px; margin-bottom: 12px; padding-left: 4px;">过期时间为12小时，可以自行修改时间，脚本可能有误差。</div>
                <div class="account-grid">
                    {accounts_html if accounts_html else '<div class="card"><p style="color: #6b6b6b; font-size: 14px; text-align:center;">暂无账户</p></div>'}
                </div>
            </div>

            <div class="section">
                <div class="section-title">环境变量配置</div>
                <div class="grid-env">
                    <div class="stack-col">
                        <div class="card">
                            <h3>必需变量 <span class="badge badge-required">REQUIRED</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNTS_CONFIG</div><div class="env-desc">JSON格式账户列表</div></div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">PATH_PREFIX</div><div class="env-desc">API路径前缀</div></div>
                                    <div class="env-value">当前: {main.PATH_PREFIX}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ADMIN_KEY</div><div class="env-desc">管理员密钥</div></div>
                                    <div class="env-value">已设置</div>
                                </div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>重试配置 <span class="badge badge-optional">OPTIONAL</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">MAX_NEW_SESSION_TRIES</div><div class="env-desc">新会话尝试账户数</div></div>
                                    <div class="env-value">{main.MAX_NEW_SESSION_TRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">MAX_REQUEST_RETRIES</div><div class="env-desc">请求失败重试次数</div></div>
                                    <div class="env-value">{main.MAX_REQUEST_RETRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">MAX_ACCOUNT_SWITCH_TRIES</div><div class="env-desc">每次重试查找账户次数</div></div>
                                    <div class="env-value">{main.MAX_ACCOUNT_SWITCH_TRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNT_FAILURE_THRESHOLD</div><div class="env-desc">账户失败阈值</div></div>
                                    <div class="env-value">{main.ACCOUNT_FAILURE_THRESHOLD} 次</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNT_COOLDOWN_SECONDS</div><div class="env-desc">账户冷却时间</div></div>
                                    <div class="env-value">{main.ACCOUNT_COOLDOWN_SECONDS} 秒</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>可选变量 <span class="badge badge-optional">OPTIONAL</span></h3>
                        <div style="margin-top: 12px;">
                            <div class="env-var">
                                <div><div class="env-name">API_KEY</div><div class="env-desc">API访问密钥</div></div>
                                <div class="env-value">{'已设置' if main.API_KEY else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">BASE_URL</div><div class="env-desc">图片URL生成（推荐设置）</div></div>
                                <div class="env-value">{'已设置' if main.BASE_URL else '未设置（自动检测）'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">PROXY</div><div class="env-desc">代理地址</div></div>
                                <div class="env-value">{'已设置' if main.PROXY else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">SESSION_CACHE_TTL_SECONDS</div><div class="env-desc">会话缓存过期时间</div></div>
                                <div class="env-value">{main.SESSION_CACHE_TTL_SECONDS} 秒</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">LOGO_URL</div><div class="env-desc">Logo URL（公开，为空则不显示）</div></div>
                                <div class="env-value">{'已设置' if main.LOGO_URL else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">CHAT_URL</div><div class="env-desc">开始对话链接（公开，为空则不显示）</div></div>
                                <div class="env-value">{'已设置' if main.CHAT_URL else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">MODEL_NAME</div><div class="env-desc">模型名称（公开）</div></div>
                                <div class="env-value">{main.MODEL_NAME}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">HIDE_HOME_PAGE</div><div class="env-desc">隐藏首页管理面板</div></div>
                                <div class="env-value">{'已隐藏' if main.HIDE_HOME_PAGE else '未隐藏'}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="section">
                <div class="section-title">服务信息</div>
                <div class="grid-3">
                    <div class="card">
                        <h3>支持的模型</h3>
                        <div class="model-grid">
                            <span class="model-tag">gemini-auto</span>
                            <span class="model-tag">gemini-2.5-flash</span>
                            <span class="model-tag">gemini-2.5-pro</span>
                            <span class="model-tag">gemini-3-flash-preview</span>
                            <span class="model-tag highlight">gemini-3-pro-preview</span>
                        </div>

                        <div class="info-box">
                            <div class="info-box-title">📸 图片生成说明</div>
                            <div class="info-box-text">
                                仅 <code style="background:none;padding:0;color:#0071e3;">gemini-3-pro-preview</code> 支持绘图。<br>
                                路径: <code>{main.IMAGE_DIR}</code><br>
                                类型: {'<span style="color: #34c759; font-weight: 600;">持久化（重启保留）</span>' if main.IMAGE_DIR == '/data/images' else '<span style="color: #ff3b30; font-weight: 600;">临时（重启丢失）</span>'}
                            </div>
                        </div>
                    </div>

                    <div class="card" style="grid-column: span 2;">
                        <h3>API 端点</h3>

                        <div class="current-url-row">
                            <span style="font-size:12px; font-weight:600; color:#0071e3; margin-right:8px;">当前页面:</span>
                            <code style="background:none; padding:0; color:#1d1d1f;">{current_url}</code>
                        </div>

                        <table class="ep-table">
                            <tr>
                                <td width="70"><span class="method m-post">POST</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/v1/chat/completions</span></td>
                                <td><span class="ep-desc">OpenAI 兼容对话接口</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/v1/models</span></td>
                                <td><span class="ep-desc">获取模型列表</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin</span></td>
                                <td><span class="ep-desc">管理首页</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin/health?key={{main.ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">健康检查 (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin/accounts?key={{main.ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">账户状态 JSON (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin/log?key={{main.ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">获取日志 JSON (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin/log/html?key={{main.ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">日志查看器 HTML (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-del">DEL</span></td>
                                <td><span class="ep-path">/{main.PATH_PREFIX}/admin/log?confirm=yes&key={{main.ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">清空系统日志 (需 Key)</span></td>
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
                        <strong>提示：</strong>编辑完成后点击"保存"按钮。JSON 格式错误时无法保存。
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

            // 统一的页面刷新函数（避免缓存）
            function refreshPage() {{
                window.location.href = window.location.pathname + '?t=' + Date.now();
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
                const config = await fetch('/{main.PATH_PREFIX}/admin/accounts-config?key={main.ADMIN_KEY}').then(r => r.json());
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
                    const response = await fetch('/{main.PATH_PREFIX}/admin/accounts-config?key={main.ADMIN_KEY}', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(data)
                    }});

                    const result = await handleApiResponse(response);
                    alert(`配置已更新！\\n当前账户数: ${{result.account_count}}`);
                    closeModal();
                    setTimeout(refreshPage, 1000);
                }} catch (error) {{
                    console.error('保存失败:', error);
                    alert('更新失败: ' + error.message);
                }}
            }}

            async function deleteAccount(accountId) {{
                if (!confirm(`确定删除账户 ${{accountId}}？`)) return;

                try {{
                    const response = await fetch('/{main.PATH_PREFIX}/admin/accounts/' + accountId + '?key={main.ADMIN_KEY}', {{
                        method: 'DELETE'
                    }});

                    const result = await handleApiResponse(response);
                    alert(`账户已删除！\\n剩余账户数: ${{result.account_count}}`);
                    refreshPage();
                }} catch (error) {{
                    console.error('删除失败:', error);
                    alert('删除失败: ' + error.message);
                }}
            }}

            // 点击模态框外部关闭
            document.getElementById('jsonModal').addEventListener('click', function(e) {{
                if (e.target === this) {{
                    closeModal();
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content


async def admin_logs_html(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """返回美化的 HTML 日志查看界面"""
    # 动态导入 main 模块的变量（避免循环依赖）
    import main

    # 验证路径前缀
    if path_prefix != main.PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != main.ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    html_content = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>日志查看器</title>
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
                max-width: 1400px;
                height: calc(100vh - 30px);
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                flex-direction: column;
            }
            h1 { color: #1a1a1a; font-size: 22px; font-weight: 600; margin-bottom: 20px; text-align: center; }
            .stats {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
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
            .controls {
                display: flex;
                gap: 8px;
                margin-bottom: 16px;
                flex-wrap: wrap;
            }
            .controls input, .controls select, .controls button {
                padding: 6px 10px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                font-size: 13px;
            }
            .controls select {
                appearance: none;
                -webkit-appearance: none;
                -moz-appearance: none;
                background-image: url("data:image/svg+xml,%3Csvg width='12' height='12' viewBox='0 0 12 12' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%236b6b6b' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
                background-repeat: no-repeat;
                background-position: right 12px center;
                padding-right: 32px;
            }
            .controls input[type="text"] { flex: 1; min-width: 150px; }
            .controls button {
                background: #1a73e8;
                color: white;
                border: none;
                cursor: pointer;
                font-weight: 500;
                transition: background 0.15s ease;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .controls button:hover { background: #1557b0; }
            .controls button.danger { background: #dc2626; }
            .controls button.danger:hover { background: #b91c1c; }
            .controls button svg { flex-shrink: 0; }
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
            /* Webkit 滚动条样式 - 更窄且不占位 */
            .log-container::-webkit-scrollbar {
                width: 4px;
            }
            .log-container::-webkit-scrollbar-track {
                background: transparent;
            }
            .log-container::-webkit-scrollbar-thumb {
                background: rgba(0,0,0,0.15);
                border-radius: 2px;
            }
            .log-container::-webkit-scrollbar-thumb:hover {
                background: rgba(0,0,0,0.3);
            }
            .log-entry {
                padding: 8px 10px;
                margin-bottom: 4px;
                background: white;
                border-radius: 6px;
                border: 1px solid #e5e5e5;
                font-size: 12px;
                color: #1a1a1a;
                display: flex;
                align-items: center;
                gap: 8px;
                word-break: break-word;
            }
            .log-entry > div:first-child {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .log-message {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .log-entry:hover { border-color: #d4d4d4; }
            .log-time { color: #6b6b6b; }
            .log-level {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: 600;
            }
            .log-level::before {
                content: '';
                width: 6px;
                height: 6px;
                border-radius: 50%;
            }
            .log-level.INFO { background: #e3f2fd; color: #1976d2; }
            .log-level.INFO::before { background: #1976d2; }
            .log-level.WARNING { background: #fff3e0; color: #f57c00; }
            .log-level.WARNING::before { background: #f57c00; }
            .log-level.ERROR { background: #ffebee; color: #d32f2f; }
            .log-level.ERROR::before { background: #d32f2f; }
            .log-level.DEBUG { background: #f3e5f5; color: #7b1fa2; }
            .log-level.DEBUG::before { background: #7b1fa2; }
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
            .log-group-header:hover {
                background: #f0f0f0;
            }
            .log-group-content {
                padding: 8px;
            }
            .log-group .log-entry {
                margin-bottom: 4px;
            }
            .log-group .log-entry:last-child {
                margin-bottom: 0;
            }
            .toggle-icon {
                display: inline-block;
                transition: transform 0.2s ease;
            }
            .toggle-icon.collapsed {
                transform: rotate(-90deg);
            }
            @media (max-width: 768px) {
                body { padding: 0; }
                .container { padding: 15px; height: 100vh; border-radius: 0; max-width: 100%; }
                h1 { font-size: 18px; margin-bottom: 12px; }
                .stats { grid-template-columns: repeat(3, 1fr); gap: 8px; }
                .stat { padding: 8px; }
                .controls { gap: 6px; }
                .controls input, .controls select { min-height: 38px; }
                .controls select { flex: 0 0 auto; }
                .controls input[type="text"] { flex: 1 1 auto; min-width: 80px; }
                .controls input[type="number"] { flex: 0 0 60px; }
                .controls button { padding: 10px 8px; font-size: 12px; flex: 1 1 22%; justify-content: center; min-height: 38px; }
                .log-entry {
                    font-size: 12px;
                    padding: 10px;
                    gap: 8px;
                    flex-direction: column;
                    align-items: flex-start;
                }
                .log-entry > div:first-child {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    width: 100%;
                    flex-wrap: wrap;
                }
                .log-time { font-size: 11px; color: #9e9e9e; }
                .log-level { font-size: 10px; }
                .log-message {
                    width: 100%;
                    white-space: normal;
                    word-break: break-word;
                    line-height: 1.5;
                    margin-top: 4px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Gemini API 日志查看器</h1>
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">总数</div>
                    <div class="stat-value" id="total-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">对话</div>
                    <div class="stat-value" id="chat-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">INFO</div>
                    <div class="stat-value" id="info-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">WARNING</div>
                    <div class="stat-value" id="warning-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">ERROR</div>
                    <div class="stat-value" id="error-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">更新</div>
                    <div class="stat-value" id="last-update" style="font-size: 11px;">-</div>
                </div>
            </div>
            <div class="controls">
                <select id="level-filter">
                    <option value="">全部</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                </select>
                <input type="text" id="search-input" placeholder="搜索...">
                <input type="number" id="limit-input" value="1500" min="10" max="3000" step="100" style="width: 80px;">
                <button onclick="loadLogs()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                    查询
                </button>
                <button onclick="exportJSON()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    导出
                </button>
                <button id="auto-refresh-btn" onclick="toggleAutoRefresh()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    自动刷新
                </button>
                <button onclick="clearAllLogs()" class="danger">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                    清空
                </button>
            </div>
            <div class="log-container" id="log-container">
                <div style="color: #6b6b6b;">正在加载...</div>
            </div>
        </div>
        <script>
            let autoRefreshTimer = null;
            async function loadLogs() {
                const level = document.getElementById('level-filter').value;
                const search = document.getElementById('search-input').value;
                const limit = document.getElementById('limit-input').value;
                // 从当前 URL 获取 key 参数
                const urlParams = new URLSearchParams(window.location.search);
                const key = urlParams.get('key');
                // 构建 API URL（使用当前路径的前缀）
                const pathPrefix = window.location.pathname.split('/')[1];
                let url = `/${pathPrefix}/admin/log?limit=${limit}`;
                if (key) url += `&key=${key}`;
                if (level) url += `&level=${level}`;
                if (search) url += `&search=${encodeURIComponent(search)}`;
                try {
                    const response = await fetch(url);
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    const data = await response.json();
                    if (data && data.logs) {
                        displayLogs(data.logs);
                        updateStats(data.stats);
                        document.getElementById('last-update').textContent = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                    } else {
                        throw new Error('Invalid data format');
                    }
                } catch (error) {
                    document.getElementById('log-container').innerHTML = '<div class="log-entry ERROR">加载失败: ' + error.message + '</div>';
                }
            }
            function updateStats(stats) {
                document.getElementById('total-count').textContent = stats.memory.total;
                document.getElementById('info-count').textContent = stats.memory.by_level.INFO || 0;
                document.getElementById('warning-count').textContent = stats.memory.by_level.WARNING || 0;
                const errorCount = document.getElementById('error-count');
                errorCount.textContent = stats.memory.by_level.ERROR || 0;
                if (stats.errors && stats.errors.count > 0) errorCount.style.color = '#dc2626';
                document.getElementById('chat-count').textContent = stats.chat_count || 0;
            }
            // 分类颜色配置（提取到外部避免重复定义）
            const CATEGORY_COLORS = {
                'SYSTEM': '#9e9e9e',
                'CONFIG': '#607d8b',
                'LOG': '#9e9e9e',
                'AUTH': '#4caf50',
                'SESSION': '#00bcd4',
                'FILE': '#ff9800',
                'CHAT': '#2196f3',
                'API': '#8bc34a',
                'CACHE': '#9c27b0',
                'ACCOUNT': '#f44336',
                'MULTI': '#673ab7'
            };

            // 账户颜色配置（提取到外部避免重复定义）
            const ACCOUNT_COLORS = {
                'account_1': '#9c27b0',
                'account_2': '#e91e63',
                'account_3': '#00bcd4',
                'account_4': '#4caf50',
                'account_5': '#ff9800'
            };

            function getCategoryColor(category) {
                return CATEGORY_COLORS[category] || '#757575';
            }

            function getAccountColor(accountId) {
                return ACCOUNT_COLORS[accountId] || '#757575';
            }

            function displayLogs(logs) {
                const container = document.getElementById('log-container');
                if (logs.length === 0) {
                    container.innerHTML = '<div class="log-entry">暂无日志</div>';
                    return;
                }

                // 按请求ID分组
                const groups = {};
                const ungrouped = [];

                logs.forEach(log => {
                    const msg = escapeHtml(log.message);
                    const reqMatch = msg.match(/\[req_([a-z0-9]+)\]/);

                    if (reqMatch) {
                        const reqId = reqMatch[1];
                        if (!groups[reqId]) {
                            groups[reqId] = [];
                        }
                        groups[reqId].push(log);
                    } else {
                        ungrouped.push(log);
                    }
                });

                // 渲染分组
                let html = '';

                // 先渲染未分组的日志
                ungrouped.forEach(log => {
                    html += renderLogEntry(log);
                });

                // 读取折叠状态
                const foldState = JSON.parse(localStorage.getItem('log-fold-state') || '{}');

                // 按请求ID分组渲染（最新的组在下面）
                Object.keys(groups).forEach(reqId => {
                    const groupLogs = groups[reqId];
                    const firstLog = groupLogs[0];
                    const lastLog = groupLogs[groupLogs.length - 1];

                    // 判断状态
                    let status = 'in_progress';
                    let statusColor = '#ff9800';
                    let statusText = '进行中';

                    if (lastLog.message.includes('响应完成') || lastLog.message.includes('非流式响应完成')) {
                        status = 'success';
                        statusColor = '#4caf50';
                        statusText = '成功';
                    } else if (lastLog.level === 'ERROR' || lastLog.message.includes('失败')) {
                        status = 'error';
                        statusColor = '#f44336';
                        statusText = '失败';
                    } else {
                        // 检查超时（最后日志超过 5 分钟）
                        const lastLogTime = new Date(lastLog.time);
                        const now = new Date();
                        const diffMinutes = (now - lastLogTime) / 1000 / 60;
                        if (diffMinutes > 5) {
                            status = 'timeout';
                            statusColor = '#ffc107';
                            statusText = '超时';
                        }
                    }

                    // 提取账户ID和模型
                    const accountMatch = firstLog.message.match(/\[account_(\d+)\]/);
                    const modelMatch = firstLog.message.match(/收到请求: ([^ ]+)/);
                    const accountId = accountMatch ? `account_${accountMatch[1]}` : '';
                    const model = modelMatch ? modelMatch[1] : '';

                    // 检查折叠状态
                    const isCollapsed = foldState[reqId] === true;
                    const contentStyle = isCollapsed ? 'style="display: none;"' : '';
                    const iconClass = isCollapsed ? 'class="toggle-icon collapsed"' : 'class="toggle-icon"';

                    html += `
                        <div class="log-group" data-req-id="${reqId}">
                            <div class="log-group-header" onclick="toggleGroup('${reqId}')">
                                <span style="color: ${statusColor}; font-weight: 600; font-size: 11px;">⬤ ${statusText}</span>
                                <span style="color: #666; font-size: 11px; margin-left: 8px;">req_${reqId}</span>
                                ${accountId ? `<span style="color: ${getAccountColor(accountId)}; font-size: 11px; margin-left: 8px;">${accountId}</span>` : ''}
                                ${model ? `<span style="color: #999; font-size: 11px; margin-left: 8px;">${model}</span>` : ''}
                                <span style="color: #999; font-size: 11px; margin-left: 8px;">${groupLogs.length}条日志</span>
                                <span ${iconClass} style="margin-left: auto; color: #999;">▼</span>
                            </div>
                            <div class="log-group-content" ${contentStyle}>
                                ${groupLogs.map(log => renderLogEntry(log)).join('')}
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = html;

                // 自动滚动到底部，显示最新日志
                container.scrollTop = container.scrollHeight;
            }

            function renderLogEntry(log) {
                const msg = escapeHtml(log.message);
                let displayMsg = msg;
                let categoryTags = [];
                let accountId = null;

                // 解析所有标签：[CATEGORY1] [CATEGORY2] [account_X] [req_X] message
                let remainingMsg = msg;
                const tagRegex = /^\[([A-Z_a-z0-9]+)\]/;

                while (true) {
                    const match = remainingMsg.match(tagRegex);
                    if (!match) break;

                    const tag = match[1];
                    remainingMsg = remainingMsg.substring(match[0].length).trim();

                    // 跳过req_标签（已在组头部显示）
                    if (tag.startsWith('req_')) {
                        continue;
                    }
                    // 判断是否为账户ID
                    else if (tag.startsWith('account_')) {
                        accountId = tag;
                    } else {
                        // 普通分类标签
                        categoryTags.push(tag);
                    }
                }

                displayMsg = remainingMsg;

                // 生成分类标签HTML
                const categoryTagsHtml = categoryTags.map(cat =>
                    `<span class="log-category" style="background: ${getCategoryColor(cat)}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-left: 2px;">${cat}</span>`
                ).join('');

                // 生成账户标签HTML
                const accountTagHtml = accountId
                    ? `<span style="color: ${getAccountColor(accountId)}; font-size: 11px; font-weight: 600; margin-left: 2px;">${accountId}</span>`
                    : '';

                return `
                    <div class="log-entry ${log.level}">
                        <div>
                            <span class="log-time">${log.time}</span>
                            <span class="log-level ${log.level}">${log.level}</span>
                            ${categoryTagsHtml}
                            ${accountTagHtml}
                        </div>
                        <div class="log-message">${displayMsg}</div>
                    </div>
                `;
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

                // 保存折叠状态到 localStorage
                const foldState = JSON.parse(localStorage.getItem('log-fold-state') || '{}');
                foldState[reqId] = !isCollapsed;
                localStorage.setItem('log-fold-state', JSON.stringify(foldState));
            }
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            async function exportJSON() {
                try {
                    const urlParams = new URLSearchParams(window.location.search);
                    const key = urlParams.get('key');
                    const pathPrefix = window.location.pathname.split('/')[1];
                    let url = `/${pathPrefix}/admin/log?limit=3000`;
                    if (key) url += `&key=${key}`;
                    const response = await fetch(url);
                    const data = await response.json();
                    const blob = new Blob([JSON.stringify({exported_at: new Date().toISOString(), logs: data.logs}, null, 2)], {type: 'application/json'});
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = 'logs_' + new Date().toISOString().slice(0, 19).replace(/:/g, '-') + '.json';
                    a.click();
                    URL.revokeObjectURL(blobUrl);
                    alert('导出成功');
                } catch (error) {
                    alert('导出失败: ' + error.message);
                }
            }
            async function clearAllLogs() {
                if (!confirm('确定清空所有日志？')) return;
                try {
                    const urlParams = new URLSearchParams(window.location.search);
                    const key = urlParams.get('key');
                    const pathPrefix = window.location.pathname.split('/')[1];
                    let url = `/${pathPrefix}/admin/log?confirm=yes`;
                    if (key) url += `&key=${key}`;
                    const response = await fetch(url, {method: 'DELETE'});
                    if (response.ok) {
                        alert('已清空');
                        loadLogs();
                    } else {
                        alert('清空失败');
                    }
                } catch (error) {
                    alert('清空失败: ' + error.message);
                }
            }
            let autoRefreshEnabled = true;
            function toggleAutoRefresh() {
                autoRefreshEnabled = !autoRefreshEnabled;
                const btn = document.getElementById('auto-refresh-btn');
                if (autoRefreshEnabled) {
                    btn.style.background = '#1a73e8';
                    autoRefreshTimer = setInterval(loadLogs, 5000);
                } else {
                    btn.style.background = '#6b6b6b';
                    if (autoRefreshTimer) {
                        clearInterval(autoRefreshTimer);
                        autoRefreshTimer = null;
                    }
                }
            }
            document.addEventListener('DOMContentLoaded', () => {
                loadLogs();
                autoRefreshTimer = setInterval(loadLogs, 5000);
                document.getElementById('search-input').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') loadLogs();
                });
                document.getElementById('level-filter').addEventListener('change', loadLogs);
                document.getElementById('limit-input').addEventListener('change', loadLogs);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
