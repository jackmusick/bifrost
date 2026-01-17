# Unified AppComponent Model Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify the app builder type system by eliminating `LayoutContainer` and making all elements (including row/column/grid) part of the `AppComponent` discriminated union with consistent `children: list[AppComponent]` for containers.

**Architecture:** Replace dual type system (`LayoutContainer` + `AppComponent`) with single `AppComponent` union where container components (row, column, grid, card, modal, tabs, form-group) have `children[]` at top level, and leaf components have no children field. Props move from nested `props: {...}` to top-level fields.

**Tech Stack:** Python/Pydantic (backend models), FastAPI (MCP tools), TypeScript/React (frontend), PostgreSQL (no schema changes needed)

---

## Phase 1: Backend Models

### Task 1.1: Create ComponentBase and Container Components

**Files:**
- Modify: `api/src/models/contracts/app_components.py`

**Step 1: Write failing test for new model structure**

Create test file:
```bash
touch api/tests/unit/test_unified_component_model.py
```

```python
# api/tests/unit/test_unified_component_model.py
"""Unit tests for unified AppComponent model."""
import pytest
from pydantic import ValidationError


def test_row_component_accepts_children():
    """Row component should accept children list."""
    from src.models.contracts.app_components import RowComponent, HeadingComponent

    heading = HeadingComponent(id="h1", text="Hello")
    row = RowComponent(id="row1", children=[heading], gap="md")

    assert row.type == "row"
    assert len(row.children) == 1
    assert row.children[0].id == "h1"


def test_button_component_rejects_children():
    """Button component should reject children field."""
    from src.models.contracts.app_components import ButtonComponent

    with pytest.raises(ValidationError) as exc_info:
        ButtonComponent(id="btn1", label="Click", children=[])

    assert "children" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()


def test_discriminated_union_routes_by_type():
    """AppComponent union should route to correct model by type."""
    from pydantic import TypeAdapter
    from src.models.contracts.app_components import AppComponent

    adapter = TypeAdapter(AppComponent)

    # Row should parse to RowComponent
    row_data = {"id": "r1", "type": "row", "children": [], "gap": "md"}
    row = adapter.validate_python(row_data)
    assert row.__class__.__name__ == "RowComponent"

    # Button should parse to ButtonComponent
    btn_data = {"id": "b1", "type": "button", "label": "Click"}
    btn = adapter.validate_python(btn_data)
    assert btn.__class__.__name__ == "ButtonComponent"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v`

Expected: FAIL - models don't exist yet with new structure

**Step 3: Create ComponentBase model**

In `api/src/models/contracts/app_components.py`, add after the literal types section (~line 95):

```python
# -----------------------------------------------------------------------------
# Component Base (shared fields for all components)
# -----------------------------------------------------------------------------

class ComponentBase(BaseModel):
    """Base fields shared by all components."""

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields

    id: str = Field(description="Unique component identifier")
    width: ComponentWidth | None = Field(default=None, description="Component width")
    visible: str | None = Field(default=None, description="Visibility expression")
    loading_workflows: list[str] | None = Field(
        default=None, description="Workflow IDs that trigger loading state"
    )
    grid_span: int | None = Field(
        default=None, description="Grid column span (for grid layouts)"
    )
    repeat_for: RepeatFor | None = Field(
        default=None, description="Repeat configuration for rendering multiple instances"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")
    style: dict[str, Any] | None = Field(
        default=None, description="Inline CSS styles (camelCase properties)"
    )
```

**Step 4: Create layout container components (row, column, grid)**

```python
# -----------------------------------------------------------------------------
# Layout Components (containers with children)
# -----------------------------------------------------------------------------

class RowComponent(ComponentBase):
    """Row layout component - horizontal flex container."""

    type: Literal["row"] = Field(default="row", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Child components")
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")
    align: LayoutAlign | None = Field(default=None, description="Cross-axis alignment")
    justify: LayoutJustify | None = Field(default=None, description="Main-axis justification")
    distribute: LayoutDistribute | None = Field(default=None, description="Child distribution")
    max_width: LayoutMaxWidth | None = Field(default=None, description="Maximum width")
    max_height: int | None = Field(default=None, description="Maximum height in pixels")
    overflow: LayoutOverflow | None = Field(default=None, description="Overflow behavior")
    sticky: LayoutSticky | None = Field(default=None, description="Sticky positioning")
    sticky_offset: int | None = Field(default=None, description="Sticky offset in pixels")


class ColumnComponent(ComponentBase):
    """Column layout component - vertical flex container."""

    type: Literal["column"] = Field(default="column", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Child components")
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")
    align: LayoutAlign | None = Field(default=None, description="Cross-axis alignment")
    max_width: LayoutMaxWidth | None = Field(default=None, description="Maximum width")
    max_height: int | None = Field(default=None, description="Maximum height in pixels")
    overflow: LayoutOverflow | None = Field(default=None, description="Overflow behavior")
    sticky: LayoutSticky | None = Field(default=None, description="Sticky positioning")
    sticky_offset: int | None = Field(default=None, description="Sticky offset in pixels")


class GridComponent(ComponentBase):
    """Grid layout component."""

    type: Literal["grid"] = Field(default="grid", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Child components")
    columns: int | str = Field(default=3, description="Number of columns or template")
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")
```

**Step 5: Run test to verify partial progress**

Run: `./test.sh api/tests/unit/test_unified_component_model.py::test_row_component_accepts_children -v`

Expected: May still fail due to forward reference issues - fix in next step

