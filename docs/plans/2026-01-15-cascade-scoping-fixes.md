# Cascade Scoping Standardization

**Date:** 2026-01-15
**Status:** In Progress

## Problem

Single-entity lookups by name/slug/key were inconsistent across the codebase. When the same identifier exists in both org scope and global scope, incorrect patterns cause `MultipleResultsFound` errors instead of properly resolving to org-specific first, then global fallback.

## The Correct Pattern

```
1. Try org-specific lookup (organization_id = user's org)
2. If found, return it
3. Fall back to global (organization_id IS NULL)
4. If found, return it
5. Return None (graceful 404)
```

## Infrastructure

**`OrgScopedRepository.get_one_cascade()`** - Added in `/api/src/repositories/org_scoped.py:211-253`

This is the standard method for all single-entity cascade lookups. Repositories extending `OrgScopedRepository` should use this instead of manual two-step queries or `filter_cascade()` + `scalar_one_or_none()`.

```python
async def get_one_cascade(self, base_query: Select) -> ModelT | None:
    """
    Get a single entity with cascade scoping: org-specific first, then global fallback.

    Usage:
        query = select(self.model).where(self.model.name == name)
        return await self.get_one_cascade(query)
    """
```

**Important:** `filter_cascade()` is safe for **list** operations (returns multiple rows). It is **NOT safe** for single-entity lookups - use `get_one_cascade()` instead.

---

## Completed Fixes

| Entity | File | Method | Fix Applied |
|--------|------|--------|-------------|
| Application | `routers/applications.py` | `get_by_slug()` | ✅ Now uses `get_one_cascade()` |
| Application | `routers/applications.py` | `get_by_id()` | ✅ Now uses `get_one_cascade()` |
| Table | `routers/tables.py` | `get_by_name()` | ✅ Now uses `get_one_cascade()` |
| Config | `routers/config.py` | `get_config()` | ✅ Now uses `get_one_cascade()` |

---

## Already Correct (No Changes Needed)

These use `BaseRepository` with manual two-step lookups. Pattern is correct, just not using the shared method.

| Entity | File | Method | Status |
|--------|------|--------|--------|
| Workflow | `repositories/workflows.py` | `get_by_name()` | ✅ Correct (manual two-step) |
| DataProvider | `repositories/data_providers.py` | `get_by_name()` | ✅ Correct (manual two-step) |
| Integration | `repositories/integrations.py` | N/A | ✅ No org_id field |

---

## Remaining Work

### MCP Tools (Low Priority)

These use `ORDER BY organization_id DESC NULLS LAST LIMIT 1` - works correctly but inconsistent with the standard pattern. They have complex queries with `selectinload()` that make refactoring non-trivial.

| Entity | File | Current Pattern |
|--------|------|-----------------|
| Agent | `services/mcp_server/tools/agents.py:200-212` | ORDER BY hack |
| Form | `services/mcp_server/tools/forms.py:387-399` | ORDER BY hack |

**Recommendation:** These work correctly. Refactor only if we need to touch these files for other reasons.

### CLI SDK Table Lookup

| Entity | File | Method | Status |
|--------|------|--------|--------|
| Table (SDK) | `routers/cli.py:2243-2287` | `_find_table_for_sdk()` | ✅ Correct (manual two-step) |

This was fixed earlier in the session with proper two-step lookup. It's a standalone function, not a repository method, so it doesn't use `get_one_cascade()` but implements the same pattern.

---

## Pattern Reference

### When to use each method:

| Method | Use Case |
|--------|----------|
| `get_one_cascade()` | Single entity by name/slug/key (cascade: org → global) |
| `filter_cascade()` | List operations returning multiple entities |
| `filter_strict()` | Single org only, no global fallback |
| `filter_org_only()` | Current org only (excludes global) |
| `filter_global_only()` | Global resources only |

### Anti-pattern (causes MultipleResultsFound):

```python
# ❌ WRONG - can return multiple rows
query = select(Model).where(Model.name == name)
query = self.filter_cascade(query)  # Adds: WHERE org_id = X OR org_id IS NULL
result = await self.session.execute(query)
return result.scalar_one_or_none()  # Throws if both exist!
```

### Correct pattern:

```python
# ✅ CORRECT - uses two-step lookup
query = select(Model).where(Model.name == name)
return await self.get_one_cascade(query)
```

---

## Authorization vs SDK Scoping

These are **separate concerns**:

| Concern | Location | Purpose |
|---------|----------|---------|
| **Authorization** | `services/authorization.py` | "Can user X access this entity?" (RBAC for UI) |
| **SDK Scoping** | Repositories, `cli.py` | "Which entity does name Y resolve to?" (cascade lookup) |

Authorization controls what shows in lists. SDK scoping controls which single entity is returned when code calls `tables.query("name")` or `configs.get("key")`.
