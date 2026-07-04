FROM python:3.11-slim

WORKDIR /app

# Install system dependencies:
# - gcc: needed to compile jieba / cryptography wheels
# - tzdata: timezone data for Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone (app uses datetime.now() for scheduling — must be local, not UTC)
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python source (use glob to avoid missing files like event_logger.py)
COPY *.py ./
COPY api/ ./api/
COPY static/ ./static/

# Data directory for SQLite DB, Xiaomi token, and logs (mount as volume)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 8011

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8011/api/config/xiaomi/status', timeout=3)" || exit 1

CMD ["python", "main.py"]
