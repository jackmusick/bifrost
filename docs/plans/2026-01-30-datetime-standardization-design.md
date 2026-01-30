# Datetime Standardization Design

**Date:** 2026-01-30
**Status:** Draft

## Problem Statement

The codebase has inconsistent datetime handling that causes runtime errors and potential timing issues:

1. **ORM models** mix `DateTime()` (naive) and `DateTime(timezone=True)` (aware)
2. **Python code** mixes `datetime.utcnow()`, `datetime.now(timezone.utc)`, and `datetime.now()`
3. **Database columns** are mostly `timestamp with time zone` (73 columns) with some `timestamp without time zone` (37 columns)
4. **No tests** catch these mismatches

### Bug That Triggered This

MCP form creation failed with:
```
can't subtract offset-naive and offset-aware datetimes
```

The MCP tool used `datetime.now(timezone.utc)` (aware) but the ORM column default used `datetime.utcnow()` (naive), and asyncpg rejected the mismatch.

## Goals

- Standardize on **naive UTC** everywhere: `DateTime()` columns + `datetime.utcnow()`
- Migrate all 73 `timestamptz` database columns to `timestamp`
- Update all Python code to use `datetime.utcnow()` consistently
- Add tests to prevent regression

## Out of Scope

- Changing API response formats (they'll continue to use `.isoformat()`)
- Client-side timezone handling

## Decision: Naive UTC

We chose naive UTC over timezone-aware because:
- ~80% of Python code already uses `datetime.utcnow()`
- Simpler code, fewer imports
- Matches PostgreSQL `NOW()` default behavior
- All server-side times are conceptually UTC anyway

## Implementation Approach

### Phase 1: Python Code Updates

Update all datetime generation to use `datetime.utcnow()`:

**Patterns to replace:**
- `datetime.now(timezone.utc)` → `datetime.utcnow()`
- `datetime.now()` → `datetime.utcnow()` (scheduler fix - critical bug)
- `lambda: datetime.now(timezone.utc)` → `datetime.utcnow` (ORM defaults)

**Files requiring changes (~15-20):**
- `src/scheduler/main.py` - Uses `datetime.now()` (wrong timezone entirely)
- `src/services/mcp_server/tools/agents.py`
- `src/services/mcp_server/tools/forms.py` (already fixed)
- `src/services/mfa_service.py`
- `src/services/workflow_validation.py`
- `src/services/passkey_service.py`
- `src/services/execution/process_pool.py`
- `src/routers/health.py`
- Various other routers and services

**Cleanup:**
- Remove unused `from datetime import timezone` imports

### Phase 2: ORM Model Updates

Update all SQLAlchemy models to use consistent patterns:

**Change:**
```python
# Before
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
    server_default=text("NOW()")
)

# After
created_at: Mapped[datetime] = mapped_column(
    DateTime,
    default=datetime.utcnow,
    server_default=text("NOW()")
)
```

**Affected ORM files (~12):**
- `models/orm/events.py` - Uses `DateTime(timezone=True)`
- `models/orm/mfa.py` - Uses `DateTime(timezone=True)` with lambda defaults
- `models/orm/cli.py` - Uses `DateTime(timezone=True)`
- `models/orm/metrics.py` - Uses `DateTime(timezone=True)`
- `models/orm/users.py` - Mixed (line 38 uses timezone=True)
- `models/orm/agents.py`
- `models/orm/forms.py`
- `models/orm/executions.py`
- `models/orm/workflows.py`
- `models/orm/oauth.py`
- `models/orm/integrations.py`
- `models/orm/organizations.py`
- `models/orm/knowledge.py`
- `models/orm/audit.py`

### Phase 3: Database Migration

Create Alembic migration to convert 73 `timestamp with time zone` columns to `timestamp without time zone`.

**Migration approach:**
```python
def upgrade():
    # PostgreSQL automatically converts, preserving UTC value
    op.alter_column('forms', 'created_at',
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True))
    # ... repeat for all 73 columns

def downgrade():
    op.alter_column('forms', 'created_at',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime())
    # ... repeat for all 73 columns
```

**Tables requiring migration (73 columns across ~30 tables):**
- agents, agent_roles
- ai_model_pricing, ai_usage
- audit_logs
- cli_sessions
- configs
- conversations
- event_deliveries, event_sources, event_subscriptions, events
- execution_logs, executions
- form_roles, forms
- integration_mappings, integrations
- knowledge_storage_daily, knowledge_store
- messages
- mfa_recovery_codes
- oauth_providers, oauth_tokens
- organizations
- roles
- schedules
- system_logs
- trusted_devices
- user_mfa_methods, user_oauth_accounts, user_passkeys, user_roles, users
- webhook_sources
- workflows

### Phase 4: Testing

**New Test File: `tests/unit/test_datetime_consistency.py`**

Static analysis tests that run on every CI build:

```python
def test_no_timezone_aware_columns():
    """Assert no ORM model uses DateTime(timezone=True)"""
    # Scan all models/orm/*.py files
    # Fail if DateTime(timezone=True) found

def test_no_timezone_aware_datetime_calls():
    """Assert no code uses datetime.now(timezone.utc)"""
    # Scan all api/src/**/*.py files
    # Fail if pattern found

def test_no_bare_datetime_now():
    """Assert no code uses datetime.now() without timezone"""
    # Scan all api/src/**/*.py files
    # Allow datetime.now(timezone.utc) replacement: datetime.utcnow()
```

**New Test File: `tests/integration/test_datetime_roundtrip.py`**

Integration tests that verify datetimes survive database roundtrips:

```python
async def test_form_datetime_roundtrip():
    """Create form, retrieve it, verify datetime is naive UTC"""
    form = await create_test_form()
    retrieved = await get_form(form.id)
    assert retrieved.created_at.tzinfo is None
    assert retrieved.created_at < datetime.utcnow()

async def test_execution_datetime_roundtrip():
    """Create execution, retrieve it, verify datetime is naive UTC"""
    # Similar pattern
```

**Existing Test Updates:**
- Audit test fixtures using `datetime.now(timezone.utc)`
- Update to use `datetime.utcnow()`

## Rollout Order

1. **Python code first** - Safe even before DB migration
2. **ORM models second** - Changes defaults, doesn't break existing
3. **Database migration third** - Point of no return
4. **Tests last** - Lock in the standard

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Migration fails mid-way | Single transaction - all or nothing rollback |
| Existing data corrupted | PostgreSQL preserves UTC value when converting types |
| Scheduler breaks | Test scheduler job registration after changes |
| Missed a file | Static analysis tests will catch stragglers in CI |
| Production rollback needed | Alembic downgrade restores `timestamptz` columns |

## Estimated Scope

- ~12 ORM model files to update
- ~15-20 business logic files with datetime patterns
- 1 Alembic migration (73 column alterations)
- 2 new test files
- ~20 existing test file updates (fixture cleanup)

## Success Criteria

1. All tests pass
2. `grep -r "DateTime(timezone=True)" api/src/models/orm/` returns nothing
3. `grep -r "datetime.now(timezone.utc)" api/src/` returns nothing
4. `grep -r "datetime.now()" api/src/` returns nothing (except comments)
5. MCP form creation works without datetime errors
6. Scheduler jobs run at correct UTC times
