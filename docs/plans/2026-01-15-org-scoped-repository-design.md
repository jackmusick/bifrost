# OrgScopedRepository Standardization Design

**Date:** 2026-01-15
**Status:** Draft - Pending Approval

---

## 1. Problem Statement & Goals

### Problem

We have inconsistent access control patterns scattered across the codebase:

1. **`OrgScopedRepository`** - Exists but only used by 2 repositories (AgentRepository, FormRepository)
2. **`AuthorizationService`** - Barely used (3 call sites, all for `can_access_app()`)
3. **`ExecutionAuthService`** - Separate service duplicating similar logic for workflow execution
4. **Manual patterns everywhere** - Many repositories extend `BaseRepository` and do ad-hoc org filtering

This creates:
- Cognitive load ("is this endpoint doing scoping correctly?")
- Risk of access control bugs
- No single source of truth for "can this user access this entity"

### Goals

1. **Single pattern for all org-scoped data access** - `OrgScopedRepository` becomes the standard
2. **Unified access control** - Scoping + role checks happen in one place
3. **Clear separation of concerns**:
   - **SDK/Execution endpoints** (CurrentSuperuser) - System calls on behalf of user, passes user context
   - **Direct user endpoints** (CurrentUser) - User calls directly, limited to forms/apps/agents
4. **No backwards compatibility shims** - Clean migration, remove old patterns entirely

### Non-Goals

- Exposing all endpoints to direct user access (most stay CurrentSuperuser only)
- Caching or performance optimization (can add later if needed)
- Changes to the role assignment system itself

---

## 2. Technical Design

### OrgScopedRepository Interface

```python
class OrgScopedRepository(Generic[ModelT]):
    """
    Base repository for all org-scoped entities.
    Handles cascade scoping + role-based access control.
    """

    model: type[ModelT]                    # The SQLAlchemy model
    role_table: type[Base] | None = None   # e.g., FormRole, AppRole (None if no RBAC)
    role_entity_id_column: str = ""        # e.g., "form_id", "app_id"

    def __init__(
        self,
        session: AsyncSession,
        org_id: UUID | None,         # Target scope (None = global only)
        user_id: UUID | None,        # For role checks
        is_superuser: bool = False,  # Bypasses role checks, trusts scope
    ):
        self.session = session
        self.org_id = org_id
        self.user_id = user_id
        self.is_superuser = is_superuser
```

### Core Methods

```python
async def get(self, **filters) -> ModelT | None:
    """
    Get single entity with cascade scoping + role check.

    Superuser: Returns entity if it exists in the specified scope.
    Regular user: Returns entity if it exists in scope AND user has access.

    Cascade order: org-specific first, then global fallback.
    """

async def can_access(self, **filters) -> ModelT:
    """
    Get entity or raise AccessDeniedError.

    Use this when you need the entity and want to fail if not accessible.
    """
    entity = await self.get(**filters)
    if not entity:
        raise AccessDeniedError()
    return entity

async def list(self, **filters) -> list[ModelT]:
    """
    List entities with cascade scoping + role check.

    Superuser: Returns all entities in the specified scope.
    Regular user: Returns entities in scope that user has role access to.
    """
```

### Access Control Logic

**For Superusers:**
```python
# Trust the scope they specified
WHERE entity.organization_id = org_id  # or IS NULL if org_id is None
```

**For Regular Users:**
```python
# Cascade scoping
WHERE (entity.organization_id IS NULL OR entity.organization_id = org_id)
# Plus role check (if entity has role_table)
AND (
    entity.access_level = 'authenticated'
    OR entity.id IN (
        SELECT entity_id FROM entity_roles
        WHERE role_id IN (
            SELECT role_id FROM user_roles WHERE user_id = user_id
        )
    )
)
```

### Cascade Get (Single Entity)

For `.get()` when both org-specific and global exist:
```python
# Query with cascade scoping, order by org_id DESC NULLS LAST, limit 1
# This prioritizes org-specific over global
ORDER BY entity.organization_id DESC NULLS LAST
LIMIT 1
```

### Repository Implementations

Each entity type extends `OrgScopedRepository` with its role table:

