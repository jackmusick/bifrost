# Module Cache Sync & Persistent DB Session Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix module cache sync to handle partial cache expiry, and establish a persistent DB session pattern for the long-lived consumer process.

**Architecture:** Add a persistent DB session to `WorkflowExecutionConsumer` that's created on `start()` and closed on `stop()`. Refactor read-heavy functions to accept an optional session parameter. Replace the naive `_ensure_module_cache()` with a smarter `_sync_module_cache()` that compares DB state with Redis and fills gaps.

**Tech Stack:** Python 3.11, SQLAlchemy AsyncSession, Redis, PostgreSQL

---

## Task 1: Add Persistent DB Session Infrastructure to Consumer

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py:58-95`
- Test: `api/tests/unit/jobs/consumers/test_workflow_execution_session.py` (new)

**Step 1: Write the failing test for session lifecycle**

Create `api/tests/unit/jobs/consumers/test_workflow_execution_session.py`:

```python
"""Tests for WorkflowExecutionConsumer persistent DB session."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConsumerSessionLifecycle:
    """Test persistent DB session management."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create mock session factory."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = mock_session
        return factory, mock_session

    @pytest.mark.asyncio
    async def test_start_creates_db_session(self, mock_session_factory):
        """Consumer.start() should create persistent DB session."""
        factory, mock_session = mock_session_factory

        with patch("src.jobs.consumers.workflow_execution.get_session_factory", return_value=factory):
            with patch("src.jobs.consumers.workflow_execution.get_redis_client"):
                with patch("src.jobs.consumers.workflow_execution.get_process_pool"):
                    with patch.object(
                        WorkflowExecutionConsumer, "__init__", lambda self: None
                    ):
                        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

                        consumer = WorkflowExecutionConsumer()
                        consumer._pool = AsyncMock()
                        consumer._pool.start = AsyncMock()
                        consumer._pool_started = False
                        consumer._session_factory = factory
                        consumer._db_session = None

                        # Mock parent start
                        with patch.object(
                            WorkflowExecutionConsumer.__bases__[0], "start", AsyncMock()
                        ):
                            await consumer.start()

                        assert consumer._db_session is not None
                        factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_closes_db_session(self, mock_session_factory):
        """Consumer.stop() should close persistent DB session."""
        factory, mock_session = mock_session_factory

        with patch("src.jobs.consumers.workflow_execution.get_session_factory", return_value=factory):
            with patch("src.jobs.consumers.workflow_execution.get_redis_client"):
                with patch("src.jobs.consumers.workflow_execution.get_process_pool"):
                    with patch.object(
                        WorkflowExecutionConsumer, "__init__", lambda self: None
                    ):
                        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

                        consumer = WorkflowExecutionConsumer()
                        consumer._pool = AsyncMock()
                        consumer._pool.stop = AsyncMock()
                        consumer._pool_started = True
                        consumer._db_session = mock_session

                        # Mock parent stop
                        with patch.object(
                            WorkflowExecutionConsumer.__bases__[0], "stop", AsyncMock()
                        ):
                            await consumer.stop()

                        mock_session.close.assert_called_once()
                        assert consumer._db_session is None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py -v`
Expected: FAIL with import or attribute errors (session infrastructure doesn't exist yet)

**Step 3: Add session factory import and instance variables**

In `api/src/jobs/consumers/workflow_execution.py`, add import at top (around line 20):

```python
from src.core.database import get_session_factory
```

Modify `__init__` method (lines 58-74) to add session variables:

```python
def __init__(self):
    from src.config import get_settings
    from src.services.execution.process_pool import get_process_pool

    settings = get_settings()
    super().__init__(
        queue_name=QUEUE_NAME,
        prefetch_count=settings.max_concurrency,
    )
    self._redis_client = get_redis_client()

    # Get the global ProcessPoolManager instance
    # This ensures package_install consumer can also update it
    self._pool = get_process_pool()
    # Set the result callback on the global pool
    self._pool.on_result = self._handle_result
    self._pool_started = False

    # Persistent DB session for read operations
    self._session_factory = get_session_factory()
    self._db_session: "AsyncSession | None" = None
