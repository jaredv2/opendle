# ──────────────────────────────────────────────────────────────────────
# Opendle Dockerfile
# Build:  docker build -t opendle .
# Run:    docker run -p 8000:8000 -e DEV_KEY=my-secret opendle
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer-cached when code changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data directory for persistent JSON storage
RUN mkdir -p /app/data

# Expose the port uvicorn listens on
EXPOSE 8000

# Production command — no reload, single worker
# In production on Render/Railway, set DEV_KEY via their env var UI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]