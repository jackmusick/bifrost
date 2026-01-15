# OrgScopedRepository Implementation Tasks

**Design:** [2026-01-15-org-scoped-repository-design.md](./2026-01-15-org-scoped-repository-design.md)

---

## Phase 1: Schema & Core Infrastructure

- [ ] **1.1** Make `IntegrationMapping.organization_id` nullable
  - File: `api/src/models/orm/integrations.py:139-141`
  - Change: `nullable=False` → `nullable=True`, update type hint to `UUID | None`
  - Create alembic migration

- [ ] **1.2** Update `OrgScopedRepository` base class
  - File: `api/src/repositories/org_scoped.py`
  - Add `user_id: UUID | None` parameter to `__init__`
  - Add `is_superuser: bool = False` parameter to `__init__`
  - Add class attributes: `role_table`, `role_entity_id_column`
  - Implement new `get(**filters)` method with cascade + role check
  - Implement `can_access(**filters)` method (calls get, raises `AccessDeniedError`)
  - Implement new `list(**filters)` method with cascade + role check
  - Keep old methods (`filter_cascade`, etc.) temporarily for backwards compat during migration

- [ ] **1.3** Create `AccessDeniedError` exception
  - File: `api/src/core/exceptions.py` (create if doesn't exist)
  - Simple exception class for access control failures

---

## Phase 2: Update Existing Repositories

- [ ] **2.1** Update `FormRepository`
  - File: `api/src/repositories/forms.py`
  - Add `role_table = FormRole`, `role_entity_id_column = "form_id"`
  - Update `__init__` to accept new params
  - Refactor methods to use new `get()`/`list()` pattern

- [ ] **2.2** Update `AgentRepository`
  - File: `api/src/repositories/agents.py`
  - Add `role_table = AgentRole`, `role_entity_id_column = "agent_id"`
  - Update `__init__` to accept new params
  - Refactor methods to use new `get()`/`list()` pattern

- [ ] **2.3** Update `ApplicationRepository`
  - File: `api/src/routers/applications.py` (inline repo)
  - Add `role_table = AppRole`, `role_entity_id_column = "app_id"`
  - Update `__init__` to accept new params
  - Refactor methods to use new `get()`/`list()` pattern

- [ ] **2.4** Update `TableRepository`
  - File: `api/src/routers/tables.py` (inline repo)
  - Add `role_table = None` (explicit)
  - Update `__init__` to accept new params
  - Refactor methods to use new `get()`/`list()` pattern

---

## Phase 3: Migrate BaseRepository Repos to OrgScopedRepository

- [ ] **3.1** Migrate `WorkflowRepository`
  - File: `api/src/repositories/workflows.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = WorkflowRole`, `role_entity_id_column = "workflow_id"`
  - Update all methods to use new pattern

- [ ] **3.2** Migrate `DataProviderRepository`
  - File: `api/src/repositories/data_providers.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = None`
  - Update all methods to use new pattern

- [ ] **3.3** Migrate `KnowledgeRepository`
  - File: `api/src/repositories/knowledge.py`
  - Change base class: `BaseRepository` → `OrgScopedRepository`
  - Add `role_table = None`
  - Update all methods to use new pattern

---

## Phase 4: Create New Repositories

- [ ] **4.1** Create `ConfigRepository`
  - Extract from inline code in `api/src/routers/config.py`
  - Extend `OrgScopedRepository[Config]`
  - Add `role_table = None`
  - Implement `get(key=...)` with cascade

- [ ] **4.2** Create `IntegrationMappingRepository`
  - New file: `api/src/repositories/integration_mappings.py`
  - Extend `OrgScopedRepository[IntegrationMapping]`
  - Add `role_table = None`
  - Implement `get(integration_name=...)` with cascade

---

## Phase 5: Update Endpoints

- [ ] **5.1** Update direct user endpoints (CurrentUser)
  - `api/src/routers/applications.py` - list and get endpoints
  - `api/src/routers/forms.py` - list and get endpoints (if exists)
  - `api/src/routers/agents.py` - list and get endpoints (if exists)
  - Pass `org_id`, `user_id`, `is_superuser` from context

- [ ] **5.2** Update SDK endpoints (CurrentSuperuser)
  - `api/src/routers/tables.py` - use new repo pattern
  - `api/src/routers/config.py` - use new `ConfigRepository`
  - `api/src/routers/cli.py` - update SDK methods to use new repos

- [ ] **5.3** Update workflow execution
  - `api/src/routers/workflows.py` - execute endpoint
  - Replace `ExecutionAuthService` calls with `WorkflowRepository.can_access()`
  - Pass original user's `org_id`, `user_id`, `is_superuser=False`

---

## Phase 6: Delete Old Code

- [ ] **6.1** Delete `AuthorizationService`
  - File: `api/src/services/authorization.py`
  - Remove all imports/usages first (should be none after Phase 5)

- [ ] **6.2** Delete `ExecutionAuthService`
  - File: `api/src/services/execution_auth.py`
  - Remove all imports/usages first (should be none after Phase 5)

- [ ] **6.3** Remove deprecated methods from `OrgScopedRepository`
  - Remove `filter_cascade()`, `filter_strict()`, `filter_org_only()`, `filter_global_only()`
  - Remove `apply_filter()`, `get_one_cascade()`
  - These should all be replaced by new `get()`/`list()` methods

---

## Phase 7: Testing & Documentation

- [ ] **7.1** Update/create tests for `OrgScopedRepository`
  - Test cascade logic (org-specific wins over global)
  - Test role checking (authenticated vs role_based)
  - Test superuser bypass
  - Test `AccessDeniedError` raised correctly

- [ ] **7.2** Update integration tests
  - Ensure SDK methods still work
  - Ensure direct user endpoints respect RBAC

- [ ] **7.3** Write `api/src/repositories/README.md`
  - Copy documentation section from design doc
  - Add code examples

- [ ] **7.4** Run full test suite
  - `./test.sh`
  - `pyright`
  - `ruff check`

---

## Verification Checkpoints

After each phase, verify:
- [ ] `pyright` passes
- [ ] `ruff check` passes
- [ ] `./test.sh` passes (or document expected failures for incomplete phases)
