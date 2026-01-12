# App Builder Type Unification Plan

## Goal

Create a **single source of truth** for App Builder types in Python Pydantic models. Frontend will import from auto-generated `v1.d.ts` instead of maintaining separate `app-builder-types.ts`.

**Success = deleting `app-builder-types.ts` and frontend still compiles.**

## Current State

- **Frontend** (`client/src/lib/app-builder-types.ts`): 1000+ lines of well-typed interfaces
- **Backend** (`api/src/models/contracts/applications.py`): Mix of typed and `dict[str, Any]`
- **Problem**: `props` is untyped JSONB - no validation that button props are actually button props

## Design Decisions

1. **TypeScript → Python**: Port frontend types to Pydantic (TS is current source of truth)
2. **Single model approach**: One model per entity that serves API, export, and import
3. **Access control**: Optional fields (`organization_id`, `access_level`, `role_ids`) - excluded from exports via `model_dump(exclude=...)`
4. **Typed props**: Discriminated union for component props - each component type has its own props model
5. **camelCase JSON**: Use `alias_generator=to_camel` for frontend compatibility

---

## Tasks

### Task 1: Create Typed Component Props Models ✅ COMPLETE

**File: `api/src/models/contracts/app_builder_types.py`**

Port all TypeScript interfaces from `client/src/lib/app-builder-types.ts` to Pydantic:

**Component Types to Port (22 total):**
1. `heading` - HeadingProps
2. `text` - TextProps
3. `html` - HtmlProps
4. `card` - CardProps
5. `divider` - DividerProps
6. `spacer` - SpacerProps
7. `button` - ButtonProps
8. `stat-card` - StatCardProps
9. `image` - ImageProps
10. `badge` - BadgeProps
11. `progress` - ProgressProps
12. `data-table` - DataTableProps
13. `tabs` - TabsProps
14. `file-viewer` - FileViewerProps
15. `modal` - ModalProps
16. `text-input` - TextInputProps
17. `number-input` - NumberInputProps
18. `select` - SelectProps
19. `checkbox` - CheckboxProps
20. `form-embed` - FormEmbedProps
21. `form-group` - FormGroupProps

**Shared Types to Port:**
- `OnCompleteAction`
- `RepeatFor`
- `TableColumn`
- `TableAction`
- `SelectOption`
- `TabItem`

**Layout Types:**
- `LayoutContainer` (row, column, grid)
- All layout literals (LayoutAlign, LayoutJustify, etc.)

**Top-Level Types:**
- `PageDefinition`
- `PagePermission`
- `DataSourceConfig`
- `NavigationItem`
- `NavigationConfig`
- `ApplicationDefinition`

**Requirements:**
- Use `CamelModel` base with `alias_generator=to_camel`
- Use `Literal` types for enums (not Python Enum)
- Use discriminated union for `AppComponent` with `Field(discriminator="type")`
- All optional fields default to `None`

**Example Structure:**
```python
"""
App Builder Type Definitions - Single Source of Truth

These Pydantic models mirror the frontend TypeScript types exactly.
After generation, frontend imports from v1.d.ts instead of
maintaining separate app-builder-types.ts.
"""

from typing import Literal, Annotated, Union, Any
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model with camelCase serialization."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# Literals (not Python Enums - these serialize to strings)
ComponentType = Literal[
    "heading", "text", "html", "card", "divider", "spacer",
    "button", "stat-card", "image", "badge", "progress",
    "data-table", "tabs", "file-viewer", "modal",
    "text-input", "number-input", "select", "checkbox",
    "form-embed", "form-group"
]

ButtonActionType = Literal["navigate", "workflow", "custom", "submit", "open-modal"]
# ... etc


class ButtonProps(CamelModel):
    label: str
    action_type: ButtonActionType
    navigate_to: str | None = None
    workflow_id: str | None = None
    # ... all fields from ButtonComponentProps.props in TypeScript


class ButtonComponent(CamelModel):
    """Button component - discriminated by type field."""
    id: str
    type: Literal["button"] = "button"
    props: ButtonProps
    width: str | None = None
    visible: str | None = None
    loading_workflows: list[str] | None = None
    grid_span: int | None = None
    repeat_for: "RepeatFor | None" = None
    class_name: str | None = None
    style: dict | None = None


# Discriminated union - validates correct props for type
AppComponent = Annotated[
    HeadingComponent | TextComponent | ButtonComponent | ...,
    Field(discriminator="type")
]


class ApplicationDefinition(CamelModel):
    """Single model for API, export, and import."""
    id: str
    name: str
    slug: str
    description: str | None = None
    icon: str | None = None
    pages: list["PageDefinition"] = Field(default_factory=list)
    navigation: "NavigationConfig | None" = None
    global_variables: dict = Field(default_factory=dict)
    global_data_sources: list["DataSourceConfig"] = Field(default_factory=list)
    styles: str | None = None

    # Access control - optional, excluded from exports
    organization_id: str | None = None
    access_level: Literal["authenticated", "role_based"] | None = None
    role_ids: list[str] | None = None

    # Timestamps
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_export_dict(self) -> dict:
        """Serialize for export, excluding env-specific fields."""
        return self.model_dump(
            mode="json",
            by_alias=True,
            exclude={"organization_id", "access_level", "role_ids"}
        )
```

