# Datetime Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize all datetime handling to naive UTC (`datetime.utcnow()`) across the entire codebase.

**Architecture:** Update Python code first (safe), then ORM models, then database migration. Add static analysis tests to enforce the standard going forward.

**Tech Stack:** Python datetime, SQLAlchemy ORM, Alembic migrations, pytest

---

## Task 1: Fix Critical Scheduler Bug

The scheduler uses `datetime.now()` (local time) instead of UTC. This is the highest priority fix.

**Files:**
- Modify: `api/src/scheduler/main.py:132,145,161,179,195,226`

**Step 1: Update scheduler datetime calls**

Replace all 6 occurrences of `datetime.now()` with `datetime.utcnow()`:

```python
# Line 132: Change
next_run_time=datetime.now(),  # Run immediately at startup
# To
next_run_time=datetime.utcnow(),  # Run immediately at startup

# Apply same change to lines 145, 161, 179, 195, 226
```

**Step 2: Verify scheduler still works**

```bash
docker compose -f docker-compose.dev.yml logs -f scheduler 2>&1 | head -50
```

Expected: Scheduler starts without errors, jobs are registered.

**Step 3: Commit**

```bash
git add api/src/scheduler/main.py
git commit -m "fix(scheduler): use utcnow instead of local time for job scheduling"
```

---

## Task 2: Update ORM Models - MFA

The MFA models have the most complex datetime patterns with lambdas.

**Files:**
- Modify: `api/src/models/orm/mfa.py`

**Step 1: Update imports**

Remove `timezone` from imports if present, ensure `datetime` is imported:

```python
from datetime import datetime
# Remove: from datetime import datetime, timezone
```

**Step 2: Update all DateTime columns**

Replace `DateTime(timezone=True)` with `DateTime()` and `lambda: datetime.now(timezone.utc)` with `datetime.utcnow`:

```python
# Lines 50-60 (UserMFAMethod)
last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
verified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
updated_at: Mapped[datetime] = mapped_column(
    DateTime,
    default=datetime.utcnow,
    server_default=text("NOW()"),
    onupdate=datetime.utcnow,
)

# Lines 80-83 (MFARecoveryCode)
used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)

# Lines 104-108 (TrustedDevice)
expires_at: Mapped[datetime] = mapped_column(DateTime)
last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)

# Lines 136-138 (UserOAuthAccount)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
last_login: Mapped[datetime | None] = mapped_column(DateTime, default=None)

# Lines 175-177 (UserPasskey)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
```

**Step 3: Commit**

```bash
git add api/src/models/orm/mfa.py
git commit -m "refactor(orm): standardize mfa.py to naive UTC datetimes"
```

---

## Task 3: Update ORM Models - Events

**Files:**
- Modify: `api/src/models/orm/events.py`

**Step 1: Update all DateTime columns**

Replace all `DateTime(timezone=True)` with `DateTime()`:

```python
# Lines 68-71 (Event)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
received_at: Mapped[datetime | None] = mapped_column(DateTime)

# Lines 131-138 (EventSource)
expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
updated_at: Mapped[datetime] = mapped_column(DateTime)

# Lines 190-193 (EventSubscription)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
updated_at: Mapped[datetime] = mapped_column(DateTime)

# Line 239 (WebhookSource)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)

# Line 264 (SystemLog)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)

# Lines 329-334 (EventDelivery)
next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
```

**Step 2: Commit**

```bash
git add api/src/models/orm/events.py
git commit -m "refactor(orm): standardize events.py to naive UTC datetimes"
```

---

## Task 4: Update ORM Models - CLI Sessions

**Files:**
- Modify: `api/src/models/orm/cli.py`

**Step 1: Update DateTime columns**

```python
# Lines 38-42
last_seen: Mapped[datetime | None] = mapped_column(DateTime, default=None)
created_at: Mapped[datetime] = mapped_column(
    DateTime, default=datetime.utcnow, server_default=text("NOW()")
)
expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
```

**Step 2: Commit**

```bash
git add api/src/models/orm/cli.py
git commit -m "refactor(orm): standardize cli.py to naive UTC datetimes"
```

---

## Task 5: Update ORM Models - Users and Metrics

**Files:**
- Modify: `api/src/models/orm/users.py:38`
- Modify: `api/src/models/orm/metrics.py:214`

