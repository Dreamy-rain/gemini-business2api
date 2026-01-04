FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY main.py .
# 复制 uptime_tracker 模块
COPY uptime_tracker.py .
# 复制 core 模块
COPY core ./core
# 复制 util 目录
COPY util ./util
CMD ["python", "-u", "main.py"]