**Verification:**
```bash
cd api && pyright src/models/contracts/app_builder_types.py
```

---

### Task 2: Update applications.py to Use New Types ✅ COMPLETE

**File: `api/src/models/contracts/applications.py`**

1. ✅ Import types from `app_builder_types.py`
2. ✅ `ApplicationExport` uses typed models from app_builder_types
3. ✅ Re-export `ApplicationDefinition`, `PageDefinition`, `AppComponent` from app_builder_types
4. ✅ Keep API-specific models (`ApplicationCreate`, `ApplicationUpdate`, `ApplicationPublic`)
5. ✅ `from_app_orm()` builds typed `ApplicationDefinition`

**Verification:**
```bash
cd api && pyright
./test.sh tests/unit/
```

---

### Task 3: Update App Indexer for Pydantic Validation

**Status: ⚠️ PARTIALLY COMPLETE**

**File: `api/src/services/file_storage/indexers/app.py`**

**Completed:**
- [x] Access control preserved on UPDATE (existing app keeps `access_level`)
- [x] Access control reset on CREATE (new app gets `AppAccessLevel.AUTHENTICATED`)
- [x] Workflow reference resolution works correctly

**Remaining:**
- [ ] Change input validation from `dict` to `ApplicationDefinition.model_validate()`
  - Current: Parses JSON to dict, validates fields manually
  - Goal: Use `ApplicationDefinition.model_validate(app_data)` for full Pydantic validation
  - This ensures clear validation errors when syncing from git or uploading files

**Why this matters:**
When an app is synced from git or uploaded via the API, the App Indexer should:
1. Parse the JSON
2. Validate against `ApplicationDefinition` Pydantic model
3. Return clear validation errors if the schema doesn't match

**Current code pattern:**
```python
app_data = json.loads(content.decode("utf-8"))
name = app_data.get("name")  # Manual field extraction
```

**Target code pattern:**
```python
from pydantic import ValidationError
from src.models.contracts.app_builder_types import ApplicationDefinition

try:
    app_data = json.loads(content.decode("utf-8"))
    app_def = ApplicationDefinition.model_validate(app_data)
except ValidationError as e:
    logger.warning(f"Invalid app schema in {path}: {e}")
    return False, []  # Or return validation errors
```

**Verification:**
```bash
./test.sh tests/unit/services/file_storage/
./test.sh tests/integration/
```

---

### Task 4: Create Round-Trip Tests ✅ COMPLETE

**File: `api/tests/unit/contracts/test_app_roundtrip.py`**