**Step 1: Update users.py**

```python
# Line 38 - only this line needs change
mfa_enforced_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
```

**Step 2: Update metrics.py**

```python
# Line 214
refreshed_at: Mapped[datetime | None] = mapped_column(
    DateTime, server_default=text("NOW()")
)
```

**Step 3: Commit**

```bash
git add api/src/models/orm/users.py api/src/models/orm/metrics.py
git commit -m "refactor(orm): standardize users.py and metrics.py to naive UTC datetimes"
```

---

## Task 6: Update Business Logic - CLI Sessions Repository

**Files:**
- Modify: `api/src/repositories/cli_sessions.py`

**Step 1: Replace datetime.now(timezone.utc) with datetime.utcnow()**

Lines to update: 57, 136, 154, 155, 184, 202, 245, 257

```python
# Line 57
now = datetime.utcnow()

# Line 136
(CLISession.expires_at > datetime.utcnow())

# Lines 154-155
session.last_seen = datetime.utcnow()
session.expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)

# Line 184
session.expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)

# Line 202
session.expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)

# Line 245
threshold = datetime.utcnow() - timedelta(seconds=SESSION_CONNECTED_THRESHOLD_SECONDS)

# Line 257
now = datetime.utcnow()
```

**Step 2: Update imports**

```python
from datetime import datetime, timedelta
# Remove timezone from imports if present
```

**Step 3: Commit**

```bash
git add api/src/repositories/cli_sessions.py
git commit -m "refactor: standardize cli_sessions.py to datetime.utcnow()"
```

---

## Task 7: Update Business Logic - MFA Service

**Files:**
- Modify: `api/src/services/mfa_service.py`

**Step 1: Replace all datetime.now(timezone.utc) calls**

Lines: 53, 136, 177, 293, 357, 360, 369, 400, 404

```python
# Line 53 - special case, needs to handle comparison
age = datetime.utcnow() - existing.created_at

# Line 136
mfa_method.verified_at = datetime.utcnow()

# Line 177
mfa_method.last_used_at = datetime.utcnow()

# Line 293
recovery_code.used_at = datetime.utcnow()

# Lines 357, 360
existing.expires_at = datetime.utcnow() + timedelta(...)
existing.last_used_at = datetime.utcnow()

# Line 369
expires_at=datetime.utcnow() + timedelta(...)

# Line 400
if device.expires_at < datetime.utcnow():

# Line 404
device.last_used_at = datetime.utcnow()
```

**Step 2: Update imports**

```python
from datetime import datetime, timedelta
# Remove timezone import
```

**Step 3: Commit**

```bash
git add api/src/services/mfa_service.py
git commit -m "refactor: standardize mfa_service.py to datetime.utcnow()"
```

---

## Task 8: Update Business Logic - Core Modules

**Files:**
- Modify: `api/src/core/security.py` (lines 76, 78, 123, 125, 202, 381)
- Modify: `api/src/core/locks.py` (lines 113, 221)
- Modify: `api/src/core/pubsub.py` (lines 508, 549, 581, 899, 926, 962)
- Modify: `api/src/core/cache/data_provider_cache.py` (lines 118, 158)

**Step 1: Update security.py**

Replace all `datetime.now(timezone.utc)` with `datetime.utcnow()` at lines 76, 78, 123, 125, 202, 381.

**Step 2: Update locks.py**

Replace at lines 113, 221.

**Step 3: Update pubsub.py**

Replace at lines 508, 549, 581, 899, 926, 962.

**Step 4: Update data_provider_cache.py**

Replace at lines 118, 158.

**Step 5: Commit**

```bash
git add api/src/core/security.py api/src/core/locks.py api/src/core/pubsub.py api/src/core/cache/data_provider_cache.py
git commit -m "refactor: standardize core modules to datetime.utcnow()"
```

---

## Task 9: Update Business Logic - Services

**Files:**
- Modify: `api/src/services/notification_service.py` (lines 91, 163)
- Modify: `api/src/services/oauth_sso.py` (line 402)
- Modify: `api/src/services/passkey_service.py` (line 301)
- Modify: `api/src/services/workflow_validation.py` (line 92)
- Modify: `api/src/services/docs_indexer.py` (line 83)
- Modify: `api/src/services/webhooks/protocol.py` (line 362)
- Modify: `api/src/services/mcp_server/config_service.py` (lines 124, 198)

