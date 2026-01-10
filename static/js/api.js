// API 请求工具函数

// 全局配置（由页面初始化）
window.ADMIN_PATH = window.ADMIN_PATH || 'admin';

// 构建 API 路径
function getApiPath(path) {
    // 如果路径已经包含 admin_path，直接返回
    if (path.startsWith(`/${window.ADMIN_PATH}`)) {
        return path;
    }
    // 否则添加前缀
    return `/${window.ADMIN_PATH}${path}`;
}

// 统一的 API 请求函数
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorText = await response.text();
            let errorMsg;
            try {
                const errorJson = JSON.parse(errorText);
                errorMsg = errorJson.detail || errorJson.message || errorText;
            } catch {
                errorMsg = errorText;
            }
            throw new Error(`HTTP ${response.status}: ${errorMsg}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

// 导出函数（如果使用模块化）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { getApiPath, apiRequest };
}