**Step 6: Commit**

```bash
git add api/src/models/contracts/app_components.py api/tests/unit/test_unified_component_model.py
git commit -m "feat(app-builder): add ComponentBase and layout components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.2: Convert Content Container Components

**Files:**
- Modify: `api/src/models/contracts/app_components.py`

**Step 1: Write failing test for card with children**

```python
# Add to api/tests/unit/test_unified_component_model.py

def test_card_component_with_children():
    """Card should have children at top level, not in props."""
    from src.models.contracts.app_components import CardComponent, TextComponent

    text = TextComponent(id="t1", text="Hello")
    card = CardComponent(
        id="card1",
        title="My Card",
        children=[text],
    )

    assert card.type == "card"
    assert card.title == "My Card"
    assert len(card.children) == 1


def test_modal_component_with_children():
    """Modal should have children at top level."""
    from src.models.contracts.app_components import ModalComponent, TextComponent

    text = TextComponent(id="t1", text="Modal content")
    modal = ModalComponent(
        id="modal1",
        title="My Modal",
        children=[text],
    )

    assert modal.type == "modal"
    assert len(modal.children) == 1


def test_tabs_with_tab_items():
    """Tabs should contain TabItemComponent children."""
    from src.models.contracts.app_components import TabsComponent, TabItemComponent, TextComponent

    tab1 = TabItemComponent(
        id="tab1",
        label="First",
        value="first",
        children=[TextComponent(id="t1", text="Tab 1 content")],
    )
    tabs = TabsComponent(id="tabs1", children=[tab1])

    assert tabs.type == "tabs"
    assert len(tabs.children) == 1
    assert tabs.children[0].type == "tab-item"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v -k "card or modal or tabs"`

Expected: FAIL - card/modal/tabs don't have new structure

**Step 3: Update CardComponent to use children**

```python
class CardComponent(ComponentBase):
    """Card container component."""

    type: Literal["card"] = Field(default="card", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Card content")
    title: str | None = Field(default=None, description="Card title")
    description: str | None = Field(default=None, description="Card description")
    collapsible: bool = Field(default=False, description="Whether card is collapsible")
    default_collapsed: bool = Field(default=False, description="Initial collapsed state")
    header_actions: list[TableAction] | None = Field(default=None, description="Header action buttons")
```

**Step 4: Update ModalComponent to use children**

```python
class ModalComponent(ComponentBase):
    """Modal dialog component."""

    type: Literal["modal"] = Field(default="modal", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Modal body content")
    title: str = Field(description="Modal title")
    description: str | None = Field(default=None, description="Modal description")
    trigger_label: str | None = Field(default=None, description="Trigger button label")
    trigger_variant: ButtonVariant | None = Field(default=None, description="Trigger button variant")
    trigger_size: ButtonSize | None = Field(default=None, description="Trigger button size")
    size: ModalSize | None = Field(default=None, description="Modal size")
    footer_actions: list[ModalFooterAction] | None = Field(default=None, description="Footer actions")
    show_close_button: bool | None = Field(default=None, description="Show close button")
```

**Step 5: Add TabItemComponent and update TabsComponent**

```python
class TabItemComponent(ComponentBase):
    """Tab item within a Tabs component."""

    type: Literal["tab-item"] = Field(default="tab-item", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Tab content")
    label: str = Field(description="Tab label")
    value: str | None = Field(default=None, description="Tab value (defaults to label)")
    icon: str | None = Field(default=None, description="Tab icon name")


class TabsComponent(ComponentBase):
    """Tabs container component."""

    type: Literal["tabs"] = Field(default="tabs", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="TabItemComponent children")
    default_tab: str | None = Field(default=None, description="Default active tab value")
    orientation: Orientation | None = Field(default=None, description="Tab orientation")
```

**Step 6: Update FormGroupComponent**

```python
class FormGroupComponent(ComponentBase):
    """Form group component for grouping form fields."""

    type: Literal["form-group"] = Field(default="form-group", description="Component type")
    children: list[AppComponent] = Field(default_factory=list, description="Form field components")
    label: str | None = Field(default=None, description="Group label")
    description: str | None = Field(default=None, description="Group description")
    required: bool | None = Field(default=None, description="Whether fields are required")
    direction: Literal["row", "column"] | None = Field(default=None, description="Layout direction")
    gap: int | str | None = Field(default=None, description="Gap between fields")
```

**Step 7: Run tests**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v`

Expected: PASS for card, modal, tabs tests

**Step 8: Commit**

```bash
git add api/src/models/contracts/app_components.py api/tests/unit/test_unified_component_model.py
git commit -m "feat(app-builder): convert container components to use children[]

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.3: Convert Leaf Components (Remove Props Wrapper)

**Files:**
- Modify: `api/src/models/contracts/app_components.py`

**Step 1: Write failing test for leaf component structure**

```python
# Add to api/tests/unit/test_unified_component_model.py

def test_heading_props_at_top_level():
    """Heading should have text/level at top level, not in props."""
    from src.models.contracts.app_components import HeadingComponent

    heading = HeadingComponent(id="h1", text="Hello World", level=2)

    assert heading.type == "heading"
    assert heading.text == "Hello World"
    assert heading.level == 2
    # Should NOT have a props field
    assert not hasattr(heading, "props")


def test_button_props_at_top_level():
    """Button should have label/variant at top level."""
    from src.models.contracts.app_components import ButtonComponent

    btn = ButtonComponent(
        id="btn1",
        label="Submit",
        action_type="workflow",
        workflow_id="wf-123",
        variant="default",
    )

    assert btn.label == "Submit"
    assert btn.action_type == "workflow"
    assert btn.workflow_id == "wf-123"


def test_data_table_props_at_top_level():
    """DataTable should have columns/data_source at top level."""
    from src.models.contracts.app_components import DataTableComponent

    table = DataTableComponent(
        id="table1",
        data_source="users_data",
        columns=[{"key": "name", "header": "Name"}],
        paginated=True,
    )

    assert table.data_source == "users_data"
    assert len(table.columns) == 1
    assert table.paginated is True
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v -k "top_level"`

Expected: FAIL - current components use `props` wrapper

**Step 3: Convert HeadingComponent**

```python
class HeadingComponent(ComponentBase):
    """Heading text component."""

    type: Literal["heading"] = Field(default="heading", description="Component type")
    text: str = Field(description="Heading text (supports expressions)")
    level: HeadingLevel | None = Field(default=None, description="Heading level (1-6)")
```

**Step 4: Convert TextComponent**

```python
class TextComponent(ComponentBase):
    """Text paragraph component."""

    type: Literal["text"] = Field(default="text", description="Component type")
    text: str = Field(description="Text content (supports expressions)")
    label: str | None = Field(default=None, description="Optional label above text")
```

**Step 5: Convert ButtonComponent**

```python
class ButtonComponent(ComponentBase):
    """Button component."""

    type: Literal["button"] = Field(default="button", description="Component type")
    label: str = Field(description="Button label (supports expressions)")
    action_type: ButtonActionType = Field(description="Action type")
    navigate_to: str | None = Field(default=None, description="Navigation path")
    workflow_id: str | None = Field(default=None, description="Workflow ID")
    custom_action_id: str | None = Field(default=None, description="Custom action ID")
    modal_id: str | None = Field(default=None, description="Modal ID to open")
    action_params: dict[str, Any] | None = Field(default=None, description="Action parameters")
    on_complete: list[OnCompleteAction] | None = Field(default=None, description="Post-workflow actions")
    on_error: list[OnCompleteAction] | None = Field(default=None, description="Error handling actions")
    variant: ButtonVariant | None = Field(default=None, description="Button variant")
    size: ButtonSize | None = Field(default=None, description="Button size")
    disabled: bool | str | None = Field(default=None, description="Disabled state or expression")
    icon: str | None = Field(default=None, description="Icon name")

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)
```

**Step 6: Convert remaining leaf components**

Continue pattern for: HtmlComponent, DividerComponent, SpacerComponent, ImageComponent, BadgeComponent, ProgressComponent, DataTableComponent, StatCardComponent, FileViewerComponent, TextInputComponent, NumberInputComponent, SelectComponent, CheckboxComponent, FormEmbedComponent.

Each follows pattern:
1. Extend `ComponentBase`
2. Add `type: Literal["component-type"]`
3. Move fields from `XxxProps` to top level
4. Remove `props: XxxProps` field
5. Keep any `@field_serializer` decorators

**Step 7: Run tests**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v`

Expected: PASS

**Step 8: Commit**

```bash
git add api/src/models/contracts/app_components.py api/tests/unit/test_unified_component_model.py
git commit -m "feat(app-builder): flatten leaf component props to top level

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.4: Update AppComponent Union and PageDefinition

**Files:**
- Modify: `api/src/models/contracts/app_components.py`

**Step 1: Write failing test for complete union**

```python
# Add to api/tests/unit/test_unified_component_model.py

def test_app_component_union_includes_layouts():
    """AppComponent union should include row, column, grid."""
    from pydantic import TypeAdapter
    from src.models.contracts.app_components import AppComponent

    adapter = TypeAdapter(AppComponent)

    # All these should parse successfully
    row = adapter.validate_python({"id": "r1", "type": "row", "children": []})
    col = adapter.validate_python({"id": "c1", "type": "column", "children": []})
    grid = adapter.validate_python({"id": "g1", "type": "grid", "children": []})

    assert row.type == "row"
    assert col.type == "column"
    assert grid.type == "grid"


def test_page_definition_has_children():
    """PageDefinition should have children instead of layout."""
    from src.models.contracts.app_components import PageDefinition, ColumnComponent

    page = PageDefinition(
        id="page1",
        title="Home",
        path="/",
        children=[ColumnComponent(id="col1", children=[])],
    )

    assert len(page.children) == 1
    assert page.children[0].type == "column"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v -k "union or page_definition"`

Expected: FAIL

**Step 3: Update AppComponent union**

```python
# -----------------------------------------------------------------------------
# Discriminated Union of All Components
# -----------------------------------------------------------------------------

AppComponent = Annotated[
    Union[
        # Layout containers
        RowComponent,
        ColumnComponent,
        GridComponent,
        # Content containers
        CardComponent,
        ModalComponent,
        TabsComponent,
        TabItemComponent,
        FormGroupComponent,
        # Leaf components
        HeadingComponent,
        TextComponent,
        HtmlComponent,
        ButtonComponent,
        DividerComponent,
        SpacerComponent,
        ImageComponent,
        BadgeComponent,
        ProgressComponent,
        DataTableComponent,
        StatCardComponent,
        FileViewerComponent,
        TextInputComponent,
        NumberInputComponent,
        SelectComponent,
        CheckboxComponent,
        FormEmbedComponent,
    ],
    Field(discriminator="type"),
]
```

**Step 4: Update PageDefinition**

```python
class PageDefinition(BaseModel):
    """Page definition for the app builder."""

    id: str = Field(description="Page identifier")
    title: str = Field(description="Page title")
    path: str = Field(description="Page path/route")
    children: list[AppComponent] = Field(
        default_factory=list,
        description="Page content - direct children like HTML body"
    )
    data_sources: list[DataSourceConfig] = Field(
        default_factory=list, description="Data sources configured for this page"
    )
    variables: dict[str, Any] | None = Field(
        default=None, description="Initial page variables"
    )
    launch_workflow_id: str | None = Field(
        default=None, description="Workflow to execute on page mount"
    )
    launch_workflow_params: dict[str, Any] | None = Field(
        default=None, description="Parameters for launch workflow"
    )
    launch_workflow_data_source_id: str | None = Field(
        default=None, description="Data source ID for workflow results"
    )
    launch_workflow: LaunchWorkflowConfig | None = Field(
        default=None, description="Alternative nested format for launch workflow"
    )
    styles: str | None = Field(
        default=None, description="Page-level CSS styles"
    )
    permission: PagePermission | None = Field(
        default=None, description="Page-level permissions"
    )

    @field_serializer("launch_workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)
```

**Step 5: Fix forward references**

Add at end of file:
```python
# Rebuild models for forward references
RowComponent.model_rebuild()
ColumnComponent.model_rebuild()
GridComponent.model_rebuild()
CardComponent.model_rebuild()
ModalComponent.model_rebuild()
TabsComponent.model_rebuild()
TabItemComponent.model_rebuild()
FormGroupComponent.model_rebuild()
```

**Step 6: Run tests**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v`

Expected: PASS

**Step 7: Commit**

```bash
git add api/src/models/contracts/app_components.py api/tests/unit/test_unified_component_model.py
git commit -m "feat(app-builder): update AppComponent union and PageDefinition

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.5: Remove Legacy Types

**Files:**
- Modify: `api/src/models/contracts/app_components.py`

**Step 1: Identify legacy types to remove**

These should be removed or deprecated:
- `LayoutContainer` class
- `LayoutContainerOrComponent` union
- `LayoutElement` alias
- All `*Props` classes (HeadingProps, ButtonProps, etc.)
- `is_layout_container()` function
- `is_app_component()` function
- `can_have_children()` function
- `CONTAINER_TYPES` constant
- `AppComponentNode` class

**Step 2: Remove LayoutContainer and related**

Delete:
```python
# DELETE these sections:
# - LayoutContainerOrComponent union
# - LayoutContainer class
# - LayoutElement alias
# - is_layout_container() function
# - is_app_component() function
# - can_have_children() function
# - CONTAINER_TYPES constant
```

**Step 3: Remove Props classes**

Delete all `*Props` classes:
- HeadingProps, TextProps, HtmlProps, CardProps, DividerProps, SpacerProps
- ButtonProps, StatCardProps, ImageProps, BadgeProps, ProgressProps
- DataTableProps, TabsProps, FileViewerProps, ModalProps
- TextInputProps, NumberInputProps, SelectProps, CheckboxProps
- FormEmbedProps, FormGroupProps

**Step 4: Update TabItem to reference AppComponent**

```python
class TabItem(BaseModel):
    """Legacy tab item for backwards compatibility during migration."""
    id: str = Field(description="Tab ID")
    label: str = Field(description="Tab label")
    icon: str | None = Field(default=None, description="Tab icon")
    # Keep for migration, but TabItemComponent is preferred
```

**Step 5: Run all model tests**

Run: `./test.sh api/tests/unit/test_unified_component_model.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add api/src/models/contracts/app_components.py
git commit -m "refactor(app-builder): remove legacy LayoutContainer and Props classes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: App Builder Service

### Task 2.1: Simplify Tree Flattening

**Files:**
- Modify: `api/src/services/app_builder_service.py`
- Test: `api/tests/unit/test_app_builder_service.py`

**Step 1: Write failing test for new flatten function**

```python
# api/tests/unit/test_app_builder_service.py
"""Unit tests for simplified app builder service."""
import pytest
from uuid import uuid4


def test_flatten_components_simple():
    """Flatten a simple component list."""
    from src.services.app_builder_service import flatten_components
    from src.models.contracts.app_components import ColumnComponent, HeadingComponent

    page_id = uuid4()
    components = [
        ColumnComponent(
            id="col1",
            children=[
                HeadingComponent(id="h1", text="Hello"),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    # Should have 2 rows: column and heading
    assert len(rows) == 2

    col_row = next(r for r in rows if r["component_id"] == "col1")
    heading_row = next(r for r in rows if r["component_id"] == "h1")

    assert col_row["type"] == "column"
    assert col_row["parent_id"] is None

    assert heading_row["type"] == "heading"
    assert heading_row["parent_id"] == col_row["id"]


def test_flatten_components_nested():
    """Flatten nested containers."""
    from src.services.app_builder_service import flatten_components
    from src.models.contracts.app_components import RowComponent, CardComponent, TextComponent

    page_id = uuid4()
    components = [
        RowComponent(
            id="row1",
            children=[
                CardComponent(
                    id="card1",
                    title="Card",
                    children=[
                        TextComponent(id="t1", text="Content"),
                    ],
                ),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    # Should have 3 rows: row, card, text
    assert len(rows) == 3

    row_row = next(r for r in rows if r["component_id"] == "row1")
    card_row = next(r for r in rows if r["component_id"] == "card1")
    text_row = next(r for r in rows if r["component_id"] == "t1")

    assert card_row["parent_id"] == row_row["id"]
    assert text_row["parent_id"] == card_row["id"]
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_app_builder_service.py -v`

Expected: FAIL - function signature changed

**Step 3: Implement simplified flatten_components**

```python
# In api/src/services/app_builder_service.py

from pydantic import TypeAdapter
from src.models.contracts.app_components import AppComponent

def flatten_components(
    components: list[AppComponent],
    page_id: UUID,
    parent_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Flatten nested component tree to flat rows for database storage.

    Each component becomes one row. Container components have their children
    recursively flattened with parent_id pointing to the container's row.

    Args:
        components: List of AppComponent instances
        page_id: Page UUID for all rows
        parent_id: Parent component UUID (None for root level)

    Returns:
        List of dicts ready for AppComponent ORM creation
    """
    rows: list[dict[str, Any]] = []

    for order, component in enumerate(components):
        component_uuid = uuid4()

        # Dump component to dict, excluding children (handled separately)
        component_dict = component.model_dump(exclude_none=True, exclude={"children"})
        component_id = component_dict.pop("id")
        component_type = component_dict.pop("type")

        rows.append({
            "id": component_uuid,
            "page_id": page_id,
            "component_id": component_id,
            "parent_id": parent_id,
            "type": component_type,
            "props": component_dict,  # Everything else becomes props
            "component_order": order,
            "visible": component_dict.pop("visible", None),
            "width": component_dict.pop("width", None),
            "loading_workflows": component_dict.pop("loading_workflows", None),
        })

        # Recursively flatten children if present
        if hasattr(component, "children") and component.children:
            child_rows = flatten_components(
                component.children,
                page_id,
                parent_id=component_uuid
            )
            rows.extend(child_rows)

    return rows
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/test_app_builder_service.py::test_flatten_components_simple -v`

Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/app_builder_service.py api/tests/unit/test_app_builder_service.py
git commit -m "feat(app-builder): implement simplified flatten_components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.2: Simplify Tree Building

**Files:**
- Modify: `api/src/services/app_builder_service.py`
- Test: `api/tests/unit/test_app_builder_service.py`

**Step 1: Write failing test for build_component_tree**

```python
# Add to api/tests/unit/test_app_builder_service.py

def test_build_component_tree_simple():
    """Build tree from flat rows."""
    from src.services.app_builder_service import build_component_tree
    from uuid import uuid4

    # Simulate ORM objects
    class FakeComponent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    row_id = uuid4()
    heading_id = uuid4()

    flat = [
        FakeComponent(
            id=row_id,
            component_id="row1",
            parent_id=None,
            type="row",
            props={"gap": "md"},
            component_order=0,
            visible=None,
            width=None,
            loading_workflows=None,
        ),
        FakeComponent(
            id=heading_id,
            component_id="h1",
            parent_id=row_id,
            type="heading",
            props={"text": "Hello", "level": 2},
            component_order=0,
            visible=None,
            width=None,
            loading_workflows=None,
        ),
    ]

    tree = build_component_tree(flat)

    assert len(tree) == 1
    assert tree[0].type == "row"
    assert tree[0].id == "row1"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].type == "heading"
    assert tree[0].children[0].text == "Hello"


def test_build_and_flatten_roundtrip():
    """Flatten then build should produce equivalent tree."""
    from src.services.app_builder_service import flatten_components, build_component_tree
    from src.models.contracts.app_components import ColumnComponent, HeadingComponent, TextComponent
    from uuid import uuid4

    class FakeComponent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    original = [
        ColumnComponent(
            id="col1",
            gap="lg",
            children=[
                HeadingComponent(id="h1", text="Title", level=1),
                TextComponent(id="t1", text="Body text"),
            ],
        ),
    ]

    page_id = uuid4()
    flat_rows = flatten_components(original, page_id)

    # Convert dicts to fake ORM objects
    fake_orm = [FakeComponent(**row) for row in flat_rows]

    rebuilt = build_component_tree(fake_orm)

    assert len(rebuilt) == 1
    assert rebuilt[0].type == "column"
    assert rebuilt[0].gap == "lg"
    assert len(rebuilt[0].children) == 2
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/test_app_builder_service.py -v -k "build"`

Expected: FAIL

**Step 3: Implement simplified build_component_tree**

```python
def build_component_tree(
    flat_components: list[Any],  # AppComponent ORM objects
    parent_id: UUID | None = None,
) -> list[AppComponent]:
    """
    Build nested component tree from flat database rows.

    Args:
        flat_components: List of AppComponent ORM instances
        parent_id: Parent UUID to filter by (None for root level)

    Returns:
        List of validated AppComponent instances with nested children
    """
    adapter = TypeAdapter(AppComponent)

    # Filter to children of this parent
    children = [c for c in flat_components if c.parent_id == parent_id]
    children.sort(key=lambda c: c.component_order)

    result: list[AppComponent] = []
    for comp in children:
        # Build component data dict
        component_data = {
            "id": comp.component_id,
            "type": comp.type,
            **comp.props,  # Spread props to top level
        }

        # Add common fields if present
        if comp.visible:
            component_data["visible"] = comp.visible
        if comp.width:
            component_data["width"] = comp.width
        if comp.loading_workflows:
            component_data["loading_workflows"] = comp.loading_workflows

        # Recursively build children for containers
        nested_children = build_component_tree(flat_components, parent_id=comp.id)
        if nested_children:
            component_data["children"] = nested_children

        # Validate through discriminated union
        validated = adapter.validate_python(component_data)
        result.append(validated)

    return result
```

**Step 4: Run tests**

Run: `./test.sh api/tests/unit/test_app_builder_service.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/app_builder_service.py api/tests/unit/test_app_builder_service.py
git commit -m "feat(app-builder): implement simplified build_component_tree

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.3: Update Service Methods to Use New Functions

**Files:**
- Modify: `api/src/services/app_builder_service.py`

**Step 1: Update create_page to use flatten_components**

Find `create_page` method and update to:
```python
async def create_page(
    self,
    app_id: UUID,
    page_data: dict[str, Any],
) -> AppPage:
    """Create a new page with optional children."""
    # ... existing validation ...

    # Create page record
    page = AppPage(...)
    self.db.add(page)
    await self.db.flush()

    # Flatten children to component rows
    children = page_data.get("children", [])
    if children:
        # Validate through PageDefinition or list[AppComponent]
        adapter = TypeAdapter(list[AppComponent])
        validated_children = adapter.validate_python(children)

        component_rows = flatten_components(validated_children, page.id)
        for row in component_rows:
            comp = AppComponent(**row)
            self.db.add(comp)

    await self.db.commit()
    return page
```

**Step 2: Update get_page to use build_component_tree**

Find `get_page_definition` or equivalent and update:
```python
async def get_page_definition(
    self,
    app_id: UUID,
    page_id: str,
) -> PageDefinition:
    """Get page with component tree."""
    page = await self._get_page(app_id, page_id)

    # Load components
    components = await self.db.execute(
        select(AppComponent)
        .where(AppComponent.page_id == page.id)
    )
    flat_components = components.scalars().all()

    # Build tree
    children = build_component_tree(list(flat_components))

    return PageDefinition(
        id=page.page_id,
        title=page.title,
        path=page.path,
        children=children,
        data_sources=[DataSourceConfig(**ds) for ds in page.data_sources],
        variables=page.variables,
        # ... other fields ...
    )
```

**Step 3: Remove old flatten_layout_tree function**

Delete the old ~200 line `flatten_layout_tree` function with all its special cases.

**Step 4: Remove old build_layout_tree function**

Delete the old tree building function.

**Step 5: Run integration tests**

Run: `./test.sh api/tests/e2e/api/test_app_components.py -v`

Expected: Some tests may fail due to API contract changes - fix in next phase

**Step 6: Commit**

```bash
git add api/src/services/app_builder_service.py
git commit -m "refactor(app-builder): update service to use simplified tree functions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: MCP Tools

### Task 3.1: Update Page MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/pages.py`

**Step 1: Update create_page tool**

Change from `layout: LayoutContainer` to `children: list[AppComponent]`:

```python
async def create_page(
    self,
    app_id: str,
    page_id: str,
    title: str,
    path: str,
    children: list[dict[str, Any]] | None = None,  # Changed from layout
    data_sources: list[dict[str, Any]] | None = None,
    # ... other params ...
) -> dict[str, Any]:
    """
    Create a new page in an application.

    Args:
        app_id: Application ID
        page_id: Unique page identifier
        title: Page title
        path: URL path for the page
        children: Page content as list of AppComponent dicts
        ...
    """
    # Validate children through discriminated union
    validated_children = []
    if children:
        adapter = TypeAdapter(list[AppComponent])
        validated_children = adapter.validate_python(children)

    # ... rest of implementation ...
```

**Step 2: Update update_page tool**

```python
async def update_page(
    self,
    app_id: str,
    page_id: str,
    children: list[dict[str, Any]] | None = None,  # Changed from layout
    # ... other params ...
) -> dict[str, Any]:
    """Update an existing page."""
    # Similar changes
```

**Step 3: Run MCP tool tests**

Run: `./test.sh api/tests/e2e/api/test_app_components.py -v`

Expected: Tests should pass with updated contracts

**Step 4: Commit**

```bash
git add api/src/services/mcp_server/tools/pages.py
git commit -m "feat(mcp): update page tools to use children instead of layout

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3.2: Update Component MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/components.py` (if exists, else pages.py)

**Step 1: Update create_component tool**

Ensure validation uses `TypeAdapter(AppComponent)`:

```python
async def create_component(
    self,
    app_id: str,
    page_id: str,
    component: dict[str, Any],
) -> dict[str, Any]:
    """Create a component on a page."""
    # Validate through discriminated union
    adapter = TypeAdapter(AppComponent)
    validated = adapter.validate_python(component)

    # Check if trying to add children to a leaf
    if "children" in component and not hasattr(validated, "children"):
        raise ValueError(f"Component type '{validated.type}' cannot have children")

    # ... rest of implementation ...
```

**Step 2: Update update_component tool**

Similar validation pattern.

**Step 3: Update get_app_schema tool**

Update schema documentation to reflect:
- No `LayoutContainer` type
- All components in single union
- Container vs leaf distinction

**Step 4: Run tests**

Run: `./test.sh api/tests/e2e/api/test_app_components.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/
git commit -m "feat(mcp): update component tools for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: File Storage / Serialization

### Task 4.1: Update AppIndexer (Import)

**Files:**
- Modify: `api/src/services/file_storage/indexers/app.py`

**Step 1: Update _create_components method**

```python
async def _create_components(
    self,
    components: list[dict[str, Any]],
    page_id: UUID,
    parent_id: UUID | None = None,
) -> None:
    """Recursively create component records from nested tree."""
    adapter = TypeAdapter(AppComponent)

    for order, comp_data in enumerate(components):
        # Pop children before validation (handled recursively)
        children = comp_data.pop("children", [])

        # Validate component
        validated = adapter.validate_python({**comp_data, "children": []})

        # Create record
        component_uuid = uuid4()
        record = AppComponent(
            id=component_uuid,
            page_id=page_id,
            component_id=comp_data["id"],
            parent_id=parent_id,
            type=validated.type,
            props=validated.model_dump(exclude={"id", "type", "children"}),
            component_order=order,
        )
        self.db.add(record)

        # Recurse for children
        if children:
            await self._create_components(children, page_id, component_uuid)
```

**Step 2: Update index_app to use children instead of layout**

```python
# In index_app method, change:
layout = page_data.get("layout")
if layout:
    await self._create_components_from_layout(page.id, layout, parent_id=None)

# To:
children = page_data.get("children", [])
if children:
    await self._create_components(children, page.id, parent_id=None)
```

**Step 3: Run indexer tests**

Run: `./test.sh api/tests/unit/ -v -k "index"`

Expected: PASS (or update tests)

**Step 4: Commit**

```bash
git add api/src/services/file_storage/indexers/app.py
git commit -m "refactor(indexer): update AppIndexer for unified component model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4.2: Update Serialization (Export)

**Files:**
- Modify: `api/src/services/file_storage/indexers/app.py`
- Modify: `api/src/services/github_sync_virtual_files.py`

**Step 1: Update _serialize_app_to_json**

```python
def _serialize_app_to_json(
    app: Application,
    pages_data: list[dict[str, Any]],
    workflow_map: dict[str, str] | None = None,
) -> bytes:
    """Serialize app to JSON with proper component tree structure."""
    context = {"workflow_map": workflow_map} if workflow_map else None

    serialized_pages = []
    for page_dict in pages_data:
        # Children should already be a tree structure
        page_def = PageDefinition.model_validate(page_dict)
        serialized_pages.append(
            page_def.model_dump(mode="json", context=context, exclude_none=True)
        )

    app_data = {
        "id": str(app.id),
        "name": app.name,
        "slug": app.slug,
        "description": app.description,
        "icon": app.icon,
        "navigation": app.navigation or {},
        "permissions": app.permissions or {},
        "pages": serialized_pages,
        "export_version": "2.0",  # Bump version for new format
    }

    return json.dumps(app_data, indent=2).encode("utf-8")
```

**Step 2: Ensure VirtualFileProvider builds tree correctly**

The page serialization should use `build_component_tree` to construct nested structure from flat rows.

**Step 3: Run serialization tests**

Run: `./test.sh api/tests/ -v -k "serial or export"`

Expected: PASS

**Step 4: Commit**

```bash
git add api/src/services/file_storage/ api/src/services/github_sync_virtual_files.py
git commit -m "refactor(serialization): update export for unified component model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 5: Frontend Refactoring

### Task 5.1: Regenerate TypeScript Types

**Step 1: Ensure API is running**

```bash
docker ps | grep bifrost
# If not running: ./debug.sh
```

**Step 2: Regenerate types**

```bash
cd client && npm run generate:types
```

**Step 3: Review generated types**

Check `client/src/lib/v1.d.ts` for:
- `RowComponent`, `ColumnComponent`, `GridComponent` in union
- No `LayoutContainer` type
- All components have flat structure (no `props` wrapper)
- Container components have `children?: AppComponent[]`

**Step 4: Commit**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore(types): regenerate TypeScript types for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.2: Update app-builder-utils.ts

**Files:**
- Modify: `client/src/lib/app-builder-utils.ts`

**Step 1: Update type guards**

```typescript
// Remove isLayoutContainer - no longer needed

// Update canHaveChildren to check for children field
export function canHaveChildren(component: AppComponent): boolean {
  return 'children' in component;
}

// Update getChildren
export function getChildren(component: AppComponent): AppComponent[] {
  if ('children' in component) {
    return (component as any).children || [];
  }
  return [];
}

// Remove CONTAINER_TYPES constant or update to derive from types
```

**Step 2: Run TypeScript compilation**

```bash
cd client && npm run tsc
```

Expected: Errors - fix in next tasks

**Step 3: Commit partial progress**

```bash
git add client/src/lib/app-builder-utils.ts
git commit -m "refactor(frontend): update app-builder-utils for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.3: Update app-builder-tree.ts

**Files:**
- Modify: `client/src/lib/app-builder-tree.ts`

**Step 1: Simplify tree operations**

Remove all `isLayoutContainer()` checks and replace with `canHaveChildren()`:

```typescript
export function insertIntoTree(
  tree: AppComponent[],
  component: AppComponent,
  targetId: string,
  position: 'before' | 'after' | 'inside',
): AppComponent[] {
  return tree.map(node => {
    if (node.id === targetId) {
      if (position === 'inside') {
        if (!canHaveChildren(node)) {
          throw new Error(`Cannot insert inside ${node.type} - it doesn't support children`);
        }
        return {
          ...node,
          children: [...getChildren(node), component],
        };
      }
      // before/after handled at parent level
    }

    if (canHaveChildren(node)) {
      return {
        ...node,
        children: insertIntoTree(getChildren(node), component, targetId, position),
      };
    }

    return node;
  });
}
```

**Step 2: Run TypeScript compilation**

```bash
cd client && npm run tsc
```

Fix any remaining errors.

**Step 3: Commit**

```bash
git add client/src/lib/app-builder-tree.ts
git commit -m "refactor(frontend): simplify tree operations for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.4: Refactor LayoutRenderer