**Step 1: Update each file**

Replace `datetime.now(timezone.utc)` with `datetime.utcnow()` at specified lines.

**Step 2: Commit**

```bash
git add api/src/services/notification_service.py api/src/services/oauth_sso.py \
    api/src/services/passkey_service.py api/src/services/workflow_validation.py \
    api/src/services/docs_indexer.py api/src/services/webhooks/protocol.py \
    api/src/services/mcp_server/config_service.py
git commit -m "refactor: standardize service modules to datetime.utcnow()"
```

---

## Task 10: Update Business Logic - Execution Services

**Files:**
- Modify: `api/src/services/execution/process_pool.py` (lines 105, 149, 287, 557, 1433, 1491, 1533)
- Modify: `api/src/services/execution/simple_worker.py` (lines 340, 362, 390)
- Modify: `api/src/services/file_storage/indexers/app.py` (lines 135, 267, 429)

**Step 1: Update process_pool.py**

Replace all `datetime.now(timezone.utc)` with `datetime.utcnow()`.

**Step 2: Update simple_worker.py**

Replace at lines 340, 362, 390.

**Step 3: Update app.py indexer**

Note: Lines 135, 267, 429 use `.replace(tzinfo=None)` - simplify to just `datetime.utcnow()`.

**Step 4: Commit**

```bash
git add api/src/services/execution/process_pool.py api/src/services/execution/simple_worker.py \
    api/src/services/file_storage/indexers/app.py
git commit -m "refactor: standardize execution services to datetime.utcnow()"
```

---

## Task 11: Update Business Logic - Routers

**Files:**
- Modify: `api/src/routers/health.py` (lines 48, 99)
- Modify: `api/src/routers/executions.py` (lines 812, 855, 889)
- Modify: `api/src/routers/files.py` (lines 337, 386, 583)
- Modify: `api/src/routers/platform/workers.py` (lines 162, 440, 509)

**Step 1: Update each router**

Replace `datetime.now(timezone.utc)` with `datetime.utcnow()`.

Note: executions.py lines have `.replace(tzinfo=None)` - simplify to just `datetime.utcnow()`.

**Step 2: Commit**

```bash
git add api/src/routers/health.py api/src/routers/executions.py \
    api/src/routers/files.py api/src/routers/platform/workers.py
git commit -m "refactor: standardize routers to datetime.utcnow()"
```

---

## Task 12: Update Business Logic - Scheduler Jobs

**Files:**
- Modify: `api/src/jobs/schedulers/oauth_token_refresh.py` (lines 63, 90, 142)
- Modify: `api/src/jobs/schedulers/webhook_renewal.py` (lines 35, 123)
- Modify: `api/src/jobs/schedulers/event_cleanup.py` (lines 39, 62, 92, 186)

**Step 1: Update each scheduler job**

Replace `datetime.now(timezone.utc)` with `datetime.utcnow()`.

**Step 2: Commit**

```bash
git add api/src/jobs/schedulers/oauth_token_refresh.py \
    api/src/jobs/schedulers/webhook_renewal.py \
    api/src/jobs/schedulers/event_cleanup.py
git commit -m "refactor: standardize scheduler jobs to datetime.utcnow()"
```

---

## Task 13: Update Test Files

**Files:**
- Modify: `api/tests/fixtures/auth.py` (line 61)
- Modify: `api/tests/unit/core/test_locks.py` (9 occurrences)
- Modify: `api/tests/unit/execution/test_process_pool.py` (35+ occurrences)
- Modify: `api/tests/unit/repositories/test_execution_logs_list.py` (3 occurrences)
- Modify: `api/tests/unit/cache/test_data_provider_cache.py` (3 occurrences)
- Modify: `api/tests/unit/routers/test_oauth_refresh.py` (2 occurrences)
- Modify: `api/tests/unit/sdk/test_sdk_credentials.py` (3 occurrences)
- Modify: `api/tests/unit/services/test_notification_service.py` (12 occurrences)
- Modify: `api/tests/integration/platform/test_deactivation_protection.py` (line 433)
- Modify: `api/tests/fixtures/large_module_generator.py` (line 98)

**Step 1: Update all test files**

Replace `datetime.now(timezone.utc)` with `datetime.utcnow()` in all files.

