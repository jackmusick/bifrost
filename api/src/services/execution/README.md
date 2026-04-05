# Execution Engine

Distributed, process-pooled execution system with Redis-first architecture for running workflows, scripts, and data providers in isolated processes.

## Architecture Overview

```
                          API Request
                               |
                               v
+---------------------------+  |  +---------------------------+
|        service.py         |  |  |      async_executor.py    |
|  - Workflow lookup        |<-+->|  - Store pending in Redis |
|  - Metadata resolution    |     |  - Publish to RabbitMQ    |
|  - Sync/async dispatch    |     |  - Return execution_id    |
+---------------------------+     +---------------------------+
                                              |
                                              v
                                     +----------------+
                                     |   RabbitMQ     |
                                     |    Queue       |
                                     +----------------+
                                              |
                                              v
+------------------------------------------------------------------+
|                  workflow_execution.py (Consumer)                 |
|  - Read pending execution from Redis                              |
|  - Create PostgreSQL record (RUNNING)                             |
|  - Pre-warm SDK cache                                             |
|  - Route to ProcessPoolManager                                    |
+------------------------------------------------------------------+
                                              |
                                              v
+------------------------------------------------------------------+
|                    process_pool.py (ProcessPoolManager)           |
|  - Manage pool of worker processes (min_workers to max_workers)   |
|  - Route executions to idle processes                             |
|  - Monitor timeouts, crashes, scale up/down                       |
|  - Heartbeat publishing for UI visibility                         |
+------------------------------------------------------------------+
                                              |
                        +---------------------+---------------------+
                        |                     |                     |
                        v                     v                     v
                 +-----------+         +-----------+         +-----------+
                 |  Worker   |         |  Worker   |         |  Worker   |
                 | Process 1 |         | Process 2 |         | Process N |
                 +-----------+         +-----------+         +-----------+
                        |
                        v
+------------------------------------------------------------------+
|                     simple_worker.py                              |
|  - Isolated subprocess for user code                              |
|  - Read context from Redis                                        |
|  - Clear workspace modules (pick up code changes)                 |
|  - Execute via engine.py                                          |
|  - Return result via queue                                        |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
|                        engine.py                                  |
|  - Unified execution for workflows, scripts, data providers       |
|  - Set up SDK context (bifrost._context)                          |
|  - Variable capture via sys.settrace()                            |
|  - Real-time log streaming to Redis                               |
|  - Type coercion for parameters                                   |
+------------------------------------------------------------------+
                        |
                        v
                 Result via Queue
                        |
                        v
+------------------------------------------------------------------+
|               workflow_execution.py (Result Handler)              |
|  - Update PostgreSQL with result                                  |
|  - Flush SDK writes (Redis -> Postgres)                           |
|  - Flush logs (Redis Stream -> Postgres)                          |
|  - Publish WebSocket updates                                      |
|  - Push sync result to Redis (for BLPOP)                          |
|  - Cleanup Redis keys                                             |
+------------------------------------------------------------------+
```

## Key Files

| File | Responsibility |
|------|----------------|
| `service.py` | High-level orchestration. Workflow lookup by ID, metadata caching (Redis-first), sync/async dispatch routing. Entry point for `run_workflow()` and `run_code()`. |
| `engine.py` | Unified execution engine. Handles workflows, inline scripts, and data providers. Sets up SDK context, captures variables via `sys.settrace()`, streams logs to Redis, handles data provider caching. |
| `async_executor.py` | Queue management. Stores pending execution in Redis, publishes minimal message to RabbitMQ, returns execution ID immediately (<100ms target). |
| `process_pool.py` | Worker process lifecycle management. Spawns/recycles processes, routes executions to idle workers, handles timeouts (SIGTERM -> SIGKILL), detects crashes, scales pool dynamically, publishes heartbeats. |
| `simple_worker.py` | Isolated subprocess entry point. Long-lived process that runs executions one at a time. Reads context from Redis, clears workspace modules before each execution, delegates to `engine.py`, returns results via multiprocessing queue. |
| `workflow_execution.py` | RabbitMQ consumer. Creates PostgreSQL records, pre-warms SDK cache, routes to process pool, handles results (success/failure), flushes data to Postgres, publishes WebSocket updates. |

## Execution States

```
PENDING     API accepted request, queued in RabbitMQ
    |
    v
RUNNING     Consumer picked up, worker executing
    |
    +---> SUCCESS              Completed successfully
    |
    +---> FAILED               Execution error (exception thrown)
    |
    +---> COMPLETED_WITH_ERRORS  Returned {success: false}
    |
    +---> TIMEOUT              Exceeded timeout_seconds
    |
    +---> CANCELLED            User cancelled via API
```

