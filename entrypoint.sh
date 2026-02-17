#!/bin/bash

echo "[ENTRYPOINT] Starting application..."

# 尝试启动 Xvfb（可选，失败不影响主程序）
echo "[ENTRYPOINT] Attempting to start Xvfb..."
if Xvfb :99 -screen 0 1280x800x24 -ac 2>/dev/null & then
    sleep 2
    export DISPLAY=:99
    echo "[ENTRYPOINT] Xvfb started on DISPLAY=:99"
else
    echo "[ENTRYPOINT] Xvfb failed to start (this is OK for cloud platforms)"
fi

# 优化 glibc 内存管理：让 free() 更积极地归还内存给 OS
export MALLOC_TRIM_THRESHOLD_=131072
export MALLOC_MMAP_THRESHOLD_=131072
export MALLOC_ARENA_MAX=2
# 强制设置监听端口为 7860 (适配 Zeabur 特定配置)
export PORT=7860

# 启动 Python 应用，强制指定端口为 7860
echo "[ENTRYPOINT] Starting Python application on port 7860..."
exec PORT=7860 python -u main.py
