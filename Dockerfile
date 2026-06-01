FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for jieba and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY main.py config.py database.py ws_manager.py \
     scheduler.py voice_poller.py points_engine.py \
     xiaomi_client.py ./
COPY api/ ./api/
COPY static/ ./static/

# Data directory for SQLite DB and Xiaomi token (mount as volume)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python", "main.py"]
