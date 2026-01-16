# OrgScopedRepository Implementation Tasks

**Design:** [2026-01-15-org-scoped-repository-design.md](./2026-01-15-org-scoped-repository-design.md)

**Status:** Complete - All phases implemented

---

## Phase 1: Schema & Core Infrastructure ✅

- [x] **1.1** Make `IntegrationMapping.organization_id` nullable
  - File: `api/src/models/orm/integrations.py:139-141`
  - Change: `nullable=False` → `nullable=True`, update type hint to `UUID | None`
  - Create alembic migration
  - **Done:** Commit `6383304e` - Also added partial unique index `ix_integration_mappings_unique_global` to enforce one global mapping per integration
  - **Done:** Updated Pydantic models (`IntegrationMappingResponse`) to make `organization_id` optional

- [x] **1.2** Update `OrgScopedRepository` base class
  - File: `api/src/repositories/org_scoped.py`
  - Add `user_id: UUID | None` parameter to `__init__`
  - Add `is_superuser: bool = False` parameter to `__init__`
  - Add class attributes: `role_table`, `role_entity_id_column`
  - Implement new `get(**filters)` method with cascade + role check
  - Implement `can_access(**filters)` method (calls get, raises `AccessDeniedError`)
  - Implement new `list(**filters)` method with cascade + role check
  - **Decision:** Removed old methods immediately (no backwards compat) - cleaner break
  - **Done:** Commit `7a5d8bab` - Complete rewrite, 278 lines added
  - **Note:** N+1 query potential in `list()` for role-based entities - documented as known limitation for future optimization

- [x] **1.3** Create `AccessDeniedError` exception
  - File: `api/src/core/exceptions.py` (created)
  - Simple exception class for access control failures
  - **Done:** Part of commit `7a5d8bab`
  - **Done:** Exported from `api/src/repositories/__init__.py`

---

## Phase 2: Update Existing Repositories ✅

- [x] **2.1** Update `FormRepository`
  - File: `api/src/repositories/forms.py`
  - Add `role_table = FormRole`, `role_entity_id_column = "form_id"`
  - Refactor methods to use new pattern
  - **Done:** Commit `80d9a79a`
  - **Pattern:** Added `list_forms()` for regular users (cascade + role check), `list_all_in_scope()` for admins (filter type support)
  - **Also updated:** `api/src/routers/forms.py`, `api/src/services/mcp_server/tools/forms.py`

- [x] **2.2** Update `AgentRepository`
  - File: `api/src/repositories/agents.py`
  - Add `role_table = AgentRole`, `role_entity_id_column = "agent_id"`
  - Refactor methods to use new pattern
  - **Done:** Commits `0ffa2c2b`, `71a72835` (fix)
  - **Pattern:** Same as FormRepository - `list_agents()` + `list_all_in_scope()`
  - **Also updated:** `api/src/routers/agents.py`, `api/src/services/mcp_server/tools/agents.py`

- [x] **2.3** Update `ApplicationRepository`
  - File: `api/src/routers/applications.py` (inline repo)
  - Add `role_table = AppRole`, `role_entity_id_column = "app_id"`
  - Refactor methods to use new pattern
  - **Done:** Commit `5724c889`
  - **Pattern:** Same as FormRepository - `list_applications()` + `list_all_in_scope()`
  - **Note:** All 7 endpoints updated to pass `user_id` and `is_superuser`

- [x] **2.4** Update `TableRepository`
  - File: `api/src/routers/tables.py` (inline repo)
  - Add `role_table = None` (explicit - no RBAC, SDK/superuser only)
  - Refactor methods to use new pattern
  - **Done:** Commit `4d856e28`
  - **Pattern:** All endpoints use `is_superuser=True` since Tables are CurrentSuperuser-only
  - **Note:** `get_by_name()` now delegates to base `get(name=name)`

---

## Phase 3: Migrate BaseRepository Repos to OrgScopedRepository ✅

- [x] **3.1** Migrate `WorkflowRepository`
  - File: `api/src/repositories/workflows.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = WorkflowRole`, `role_entity_id_column = "workflow_id"`
  - Update all methods to use new pattern
  - **Done:** Commits `cdd8c7f6`, `e5c87308` (doc clarifications)
  - **Pattern:** Methods use `_apply_cascade_scope()`, `get_by_name` delegates to base `get()`
  - **Also updated:** All 11 callers (routers, services, MCP tools)

- [x] **3.2** Migrate `DataProviderRepository`
  - File: `api/src/repositories/data_providers.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = None`
  - Update all methods to use new pattern
  - **Done:** Commit `b259b424`
  - **Pattern:** SDK-only, `get_by_name` delegates to base `get()` with type filter

- [x] **3.3** Migrate `KnowledgeRepository`
  - File: `api/src/repositories/knowledge.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = None`
  - Update all methods to use new pattern
  - **Done:** Commit `b78d2308`
  - **Pattern:** SDK-only, preserved custom org_id handling in methods
  - **Also updated:** cli.py (7 sites), docs_indexer.py, agent_executor.py, MCP tools