For files using `.replace(tzinfo=None)`, simplify to just `datetime.utcnow()`.

**Step 2: Run tests to verify**

```bash
./test.sh tests/unit/
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add api/tests/
git commit -m "refactor: standardize test files to datetime.utcnow()"
```

---

## Task 14: Create Database Migration

**Files:**
- Create: `api/alembic/versions/XXXX_standardize_datetime_columns.py`

**Step 1: Generate migration**

```bash
cd /home/jack/GitHub/bifrost/api && alembic revision -m "standardize_datetime_columns_to_naive_utc"
```

**Step 2: Edit migration file**

```python
"""standardize_datetime_columns_to_naive_utc

Revision ID: <generated>
Revises: <previous>
Create Date: 2026-01-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '<generated>'
down_revision = '<previous>'
branch_labels = None
depends_on = None

# All columns that need to be converted from timestamptz to timestamp
COLUMNS_TO_MIGRATE = [
    ("agent_roles", "assigned_at"),
    ("agents", "created_at"),
    ("agents", "updated_at"),
    ("ai_model_pricing", "created_at"),
    ("ai_model_pricing", "updated_at"),
    ("ai_usage", "timestamp"),
    ("audit_logs", "created_at"),
    ("cli_sessions", "created_at"),
    ("cli_sessions", "expires_at"),
    ("cli_sessions", "last_seen"),
    ("configs", "created_at"),
    ("configs", "updated_at"),
    ("conversations", "created_at"),
    ("conversations", "updated_at"),
    ("event_deliveries", "completed_at"),
    ("event_deliveries", "created_at"),
    ("event_deliveries", "next_retry_at"),
    ("event_sources", "created_at"),
    ("event_sources", "updated_at"),
    ("event_subscriptions", "created_at"),
    ("event_subscriptions", "updated_at"),
    ("events", "created_at"),
    ("events", "received_at"),
    ("execution_logs", "timestamp"),
    ("executions", "completed_at"),
    ("executions", "created_at"),
    ("executions", "started_at"),
    ("form_roles", "assigned_at"),
    ("forms", "created_at"),
    ("forms", "last_seen_at"),
    ("forms", "updated_at"),
    ("integration_mappings", "created_at"),
    ("integration_mappings", "updated_at"),
    ("integrations", "created_at"),
    ("integrations", "updated_at"),
    ("knowledge_storage_daily", "created_at"),
    ("knowledge_store", "created_at"),
    ("knowledge_store", "updated_at"),
    ("messages", "created_at"),
    ("mfa_recovery_codes", "created_at"),
    ("mfa_recovery_codes", "used_at"),
    ("oauth_providers", "created_at"),
    ("oauth_providers", "last_token_refresh"),
    ("oauth_providers", "updated_at"),
    ("oauth_tokens", "created_at"),
    ("oauth_tokens", "expires_at"),
    ("oauth_tokens", "updated_at"),
    ("organizations", "created_at"),
    ("organizations", "updated_at"),
    ("roles", "created_at"),
    ("roles", "updated_at"),
    ("schedules", "created_at"),
    ("schedules", "last_run_at"),
    ("schedules", "updated_at"),
    ("system_logs", "timestamp"),
    ("trusted_devices", "created_at"),
    ("trusted_devices", "expires_at"),
    ("trusted_devices", "last_used_at"),
    ("user_mfa_methods", "created_at"),
    ("user_mfa_methods", "last_used_at"),
    ("user_mfa_methods", "updated_at"),
    ("user_mfa_methods", "verified_at"),
    ("user_oauth_accounts", "created_at"),
    ("user_oauth_accounts", "last_login"),
    ("user_passkeys", "created_at"),
    ("user_passkeys", "last_used_at"),
    ("user_roles", "assigned_at"),
    ("users", "created_at"),
    ("users", "last_login"),
    ("users", "mfa_enforced_at"),
    ("users", "updated_at"),
    ("webhook_sources", "created_at"),
    ("webhook_sources", "expires_at"),
    ("webhook_sources", "updated_at"),
    ("workflows", "api_key_created_at"),
    ("workflows", "api_key_expires_at"),
    ("workflows", "api_key_last_used_at"),
    ("workflows", "created_at"),
    ("workflows", "last_seen_at"),
    ("workflows", "updated_at"),
]


def upgrade():
    for table, column in COLUMNS_TO_MIGRATE:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,  # Most allow NULL
        )


def downgrade():
    for table, column in COLUMNS_TO_MIGRATE:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=True,
        )
```

