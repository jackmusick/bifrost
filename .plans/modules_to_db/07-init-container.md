# Phase 7: Init Container

## Overview

Create an init container that runs database migrations and warms the Redis module cache before other services start.

## Init Container Script

**File:** `api/scripts/init_container.py`

```python
#!/usr/bin/env python3
"""
Init container script for Bifrost.

Runs before API and workers start:
1. Run database migrations (alembic upgrade head)
2. Warm Redis module cache from database

Usage:
    python -m scripts.init_container
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("init_container")


def run_migrations() -> bool:
    """Run alembic migrations."""
    logger.info("Running database migrations...")

    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=Path(__file__).parent.parent,  # api/ directory
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Migrations completed successfully")
        if result.stdout:
            logger.debug(f"Migration output: {result.stdout}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed: {e.stderr}")
        return False


async def warm_module_cache() -> int:
    """Warm Redis module cache from database."""
    logger.info("Warming module cache...")

    try:
        from src.core.module_cache import warm_cache_from_db
        count = await warm_cache_from_db()
        logger.info(f"Module cache warmed with {count} modules")
        return count

    except Exception as e:
        logger.error(f"Failed to warm cache: {e}")
        raise


async def main() -> int:
    """Main entry point."""
    logger.info("Init container starting...")

    # Step 1: Run migrations
    if not run_migrations():
        logger.error("Migrations failed - aborting")
        return 1

    # Step 2: Warm module cache
    try:
        await warm_module_cache()
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        return 1

    logger.info("Init container completed successfully")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

## Docker Compose Configuration

**File:** `docker-compose.yml`

```yaml
services:
  # Init container runs first
  init:
    image: bifrost-api
    command: python -m scripts.init_container
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - bifrost

  # API waits for init to complete
  api:
    image: bifrost-api
    # REMOVE: alembic upgrade head from command
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000
    depends_on:
      init:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    # ... rest of config ...

  # Workers wait for init to complete
  worker:
    image: bifrost-api
    command: python -m src.jobs.worker
    depends_on:
      init:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    # ... rest of config ...
```

**File:** `docker-compose.dev.yml`

Same pattern - add init service that runs before api/worker.

## Benefits

### 1. Atomic Startup

All services start with:
- Database at correct schema version
- Module cache fully populated

No race conditions where a worker tries to import before cache is warm.

### 2. Clean Separation

- Init container: one-time setup tasks
- API: handles HTTP requests
- Worker: executes workflows

Each service has a single responsibility.

### 3. Restart Safety

If init container fails:
- `condition: service_completed_successfully` prevents dependent services from starting
- Operator sees clear failure in logs
- Can debug and re-run

### 4. Development Consistency

Same init process in dev and prod. No "works on my machine" issues with migrations or cache state.

## Health Checks

Ensure Postgres and Redis have health checks so init doesn't start until they're ready:

```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 5s
    timeout: 5s
    retries: 5

redis:
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 5
```

## Kubernetes Equivalent

For K8s deployment, use an init container in the pod spec:

```yaml
spec:
  initContainers:
    - name: init
      image: bifrost-api
      command: ["python", "-m", "scripts.init_container"]
      env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: bifrost-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: bifrost-secrets
              key: redis-url
  containers:
    - name: api
      image: bifrost-api
      # ...
```