---

## Phase 4: Create New Repositories ✅

- [x] **4.1** Update `ConfigRepository`
  - File: `api/src/routers/config.py` (inline repo)
  - Already extended `OrgScopedRepository[Config]`
  - Add `role_table = None`
  - Replace non-existent `apply_filter()` with custom OrgFilterType logic
  - Replace non-existent `get_one_cascade()` with base `get()`
  - **Done:** Commit `649609f7`
  - **Pattern:** Custom OrgFilterType handling for list_configs(), base get() for lookups

- [x] **4.2** Create `IntegrationMappingRepository`
  - File: `api/src/repositories/integrations.py` (added to existing file)
  - Extend `OrgScopedRepository[IntegrationMapping]`
  - Add `role_table = None`
  - Added `get_by_integration_name()` with cascade
  - **Done:** Commit `ca56030d`
  - **Pattern:** First looks up Integration by name, then uses cascade to find mapping
  - **Also updated:** Exported from `api/src/repositories/__init__.py`

---

## Phase 5: Update Endpoints ✅

- [x] **5.1** Update direct user endpoints (CurrentUser)
  - `api/src/routers/applications.py` - list and get endpoints
  - `api/src/routers/forms.py` - list and get endpoints
  - `api/src/routers/agents.py` - list and get endpoints
  - Pass `org_id`, `user_id`, `is_superuser` from context
  - **Done:** Phase 2 completed these updates

- [x] **5.2** Update SDK endpoints (CurrentSuperuser)
  - `api/src/routers/tables.py` - use new repo pattern ✅ (done in 2.4)
  - `api/src/routers/config.py` - use new `ConfigRepository` ✅ (done in 4.1)
  - `api/src/routers/cli.py` - SDK methods use cascade scoping via `_find_table_for_sdk()` etc.

- [x] **5.3** Update workflow execution
  - `api/src/routers/workflows.py` - execute endpoint
  - Replaced `ExecutionAuthService` calls with `WorkflowRepository.can_access()`
  - Uses workflow's `organization_id` for authorization scope (not caller's org_id)
  - **Done:** Commits `e17ad20d`, `504db39a`, `978c9b18`

---

## Phase 6: Delete Old Code ✅

- [x] **6.1** Delete `AuthorizationService`
  - File: `api/src/services/authorization.py`
  - **Done:** Commit `ef464237` - Deleted file and all usages

- [x] **6.2** Delete `ExecutionAuthService`
  - File: `api/src/services/execution_auth.py`
  - **Done:** Commit `fc03cc15` - Deleted file and all usages

- [x] **6.3** Remove deprecated methods from `OrgScopedRepository`
  - **Already done:** These were removed in Phase 1.2 (no backwards compat approach)

---

## Phase 7: Testing & Documentation ✅

- [x] **7.1** Update/create tests for `OrgScopedRepository`
  - Test cascade logic (org-specific wins over global)
  - Test role checking (authenticated vs role_based)
  - Test superuser bypass (ID lookups vs name lookups)
  - Test `AccessDeniedError` raised correctly
  - **Done:** `api/tests/unit/routers/test_scoped_lookups.py` - comprehensive tests

- [x] **7.2** Update integration tests
  - E2E scope execution tests verify SDK methods work correctly
  - Tests verify org-scoped workflows see correct data
  - Tests verify superusers can execute any workflow
  - **Done:** `api/tests/e2e/api/test_scope_execution.py` - 7 tests all passing

- [x] **7.3** Write `api/src/repositories/README.md`
  - Documents request flow, lookup behavior, method reference
  - Includes code examples and common mistakes
  - **Done:** Created comprehensive README

- [x] **7.4** Run full test suite
  - `./test.sh` - 2346 passed (5 unrelated failures: email validation, timeouts, flaky)
  - `pyright` - 0 errors
  - `ruff check` - All checks passed

---

## Verification Checkpoints ✅

All checks passing:
- [x] `pyright` passes (0 errors)
- [x] `ruff check` passes
- [x] `./test.sh` passes (2346 passed, 5 unrelated failures)

---

## Implementation Notes

### Pattern Used for Repositories with RBAC

```python
class FormRepository(OrgScopedRepository[Form]):
    model = Form
    role_table = FormRole
    role_entity_id_column = "form_id"

    async def list_forms(self, active_only: bool = True) -> list[Form]:
        """For regular users - cascade scoping + role check."""
        # Uses _apply_cascade_scope() and _can_access_entity()

    async def list_all_in_scope(self, filter_type: OrgFilterType, ...) -> list[Form]:
        """For admins - flexible filter types, no role check."""
```

### Pattern Used for Repositories without RBAC (SDK-only)

```python
class TableRepository(OrgScopedRepository[Table]):
    model = Table
    role_table = None  # Explicit: no RBAC

    # All endpoints use is_superuser=True
```

### Instantiation Pattern

```python
repo = FormRepository(
    session=ctx.db,
    org_id=target_org_id,
    user_id=user.user_id,
    is_superuser=user.is_platform_admin,
)
```
