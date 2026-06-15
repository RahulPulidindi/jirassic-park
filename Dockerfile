# syntax=docker/dockerfile:1.6

# ---------- Stage 1: build Next.js static export ----------
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: install Python + app ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        sqlite3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cached layer)
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN pip install --upgrade pip && \
    pip install -e "/app/backend[agent]"

# Copy backend source
COPY backend/ /app/backend/

# Copy static UI from frontend build stage
COPY --from=frontend-build /frontend/out /app/static

# Entrypoint
COPY ops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
