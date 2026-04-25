# Bifrost - Unified Container Image
# Used by all services: API, Discovery, Scheduler, Worker
# Multi-stage build for efficient image size

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.14-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.14-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    gosu \
    git \
    awscli \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (paths relative to root context)
COPY api/src/ /app/src/
COPY api/shared/ /app/shared/
COPY api/alembic/ /app/alembic/
COPY api/alembic.ini /app/
COPY api/bifrost/ /app/bifrost/
COPY api/bifrost.py /app/
COPY api/scripts/ /app/scripts/

# Install app compiler Node.js dependencies
COPY api/src/services/app_compiler/package.json api/src/services/app_compiler/package-lock.json* /app/src/services/app_compiler/
COPY api/src/services/app_compiler/compile.js /app/src/services/app_compiler/
COPY api/src/services/app_compiler/tailwind.js /app/src/services/app_compiler/
RUN cd /app/src/services/app_compiler && npm install --production

# Install app bundler Node.js dependencies (esbuild)
COPY api/src/services/app_bundler/package.json api/src/services/app_bundler/package-lock.json* /app/src/services/app_bundler/
RUN cd /app/src/services/app_bundler && npm install --production

# Create non-root user
RUN useradd -m -u 1000 bifrost && \
    chown -R bifrost:bifrost /app

# Create directories for workspace and temp
RUN mkdir -p /workspace /tmp/bifrost && \
    chown -R bifrost:bifrost /workspace /tmp/bifrost

# Copy entrypoint script
COPY api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Don't switch to bifrost here - entrypoint handles user switching
# This allows the entrypoint to fix volume permissions when needed
ENTRYPOINT ["/entrypoint.sh"]

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ARG BIFROST_VERSION=unknown
ENV BIFROST_VERSION=${BIFROST_VERSION}

# No default CMD - let docker-compose specify the command per service