```

**Step 4: Modify start() to create session**

Modify `start()` method (lines 76-84):

```python
async def start(self) -> None:
    """Start the consumer and process pool."""
    # Call parent start to set up RabbitMQ connection
    await super().start()

    # Create persistent DB session for read operations
    self._db_session = self._session_factory()
    logger.info("Persistent DB session created")

    # Start process pool
    await self._pool.start()
    self._pool_started = True
    logger.info("Process pool started")
```

**Step 5: Modify stop() to close session**

Modify `stop()` method (lines 86-95):

```python
async def stop(self) -> None:
    """Stop the consumer and process pool."""
    # Stop process pool
    if self._pool_started:
        await self._pool.stop()
        self._pool_started = False
        logger.info("Process pool stopped")

    # Close persistent DB session
    if self._db_session:
        await self._db_session.close()
        self._db_session = None
        logger.info("Persistent DB session closed")

    # Call parent stop
    await super().stop()
```

**Step 6: Run test to verify it passes**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py api/tests/unit/jobs/consumers/test_workflow_execution_session.py
git commit -m "$(cat <<'EOF'
feat(consumer): add persistent DB session lifecycle

Add session factory and persistent session to WorkflowExecutionConsumer:
- Created in start(), closed in stop()
- Will be used for read operations to avoid per-request connection overhead

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Session Health Check and Reconnection Logic

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py`
- Test: `api/tests/unit/jobs/consumers/test_workflow_execution_session.py`

**Step 1: Write the failing test for reconnection**

Add to `api/tests/unit/jobs/consumers/test_workflow_execution_session.py`:

```python
class TestConsumerSessionReconnection:
    """Test session health check and reconnection."""

    @pytest.mark.asyncio
    async def test_get_db_session_returns_healthy_session(self):
        """_get_db_session() returns existing session when healthy."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_session
            consumer._session_factory = MagicMock()

            result = await consumer._get_db_session()

            assert result is mock_session
            mock_session.execute.assert_called_once()  # Health check ran

    @pytest.mark.asyncio
    async def test_get_db_session_reconnects_on_stale(self):
        """_get_db_session() reconnects when session is stale."""
        from sqlalchemy.exc import DBAPIError
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        stale_session = AsyncMock()
        stale_session.execute = AsyncMock(side_effect=DBAPIError("connection closed", None, None))
        stale_session.close = AsyncMock()

        fresh_session = AsyncMock()
        fresh_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = fresh_session

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = stale_session
            consumer._session_factory = factory

            result = await consumer._get_db_session()

            assert result is fresh_session
            stale_session.close.assert_called_once()
            factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_session_creates_when_none(self):
        """_get_db_session() creates session when None."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        new_session = AsyncMock()
        new_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = new_session

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = None
            consumer._session_factory = factory

            result = await consumer._get_db_session()

            assert result is new_session
            factory.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py::TestConsumerSessionReconnection -v`
Expected: FAIL with `AttributeError: 'WorkflowExecutionConsumer' object has no attribute '_get_db_session'`

**Step 3: Implement _get_db_session() method**

Add method to `WorkflowExecutionConsumer` class (after `stop()`, around line 100):

```python
async def _get_db_session(self) -> "AsyncSession":
    """
    Get the persistent DB session, reconnecting if needed.

    Performs a health check and reconnects if the connection is stale.
    This is important for long-running consumers where connections may drop.

    Returns:
        Healthy AsyncSession instance
    """
    from sqlalchemy import text

    # Create session if None
    if self._db_session is None:
        self._db_session = self._session_factory()
        logger.debug("Created new persistent DB session")

    # Health check - try a simple query
    try:
        await self._db_session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"DB session stale ({type(e).__name__}), reconnecting...")
        try:
            await self._db_session.close()
        except Exception:
            pass  # Ignore close errors on stale session
        self._db_session = self._session_factory()
        logger.info("Reconnected persistent DB session")

    return self._db_session
```

Also add the AsyncSession type import at the top of the file:

