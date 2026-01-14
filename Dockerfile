# 多阶段构建：前端构建
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 后端运行环境
FROM python:3.11-slim
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 复制后端代码
COPY main.py .
COPY core ./core
COPY util ./util

# 复制前端构建产物
COPY --from=frontend-builder /frontend/dist ./static

# 创建数据目录（支持本地和 HF Spaces Pro）
RUN mkdir -p ./data

# 声明数据卷
VOLUME ["/app/data"]

# 启动服务
CMD ["python", "-u", "main.py"]