```python
class FormRepository(OrgScopedRepository[Form]):
    model = Form
    role_table = FormRole
    role_entity_id_column = "form_id"

class ApplicationRepository(OrgScopedRepository[Application]):
    model = Application
    role_table = AppRole
    role_entity_id_column = "app_id"

class AgentRepository(OrgScopedRepository[Agent]):
    model = Agent
    role_table = AgentRole
    role_entity_id_column = "agent_id"

class WorkflowRepository(OrgScopedRepository[Workflow]):
    model = Workflow
    role_table = WorkflowRole
    role_entity_id_column = "workflow_id"

class TableRepository(OrgScopedRepository[Table]):
    model = Table
    role_table = None  # No RBAC, superuser only

class ConfigRepository(OrgScopedRepository[Config]):
    model = Config
    role_table = None  # No RBAC, superuser only

class IntegrationMappingRepository(OrgScopedRepository[IntegrationMapping]):
    model = IntegrationMapping
    role_table = None  # No RBAC, superuser only
```

### Endpoint Patterns

**SDK/Execution Endpoints (CurrentSuperuser):**
```python
@router.get("/{name}")
async def get_config(name: str, ctx: Context, user: CurrentSuperuser, scope: str | None = None):
    # System user passes original user's context
    target_org = resolve_target_org(ctx.user, scope, ctx.org_id)

    # For SDK calls, we typically want superuser behavior (trust the scope)
    repo = ConfigRepository(ctx.db, org_id=target_org, user_id=None, is_superuser=True)
    return await repo.can_access(name=name)
```

**Direct User Endpoints (CurrentUser):**
```python
@router.get("/{slug}")
async def get_application(slug: str, ctx: Context, user: CurrentUser):
    # User calling directly - apply full access control
    repo = ApplicationRepository(
        ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        is_superuser=ctx.user.is_superuser,
    )
    return await repo.can_access(slug=slug)
```

**Workflow Execution (System calling on behalf of user):**
```python
# In execution engine
repo = WorkflowRepository(
    session=db,
    org_id=execution_context.user_org_id,
    user_id=execution_context.user_id,
    is_superuser=False,  # Check as if user is calling
)
workflow = await repo.can_access(id=workflow_id)
```

---

## 3. Migration Plan

### Repositories to Migrate

| Repository | Current Base | Has Role Table | Action |
|------------|--------------|----------------|--------|
| `FormRepository` | `OrgScopedRepository` | `FormRole` | Update to new pattern |
| `AgentRepository` | `OrgScopedRepository` | `AgentRole` | Update to new pattern |
| `ApplicationRepository` | `OrgScopedRepository` | `AppRole` | Update to new pattern |
| `TableRepository` | `OrgScopedRepository` | None | Update to new pattern |
| `WorkflowRepository` | `BaseRepository` | `WorkflowRole` | Migrate to `OrgScopedRepository` |
| `DataProviderRepository` | `BaseRepository` | None | Migrate to `OrgScopedRepository` |
| `ConfigRepository` | None (inline) | None | Create repository, use `OrgScopedRepository` |
| `KnowledgeRepository` | `BaseRepository` | None | Migrate to `OrgScopedRepository` |
| `IntegrationMappingRepository` | N/A | None | Create new, use `OrgScopedRepository` |
| `IntegrationsRepository` | `BaseRepository` | N/A | Keep as-is (global definitions, no org scoping) |
| `ExecutionRepository` | `BaseRepository` | None | Strict scoping only (no cascade) - special case |
| `UserRepository` | `BaseRepository` | N/A | No org scoping needed |
| `OrganizationRepository` | `BaseRepository` | N/A | No org scoping needed |

### Services to Delete

| Service | Current Location | Replacement |
|---------|------------------|-------------|
| `AuthorizationService` | `api/src/services/authorization.py` | `OrgScopedRepository.can_access()` |
| `ExecutionAuthService` | `api/src/services/execution_auth.py` | `WorkflowRepository.can_access()` |

### Endpoints to Update

**Direct User Access (CurrentUser) - Need full RBAC:**
- `GET /api/applications` - list with role filtering
- `GET /api/applications/{slug}` - get with role check
- `GET /api/forms` - list with role filtering
- `GET /api/forms/{id}` - get with role check
- `GET /api/agents` - list with role filtering
- `GET /api/agents/{id}` - get with role check

**SDK/Execution Access (CurrentSuperuser) - Cascade scoping only:**
- `GET /api/tables/{name}` - cascade get
- `GET /api/tables/{name}/documents/*` - cascade to find table
- `GET /api/configs/{key}` - cascade get
- `GET /api/knowledge/{name}` - cascade get
- `GET /api/workflows/{id}` - cascade get (when called from SDK)
- `POST /api/workflows/execute` - uses `WorkflowRepository.can_access()` with user context

