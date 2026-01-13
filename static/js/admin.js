let currentConfig = null;

            // 复制到剪贴板函数
            function copyToClipboard(text, button) {
                navigator.clipboard.writeText(text).then(() => {
                    // 显示复制成功状态
                    const originalText = button.innerHTML;
                    button.innerHTML = '✓';
                    button.classList.add('copied');

                    // 2秒后恢复
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.classList.remove('copied');
                    }, 2000);
                }).catch(err => {
                    console.error('复制失败:', err);
                    alert('复制失败，请手动复制');
                });
            }

            // 标签页切换函数
            function switchTab(tabName) {
                // 隐藏所有标签页内容
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                // 移除所有标签按钮的active状态
                document.querySelectorAll('.tab-button').forEach(button => {
                    button.classList.remove('active');
                });

                // 显示选中的标签页
                document.getElementById('tab-' + tabName).classList.add('active');
                // 激活对应的按钮
                event.target.classList.add('active');
            }

            // 统一的页面刷新函数（避免缓存）
            function refreshPage() {
                window.location.reload();
            }

            // 统一的错误处理函数
            async function handleApiResponse(response) {
                if (!response.ok) {
                    const errorText = await response.text();
                    let errorMsg;
                    try {
                        const errorJson = JSON.parse(errorText);
                        errorMsg = errorJson.detail || errorJson.message || errorText;
                    } catch {
                        errorMsg = errorText;
                    }
                    throw new Error(`HTTP $${response.status}: $${errorMsg}`);
                }
                return await response.json();
            }

            async function showEditConfig() {
                const config = await fetch(`/${window.ADMIN_PATH}/accounts-config`).then(r => r.json());
                currentConfig = config.accounts;
                const json = JSON.stringify(config.accounts, null, 2);
                document.getElementById('jsonEditor').value = json;
                document.getElementById('jsonError').classList.remove('show');
                document.getElementById('jsonModal').classList.add('show');

                // 实时验证 JSON
                document.getElementById('jsonEditor').addEventListener('input', validateJSON);
            }

            function validateJSON() {
                const editor = document.getElementById('jsonEditor');
                const errorDiv = document.getElementById('jsonError');
                try {
                    JSON.parse(editor.value);
                    errorDiv.classList.remove('show');
                    errorDiv.textContent = '';
                    return true;
                } catch (e) {
                    errorDiv.classList.add('show');
                    errorDiv.textContent = '❌ JSON 格式错误: ' + e.message;
                    return false;
                }
            }

            function closeModal() {
                document.getElementById('jsonModal').classList.remove('show');
                document.getElementById('jsonEditor').removeEventListener('input', validateJSON);
            }

            async function saveConfig() {
                if (!validateJSON()) {
                    alert('JSON 格式错误，请修正后再保存');
                    return;
                }

                const newJson = document.getElementById('jsonEditor').value;
                const originalJson = JSON.stringify(currentConfig, null, 2);

                if (newJson === originalJson) {
                    closeModal();
                    return;
                }

                try {
                    const data = JSON.parse(newJson);
                    const response = await fetch(`/${window.ADMIN_PATH}/accounts-config`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });

                    await handleApiResponse(response);
                    closeModal();
                    refreshPage();
                } catch (error) {
                    console.error('保存失败:', error);
                    alert('更新失败: ' + error.message);
                }
            }

            async function deleteAccount(accountId) {
                if (!confirm(`确定删除账户 $${accountId}？`)) return;

                try {
                    const response = await fetch(`/${window.ADMIN_PATH}/accounts/${accountId}`, {
                        method: 'DELETE'
                    });

                    await handleApiResponse(response);
                    refreshPage();
                } catch (error) {
                    console.error('删除失败:', error);
                    alert('删除失败: ' + error.message);
                }
            }

            async function disableAccount(accountId) {
                try {
                    const response = await fetch(`/${window.ADMIN_PATH}/accounts/${accountId}/disable`, {
                        method: 'PUT'
                    });

                    await handleApiResponse(response);
                    refreshPage();
                } catch (error) {
                    console.error('禁用失败:', error);
                    alert('禁用失败: ' + error.message);
                }
            }

            async function enableAccount(accountId) {
                try {
                    const response = await fetch(`/${window.ADMIN_PATH}/accounts/${accountId}/enable`, {
                        method: 'PUT'
                    });

                    await handleApiResponse(response);
                    refreshPage();
                } catch (error) {
                    console.error('启用失败:', error);
                    alert('启用失败: ' + error.message);
                }
            }

            // 批量上传相关函数
            async function handleFileUpload(event) {
                const files = event.target.files;
                if (!files.length) return;

                let newAccounts = [];
                for (const file of files) {
                    try {
                        const text = await file.text();
                        const data = JSON.parse(text);
                        if (Array.isArray(data)) {
                            newAccounts.push(...data);
                        } else {
                            newAccounts.push(data);
                        }
                    } catch (e) {
                        alert(`文件 $${file.name} 解析失败: $${e.message}`);
                        event.target.value = '';
                        return;
                    }
                }

                if (!newAccounts.length) {
                    alert('未找到有效账户数据');
                    event.target.value = '';
                    return;
                }

                try {
                    // 获取现有配置
                    const configResp = await fetch(`/${window.ADMIN_PATH}/accounts-config`);
                    const configData = await handleApiResponse(configResp);
                    const existing = configData.accounts || [];

                    // 构建ID到索引的映射
                    const idToIndex = new Map();
                    existing.forEach((acc, idx) => {
                        if (acc.id) idToIndex.set(acc.id, idx);
                    });

                    // 合并：相同ID覆盖，新ID追加
                    let added = 0;
                    let updated = 0;
                    for (const acc of newAccounts) {
                        if (!acc.secure_c_ses || !acc.csesidx || !acc.config_id) continue;
                        const accId = acc.id || `account_${existing.length + added + 1}`;
                        acc.id = accId;

                        if (idToIndex.has(accId)) {
                            // 覆盖已存在的账户
                            existing[idToIndex.get(accId)] = acc;
                            updated++;
                        } else {
                            // 追加新账户
                            existing.push(acc);
                            idToIndex.set(accId, existing.length - 1);
                            added++;
                        }
                    }

                    if (added === 0 && updated === 0) {
                        alert('没有有效账户可导入');
                        event.target.value = '';
                        return;
                    }

                    // 保存合并后的配置
                    const response = await fetch(`/${window.ADMIN_PATH}/accounts-config`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(existing)
                    });

                    await handleApiResponse(response);
                    event.target.value = '';
                    refreshPage();
                } catch (error) {
                    console.error('导入失败:', error);
                    alert('导入失败: ' + error.message);
                    event.target.value = '';
                }
            }

            // 点击模态框外部关闭
            document.getElementById('jsonModal').addEventListener('click', function(e) {
                if (e.target === this) {
                    closeModal();
                }
            });

            // ========== 系统设置相关函数 ==========
            async function loadSettings() {
                try {
                    const response = await fetch(`/${window.ADMIN_PATH}/settings`);
                    const settings = await handleApiResponse(response);

                    // 基础配置
                    document.getElementById('setting-api-key').value = settings.basic?.api_key || '';
                    document.getElementById('setting-base-url').value = settings.basic?.base_url || '';
                    document.getElementById('setting-proxy').value = settings.basic?.proxy || '';

                    // 图片生成配置
                    document.getElementById('setting-image-enabled').checked = settings.image_generation?.enabled ?? true;
                    const supportedModels = settings.image_generation?.supported_models || [];
                    document.querySelectorAll('#setting-image-models input[type="checkbox"]').forEach(cb => {
                        cb.checked = supportedModels.includes(cb.value);
                    });
                    document.getElementById('setting-image-output-format').value = settings.image_generation?.output_format || 'base64';

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
                } catch (error) {
                    console.error('加载设置失败:', error);
                    alert('加载设置失败: ' + error.message);
                }
            }

            async function saveSettings() {
                try {
                    // 收集图片生成支持的模型
                    const supportedModels = [];
                    document.querySelectorAll('#setting-image-models input[type="checkbox"]:checked').forEach(cb => {
                        supportedModels.push(cb.value);
                    });

                    const settings = {
                        basic: {
                            api_key: document.getElementById('setting-api-key').value,
                            base_url: document.getElementById('setting-base-url').value,
                            proxy: document.getElementById('setting-proxy').value
                        },
                        image_generation: {
                            enabled: document.getElementById('setting-image-enabled').checked,
                            supported_models: supportedModels,
                            output_format: document.getElementById('setting-image-output-format').value
                        },
                        retry: {
                            max_new_session_tries: parseInt(document.getElementById('setting-max-new-session').value) || 5,
                            max_request_retries: parseInt(document.getElementById('setting-max-retries').value) || 3,
                            max_account_switch_tries: parseInt(document.getElementById('setting-max-switch').value) || 5,
                            account_failure_threshold: parseInt(document.getElementById('setting-failure-threshold').value) || 3,
                            rate_limit_cooldown_seconds: parseInt(document.getElementById('setting-cooldown').value) || 600,
                            session_cache_ttl_seconds: parseInt(document.getElementById('setting-cache-ttl').value) || 3600
                        },
                        public_display: {
                            logo_url: document.getElementById('setting-logo-url').value,
                            chat_url: document.getElementById('setting-chat-url').value
                        },
                        session: {
                            expire_hours: parseInt(document.getElementById('setting-session-hours').value) || 24
                        }
                    };

                    const response = await fetch(`/${window.ADMIN_PATH}/settings`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(settings)
                    });

                    await handleApiResponse(response);

                    // 直接刷新页面，不显示弹窗
                    window.location.reload();
                } catch (error) {
                    console.error('保存设置失败:', error);
                    alert('保存设置失败: ' + error.message);
                }
            }

            // 页面加载时自动加载设置
            document.addEventListener('DOMContentLoaded', function() {
                loadSettings();
            });