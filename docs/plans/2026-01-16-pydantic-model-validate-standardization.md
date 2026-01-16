# Pydantic model_validate() Standardization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate all manual field construction and `dict[str, Any]` patterns, standardizing on `model_validate()` across the entire Bifrost API.

**Architecture:** All data entering or leaving the system flows through Pydantic models with `from_attributes=True`. MCP tools use the same repositories/services as REST routes. Load-time validation catches data integrity issues before they cause silent failures.

**Tech Stack:** Pydantic v2, FastAPI, SQLAlchemy ORM

---

## Problem Statement

The PM Demo app broke because MCP tools bypass Pydantic validation:
- MCP tools use `dict[str, Any]` and store data directly
- REST routes have inconsistent patterns (some `model_validate()`, some manual)
- Bad data (like `navigation.items` instead of `navigation.sidebar`) causes silent failures

## Success Criteria

- [ ] All models have `from_attributes=True`
- [ ] All routers use `model_validate()` (zero manual field construction)
- [ ] All MCP tools validate through Pydantic models (not raw dicts)
- [ ] `NavigationConfig` and `NavItem` have `extra="forbid"`
- [ ] Final audit: every `dict[]` pattern justified or fixed

**Note:** No dedicated validation service needed - `model_validate()` handles validation automatically on create/update and load paths.

---

## Phase 1: Applications

**Fixes PM Demo and establishes the pattern for other phases.**

### Task 1.1: Add `extra="forbid"` to Navigation Models

**Why `extra="forbid"`?**

Pydantic's default is `extra="ignore"` - it **silently drops** unknown fields. This is how `{"items": [...]}` got stored: Pydantic saw `items` wasn't a field, ignored it, and stored the dict anyway.

With `extra="forbid"`, Pydantic raises `ValidationError` for unknown fields. When `ApplicationPublic.model_validate()` runs and validates its nested `navigation` field, the bad `items` field will be caught.

**Files:**
- Modify: `api/src/models/contracts/app_components.py:1490-1525`
- Test: `api/tests/unit/models/test_navigation_validation.py` (create)

**Step 1: Write failing test**

```python
# api/tests/unit/models/test_navigation_validation.py
"""Test that navigation models reject unknown fields."""
import pytest
from pydantic import ValidationError
from src.models.contracts.app_components import NavItem, NavigationConfig


def test_navitem_rejects_unknown_fields():
    """NavItem should reject unknown fields like 'items'."""
    with pytest.raises(ValidationError) as exc_info:
        NavItem(id="test", label="Test", unknown_field="bad")
    assert "extra_forbidden" in str(exc_info.value)


def test_navigation_config_rejects_items_field():
    """NavigationConfig should reject 'items' field (must use 'sidebar')."""
    with pytest.raises(ValidationError) as exc_info:
        NavigationConfig(items=[{"id": "test", "label": "Test"}])
    assert "extra_forbidden" in str(exc_info.value)


def test_navigation_config_accepts_sidebar():
    """NavigationConfig should accept proper 'sidebar' field."""
    nav = NavigationConfig(
        sidebar=[NavItem(id="home", label="Home", path="/", icon="Home")]
    )
    assert len(nav.sidebar) == 1
    assert nav.sidebar[0].id == "home"
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/unit/models/test_navigation_validation.py -v
```
Expected: FAIL - currently accepts unknown fields

**Step 3: Add `extra="forbid"` to models**

```python
# api/src/models/contracts/app_components.py:1490
class NavItem(BaseModel):
    """Navigation item for sidebar/navbar."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Item identifier (usually page ID)")
    # ... rest unchanged


# api/src/models/contracts/app_components.py:1511
class NavigationConfig(BaseModel):
    """Navigation configuration for the application."""

    model_config = ConfigDict(extra="forbid")

    sidebar: list[NavItem] | None = Field(
    # ... rest unchanged
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/unit/models/test_navigation_validation.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/models/contracts/app_components.py api/tests/unit/models/test_navigation_validation.py
git commit -m "feat(app-builder): add extra=forbid to navigation models

Prevents invalid fields like 'items' from being silently accepted.
Must use 'sidebar' field for navigation items."
```

---

### Task 1.2: Add `navigation` to `ApplicationUpdate` Model