**Step 3: Test migration locally**

```bash
docker compose -f docker-compose.dev.yml restart api
```

Expected: API starts without errors, migration applied.

**Step 4: Verify columns changed**

```bash
docker exec bifrost-postgres psql -U bifrost -d bifrost -c "
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE data_type = 'timestamp with time zone'
AND table_schema = 'public'
LIMIT 5;
"
```

Expected: No results (all columns converted).

**Step 5: Commit**

```bash
git add api/alembic/versions/
git commit -m "migration: convert all timestamp columns to naive UTC"
```

---

## Task 15: Add Static Analysis Tests

**Files:**
- Create: `api/tests/unit/test_datetime_consistency.py`

**Step 1: Create test file**

```python
"""
Static analysis tests to enforce datetime standardization.

These tests scan the codebase to ensure no timezone-aware datetime patterns
are reintroduced after standardization.
"""
import ast
import os
from pathlib import Path

import pytest

API_SRC_DIR = Path(__file__).parent.parent.parent / "src"
API_MODELS_ORM_DIR = API_SRC_DIR / "models" / "orm"


def get_python_files(directory: Path) -> list[Path]:
    """Get all Python files in a directory recursively."""
    return list(directory.rglob("*.py"))


class TestDatetimeConsistency:
    """Ensure datetime patterns are consistent across the codebase."""

    def test_no_timezone_aware_columns_in_orm(self):
        """ORM models must not use DateTime(timezone=True)."""
        violations = []

        for py_file in get_python_files(API_MODELS_ORM_DIR):
            content = py_file.read_text()
            if "DateTime(timezone=True)" in content:
                # Find line numbers
                for i, line in enumerate(content.split("\n"), 1):
                    if "DateTime(timezone=True)" in line:
                        violations.append(f"{py_file.name}:{i}")

        assert not violations, (
            f"Found DateTime(timezone=True) in ORM models. "
            f"Use DateTime() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_datetime_now_with_timezone_utc(self):
        """Code must not use datetime.now(timezone.utc)."""
        violations = []

        for py_file in get_python_files(API_SRC_DIR):
            content = py_file.read_text()
            if "datetime.now(timezone.utc)" in content:
                for i, line in enumerate(content.split("\n"), 1):
                    if "datetime.now(timezone.utc)" in line:
                        violations.append(f"{py_file.relative_to(API_SRC_DIR)}:{i}")

        assert not violations, (
            f"Found datetime.now(timezone.utc) in source code. "
            f"Use datetime.utcnow() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_bare_datetime_now(self):
        """Code must not use datetime.now() without timezone (local time)."""
        violations = []

        for py_file in get_python_files(API_SRC_DIR):
            content = py_file.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Match datetime.now() but not datetime.now(timezone.utc)
                if "datetime.now()" in line and "timezone" not in line:
                    # Skip comments
                    stripped = line.strip()
                    if not stripped.startswith("#"):
                        violations.append(f"{py_file.relative_to(API_SRC_DIR)}:{i}")

        assert not violations, (
            f"Found datetime.now() (local time) in source code. "
            f"Use datetime.utcnow() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_lambda_datetime_defaults_in_orm(self):
        """ORM models must not use lambda datetime defaults."""
        violations = []

        for py_file in get_python_files(API_MODELS_ORM_DIR):
            content = py_file.read_text()
            if "default=lambda:" in content and "datetime" in content:
                for i, line in enumerate(content.split("\n"), 1):
                    if "default=lambda:" in line and "datetime" in line:
                        violations.append(f"{py_file.name}:{i}")

        assert not violations, (
            f"Found lambda datetime defaults in ORM models. "
            f"Use default=datetime.utcnow instead.\nViolations:\n" + "\n".join(violations)
        )
```

**Step 2: Run the tests (should pass after all previous tasks)**

```bash
./test.sh tests/unit/test_datetime_consistency.py -v
```

Expected: All 4 tests pass.

**Step 3: Commit**

```bash
git add api/tests/unit/test_datetime_consistency.py
git commit -m "test: add static analysis tests for datetime consistency"
```

---