```python
from sqlalchemy.ext.asyncio import AsyncSession
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py::TestConsumerSessionReconnection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py api/tests/unit/jobs/consumers/test_workflow_execution_session.py
git commit -m "$(cat <<'EOF'
feat(consumer): add session health check and reconnection

Add _get_db_session() method that:
- Returns existing session if healthy
- Reconnects automatically if connection is stale
- Creates new session if None

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Refactor get_workflow_for_execution() to Accept Optional Session

**Files:**
- Modify: `api/src/services/execution/service.py:124-181`
- Test: `api/tests/unit/services/execution/test_service.py` (may need to create)

**Step 1: Write the failing test**

Create or add to `api/tests/unit/services/execution/test_service.py`:

```python
"""Tests for execution service functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestGetWorkflowForExecution:
    """Test get_workflow_for_execution with optional session."""

    @pytest.mark.asyncio
    async def test_uses_provided_session(self):
        """Should use provided session instead of creating new one."""
        from src.services.execution.service import get_workflow_for_execution

        workflow_id = str(uuid4())
        mock_session = AsyncMock()

        # Create mock workflow record
        mock_workflow = MagicMock()
        mock_workflow.name = "test_workflow"
        mock_workflow.function_name = "run"
        mock_workflow.path = "workflows/test.py"
        mock_workflow.code = "def run(): pass"
        mock_workflow.timeout_seconds = 300
        mock_workflow.time_saved = 5
        mock_workflow.value = 10.0
        mock_workflow.execution_mode = "async"
        mock_workflow.organization_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_workflow_for_execution(workflow_id, db=mock_session)

        assert result["name"] == "test_workflow"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_session_when_not_provided(self):
        """Should create own session when none provided."""
        from src.services.execution.service import get_workflow_for_execution

        workflow_id = str(uuid4())

        mock_workflow = MagicMock()
        mock_workflow.name = "test_workflow"
        mock_workflow.function_name = "run"
        mock_workflow.path = "workflows/test.py"
        mock_workflow.code = "def run(): pass"
        mock_workflow.timeout_seconds = 300
        mock_workflow.time_saved = 5
        mock_workflow.value = 10.0
        mock_workflow.execution_mode = "async"
        mock_workflow.organization_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("src.services.execution.service.get_session_factory", return_value=mock_factory):
            result = await get_workflow_for_execution(workflow_id)

        assert result["name"] == "test_workflow"
        mock_factory.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/execution/test_service.py::TestGetWorkflowForExecution -v`
Expected: FAIL with `TypeError: get_workflow_for_execution() got an unexpected keyword argument 'db'`

**Step 3: Refactor get_workflow_for_execution()**

Modify `api/src/services/execution/service.py` function (lines 124-181):

```python
async def get_workflow_for_execution(
    workflow_id: str,
    db: "AsyncSession | None" = None,
) -> dict[str, Any]:
    """
    Get workflow data needed for subprocess execution.

    Unlike get_workflow_metadata_only(), this includes the code and function_name
    so the worker subprocess can execute directly from database without file access.

    This is DB-only (no Redis caching) since code may be updated frequently
    and we want the latest version for each execution.

    Args:
        workflow_id: Workflow UUID from database
        db: Optional AsyncSession. If not provided, creates its own.

    Returns:
        Dict with keys:
        - name: Workflow display name
        - function_name: Python function name
        - path: Relative path (for __file__ injection)
        - code: Python source code (or None if not stored)
        - timeout_seconds: Execution timeout
        - time_saved: ROI time saved value
        - value: ROI value
        - execution_mode: sync or async

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist in database
    """
    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models import Workflow as WorkflowORM

    async def _fetch(session: "AsyncSession") -> dict[str, Any]:
        stmt = select(WorkflowORM).where(
            WorkflowORM.id == workflow_id,
            WorkflowORM.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        workflow_record = result.scalar_one_or_none()

        if not workflow_record:
            raise WorkflowNotFoundError(f"Workflow with ID '{workflow_id}' not found")

        logger.debug(f"Loaded workflow for execution: {workflow_id} -> {workflow_record.name}")

        return {
            "name": workflow_record.name,
            "function_name": workflow_record.function_name,
            "path": workflow_record.path,
            "code": workflow_record.code,  # May be None for legacy workflows
            "timeout_seconds": workflow_record.timeout_seconds or 1800,
            "time_saved": workflow_record.time_saved or 0,
            "value": float(workflow_record.value) if workflow_record.value else 0.0,
            "execution_mode": workflow_record.execution_mode or "async",
            "organization_id": str(workflow_record.organization_id) if workflow_record.organization_id else None,
        }

    if db is not None:
        return await _fetch(db)
    else:
        session_factory = get_session_factory()
        async with session_factory() as session:
            return await _fetch(session)
```

Add the AsyncSession import at the top of the file if not present:

```python
from sqlalchemy.ext.asyncio import AsyncSession
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/execution/test_service.py::TestGetWorkflowForExecution -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/execution/service.py api/tests/unit/services/execution/test_service.py
git commit -m "$(cat <<'EOF'
refactor(service): add optional db param to get_workflow_for_execution

Allow passing an existing session to avoid creating new connections.
Backwards compatible - creates own session if none provided.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Refactor ConfigResolver Methods to Accept Optional Session

**Files:**
- Modify: `api/src/core/config_resolver.py:156-359`
- Test: `api/tests/unit/core/test_config_resolver.py` (may need to create)

**Step 1: Write the failing test for get_organization()**

Create or add to `api/tests/unit/core/test_config_resolver.py`:

```python
"""Tests for ConfigResolver with optional session parameter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestConfigResolverWithSession:
    """Test ConfigResolver methods with optional session."""

    @pytest.fixture
    def resolver(self):
        """Create ConfigResolver instance."""
        from src.core.config_resolver import ConfigResolver
        return ConfigResolver()

    @pytest.mark.asyncio
    async def test_get_organization_uses_provided_session(self, resolver):
        """get_organization() should use provided session on cache miss."""
        org_id = str(uuid4())

        # Mock cache miss
        resolver._get_org_from_cache = AsyncMock(return_value=None)
        resolver._set_org_cache = AsyncMock()

        mock_org = MagicMock()
        mock_org.id = uuid4()
        mock_org.name = "Test Org"
        mock_org.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await resolver.get_organization(org_id, db=mock_session)

        assert result is not None
        assert result.name == "Test Org"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_config_for_scope_uses_provided_session(self, resolver):
        """load_config_for_scope() should use provided session on cache miss."""
        org_id = str(uuid4())

        # Mock cache miss
        resolver._get_config_from_cache = AsyncMock(return_value=None)
        resolver._set_config_cache = AsyncMock()

        mock_config = MagicMock()
        mock_config.key = "test_key"
        mock_config.value = {"value": "test_value"}
        mock_config.config_type = MagicMock(value="string")

        mock_result = MagicMock()
        mock_result.scalars.return_value = [mock_config]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await resolver.load_config_for_scope(f"ORG:{org_id}", db=mock_session)

        assert "test_key" in result
        mock_session.execute.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/core/test_config_resolver.py::TestConfigResolverWithSession -v`
Expected: FAIL with `TypeError: get_organization() got an unexpected keyword argument 'db'`

**Step 3: Refactor get_organization() method**

Modify `api/src/core/config_resolver.py` `get_organization()` method (lines 156-225):

```python
async def get_organization(
    self, org_id: str, db: "AsyncSession | None" = None
) -> "Organization | None":
    """
    Get organization by ID.

    Uses Redis cache first, falls back to PostgreSQL on miss.

    Args:
        org_id: Organization ID (UUID or "ORG:uuid" format)
        db: Optional AsyncSession. If not provided, creates its own.

    Returns:
        Organization object or None if not found
    """
    from uuid import UUID
    from src.sdk.context import Organization

    # Parse org_id - may be "ORG:uuid" or just "uuid"
    if org_id.startswith("ORG:"):
        org_uuid = org_id[4:]
    else:
        org_uuid = org_id

    try:
        UUID(org_uuid)  # Validate format
    except ValueError:
        logger.warning(f"Invalid organization ID format: {org_id}")
        return None

    # Try Redis cache first
    cached = await self._get_org_from_cache(org_uuid)
    if cached is not None:
        logger.debug(f"Org cache hit for org_id={org_uuid}")
        return Organization(
            id=cached["id"],
            name=cached["name"],
            is_active=cached["is_active"],
        )

    # Cache miss - load from PostgreSQL
    logger.debug(f"Org cache miss for org_id={org_uuid}, loading from DB")

    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models import Organization as OrgModel

    async def _fetch(session: "AsyncSession") -> "Organization | None":
        org_uuid_obj = UUID(org_uuid)
        result = await session.execute(
            select(OrgModel).where(OrgModel.id == org_uuid_obj)
        )
        org_entity = result.scalar_one_or_none()

        if not org_entity:
            logger.debug(f"Organization not found: {org_id}")
            return None

        # Populate cache for next time
        await self._set_org_cache(
            org_id=str(org_entity.id),
            name=org_entity.name,
            domain=org_entity.domain,
            is_active=org_entity.is_active,
        )

        return Organization(
            id=str(org_entity.id),
            name=org_entity.name,
            is_active=org_entity.is_active,
        )

    if db is not None:
        return await _fetch(db)
    else:
        session_factory = get_session_factory()
        async with session_factory() as session:
            return await _fetch(session)
