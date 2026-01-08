# Phase 6: Worker Integration

## Overview

Update the worker to install the virtual import hook before executing any workflow code. Remove filesystem-based workspace sync.

## Current Worker Flow

**File:** `api/src/services/execution/worker.py`

Currently, the worker:
1. Starts up and connects to message queue
2. Downloads workspace files to `/tmp/bifrost/workspace` (or waits for sync)
3. Adds workspace to `sys.path`
4. Executes workflows that may import from workspace

## New Worker Flow

1. Starts up and connects to message queue
2. **Installs virtual import hook** (no file download needed)
3. Adds virtual workspace to `sys.path` (for `__file__` resolution)
4. Executes workflows - imports load from Redis cache

## Implementation Changes

```python
# api/src/services/execution/worker.py

import sys
from pathlib import Path

VIRTUAL_WORKSPACE = Path("/tmp/bifrost/workspace")


async def worker_main(execution_id: str):
    """Main worker entry point."""

    # Install virtual import hook BEFORE any workspace imports
    from src.services.execution.virtual_import import install_virtual_import_hook
    install_virtual_import_hook()

    # Add virtual workspace to path (for __file__ resolution in tracebacks)
    workspace_str = str(VIRTUAL_WORKSPACE)
    if workspace_str not in sys.path:
        sys.path.insert(0, workspace_str)

    # REMOVED: workspace sync/download logic
    # await workspace_sync.ensure_synced()
    # await wait_for_workspace_download()

    # Continue with workflow execution...
    await execute_workflow(execution_id)
```

## What Gets Removed

### 1. Workspace Download on Startup

```python
# REMOVE this pattern:
async def ensure_workspace_ready():
    """Wait for workspace files to be downloaded from S3."""
    download_queue.wait_for_sync()
    # ...
```

### 2. File System Watching

```python
# REMOVE this pattern:
async def start_file_watcher():
    """Watch /tmp/bifrost/workspace for changes."""
    # ...
```

### 3. S3 Download Consumers

Any background job that downloads Python files from S3 to `/tmp/bifrost/workspace` can be removed.

## Multiprocessing Considerations

Workers use multiprocessing with spawn context for isolation. Each spawned process needs to:

1. Install the import hook in its own `sys.meta_path`
2. Have access to Redis for module fetching

The `install_virtual_import_hook()` function handles this - it's called at the start of each worker process.

```python
# In the spawned process entry point:
def run_workflow_process(execution_id: str):
    """Entry point for spawned workflow process."""
    import asyncio

    # Install hook in this process
    from src.services.execution.virtual_import import install_virtual_import_hook
    install_virtual_import_hook()

    # Run the workflow
    asyncio.run(execute_workflow(execution_id))
```

## Virtual Workspace Directory

We keep `/tmp/bifrost/workspace` as a virtual path for:

1. **Tracebacks**: `__file__` attributes point here for readable stack traces
2. **`sys.path`**: Python expects directories in the path
3. **Code that uses `__file__`**: Will get meaningful errors if trying to access relative files

The directory can be empty or not exist - the import hook intercepts before filesystem access.

## Environment Variables

The worker needs Redis connection info:

```bash
REDIS_URL=redis://redis:6379/0
```

This is already configured in `docker-compose.yml` for workers.