**Files:**
- Modify: `client/src/components/app-builder/LayoutRenderer.tsx`
- Rename to: `client/src/components/app-builder/ComponentRenderer.tsx`

**Step 1: Create unified renderer**

```typescript
// client/src/components/app-builder/ComponentRenderer.tsx
import { ComponentRegistry } from './ComponentRegistry';
import type { AppComponent } from '@/lib/v1';

interface ComponentRendererProps {
  component: AppComponent;
  context: RenderContext;
}

export function ComponentRenderer({ component, context }: ComponentRendererProps) {
  const Component = ComponentRegistry[component.type];

  if (!Component) {
    console.warn(`Unknown component type: ${component.type}`);
    return null;
  }

  // Render children if this is a container
  const renderChildren = (children?: AppComponent[]) => {
    if (!children) return null;
    return children.map(child => (
      <ComponentRenderer key={child.id} component={child} context={context} />
    ));
  };

  return (
    <Component
      {...component}
      context={context}
      renderChildren={renderChildren}
    />
  );
}
```

**Step 2: Update ComponentRegistry**

```typescript
// client/src/components/app-builder/ComponentRegistry.tsx
export const ComponentRegistry: Record<string, React.FC<any>> = {
  // Layout containers
  row: RowComponent,
  column: ColumnComponent,
  grid: GridComponent,

  // Content containers
  card: CardComponent,
  modal: ModalComponent,
  tabs: TabsComponent,
  'tab-item': TabItemComponent,
  'form-group': FormGroupComponent,

  // Leaf components
  heading: HeadingComponent,
  text: TextComponent,
  html: HtmlComponent,
  button: ButtonComponent,
  // ... rest
};
```