```python
"""
Round-trip tests for App Builder type unification.

These tests verify that:
1. Discriminated union validates correct props per component type
2. Export → JSON → Import preserves all data
3. camelCase serialization works correctly
"""

import pytest
from pydantic import ValidationError
from src.models.contracts.app_builder_types import (
    ApplicationDefinition,
    PageDefinition,
    LayoutContainer,
    ButtonComponent,
    DataTableComponent,
    HeadingComponent,
    ButtonProps,
    DataTableProps,
    TableColumn,
)


class TestDiscriminatedUnion:
    """Test that discriminated union validates props correctly."""

    def test_button_with_button_props_valid(self):
        """Button component with ButtonProps is valid."""
        btn = ButtonComponent(
            id="btn1",
            type="button",
            props=ButtonProps(label="Click me", action_type="navigate", navigate_to="/home")
        )
        assert btn.type == "button"
        assert btn.props.label == "Click me"

    def test_button_with_wrong_props_fails(self):
        """Button component with DataTable props fails validation."""
        with pytest.raises(ValidationError):
            ButtonComponent(
                id="btn1",
                type="button",
                props=DataTableProps(data_source="clients", columns=[])
            )

    def test_data_table_requires_columns(self):
        """DataTable without columns fails validation."""
        with pytest.raises(ValidationError):
            DataTableComponent(
                id="tbl1",
                type="data-table",
                props={"data_source": "clients"}  # Missing required 'columns'
            )


class TestCamelCaseSerialization:
    """Test camelCase JSON serialization."""

    def test_button_serializes_camelcase(self):
        """Button props serialize with camelCase keys."""
        btn = ButtonComponent(
            id="btn1",
            type="button",
            props=ButtonProps(
                label="Submit",
                action_type="workflow",
                workflow_id="wf-123",
                on_complete=[{"type": "navigate", "navigate_to": "/done"}]
            ),
            loading_workflows=["wf-123"]
        )
        json_data = btn.model_dump(mode="json", by_alias=True)

        assert "actionType" in json_data["props"]
        assert "action_type" not in json_data["props"]
        assert "workflowId" in json_data["props"]
        assert "loadingWorkflows" in json_data
        assert "loading_workflows" not in json_data

    def test_layout_serializes_camelcase(self):
        """Layout container serializes with camelCase keys."""
        layout = LayoutContainer(
            id="layout1",
            type="column",
            gap=16,
            max_width="lg",
            sticky_offset=10,
            children=[]
        )
        json_data = layout.model_dump(mode="json", by_alias=True)

        assert "maxWidth" in json_data
        assert "max_width" not in json_data
        assert "stickyOffset" in json_data


class TestRoundTrip:
    """Test export → JSON → import preserves all data."""

    def test_simple_app_roundtrip(self):
        """Simple app survives round-trip."""
        app = ApplicationDefinition(
            id="app-1",
            name="Test App",
            slug="test-app",
            description="A test application",
            pages=[
                PageDefinition(
                    id="home",
                    title="Home",
                    path="/",
                    layout=LayoutContainer(
                        id="root",
                        type="column",
                        children=[
                            HeadingComponent(
                                id="h1",
                                type="heading",
                                props={"text": "Welcome", "level": 1}
                            )
                        ]
                    )
                )
            ]
        )

        # Serialize to JSON
        json_str = app.model_dump_json(by_alias=True)

        # Parse back
        restored = ApplicationDefinition.model_validate_json(json_str)

        assert restored.id == app.id
        assert restored.name == app.name
        assert len(restored.pages) == 1
        assert restored.pages[0].title == "Home"

    def test_complex_nested_layout_roundtrip(self):
        """Complex nested layout survives round-trip."""
        app = ApplicationDefinition(
            id="app-2",
            name="Complex App",
            slug="complex-app",
            pages=[
                PageDefinition(
                    id="dashboard",
                    title="Dashboard",
                    path="/dashboard",
                    layout=LayoutContainer(
                        id="root",
                        type="column",
                        gap=24,
                        children=[
                            LayoutContainer(
                                id="stats-row",
                                type="row",
                                gap=16,
                                distribute="equal",
                                children=[
                                    # Stat cards would go here
                                ]
                            ),
                            LayoutContainer(
                                id="content",
                                type="row",
                                children=[
                                    LayoutContainer(
                                        id="sidebar",
                                        type="column",
                                        max_width="sm",
                                        children=[]
                                    ),
                                    LayoutContainer(
                                        id="main",
                                        type="column",
                                        children=[
                                            DataTableComponent(
                                                id="clients-table",
                                                type="data-table",
                                                props=DataTableProps(
                                                    data_source="clients",
                                                    columns=[
                                                        TableColumn(key="name", header="Name"),
                                                        TableColumn(key="email", header="Email"),
                                                    ],
                                                    searchable=True,
                                                    paginated=True,
                                                    page_size=20
                                                )
                                            )
                                        ]
                                    )
                                ]
                            )
                        ]
                    )
                )
            ]
        )

        json_str = app.model_dump_json(by_alias=True)
        restored = ApplicationDefinition.model_validate_json(json_str)

        # Verify nested structure
        assert len(restored.pages[0].layout.children) == 2
        content_row = restored.pages[0].layout.children[1]
        assert content_row.type == "row"
        assert len(content_row.children) == 2

    def test_export_excludes_access_control(self):
        """Export dict excludes organization_id, access_level, role_ids."""
        app = ApplicationDefinition(
            id="app-3",
            name="Secured App",
            slug="secured-app",
            organization_id="org-123",
            access_level="role_based",
            role_ids=["role-1", "role-2"],
            pages=[]
        )

        export_dict = app.to_export_dict()

        assert "organizationId" not in export_dict
        assert "organization_id" not in export_dict
        assert "accessLevel" not in export_dict
        assert "roleIds" not in export_dict


class TestAllComponentTypes:
    """Test each component type can be created and round-tripped."""

    @pytest.mark.parametrize("component_type,props", [
        ("heading", {"text": "Hello", "level": 1}),
        ("text", {"text": "Body text"}),
        ("html", {"content": "<div>HTML</div>"}),
        ("button", {"label": "Click", "action_type": "navigate"}),
        ("divider", {}),
        ("spacer", {"size": 24}),
        ("badge", {"text": "New"}),
        ("progress", {"value": 75}),
        ("image", {"src": "/img.png"}),
        ("card", {"title": "Card Title"}),
        ("stat-card", {"title": "Users", "value": "1,234"}),
        ("text-input", {"field_id": "name"}),
        ("number-input", {"field_id": "age"}),
        ("select", {"field_id": "country", "options": []}),
        ("checkbox", {"field_id": "agree", "label": "I agree"}),
        ("data-table", {"data_source": "items", "columns": [{"key": "id", "header": "ID"}]}),
        ("tabs", {"items": [{"id": "tab1", "label": "Tab 1", "content": {"id": "c", "type": "column", "children": []}}]}),
        ("file-viewer", {"src": "/doc.pdf"}),
        ("modal", {"title": "Dialog", "content": {"id": "m", "type": "column", "children": []}}),
        ("form-embed", {"form_id": "form-123"}),
        ("form-group", {"children": []}),
    ])
    def test_component_roundtrip(self, component_type, props):
        """Each component type survives round-trip."""
        # This test will be implemented once all component models exist
        pass  # Placeholder - implement after Task 1
```

