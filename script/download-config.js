    // ==UserScript==
    // @name         Gemini Business Helper
    // @version      2.0
    // @description  自动下载配置
    // @match        https://business.gemini.google/*
    // @grant        GM_addStyle
    // @grant        GM_cookie
    // ==/UserScript==

    (function() {
        'use strict';

        GM_addStyle(`
            #gb-btn {
                position: fixed;
                bottom: 32px;
                right: 32px;
                width: 60px;
                height: 60px;
                background: #1a73e8;
                border-radius: 50%;
                box-shadow: 0 4px 16px rgba(0,0,0,0.2);
                cursor: pointer;
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 24px;
                transition: all 0.2s;
            }
            #gb-btn:hover {
                transform: scale(1.1);
                background: #1557b0;
            }
        `);

        const btn = document.createElement('div');
        btn.id = 'gb-btn';
        btn.textContent = '⬇';
        btn.title = '下载配置';
        document.body.appendChild(btn);

        const formatTime = (ts) => {
            if (!ts) return null;
            const d = new Date((ts - 43200) * 1000);
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;
        };

        const download = (data, filename) => {
            const blob = new Blob([data], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        };

        btn.onclick = () => {
            const pathParts = window.location.pathname.split('/');
            const cidIndex = pathParts.indexOf('cid');
            const config_id = (cidIndex !== -1 && pathParts[cidIndex + 1]) || null;
            const csesidx = new URLSearchParams(window.location.search).get('csesidx');

            let email = localStorage.getItem('gemini_user_email');
            if (!email) {
                email = prompt('请输入您的邮箱地址：');
                if (email) {
                    localStorage.setItem('gemini_user_email', email);
                }
            }

            GM_cookie('list', {}, (cookies, error) => {
                if (error || !config_id || !csesidx || !email) {
                    alert('❌ 数据不完整');
                    return;
                }

                const host_c_oses = (cookies.find(c => c.name === '__Host-C_OSES') || {}).value || null;
                const sesCookie = cookies.find(c => c.name === '__Secure-C_SES') || {};
                const secure_c_ses = sesCookie.value || null;

                if (!secure_c_ses) {
                    alert('❌ Cookie 读取失败');
                    return;
                }

                const data = {
                    id: email,
                    csesidx,
                    config_id,
                    secure_c_ses,
                    host_c_oses,
                    expires_at: formatTime(sesCookie.expirationDate)
                };

                download(JSON.stringify(data, null, 2), `${email}.json`);

                btn.textContent = '✓';
                btn.style.background = '#1e8e3e';
                setTimeout(() => {
                    btn.textContent = '⬇';
                    btn.style.background = '#1a73e8';
                }, 1500);
            });
        };
    })();
