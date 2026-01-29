# Fix Database Connection Churn Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce database connections per workflow execution from 16+ to ~2 by eliminating worker subprocess DB access and consolidating consumer result handling into a single transaction.

**Architecture:** Two-part fix: (1) Remove sync DB fallback from worker's virtual import hook - instead, consumer verifies Redis module cache before dispatching and re-warms if empty. (2) Consolidate 6+ separate DB sessions in result handling into a single session passed through all functions.

**Tech Stack:** Python, SQLAlchemy (async), Redis, FastAPI, PostgreSQL via PGBouncer

---

## Task 1: Remove Sync DB Fallback from Worker

**Files:**
- Modify: `api/src/core/module_cache_sync.py:49-77` (remove DB fallback)
- Modify: `api/src/core/module_cache_sync.py:79-133` (delete entire function)

**Step 1: Read the current implementation**

Read `api/src/core/module_cache_sync.py` to understand the current `get_module_sync` and `_fetch_and_cache_from_db_sync` functions.

**Step 2: Simplify `get_module_sync` to remove DB fallback**

Replace lines 49-77 with:

```python
def get_module_sync(path: str) -> CachedModule | None:
    """
    Fetch a single module from cache (synchronous).

    Called by VirtualModuleFinder.find_spec() during import resolution.

    If module is not in Redis cache, returns None. The consumer is responsible
    for ensuring the cache is warm before dispatching to workers.

    Args:
        path: Module path relative to workspace

    Returns:
        CachedModule dict if found, None otherwise
    """
    try:
        client = _get_sync_redis()
        key = f"{MODULE_KEY_PREFIX}{path}"
        data = client.get(key)
        if data:
            return json.loads(data)

        # No DB fallback - consumer ensures cache is warm
        logger.debug(f"Module not in cache: {path}")
        return None

    except redis.RedisError as e:
        logger.warning(f"Redis error fetching module {path}: {e}")
        return None
```

**Step 3: Delete `_fetch_and_cache_from_db_sync` function**

Remove lines 79-133 entirely (the `_fetch_and_cache_from_db_sync` function). This function is no longer called.

**Step 4: Verify no other code references the deleted function**

Run: `grep -r "_fetch_and_cache_from_db_sync" api/`
Expected: No matches (only the definition we just removed)

**Step 5: Run existing tests to verify nothing breaks**

Run: `./test.sh tests/unit/core/test_module_cache.py -v`
Expected: All tests pass (or update tests if they explicitly test DB fallback)

**Step 6: Commit**

```bash
git add api/src/core/module_cache_sync.py
git commit -m "refactor: remove sync DB fallback from module cache

Worker subprocess no longer touches database directly. Consumer is
responsible for ensuring module cache is warm before dispatching."
```

---

## Task 2: Add Cache Verification to Consumer

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py` (add method and call it)

**Step 1: Read the current consumer implementation**

Read `api/src/jobs/consumers/workflow_execution.py` lines 406-700 to understand `process_message`.

**Step 2: Add `_ensure_module_cache` method to `WorkflowExecutionConsumer` class**

Add this method after line 93 (after `stop` method):

```python
    async def _ensure_module_cache(self) -> None:
        """
        Verify module cache exists, re-warm if empty.

        Called before dispatching to worker to ensure modules are available.
        Uses O(1) Redis SCARD to check if index has any members.
        """
        redis_conn = await self._redis_client._get_redis()

        # O(1) check - does index have any members?
        count = await redis_conn.scard("bifrost:module:index")

        if count == 0:
            logger.warning("Module cache empty, re-warming from DB")
            from src.core.module_cache import warm_cache_from_db
            await warm_cache_from_db()
            logger.info("Module cache re-warmed")