**Step 3: Update layout components to use renderChildren**

```typescript
// Example: RowComponent.tsx
interface RowComponentProps {
  children?: AppComponent[];
  gap?: string | number;
  align?: string;
  justify?: string;
  renderChildren: (children?: AppComponent[]) => React.ReactNode;
}

export function RowComponent({
  children,
  gap,
  align,
  justify,
  renderChildren
}: RowComponentProps) {
  return (
    <div className={cn(
      "flex flex-row",
      gap && `gap-${gap}`,
      align && `items-${align}`,
      justify && `justify-${justify}`,
    )}>
      {renderChildren(children)}
    </div>
  );
}
```

**Step 4: Run TypeScript compilation**

```bash
cd client && npm run tsc
```

**Step 5: Run frontend tests**

```bash
cd client && npm test
```

**Step 6: Commit**

```bash
git add client/src/components/app-builder/
git commit -m "refactor(frontend): create unified ComponentRenderer

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.5: Update Page Rendering

**Files:**
- Modify: `client/src/components/app-builder/PageRenderer.tsx` (or equivalent)

**Step 1: Update to render children directly**

```typescript
export function PageRenderer({ page }: { page: PageDefinition }) {
  const context = useRenderContext(page);

  return (
    <div className="page-content">
      {page.children?.map(component => (
        <ComponentRenderer
          key={component.id}
          component={component}
          context={context}
        />
      ))}
    </div>
  );
}
```

**Step 2: Run full frontend build**

```bash
cd client && npm run build
```

**Step 3: Commit**

```bash
git add client/src/components/app-builder/
git commit -m "refactor(frontend): update PageRenderer for children

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 6: Integration Testing