**Files:**
- Modify: `api/src/models/contracts/applications.py:77-102`
- Test: `api/tests/unit/models/test_application_update.py` (create)

**Step 1: Write failing test**

```python
# api/tests/unit/models/test_application_update.py
"""Test ApplicationUpdate model with navigation field."""
import pytest
from pydantic import ValidationError
from src.models.contracts.applications import ApplicationUpdate
from src.models.contracts.app_components import NavigationConfig, NavItem


def test_application_update_accepts_navigation():
    """ApplicationUpdate should accept navigation field."""
    update = ApplicationUpdate(
        navigation=NavigationConfig(
            sidebar=[NavItem(id="home", label="Home", path="/")]
        )
    )
    assert update.navigation is not None
    assert update.navigation.sidebar[0].id == "home"


def test_application_update_rejects_invalid_navigation():
    """ApplicationUpdate should reject invalid navigation."""
    with pytest.raises(ValidationError):
        ApplicationUpdate(
            navigation={"items": [{"id": "test", "label": "Test"}]}  # Wrong field name
        )
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/unit/models/test_application_update.py -v
```
Expected: FAIL - navigation field doesn't exist

**Step 3: Add navigation field to ApplicationUpdate**

```python
# api/src/models/contracts/applications.py - add import at top
from src.models.contracts.app_components import NavigationConfig, PageDefinition

# api/src/models/contracts/applications.py:77 - add field to ApplicationUpdate
class ApplicationUpdate(BaseModel):
    """Input for updating application metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=50)
    scope: str | None = Field(
        default=None,
        description="Organization scope: 'global' for platform-wide, or org UUID string. Platform admin only.",
    )
    access_level: str | None = Field(
        default=None,
        description="Access level: 'authenticated' (any logged-in user) or 'role_based' (specific roles)",
    )
    role_ids: list[UUID] | None = Field(
        default=None,
        description="Role IDs for role_based access (replaces existing roles)",
    )
    navigation: NavigationConfig | None = Field(
        default=None,
        description="Navigation configuration (sidebar items, header settings)",
    )

    @field_validator("access_level")
    # ... rest unchanged
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/unit/models/test_application_update.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/models/contracts/applications.py api/tests/unit/models/test_application_update.py
git commit -m "feat(app-builder): add navigation field to ApplicationUpdate

Enables REST API to update navigation with full Pydantic validation."
```

---

### Task 1.3: Handle Navigation in `ApplicationRepository.update_application()`

**Files:**
- Modify: `api/src/routers/applications.py` (ApplicationRepository.update_application method)
- Test: `api/tests/integration/test_application_navigation.py` (create)

**Step 1: Write failing test**

```python
# api/tests/integration/test_application_navigation.py
"""Test application navigation updates via REST API."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_update_application_navigation(
    async_client: AsyncClient,
    auth_headers: dict,
    test_application: dict,
):
    """Should update application navigation via REST API."""
    response = await async_client.put(
        f"/api/applications/{test_application['slug']}",
        json={
            "navigation": {
                "sidebar": [
                    {"id": "home", "label": "Home", "path": "/", "icon": "Home"},
                    {"id": "settings", "label": "Settings", "path": "/settings"},
                ],
                "show_sidebar": True,
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["navigation"]["sidebar"][0]["id"] == "home"


@pytest.mark.asyncio
async def test_update_application_rejects_invalid_navigation(
    async_client: AsyncClient,
    auth_headers: dict,
    test_application: dict,
):
    """Should reject navigation with invalid 'items' field."""
    response = await async_client.put(
        f"/api/applications/{test_application['slug']}",
        json={
            "navigation": {
                "items": [{"id": "home", "label": "Home"}]  # Wrong field
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 422  # Validation error
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/integration/test_application_navigation.py -v
```
Expected: FAIL - navigation not handled in update

**Step 3: Handle navigation in repository**

```python
# api/src/routers/applications.py - in ApplicationRepository.update_application()
# Add after line ~295 (after existing field updates):

        if data.navigation is not None:
            application.navigation = data.navigation.model_dump(exclude_none=True)
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/integration/test_application_navigation.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/routers/applications.py api/tests/integration/test_application_navigation.py
git commit -m "feat(app-builder): handle navigation in ApplicationRepository.update_application

Navigation updates now go through Pydantic validation before storage."
```