## Data Flow

### Async Execution (Default)

1. API calls `run_workflow()` or `run_code()`
2. `async_executor.py` stores pending execution in Redis
3. Minimal message published to RabbitMQ queue
4. API returns `{execution_id, status: "Pending"}` immediately
5. Consumer reads from RabbitMQ, fetches context from Redis
6. Consumer creates PostgreSQL record with `RUNNING` status
7. Consumer routes to `ProcessPoolManager`
8. Worker process executes code, returns result via queue
9. Consumer updates PostgreSQL, flushes logs/writes, publishes WebSocket update
10. Client receives update via WebSocket subscription

### Sync Execution (Tool Calls, `sync=True`)

1. Steps 1-8 same as async
2. Consumer pushes result to Redis list: `bifrost:result:{execution_id}`
3. API waits on `BLPOP` for result (up to timeout)
4. API returns complete result to caller

```python
# Sync execution with BLPOP
result = await redis_client.wait_for_result(execution_id, timeout_seconds=1800)
```

## SDK Context Injection

The execution engine injects context for the Bifrost SDK:

```python
# engine.py sets up context before execution
from bifrost._context import set_execution_context

context = ExecutionContext(
    user_id=request.caller.user_id,
    email=request.caller.email,
    organization=request.organization,
    execution_id=request.execution_id,
    _config=request.config,      # Integration credentials
    startup=request.startup,     # Launch workflow results
    roi=roi,                     # ROI tracking
)
set_execution_context(context)
```

Workflows access via:
```python
from bifrost import context

# Available in @workflow functions
context.user_id
context.organization.name
context.startup["launch_workflow_result"]
```

## Error Handling

### Timeouts

Process pool monitors execution duration:

```python
# process_pool.py
if elapsed > exec_info.timeout_seconds:
    # 1. Send SIGTERM for graceful shutdown
    os.kill(pid, signal.SIGTERM)

    # 2. Wait grace period
    await asyncio.sleep(graceful_shutdown_seconds)

    # 3. Force kill if still running
    os.kill(pid, signal.SIGKILL)

    # 4. Report timeout via callback
    await on_result({
        "execution_id": exec_info.execution_id,
        "success": False,
        "error_type": "TimeoutError",
    })
```

### Process Crashes

Pool detects crashed processes and replaces them:

```python
# process_pool.py
if not handle.is_alive and handle.state != ProcessState.KILLED:
    # Report crash if execution was in progress
    if handle.current_execution:
        await _report_crash(handle.current_execution)

    # Spawn replacement to maintain min_workers
    self._spawn_or_fork_process()
```

### Cancellation

Cancellation requests via Redis pub/sub:

```python
# Client publishes to bifrost:cancel channel
await redis.publish("bifrost:cancel", {"execution_id": "..."})

# Pool listens and kills the process
await _handle_cancel_request(execution_id)
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `min_workers` | 2 | Minimum worker processes to maintain |
| `max_workers` | 10 | Maximum worker processes |
| `execution_timeout_seconds` | 300 | Default timeout per execution |
| `graceful_shutdown_seconds` | 5 | Time between SIGTERM and SIGKILL |
| `recycle_after_executions` | 0 | Recycle process after N executions (0 = never) |
| `worker_heartbeat_interval_seconds` | 10 | Heartbeat publish interval |
| `worker_registration_ttl_seconds` | 30 | Redis registration TTL |

Environment variables:
```bash
BIFROST_MIN_WORKERS=2
BIFROST_MAX_WORKERS=10
BIFROST_EXECUTION_TIMEOUT_SECONDS=300
```

## Process Recycling

Workers are long-lived but can be recycled:

1. **After package install**: `mark_for_recycle()` flags all processes
2. **Execution count threshold**: Automatic recycling after N executions
3. **Manual API request**: Recycle specific process by PID

```python
# Idle processes recycled immediately
# Busy processes recycled after current execution completes
pool.mark_for_recycle()
```

## Redis Keys

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `bifrost:pending:{execution_id}` | Pending execution context | 1 hour |
| `bifrost:exec:{execution_id}:context` | Worker process context | 1 hour |
| `bifrost:result:{execution_id}` | Sync execution result (BLPOP) | 1 hour |
| `bifrost:pool:{worker_id}` | Worker registration/heartbeat | 30 seconds |
| `bifrost:logs:{execution_id}` | Real-time log stream | Until flush |
| `bifrost:workflow:metadata:{workflow_id}` | Cached workflow metadata | 5 minutes |