```

**Step 3: Call `_ensure_module_cache` before dispatching to pool**

Find the line `await self._pool.route_execution(` (around line 687) and add the cache check before it:

```python
            # Ensure module cache is warm before dispatching to worker
            await self._ensure_module_cache()

            # Route to process pool
            # Results are handled asynchronously via _handle_result callback
            await self._pool.route_execution(
```

**Step 4: Run consumer tests to verify**

Run: `./test.sh tests/unit/jobs/ -v -k "workflow_execution"`
Expected: Tests pass

**Step 5: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py
git commit -m "feat: add module cache verification before worker dispatch

Consumer now checks Redis module cache is warm before dispatching
to worker subprocess. Re-warms from DB if cache is empty."
```

---

## Task 3: Add Session Parameter to `update_execution`

**Files:**
- Modify: `api/src/repositories/executions.py`

**Step 1: Read current `update_execution` function**

Read `api/src/repositories/executions.py` to find the `update_execution` function signature and implementation.

**Step 2: Add optional session parameter**

Modify the function signature to accept an optional session:

```python
async def update_execution(
    execution_id: str,
    status: ExecutionStatus,
    result: Any | None = None,
    error_message: str | None = None,
    error_type: str | None = None,
    duration_ms: int | None = None,
    variables: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    time_saved: int | None = None,
    value: float | None = None,
    session: AsyncSession | None = None,  # NEW
) -> None:
```

**Step 3: Modify implementation to use provided session or create new one**

Wrap the implementation logic:

```python
async def update_execution(
    execution_id: str,
    status: ExecutionStatus,
    # ... other params ...
    session: AsyncSession | None = None,
) -> None:
    """Update execution record in database."""

    async def _do_update(db: AsyncSession) -> None:
        # Existing implementation goes here
        repo = ExecutionRepository(db)
        # ... rest of update logic ...

    if session is not None:
        # Use provided session (caller manages commit)
        await _do_update(session)
    else:
        # Backward compatible: create own session
        session_factory = get_session_factory()
        async with session_factory() as db:
            await _do_update(db)
            await db.commit()
```

**Step 4: Do the same for `create_execution`**

Apply the same pattern to `create_execution` function.

**Step 5: Run repository tests**

Run: `./test.sh tests/unit/repositories/ -v -k "execution"`
Expected: Tests pass

**Step 6: Commit**

```bash
git add api/src/repositories/executions.py
git commit -m "refactor: add optional session param to execution repo functions

Allows callers to pass a shared session for batched transactions
while maintaining backward compatibility for existing callers."
```

---

## Task 4: Add Session Parameter to `flush_pending_changes`

**Files:**
- Modify: `api/bifrost/_sync.py`

**Step 1: Read current implementation**

Read `api/bifrost/_sync.py` lines 30-77 to understand `flush_pending_changes`.

**Step 2: Add optional session parameter**

```python
async def flush_pending_changes(
    execution_id: str,
    session: AsyncSession | None = None,  # NEW
) -> int:
    """
    Flush all pending changes for an execution to Postgres.

    Args:
        execution_id: Execution ID to flush
        session: Optional database session. If provided, uses it and
                 caller is responsible for commit. If None, creates own session.

    Returns:
        int: Number of changes applied
    """
```

**Step 3: Modify implementation**

```python
    from src.core.database import get_session_factory

    r = await get_shared_redis()
    redis_key = pending_changes_key(execution_id)

    pending = await r.hgetall(redis_key)
    if not pending:
        return 0

    changes: list[dict[str, Any]] = []
    for value in pending.values():
        try:
            changes.append(json.loads(value))
        except json.JSONDecodeError:
            continue

    changes.sort(key=lambda c: c.get("sequence", 0))

    async def _apply_all(db: AsyncSession) -> None:
        for change in changes:
            await _apply_change(db, change)

    for attempt in range(3):
        try:
            if session is not None:
                # Use provided session (caller manages commit)
                await _apply_all(session)
            else:
                # Create own session
                session_factory = get_session_factory()
                async with session_factory() as db:
                    await _apply_all(db)
                    await db.commit()

            await r.delete(redis_key)
            logger.info(f"Flushed {len(changes)} changes for {execution_id}")
            return len(changes)
        except Exception as e:
            if attempt == 2:
                raise SyncError(f"Failed to flush: {e}") from e

    return 0
```

**Step 4: Run tests**

Run: `./test.sh tests/unit/ -v -k "sync"`
Expected: Tests pass

**Step 5: Commit**

```bash
git add api/bifrost/_sync.py
git commit -m "refactor: add optional session param to flush_pending_changes"
```

---

## Task 5: Add Session Parameter to `flush_logs_to_postgres`

**Files:**
- Modify: `api/bifrost/_logging.py`

**Step 1: Read current implementation**

Read `api/bifrost/_logging.py` lines 389-460 to understand `flush_logs_to_postgres`.

**Step 2: Add optional session parameter**

```python
async def flush_logs_to_postgres(
    execution_id: str | UUID,
    session: AsyncSession | None = None,  # NEW
) -> int:
```

**Step 3: Modify implementation to use provided session**

Replace the session handling section (around lines 446-449):

```python
            if not logs_to_insert:
                return 0

            # Batch insert to Postgres
            if session is not None:
                # Use provided session (caller manages commit)
                session.add_all(logs_to_insert)
            else:
                # Create own session
                session_factory = get_session_factory()
                async with session_factory() as db:
                    db.add_all(logs_to_insert)
                    await db.commit()

            # Clear the stream after successful persistence
            await r.delete(stream_key)
```

**Step 4: Run tests**

Run: `./test.sh tests/unit/ -v -k "logging"`
Expected: Tests pass

**Step 5: Commit**

```bash
git add api/bifrost/_logging.py
git commit -m "refactor: add optional session param to flush_logs_to_postgres"
```

---

## Task 6: Add Session Parameter to `update_delivery_from_execution`

**Files:**
- Modify: `api/src/services/events/processor.py`

**Step 1: Find and read the function**

Run: `grep -n "async def update_delivery_from_execution" api/src/services/events/processor.py`

Read the function implementation.

**Step 2: Add optional session parameter**

Apply the same pattern as previous tasks - add `session: AsyncSession | None = None` parameter and modify implementation to use it if provided.

**Step 3: Run tests**

Run: `./test.sh tests/unit/services/ -v -k "event"`
Expected: Tests pass

**Step 4: Commit**

```bash
git add api/src/services/events/processor.py
git commit -m "refactor: add optional session param to update_delivery_from_execution"
```

---

## Task 7: Consolidate Result Handling into Single Session

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py`

**Step 1: Modify `_handle_result` to create session**

Replace the current `_handle_result` method:

```python
    async def _handle_result(self, result: dict[str, Any]) -> None:
        """
        Handle result from process pool.

        This callback is invoked by the pool when a worker reports
        a result (success or failure, including timeouts and crashes).

        All DB operations are batched into a single transaction.
        """
        from src.core.database import get_session_factory

        execution_id = result.get("execution_id", "")

        # Single session for all DB operations
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                if result.get("success"):
                    await self._process_success(execution_id, result, session)
                else:
                    await self._process_failure(execution_id, result, session)

                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to process result for {execution_id}: {e}")
                raise
```

**Step 2: Modify `_process_success` signature and implementation**

Change signature to accept session:

```python
    async def _process_success(
        self,
        execution_id: str,
        result: dict[str, Any],
        session: AsyncSession,
    ) -> None:
```

Update all DB function calls to pass the session:

```python
        # Update database
        await update_execution(
            execution_id=execution_id,
            status=status,
            result=workflow_result,
            error_message=result.get("error"),
            error_type=result.get("error_type"),
            duration_ms=duration_ms,
            variables=result.get("variables"),
            metrics=result.get("metrics"),
            time_saved=roi_time_saved,
            value=roi_value,
            session=session,  # ADD THIS
        )

        # Update event delivery status if this execution was triggered by an event
        try:
            from src.services.events.processor import update_delivery_from_execution
            await update_delivery_from_execution(execution_id, status.value, session=session)
        except Exception as e:
            logger.warning(f"Failed to update event delivery for {execution_id[:8]}...: {e}")

        # Flush pending changes (SDK writes) from Redis to Postgres
        try:
            from bifrost._sync import flush_pending_changes
            changes_count = await flush_pending_changes(execution_id, session=session)
            if changes_count > 0:
                logger.info(f"Flushed {changes_count} pending changes for {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush pending changes for {execution_id[:8]}...: {e}")

        # Flush logs from Redis Stream to Postgres
        try:
            from bifrost._logging import flush_logs_to_postgres
            logs_count = await flush_logs_to_postgres(execution_id, session=session)
            if logs_count > 0:
                logger.debug(f"Flushed {logs_count} logs for {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush logs for {execution_id[:8]}...: {e}")

        # ... pubsub operations stay the same (no session needed) ...

        # Update metrics (these already have db param)
        metrics = result.get("metrics") or {}
        await update_daily_metrics(
            org_id=org_id,
            status=status.value,
            duration_ms=duration_ms,
            peak_memory_bytes=metrics.get("peak_memory_bytes"),
            cpu_total_seconds=metrics.get("cpu_total_seconds"),
            time_saved=roi_time_saved,
            value=roi_value,
            workflow_id=workflow_id,
            db=session,  # CHANGE FROM NOTHING TO session
        )

        if workflow_id:
            await update_workflow_roi_daily(
                workflow_id=workflow_id,
                org_id=org_id,
                status=status.value,
                time_saved=roi_time_saved,
                value=roi_value,
                db=session,  # CHANGE FROM NOTHING TO session
            )
```

**Step 3: Apply same changes to `_process_failure`**

Same pattern - add session param and pass to all DB functions.

**Step 4: Add import for AsyncSession at top of file**

```python
from sqlalchemy.ext.asyncio import AsyncSession
```

**Step 5: Run all consumer tests**

Run: `./test.sh tests/unit/jobs/ tests/integration/ -v -k "workflow_execution or consumer"`
Expected: Tests pass

**Step 6: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py
git commit -m "feat: consolidate result handling into single DB transaction

All DB operations in _process_success and _process_failure now use
a single session passed from _handle_result, reducing connections
from 6+ to 1 per execution result."
```

---

## Task 8: Integration Test - Verify Connection Reduction

**Files:**
- No code changes - verification only

**Step 1: Start the dev environment**

Run: `./debug.sh`
Wait for all services to be ready.

**Step 2: Monitor pgbouncer logs**

In a separate terminal:
```bash
docker compose logs -f pgbouncer 2>&1 | grep -E "login attempt|closing because"
```

**Step 3: Execute a workflow**

Use the UI or API to execute a simple workflow.

**Step 4: Count connection cycles**

Expected: ~2 connection open/close cycles per execution instead of 16+

**Step 5: Test cache wipe recovery**

```bash
# Wipe the module cache
docker compose exec redis redis-cli DEL bifrost:module:index

# Execute another workflow
# Expected: Consumer re-warms cache, workflow succeeds
```

**Step 6: Run full test suite**

```bash
./test.sh
```

Expected: All tests pass

**Step 7: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "test: verify connection reduction works end-to-end"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `api/src/core/module_cache_sync.py` | Remove sync DB fallback |
| `api/src/jobs/consumers/workflow_execution.py` | Add cache verification + single session for result handling |
| `api/src/repositories/executions.py` | Add optional session param |
| `api/bifrost/_sync.py` | Add optional session param |
| `api/bifrost/_logging.py` | Add optional session param |
| `api/src/services/events/processor.py` | Add optional session param |

## Expected Result

- **Before:** 16+ DB connections per workflow execution
- **After:** ~2 DB connections per workflow execution
- Worker subprocess: Zero direct DB access
- Consumer result handling: Single transaction for all writes