---

### Task 1.4: Refactor MCP `update_app` to Validate Through Pydantic

**Files:**
- Modify: `api/src/services/mcp_server/tools/apps.py`
- Test: `api/tests/unit/services/mcp_server/test_apps_validation.py` (create)

**Step 1: Write failing test**

```python
# api/tests/unit/services/mcp_server/test_apps_validation.py
"""Test MCP app tools validate through Pydantic models."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_update_app_rejects_invalid_navigation():
    """MCP update_app should reject navigation with 'items' field."""
    from src.services.mcp_server.tools.apps import update_app

    mock_context = MagicMock()
    mock_context.org_id = None
    mock_context.is_platform_admin = True
    mock_context.user_id = "test-user"
    mock_context.user_email = "test@example.com"

    result = await update_app(
        context=mock_context,
        app_id="b8741301-2996-4efc-b66c-fe019fa2a565",
        navigation={"items": [{"id": "test", "label": "Test"}]},  # Invalid
    )

    result_data = json.loads(result)
    assert "error" in result_data
    assert "validation" in result_data["error"].lower() or "extra" in result_data["error"].lower()


@pytest.mark.asyncio
async def test_update_app_accepts_valid_navigation():
    """MCP update_app should accept navigation with 'sidebar' field."""
    from src.services.mcp_server.tools.apps import update_app

    # This test needs proper mocking of database - simplified version
    # Full integration test should verify end-to-end
    pass  # Covered by integration tests
```

**Step 2: Run test to verify it fails**

```bash
./test.sh tests/unit/services/mcp_server/test_apps_validation.py -v
```
Expected: FAIL - MCP tool doesn't validate

**Step 3: Refactor MCP update_app to validate through Pydantic**

```python
# api/src/services/mcp_server/tools/apps.py - update the update_app function

# Add imports at top:
from pydantic import ValidationError
from src.models.contracts.app_components import NavigationConfig

# Replace the navigation handling in update_app (around line 433-435):
            if navigation is not None:
                # Validate through Pydantic model
                try:
                    validated_nav = NavigationConfig.model_validate(navigation)
                    app.navigation = validated_nav.model_dump(exclude_none=True)
                except ValidationError as e:
                    return json.dumps({
                        "error": f"Invalid navigation configuration: {e}"
                    })
```

**Step 4: Run test to verify it passes**

```bash
./test.sh tests/unit/services/mcp_server/test_apps_validation.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/apps.py api/tests/unit/services/mcp_server/test_apps_validation.py
git commit -m "feat(mcp): validate navigation through Pydantic in update_app

MCP tools now reject invalid navigation (like 'items' instead of 'sidebar')
with proper validation errors instead of storing bad data."
```

---

### Task 1.5: Fix PM Demo App

**Files:**
- None (uses MCP tools)

**Step 1: Fix navigation via MCP**

Use the Bifrost MCP server to fix the PM Demo app:

```python
# Via MCP update_app tool
await update_app(
    app_id="b8741301-2996-4efc-b66c-fe019fa2a565",
    navigation={
        "sidebar": [
            {"id": "dashboard", "icon": "LayoutDashboard", "path": "/", "label": "Dashboard"},
            {"id": "customers", "icon": "Users", "path": "/customers", "label": "Customers"},
            {"id": "projects", "icon": "FolderKanban", "path": "/projects", "label": "Projects"},
            {"id": "tasks", "icon": "CheckSquare", "path": "/tasks", "label": "Tasks"}
        ],
        "show_sidebar": True
    }
)
```

**Step 2: Verify the fix**

Navigate to `http://localhost:3000/apps/pm-demo/preview` and confirm:
- Sidebar shows only 4 items (Dashboard, Customers, Projects, Tasks)
- No more Edit*, New*, *Details pages in sidebar

**Step 3: Fix orphaned dashboard components**

Investigate and rebuild dashboard components with correct parent references.
(Specific steps depend on current state - may need to delete and recreate.)

---

### Task 1.6: Run Full Test Suite for Phase 1

**Step 1: Run all tests**

```bash
./test.sh
```
Expected: All tests pass