### Schema Change

- `IntegrationMapping.organization_id` becomes nullable (no data migration needed - not in production)

### Migration Order

1. **Schema change** - Make `IntegrationMapping.organization_id` nullable
2. **Update `OrgScopedRepository`** - Add `user_id`, `is_superuser`, role checking logic
3. **Update existing repos** - `FormRepository`, `AgentRepository`, `ApplicationRepository`, `TableRepository`
4. **Migrate remaining repos** - `WorkflowRepository`, `DataProviderRepository`, `KnowledgeRepository`
5. **Create new repos** - `ConfigRepository`, `IntegrationMappingRepository`
6. **Update endpoints** - Switch to new repository methods
7. **Delete old services** - Remove `AuthorizationService`, `ExecutionAuthService`
8. **Update tests** - Ensure all access control paths are tested
9. **Write documentation** - `api/src/repositories/README.md`

### No Backwards Compatibility

- Old `filter_cascade()`, `filter_strict()` methods removed (replaced by new `get()`/`list()`)
- `AuthorizationService` deleted entirely
- `ExecutionAuthService` deleted entirely
- Any code importing these will fail at compile time (intentional - forces migration)

---

## 4. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Missing scoping on an endpoint** | Data leak across orgs | Every repository must extend `OrgScopedRepository`. Review all endpoints during migration. |
| **Superuser flag incorrectly set** | Users bypass role checks, or SDK calls get blocked | Clear pattern: SDK endpoints pass `is_superuser=True`, direct user endpoints pass `ctx.user.is_superuser` |
| **Role table not configured** | RBAC silently skipped | Require explicit `role_table = None` for entities without RBAC (makes it intentional) |
| **Cascade returns wrong entity** | User gets global when they expected org-specific (or vice versa) | Order by `organization_id DESC NULLS LAST` - org-specific always wins |
| **Performance regression on list endpoints** | Slow queries from role joins | Index on `role_id` columns (already exists). Monitor query plans. |
| **Breaking existing SDK calls** | Workflows fail in execution | No backwards compatibility = clean break. Test all SDK methods against new pattern. |
| **IntegrationMapping schema change** | Existing mappings break | Not in production - just change the schema, no migration needed |

---

## 5. Documentation Requirements

### README Location

`api/src/repositories/README.md`

### Contents

**1. Request Flow & Where Scoping Happens**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ DIRECT USER ACCESS (e.g., GET /api/applications)                            │
│                                                                             │
│   User ──► API Endpoint ──► OrgScopedRepository                             │
│                                  │                                          │
│                                  ├─ org_id = ctx.org_id                     │
│                                  ├─ user_id = ctx.user.user_id              │
│                                  └─ is_superuser = ctx.user.is_superuser    │
│                                                                             │
│   Repository does: cascade scoping + role check (unless platform admin)     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ SDK/EXECUTION (e.g., configs.get("MyVar"))                                  │
│                                                                             │
│   User ──► Form/App ──► Workflow Execution ──► SDK ──► API ──► Repository   │
│                              │                  │                           │
│                              │                  └─ Calls as CurrentSuperuser│
│                              │                                              │
│                              └─ Captures user's org_id & user_id            │
│                                 into execution_context                      │
│                                                                             │
│   At the API layer: CurrentSuperuser allows the call through                │
│   At the Repository layer: We pass the ORIGINAL user's context              │
│                                                                             │
│                                  ├─ org_id = execution_context.user_org_id  │
│                                  ├─ user_id = execution_context.user_id     │
│                                  └─ is_superuser = False (check as user)    │
│                                                                             │
│   Repository does: cascade scoping + role check AS IF the user called it    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight:** The superuser is just the transport mechanism. The repository checks permissions as the original user.

**2. Access Control Logic (Inside Repository)**

```python
if is_superuser:
    # Trust the scope, no role check
    # Used for: platform admins in UI, or SDK calls that don't need user-level checks
    WHERE entity.organization_id = org_id (or IS NULL if org_id is None)
else:
    # Cascade scoping + role check
    # Used for: regular users in UI, or SDK calls checking original user's access
    WHERE (entity.organization_id IS NULL OR entity.organization_id = org_id)
    AND (entity.access_level = 'authenticated' OR user has matching role)
```