### Task 6.1: Run Full E2E Test Suite

**Step 1: Start test environment**

```bash
./test.sh --e2e
```

**Step 2: Fix any failures**

Review failures and fix. Common issues:
- API contract changes
- Missing type conversions
- Frontend component props

**Step 3: Commit fixes**

```bash
git add .
git commit -m "fix: resolve E2E test failures for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6.2: Run Playwright E2E Tests

**Step 1: Run client E2E tests**

```bash
./test.sh --client
```

**Step 2: Fix any UI issues**

Review screenshots, fix component rendering.

**Step 3: Commit fixes**

```bash
git add .
git commit -m "fix: resolve Playwright test failures

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6.3: Manual Testing Checklist

**Step 1: Test app builder in browser**

- [ ] Create new page
- [ ] Add row/column/grid layouts
- [ ] Add components inside layouts
- [ ] Nest containers (card inside row)
- [ ] Edit component props
- [ ] Move components via drag-drop
- [ ] Delete components
- [ ] Save and reload page

**Step 2: Test MCP operations**

- [ ] Create app via MCP
- [ ] Create page with nested children
- [ ] Update component props
- [ ] Export app to JSON
- [ ] Import app from JSON

**Step 3: Document any issues**

Create GitHub issues for any remaining bugs.

**Step 4: Final commit**

```bash
git add .
git commit -m "test: complete manual testing for unified model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Phase | Tasks | Estimated Complexity |
|-------|-------|---------------------|
| 1. Backend Models | 5 tasks | Medium |
| 2. App Builder Service | 3 tasks | Medium |
| 3. MCP Tools | 2 tasks | Low |
| 4. File Storage | 2 tasks | Low |
| 5. Frontend | 5 tasks | High |
| 6. Integration | 3 tasks | Medium |

**Total: 20 tasks**

**Key Risk:** Frontend refactoring is the largest change. Consider feature flag for gradual rollout.

**No database migration needed** - existing `app_components` table supports new model.