**Step 2: Run type checking**

```bash
cd api && pyright
```
Expected: No errors

**Step 3: Run linting**

```bash
cd api && ruff check .
```
Expected: No errors

**Step 4: Regenerate frontend types**

```bash
cd client && npm run generate:types
```

**Step 5: Run frontend checks**

```bash
cd client && npm run tsc && npm run lint
```
Expected: No errors

---

## Phase 2: Agents

### Task 2.1: Change REST Router to Use `model_validate()`

**Files:**
- Modify: `api/src/routers/agents.py` (remove `_agent_to_public()` helper)
- Test: Existing tests should continue to pass

**Step 1: Replace manual construction with model_validate**

```python
# api/src/routers/agents.py - replace _agent_to_public() usage with:
AgentPublic.model_validate(agent)
```

**Step 2: Remove the `_agent_to_public()` helper function**

**Step 3: Run tests**

```bash
./test.sh tests/ -k agent -v
```
Expected: PASS

**Step 4: Commit**

```bash
git commit -m "refactor(agents): use model_validate instead of manual construction"
```

---

### Task 2.2: Refactor Agent MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/agents.py`

Similar pattern to Task 1.6 - validate through Pydantic models instead of raw dicts.

---

## Phase 3: Workflows

### Task 3.1: Add `from_attributes=True` to WorkflowMetadata

**Files:**
- Modify: `api/src/models/contracts/workflows.py`

```python
class WorkflowMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # ... rest unchanged
```

### Task 3.2: Change REST Router to Use `model_validate()`

**Files:**
- Modify: `api/src/routers/workflows.py` (remove `_convert_workflow_orm_to_schema()`)

### Task 3.3: Refactor Workflow MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/workflow.py`

### Task 3.4: Add Validation to Workflow Indexer

**Files:**
- Modify: `api/src/services/file_storage/indexers/workflow.py`

---

## Phase 4: Forms MCP

### Task 4.1: Refactor Form MCP Tools to Use `FormPublic.model_validate()`

**Files:**
- Modify: `api/src/services/mcp_server/tools/forms.py`

REST router is already correct - only MCP tools need updating.

---

## Phase 5: Remaining Routers

### Task 5.1: chat.py - Use model_validate()

Replace manual `ConversationPublic()` and `MessagePublic()` construction.

### Task 5.2: events.py - Use model_validate()

Replace `_build_event_source_response()` and `_build_event_subscription_response()` helpers.

### Task 5.3: executions.py - Use model_validate()

Remove `_to_pydantic()` method, use `WorkflowExecution.model_validate()`.

### Task 5.4: tables.py - Use model_validate()

Use the already-configured `from_attributes=True` on `TablePublic`.

---

## Phase 6: Final Audit

### Task 6.1: Find All `dict[]` Patterns

```bash
grep -r "dict\[str, Any\]" api/src/routers/ api/src/services/ --include="*.py"
grep -r ": dict\[" api/src/models/contracts/ --include="*.py"
```

### Task 6.2: Justify or Fix Each Instance

For each instance, categorize:

| Justified Use | Example |
|---------------|---------|
| JSONB storage fields | `props: dict[str, Any]` on ORM |
| External API responses | Response from 3rd party |
| Serialization context | `context: dict[str, str]` |
| Logging/debugging | Non-critical metadata |

**NOT justified (must fix):**
- Function parameters accepting user input
- Return types that should be typed models
- MCP tool inputs/outputs

### Task 6.3: Document Findings

Create `docs/adr/YYYY-MM-DD-dict-usage-audit.md` with all findings and justifications.

---

## Verification Checklist

After all phases complete:

- [ ] `./test.sh` - All tests pass
- [ ] `cd api && pyright` - No type errors
- [ ] `cd api && ruff check .` - No lint errors
- [ ] `cd client && npm run tsc` - No type errors
- [ ] `cd client && npm run lint` - No lint errors
- [ ] PM Demo app loads correctly with 4 sidebar items
- [ ] PM Demo dashboard shows stats
- [ ] MCP `update_app` with `{"items": [...]}` returns validation error
- [ ] Loading app with bad data returns 422 (not silent failure)
- [ ] All `dict[]` patterns documented and justified
