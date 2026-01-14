FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY main.py .
COPY core ./core
COPY util ./util

# Copy prebuilt static assets
COPY static ./static

# Create data directory (local + HF Spaces Pro)
RUN mkdir -p ./data

# Declare data volume
VOLUME ["/app/data"]

# Start service
CMD ["python", "-u", "main.py"]
