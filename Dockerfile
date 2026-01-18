# Stage 1: 构建前端
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# 先复制 package 文件利用 Docker 缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build

# Stage 2: 最终运行时镜像
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装 Python 依赖和浏览器依赖（合并为单一 RUN 指令以减少层数）
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        chromium chromium-driver \
        dbus dbus-x11 \
        libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
        libcairo2 fonts-liberation fonts-noto-cjk && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 复制后端代码
COPY main.py .
COPY core ./core
COPY util ./util

# 从 builder 阶段只复制构建好的静态文件
COPY --from=frontend-builder /app/static ./static

# 创建数据目录
RUN mkdir -p ./data

# 声明数据卷
VOLUME ["/app/data"]

# 启动服务
CMD ["python", "-u", "main.py"]