## Task 16: Add Integration Test for Datetime Roundtrip

**Files:**
- Create: `api/tests/integration/test_datetime_roundtrip.py`

**Step 1: Create test file**

```python
"""
Integration tests to verify datetimes survive database roundtrips as naive UTC.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.forms import Form
from src.models.orm.users import User


@pytest.mark.asyncio
async def test_form_datetime_roundtrip(db_session: AsyncSession):
    """Form created_at should be naive UTC after roundtrip."""
    # Create a form
    form = Form(
        id=uuid4(),
        name="Test Form",
        created_by="test@example.com",
    )
    db_session.add(form)
    await db_session.commit()

    # Retrieve it
    result = await db_session.execute(select(Form).where(Form.id == form.id))
    retrieved = result.scalar_one()

    # Verify datetime is naive (no timezone info)
    assert retrieved.created_at is not None
    assert retrieved.created_at.tzinfo is None, "created_at should be naive UTC"

    # Verify it's recent (within last minute)
    now = datetime.utcnow()
    assert now - retrieved.created_at < timedelta(minutes=1), "created_at should be recent"


@pytest.mark.asyncio
async def test_user_datetime_roundtrip(db_session: AsyncSession):
    """User timestamps should be naive UTC after roundtrip."""
    # Create a user
    user = User(
        id=uuid4(),
        email=f"test-{uuid4()}@example.com",
        name="Test User",
    )
    db_session.add(user)
    await db_session.commit()

    # Retrieve it
    result = await db_session.execute(select(User).where(User.id == user.id))
    retrieved = result.scalar_one()

    # Verify datetimes are naive
    assert retrieved.created_at is not None
    assert retrieved.created_at.tzinfo is None, "created_at should be naive UTC"

    if retrieved.updated_at:
        assert retrieved.updated_at.tzinfo is None, "updated_at should be naive UTC"


@pytest.mark.asyncio
async def test_datetime_comparison_works(db_session: AsyncSession):
    """Naive UTC datetimes should be comparable without errors."""
    form1 = Form(
        id=uuid4(),
        name="Form 1",
        created_by="test@example.com",
    )
    db_session.add(form1)
    await db_session.flush()

    form2 = Form(
        id=uuid4(),
        name="Form 2",
        created_by="test@example.com",
    )
    db_session.add(form2)
    await db_session.commit()

    # Retrieve both
    result = await db_session.execute(select(Form).where(Form.id.in_([form1.id, form2.id])))
    forms = result.scalars().all()

    # Comparison should work without TypeError
    sorted_forms = sorted(forms, key=lambda f: f.created_at)
    assert len(sorted_forms) == 2
```

**Step 2: Run the tests**

```bash
./test.sh tests/integration/test_datetime_roundtrip.py -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add api/tests/integration/test_datetime_roundtrip.py
git commit -m "test: add integration tests for datetime roundtrip"
```

---

## Task 17: Final Verification

**Step 1: Run full test suite**

```bash
./test.sh
```

Expected: All tests pass.

**Step 2: Verify no timezone patterns remain**

```bash
grep -r "DateTime(timezone=True)" api/src/models/orm/ || echo "OK: No timezone columns"
grep -r "datetime.now(timezone.utc)" api/src/ || echo "OK: No timezone.utc calls"
grep -r "datetime.now()" api/src/ | grep -v "utcnow" | grep -v "#" || echo "OK: No bare datetime.now()"
```

Expected: All three checks return "OK".

**Step 3: Verify database columns**

```bash
docker exec bifrost-postgres psql -U bifrost -d bifrost -c "
SELECT COUNT(*) as remaining_timestamptz
FROM information_schema.columns
WHERE data_type = 'timestamp with time zone'
AND table_schema = 'public';
"
```

Expected: `remaining_timestamptz = 0`

**Step 4: Test MCP form creation (original bug)**

```bash
# Use the MCP tool to create a form - should work now
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: datetime standardization complete - all naive UTC"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Fix scheduler bug | 1 |
| 2-5 | Update ORM models | 5 |
| 6-12 | Update business logic | ~20 |
| 13 | Update test files | ~10 |
| 14 | Database migration | 1 |
| 15-16 | Add consistency tests | 2 |
| 17 | Final verification | 0 |

**Total: ~40 files, 17 tasks, 1 migration**