**3. When to Use Each Pattern**

| Scenario | `is_superuser` | Why |
|----------|----------------|-----|
| Platform admin browsing UI | `True` (from ctx) | They're a superuser, trust their scope selection |
| Regular user browsing UI | `False` (from ctx) | Check their roles |
| SDK: `configs.get()` | `True` | No RBAC on configs, just cascade to find the right one |
| SDK: `workflows.execute()` | `False` | Check if original user has permission to run this workflow |

**4. Understanding `is_superuser=True` in SDK Context**

For entities **without role tables** (Tables, Configs, Knowledge, IntegrationMappings):
- API is protected by `CurrentSuperuser` - regular users can't call directly
- Execution engine (running as superuser) calls on behalf of users
- Engine passes user's `org_id` for cascade resolution
- `is_superuser=True` means "trust the scope, just cascade" - not "skip security"
- Security was already validated when the user was allowed to execute the workflow

```python
# Execution engine calling configs.get("MyVar")
repo = ConfigRepository(
    session=db,
    org_id=execution_context.user_org_id,  # User's org for cascade
    user_id=None,                           # Not needed - no RBAC on configs
    is_superuser=True,                      # Trust scope, resolve cascade
)
config = await repo.get(key="MyVar")
# Returns: org-specific if exists, else global, else None
```

**5. Method Reference**

| Method | Returns | Use Case |
|--------|---------|----------|
| `get(**filters)` | `Entity \| None` | Single entity lookup with cascade |
| `can_access(**filters)` | `Entity` | Same as get, raises `AccessDeniedError` if not found |
| `list(**filters)` | `list[Entity]` | Multiple entities with cascade + role filtering |

**6. Entity Configuration**

| Entity | Role Table | Direct User Access | Notes |
|--------|------------|-------------------|-------|
| Form | `FormRole` | Yes | RBAC via roles, has `access_level` field |
| Application | `AppRole` | Yes | RBAC via roles, has `access_level` field |
| Agent | `AgentRole` | Yes | RBAC via roles, has `access_level` field |
| Workflow | `WorkflowRole` | No (SDK only) | RBAC checked during execution, has `access_level` field |
| Table | None | No (SDK only) | Cascade only, no RBAC - `CurrentSuperuser` API |
| Config | None | No (SDK only) | Cascade only, no RBAC - `CurrentSuperuser` API |
| Knowledge | None | No (SDK only) | Cascade only, no RBAC - `CurrentSuperuser` API |
| IntegrationMapping | None | No (SDK only) | Cascade only, no RBAC - `CurrentSuperuser` API |

**Understanding `access_level`:**
- `'authenticated'` = Any user who can cascade to this scope can access (no role check)
- `'role_based'` = User must have a matching role in the entity's role table
- Entities without role tables don't have `access_level` - they're cascade-only via `CurrentSuperuser` API

**7. Common Mistakes**

- ❌ Passing `is_superuser=True` when you should be checking user permissions
- ❌ Forgetting to pass original user's `org_id`/`user_id` in SDK execution context
- ❌ Using `BaseRepository` for org-scoped entities
- ❌ Looking for `AuthorizationService` (absorbed into repository)

---

## 6. Summary

### What We're Building

A unified `OrgScopedRepository` that handles both cascade scoping and role-based access control, replacing the scattered patterns across `AuthorizationService`, `ExecutionAuthService`, and ad-hoc repository code.

### Key Decisions

1. **Single entry point** - All org-scoped data access goes through `OrgScopedRepository`
2. **Scoping + RBAC in one place** - Repository handles both, not separate services
3. **Superuser = trust the scope** - No role checks, just use what they asked for
4. **SDK passes original user context** - The superuser is transport, repository checks as the user
5. **No backwards compatibility** - Clean migration, delete old code
6. **Direct user access limited** - Only forms, apps, agents exposed to `CurrentUser`; everything else is `CurrentSuperuser` only

### What Gets Deleted

- `api/src/services/authorization.py`
- `api/src/services/execution_auth.py`

### What Gets Created

- Updated `OrgScopedRepository` with `user_id`, `is_superuser`, role checking
- `api/src/repositories/README.md` documenting the pattern

### Schema Change

- `IntegrationMapping.organization_id` becomes nullable (enables standard cascade pattern)
