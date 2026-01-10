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
# 复制 core 模块
COPY core ./core
# 复制 util 目录
COPY util ./util
# 复制 templates 目录
COPY templates ./templates
# 复制 static 目录
COPY static ./static
# 创建数据目录
RUN mkdir -p ./data/images
# 声明数据卷（运行时需要 -v 挂载才能持久化）
VOLUME ["/app/data"]
CMD ["python", "-u", "main.py"]