```

**Step 4: Refactor load_config_for_scope() method**

Modify `api/src/core/config_resolver.py` `load_config_for_scope()` method (lines 280-359):

```python
async def load_config_for_scope(
    self, scope: str, db: "AsyncSession | None" = None
) -> dict[str, Any]:
    """
    Load all config for a scope (org_id or "GLOBAL").

    Uses Redis cache first, falls back to PostgreSQL on miss.
    Secrets are stored encrypted in cache and decrypted at get_config() time.

    Returns config as dict: {key: {"value": v, "type": t}, ...}

    Args:
        scope: "GLOBAL" or organization ID
        db: Optional AsyncSession. If not provided, creates its own.

    Returns:
        Configuration dictionary
    """
    from uuid import UUID

    # Normalize org_id for cache key
    if scope == "GLOBAL":
        org_id_for_cache = None
    elif scope.startswith("ORG:"):
        org_id_for_cache = scope[4:]
    else:
        org_id_for_cache = scope

    # Try Redis cache first
    cached = await self._get_config_from_cache(org_id_for_cache)
    if cached is not None:
        logger.debug(f"Config cache hit for scope={scope}")
        return cached

    # Cache miss - load from PostgreSQL
    logger.debug(f"Config cache miss for scope={scope}, loading from DB")

    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models import Config

    async def _fetch(session: "AsyncSession") -> dict[str, Any]:
        config_dict: dict[str, Any] = {}

        # For GLOBAL, get configs with no organization_id
        # For org scope, get global + org-specific configs (org overrides global)
        if scope == "GLOBAL":
            result = await session.execute(
                select(Config).where(Config.organization_id.is_(None))
            )
            for config in result.scalars():
                config_dict[config.key] = {
                    "value": config.value.get("value") if isinstance(config.value, dict) else config.value,
                    "type": config.config_type.value if config.config_type else "string",
                }
        else:
            try:
                org_uuid_obj = UUID(org_id_for_cache) if org_id_for_cache else None
            except ValueError:
                logger.warning(f"Invalid scope format: {scope}")
                return config_dict

            # Get global configs first
            global_result = await session.execute(
                select(Config).where(Config.organization_id.is_(None))
            )
            for config in global_result.scalars():
                config_dict[config.key] = {
                    "value": config.value.get("value") if isinstance(config.value, dict) else config.value,
                    "type": config.config_type.value if config.config_type else "string",
                }

            # Get org-specific configs (these override global)
            result = await session.execute(
                select(Config).where(Config.organization_id == org_uuid_obj)
            )
            for config in result.scalars():
                config_dict[config.key] = {
                    "value": config.value.get("value") if isinstance(config.value, dict) else config.value,
                    "type": config.config_type.value if config.config_type else "string",
                }

        # Populate cache for next time
        await self._set_config_cache(org_id_for_cache, config_dict)

        return config_dict

    if db is not None:
        return await _fetch(db)
    else:
        session_factory = get_session_factory()
        async with session_factory() as session:
            return await _fetch(session)
