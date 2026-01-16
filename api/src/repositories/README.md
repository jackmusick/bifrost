# Organization-Scoped Repository Pattern

This directory contains the standardized repository pattern for all org-scoped data access in Bifrost.

## Overview

`OrgScopedRepository` is the single entry point for accessing org-scoped entities. It handles:

1. **Organization cascade scoping** - org-specific entities take priority over global
2. **Role-based access control** - for entities with role tables (forms, apps, agents, workflows)

## Request Flow

```
DIRECT USER ACCESS (e.g., GET /api/applications)

  User ──► API Endpoint ──► OrgScopedRepository
                                 │
                                 ├─ org_id = ctx.org_id
                                 ├─ user_id = ctx.user.user_id
                                 └─ is_superuser = ctx.user.is_superuser

  Repository does: cascade scoping + role check (unless superuser)
```

```
SDK/WORKFLOW EXECUTION (e.g., tables.query("users"))

  User ──► Form/App ──► Workflow Execution ──► SDK ──► API ──► Repository
                             │                  │
                             │                  └─ Calls as system user
                             │
                             └─ Determines effective scope:
                                - Org-scoped workflow → workflow's org_id
                                - Global workflow → caller's org_id

  Repository uses the effective org_id for cascade resolution.
  No per-user authorization during execution (security validated at workflow start).
```

## Lookup Behavior

### ID Lookups (`get(id=...)`)

IDs are globally unique. No cascade needed.

- Find entity directly by ID
- **Superusers**: Can access any entity by ID
- **Regular users**: Must be in their scope (their org or global) + pass role check

### Name/Key Lookups (`get(name=...)`, `get(key=...)`)

Names can exist in multiple orgs. Cascade scoping required.

1. Try org-specific first (`WHERE organization_id = org_id`)
2. Fall back to global (`WHERE organization_id IS NULL`)
3. Check access permissions on found entity

This applies to **all users including superusers** - cascade determines which entity to return.

## Method Reference

| Method | Returns | Use Case |
|--------|---------|----------|
| `get(**filters)` | `Entity \| None` | Single entity lookup |
| `can_access(**filters)` | `Entity` | Same as get, raises `AccessDeniedError` if not found |
| `list(**filters)` | `list[Entity]` | Multiple entities with cascade + role filtering |

## Entity Configuration

| Entity | Role Table | Direct User Access | Notes |
|--------|------------|-------------------|-------|
| Form | `FormRole` | Yes | RBAC via roles, has `access_level` |
| Application | `AppRole` | Yes | RBAC via roles, has `access_level` |
| Agent | `AgentRole` | Yes | RBAC via roles, has `access_level` |
| Workflow | `WorkflowRole` | No (SDK only) | RBAC checked at execution start |
| Table | None | No (SDK only) | Cascade only, no RBAC |
| Config | None | No (SDK only) | Cascade only, no RBAC |
| Knowledge | None | No (SDK only) | Cascade only, no RBAC |
| IntegrationMapping | None | No (SDK only) | Cascade only, no RBAC |
| DataProvider | None | No (SDK only) | Cascade only, no RBAC |

### Understanding `access_level`

- `'authenticated'` - Any user who can cascade to this scope can access
- `'role_based'` - User must have a matching role in the entity's role table
- Entities without role tables don't have `access_level` - cascade-only via system API

## Creating a Repository

```python
from src.repositories import OrgScopedRepository
from src.models.orm import MyEntity, MyEntityRole

class MyEntityRepository(OrgScopedRepository[MyEntity]):
    model = MyEntity
    role_table = MyEntityRole        # Optional: for RBAC
    role_entity_id_column = "entity_id"  # Column name in role table
```

For entities without RBAC:

```python
class TableRepository(OrgScopedRepository[Table]):
    model = Table
    # No role_table - cascade scoping only
```

## Usage Examples

### Direct User Access (API Endpoint)

```python
@router.get("/{slug}")
async def get_application(slug: str, ctx: Context, user: CurrentUser):
    repo = ApplicationRepository(
        ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        is_superuser=ctx.user.is_superuser,
    )
    return await repo.can_access(slug=slug)
```

### Workflow Execution Authorization

```python
# When checking if user can execute a workflow
workflow_repo = WorkflowRepository(
    session=db,
    org_id=workflow.organization_id,  # Use workflow's org, not caller's
    user_id=ctx.user.user_id,
    is_superuser=ctx.user.is_superuser,
)
await workflow_repo.can_access(id=workflow_id)
```

### SDK Data Access (During Execution)

```python
# Inside CLI endpoints called by SDK during workflow execution
# org_id comes from execution context (workflow's org or caller's org)
repo = TableRepository(
    session=db,
    org_id=execution_org_id,
    is_superuser=True,  # Trust scope, just resolve cascade
)
table = await repo.get(name=table_name)
```

## Common Mistakes

- **Using `ctx.org_id` for workflow execution auth** - Use `workflow.organization_id` instead
- **Forgetting cascade affects superusers too** - For name lookups, cascade determines which entity
- **Using `BaseRepository` for org-scoped entities** - Always use `OrgScopedRepository`
- **Looking for `AuthorizationService`** - Absorbed into repository pattern

## Deleted Services

These services were replaced by `OrgScopedRepository`:

- `api/src/services/authorization.py` - `AuthorizationService`
- `api/src/services/execution_auth.py` - `ExecutionAuthService`