**Verification:**
```bash
./test.sh tests/unit/contracts/test_app_roundtrip.py -v
```

---

### Task 5: Migrate Frontend to Generated Types ✅ COMPLETE

**Goal: Delete `client/src/lib/app-builder-types.ts` and have frontend compile.** ✅ ACHIEVED

**Step 1: Regenerate types**
```bash
cd client && npm run generate:types
```

**Step 2: Find all imports of app-builder-types.ts**
```bash
grep -r "from.*app-builder-types" client/src/
```

**Step 3: Update each file to import from v1.d.ts**

The generated types will be in `client/src/lib/v1.d.ts` under `components["schemas"]`.

Import pattern:
```typescript
// Before
import type { AppComponent, LayoutContainer, ComponentType } from "@/lib/app-builder-types";

// After
import type { components } from "@/lib/v1";

type AppComponent = components["schemas"]["AppComponent"];
type LayoutContainer = components["schemas"]["LayoutContainer"];
type ComponentType = components["schemas"]["ComponentType"];
```

**Files to update (from grep):**
- `client/src/components/app-builder/ComponentRegistry.tsx`
- `client/src/components/app-builder/LayoutRenderer.tsx`
- `client/src/components/app-builder/AppRenderer.tsx`
- `client/src/components/app-builder/AppShell.tsx`
- `client/src/components/app-builder/editor/*.tsx` (multiple files)
- `client/src/components/app-builder/components/*.tsx` (multiple files)
- `client/src/lib/expression-parser.ts`
- `client/src/hooks/usePageData.ts`

**Step 4: Delete app-builder-types.ts**
```bash
rm client/src/lib/app-builder-types.ts
```

**Step 5: Verify**
```bash
cd client && npm run tsc
```

**Step 6: Manual testing**
- Start dev server: `./debug.sh`
- Navigate to app builder
- Create/edit an app
- Verify all component types work

