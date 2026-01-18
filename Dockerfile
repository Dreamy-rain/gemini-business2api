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
