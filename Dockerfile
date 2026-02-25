# Stage 1: 构建前端
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# 使用国内镜像加速 npm install
COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com && \
  npm install --silent

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build

# Stage 2: 最终运行时镜像
FROM python:3.11-slim-bookworm
WORKDIR /app

ARG APT_MIRROR=https://deb.debian.org/debian
ARG APT_SECURITY_MIRROR=https://deb.debian.org/debian-security
ARG APT_RETRIES=3
ARG APT_TIMEOUT=30
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_RETRIES=5
ARG PIP_TIMEOUT=120

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  TZ=Asia/Shanghai \
  DEBIAN_FRONTEND=noninteractive

# 1) Install system dependencies using local mirrors
RUN set -eux; \
  if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
  sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
  sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
  else \
  printf 'deb %s bookworm main\n' "$APT_MIRROR" > /etc/apt/sources.list; \
  printf 'deb %s bookworm-updates main\n' "$APT_MIRROR" >> /etc/apt/sources.list; \
  printf 'deb %s bookworm-security main\n' "$APT_SECURITY_MIRROR" >> /etc/apt/sources.list; \
  fi; \
  apt-get update -o Acquire::Retries="${APT_RETRIES}" -o Acquire::http::Timeout="${APT_TIMEOUT}"; \
  apt-get install -y --no-install-recommends \
  -o Acquire::Retries="${APT_RETRIES}" \
  -o Acquire::http::Timeout="${APT_TIMEOUT}" \
  gcc curl tzdata dbus dbus-x11 xvfb xauth libglib2.0-0 libnss3 libnspr4 \
  libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
  libpango-1.0-0 libcairo2 libthai-data fonts-liberation fonts-noto-cjk \
  chromium chromium-driver; \
  ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone; \
  apt-get clean; \
  rm -rf /var/lib/apt/lists/*

# 2) Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir \
  --retries "${PIP_RETRIES}" \
  --timeout "${PIP_TIMEOUT}" \
  --index-url "${PIP_INDEX_URL}" \
  -r requirements.txt

# 3. 后端代码复制（变动较频繁的部分）
COPY core ./core
COPY util ./util
COPY main.py .

# 4. 从 builder 阶段复制静态文件
COPY --from=frontend-builder /app/static ./static

# 5. 清理和准备启动
RUN apt-get purge -y gcc && apt-get autoremove -y && rm -rf /tmp/* /var/tmp/* && \
  mkdir -p ./data

COPY entrypoint.sh .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh



EXPOSE 7860

CMD ["./entrypoint.sh"]
