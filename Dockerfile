# Stage 1: 构建前端
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# 复制 package 文件利用 Docker 缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build

# Stage 2: 最终运行时镜像
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖（包括 Chromium 和浏览器依赖）
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # 编译依赖
    gcc \
    # Chromium 浏览器
    chromium \
    chromium-driver \
    # 浏览器运行依赖
    dbus \
    dbus-x11 \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    # 字体支持
    fonts-liberation \
    fonts-noto-cjk \
    && \
    # 安装 Python 依赖
    pip install --no-cache-dir -r requirements.txt && \
    # 清理
    apt-get purge -y gcc && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 复制后端代码
COPY main.py .
COPY core ./core
COPY util ./util

# 从 builder 阶段复制构建好的静态文件
COPY --from=frontend-builder /app/static ./static

# 创建数据目录和浏览器缓存目录
RUN mkdir -p ./data /tmp/chrome-profile && \
    chmod 1777 /tmp/chrome-profile

# 声明数据卷
VOLUME ["/app/data"]

# 启动服务
CMD ["python", "-u", "main.py"]