---

## Files Summary

| File | Action | Status |
|------|--------|--------|
| `api/src/models/contracts/app_builder_types.py` | All typed models with Field descriptions | ✅ Complete |
| `api/src/models/contracts/applications.py` | Import from app_builder_types | ✅ Complete |
| `api/src/models/contracts/base.py` | Shared CamelModel base | ✅ Complete |
| `api/src/services/file_storage/indexers/app.py` | Add Pydantic validation | ✅ Complete |
| `api/tests/unit/contracts/test_app_roundtrip.py` | Round-trip tests | ✅ Complete |
| `client/src/lib/app-builder-types.ts` | **DELETED** | ✅ Complete |
| `client/src/components/app-builder/**/*.tsx` | Updated imports to v1.d.ts | ✅ Complete |
| `client/src/lib/expression-parser.ts` | Updated imports | ✅ Complete |
| `client/src/hooks/usePageData.ts` | Updated imports | ✅ Complete |

---

## Verification Commands

```bash
# Backend type checking
cd api && pyright

# Backend tests
./test.sh tests/unit/contracts/test_app_roundtrip.py -v
./test.sh tests/unit/ -v

# Regenerate frontend types
cd client && npm run generate:types

# Frontend type checking (THE KEY TEST)
cd client && npm run tsc

# Full test suite
./test.sh
```

---

## Success Criteria

- [x] All 22 component types have typed props models in Pydantic
- [x] Discriminated union validates correct props per component type
- [x] Round-trip tests pass for all component types
- [x] Access control preserved on app update, reset on create
- [x] **`app-builder-types.ts` is DELETED**
- [x] All frontend imports updated to use `@/lib/v1`
- [x] `npm run tsc` passes with zero errors
- [ ] App builder works in browser (manual verification)
- [x] App Indexer uses Pydantic validation (Task 6 complete)

---

## Remaining Work (From Review)

### Task 6: App Indexer Pydantic Validation ✅ COMPLETE

**Priority: HIGH** - For clear validation errors when syncing from git or uploading files

- [x] **Task 6.1**: Update App Indexer to use `ApplicationDefinition.model_validate()`
  - File: `api/src/services/file_storage/indexers/app.py`
  - Added Pydantic validation after JSON parsing, before workflow ref resolution
  - Clear error messages when app schema is invalid
  - Fixed deprecated `datetime.utcnow()` to use `datetime.now(tz=timezone.utc)`

**Implementation:**
```python
from pydantic import ValidationError
from src.models.contracts.app_builder_types import ApplicationDefinition

async def index_app(self, path: str, content: bytes, ...) -> tuple[bool, list[UnresolvedRef]]:
    try:
        app_data = json.loads(content.decode("utf-8"))
        # Validate with Pydantic
        app_def = ApplicationDefinition.model_validate(app_data)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in app file {path}: {e}")
        return False, []
    except ValidationError as e:
        logger.warning(f"Invalid app schema in {path}: {e}")
        # Could return validation errors to caller for MCP feedback
        return False, []
```

### Task 7: Clean Up Frontend Navigation Types

**Priority: LOW** - Cleanup for maintainability

- [ ] **Task 7.1**: Remove duplicate NavigationItem types from `app-builder-helpers.ts`
  - Currently has local `NavigationItem` interface
  - Should import from `@/lib/v1` instead

---

## Reference: TypeScript Source File (ARCHIVED)

The frontend types file `client/src/lib/app-builder-types.ts` has been **DELETED**.
All types now come from auto-generated `@/lib/v1.d.ts`.

Original file contained:
- Lines 10-33: `ComponentType` literal union → Now in `app_builder_types.py`
- Lines 35-72: Width, action, layout literals → Now in `app_builder_types.py`
- Lines 177-196: `BaseComponentProps` → Now in `app_builder_types.py`
- Lines 201-826: All component-specific props interfaces → Now in `app_builder_types.py`
- Lines 846-902: `LayoutContainer` → Now in `app_builder_types.py`
- Lines 907-934: `PageDefinition` → Now in `app_builder_types.py`
- Lines 970-1006: `NavigationConfig` → Now in `app_builder_types.py`
- Lines 1011-1030: `ApplicationDefinition` → Now in `app_builder_types.py`