```

Add AsyncSession import at the top if not present:

```python
from sqlalchemy.ext.asyncio import AsyncSession
```

**Step 5: Run test to verify it passes**

Run: `./test.sh tests/unit/core/test_config_resolver.py::TestConfigResolverWithSession -v`
Expected: PASS

**Step 6: Commit**

```bash
git add api/src/core/config_resolver.py api/tests/unit/core/test_config_resolver.py
git commit -m "$(cat <<'EOF'
refactor(config): add optional db param to ConfigResolver methods

Allow passing an existing session to get_organization() and
load_config_for_scope() to avoid creating new connections.
Backwards compatible - creates own session if none provided.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement _sync_module_cache() Method

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py:97-113`
- Test: `api/tests/unit/jobs/consumers/test_workflow_execution_session.py`

**Step 1: Write the failing test**

Add to `api/tests/unit/jobs/consumers/test_workflow_execution_session.py`:

```python
class TestSyncModuleCache:
    """Test module cache sync logic."""

    @pytest.mark.asyncio
    async def test_sync_adds_missing_modules(self):
        """_sync_module_cache() should add modules missing from Redis."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - empty cache
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.exists = AsyncMock(return_value=False)

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            # Mock the module caching function
            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    mock_set.assert_called_once_with(
                        path="modules/test.py",
                        content="# test module",
                        content_hash="abc123",
                    )

    @pytest.mark.asyncio
    async def test_sync_skips_cached_modules(self):
        """_sync_module_cache() should not re-cache existing modules."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - module already cached
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"bifrost:module:modules/test.py"})
        mock_redis.exists = AsyncMock(return_value=True)  # Key exists

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_handles_expired_keys(self):
        """_sync_module_cache() should re-cache modules with expired content keys."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - key in index but content expired
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"bifrost:module:modules/test.py"})
        mock_redis.exists = AsyncMock(return_value=False)  # Content expired!

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    # Should re-cache because content key expired
                    mock_set.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py::TestSyncModuleCache -v`
Expected: FAIL with `AttributeError: 'WorkflowExecutionConsumer' object has no attribute '_sync_module_cache'`

**Step 3: Implement _sync_module_cache() method**

Replace `_ensure_module_cache()` method (lines 97-113) with `_sync_module_cache()`:

```python
async def _sync_module_cache(self, org_id: str | None = None) -> None:
    """
    Sync module cache from DB, adding any missing modules.

    Unlike the old _ensure_module_cache() which only checked if the index
    was empty, this method:
    1. Queries all modules from DB
    2. Checks each module's content key exists in Redis
    3. Re-caches any modules with missing/expired content

    Args:
        org_id: Organization ID (currently unused, modules are global)
    """
    from sqlalchemy import select
    from src.models.orm.workspace import WorkspaceFile
    from src.core.module_cache import set_module

    db = await self._get_db_session()
    redis_conn = await self._redis_client._get_redis()

    # Get all modules from DB
    stmt = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,  # noqa: E712
        WorkspaceFile.content.isnot(None),
    )
    result = await db.execute(stmt)
    db_modules = result.scalars().all()

    if not db_modules:
        logger.debug("No modules in database, cache sync complete")
        return

    # Get current cache index
    cached_keys = await redis_conn.smembers("bifrost:module:index")
    cached_keys = {k.decode() if isinstance(k, bytes) else k for k in cached_keys}

    # Check each DB module
    modules_added = 0
    for module in db_modules:
        cache_key = f"bifrost:module:{module.path}"

        # Check if content key exists (not just in index)
        key_exists = await redis_conn.exists(cache_key)

        if not key_exists:
            # Module missing or expired - re-cache it
            await set_module(
                path=module.path,
                content=module.content,
                content_hash=module.content_hash or "",
            )
            modules_added += 1
            logger.debug(f"Re-cached module: {module.path}")

    if modules_added > 0:
        logger.info(f"Module cache sync: added {modules_added} missing modules")
    else:
        logger.debug("Module cache sync: all modules present")
```

Add the import at the top of the file:

```python
from src.core.module_cache import set_module
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/jobs/consumers/test_workflow_execution_session.py::TestSyncModuleCache -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py api/tests/unit/jobs/consumers/test_workflow_execution_session.py
git commit -m "$(cat <<'EOF'
feat(consumer): replace _ensure_module_cache with _sync_module_cache

New method properly handles partial cache expiry by:
- Querying all modules from DB
- Checking each module's content key exists in Redis
- Re-caching only missing/expired modules

Fixes ImportError when module content expires but index entry remains.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update process_message() to Use Persistent Session

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py:470-760`
- Test: Integration test (existing tests should cover this)

**Step 1: Identify the changes needed in process_message()**

The key sections that need to pass the persistent session:

1. Line ~590: `get_workflow_for_execution(workflow_id)` → `get_workflow_for_execution(workflow_id, db=db)`
2. Line ~700: `await config_resolver.get_organization(org_id)` → `await config_resolver.get_organization(org_id, db=db)`
3. Line ~705: `await config_resolver.load_config_for_scope(org_id)` → `await config_resolver.load_config_for_scope(org_id, db=db)`
4. Line ~745: `await self._ensure_module_cache()` → `await self._sync_module_cache(org_id)`

**Step 2: Make the changes**

At the start of `process_message()`, get the persistent session:

```python
async def process_message(self, message: IncomingMessage) -> None:
    """Process a workflow execution message."""
    # Get persistent session for read operations
    db = await self._get_db_session()

    # ... existing code ...
```

Then update each call site. Find and replace:

```python
# Before:
workflow_data = await get_workflow_for_execution(workflow_id)

# After:
workflow_data = await get_workflow_for_execution(workflow_id, db=db)
```

```python
# Before:
org = await config_resolver.get_organization(org_id)

# After:
org = await config_resolver.get_organization(org_id, db=db)
```

```python
# Before:
config = await config_resolver.load_config_for_scope(org_id)

# After:
config = await config_resolver.load_config_for_scope(org_id, db=db)
```

```python
# Before:
await self._ensure_module_cache()

# After:
await self._sync_module_cache(org_id)
```

**Step 3: Run existing integration tests**

Run: `./test.sh tests/integration/engine/test_workflow_execution.py -v`
Expected: PASS (existing functionality preserved)

**Step 4: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py
git commit -m "$(cat <<'EOF'
feat(consumer): use persistent session for all read operations

Update process_message() to pass persistent DB session to:
- get_workflow_for_execution()
- ConfigResolver.get_organization()
- ConfigResolver.load_config_for_scope()
- _sync_module_cache()

Reduces connection churn from 6-7 connections per execution to 1.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final Verification and Cleanup

**Files:**
- All modified files
- Test files

**Step 1: Run full test suite**

Run: `./test.sh`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd api && pyright`
Expected: 0 errors

**Step 3: Run linting**

Run: `cd api && ruff check .`
Expected: No errors (or only pre-existing ones)

**Step 4: Manual verification**

Start the dev stack and verify module cache sync works:

```bash
./debug.sh
# In another terminal:
docker compose -f docker-compose.dev.yml logs -f worker
# Trigger a workflow execution and observe logs for:
# "Module cache sync: added X missing modules" or "all modules present"
```

**Step 5: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: final cleanup for module cache sync refactor

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements:

1. **Persistent DB session** in `WorkflowExecutionConsumer` with proper lifecycle management
2. **Health check and reconnection** for long-running consumer resilience
3. **Refactored functions** to accept optional `db` parameter:
   - `get_workflow_for_execution()`
   - `ConfigResolver.get_organization()`
   - `ConfigResolver.load_config_for_scope()`
4. **New `_sync_module_cache()`** that properly handles partial cache expiry
5. **Updated `process_message()`** to use persistent session for all reads

Connection overhead reduced from 6-7 sessions per execution to 1 persistent session.
