# Unified AppComponent Model Design

## Problem Statement

The app builder currently has two parallel type systems:

1. **LayoutContainer** - for `row`, `column`, `grid` layouts with `children[]`
2. **AppComponent** - for content components, some with children in different places

This creates complexity:

| Component | How Children Are Stored |
|-----------|-------------------------|
| `row`/`column`/`grid` | `children: list[LayoutContainerOrComponent]` (LayoutContainer) |
| Card | `props.children: list[LayoutContainerOrComponent]` |
| Modal | `props.content: LayoutContainer` (single) |
| Tabs | `props.items[].content: LayoutContainer` |
| FormGroup | `props.children: list[AppComponent]` (no layouts!) |

The `app_builder_service.py` has ~400 lines of special-case logic to flatten and rebuild these inconsistent trees. The frontend duplicates this with `isLayoutContainer()` checks everywhere.

## Solution

**Normalize everything to `AppComponent` with consistent `children: list[AppComponent]`.**

- Remove `LayoutContainer` as a separate type
- Layout components (`row`, `column`, `grid`) become regular `AppComponent` members
- All container components use `children: list[AppComponent]`
- Leaf components have no `children` field (validation error if MCP tries)

## Design

### Component Categories

**Container Components** (have `children: list[AppComponent]`):
- `row`, `column`, `grid` - layout containers
- `card`, `modal`, `form-group` - content containers
- `tabs` - contains `tab-item` children
- `tab-item` - contains tab content

**Leaf Components** (no `children` field):
- `heading`, `text`, `html`, `button`, `image`, `badge`
- `text-input`, `number-input`, `select`, `checkbox`
- `data-table`, `stat-card`, `file-viewer`, `progress`
- `divider`, `spacer`, `form-embed`

### Model Structure

#### Base Fields (all components)

```python
class ComponentBase(BaseModel):
    id: str
    type: str  # discriminator
    width: WidthOption = "auto"
    visible: str | None = None  # expression for conditional visibility
    loading_workflows: list[str] | None = None
    grid_span: int | None = None
    repeat_for: RepeatConfig | None = None
    class_name: str | None = None
    style: dict[str, Any] | None = None
```

#### Container Components

```python
class RowComponent(ComponentBase):
    type: Literal["row"]
    children: list[AppComponent] = []
    gap: str | None = None
    padding: str | None = None
    align: AlignOption | None = None
    justify: JustifyOption | None = None
    distribute: DistributeOption | None = None
    max_width: str | None = None
    overflow: OverflowOption | None = None

class ColumnComponent(ComponentBase):
    type: Literal["column"]
    children: list[AppComponent] = []
    gap: str | None = None
    padding: str | None = None
    align: AlignOption | None = None
    max_width: str | None = None
    overflow: OverflowOption | None = None

class GridComponent(ComponentBase):
    type: Literal["grid"]
    children: list[AppComponent] = []
    columns: int | str = 3
    gap: str | None = None
    padding: str | None = None

class CardComponent(ComponentBase):
    type: Literal["card"]
    children: list[AppComponent] = []
    title: str | None = None
    description: str | None = None
    collapsible: bool = False
    default_collapsed: bool = False
    header_actions: list[ActionConfig] | None = None

class ModalComponent(ComponentBase):
    type: Literal["modal"]
    children: list[AppComponent] = []  # Modal body content
    title: str | None = None
    description: str | None = None
    trigger_label: str | None = None
    trigger_variant: ButtonVariant = "default"
    size: ModalSize = "md"

class TabsComponent(ComponentBase):
    type: Literal["tabs"]
    children: list[AppComponent] = []  # TabItemComponents
    default_tab: str | None = None

class TabItemComponent(ComponentBase):
    type: Literal["tab-item"]
    children: list[AppComponent] = []  # Tab content
    label: str
    value: str | None = None
    icon: str | None = None

class FormGroupComponent(ComponentBase):
    type: Literal["form-group"]
    children: list[AppComponent] = []  # Form fields
    label: str | None = None
    description: str | None = None
    direction: Literal["row", "column"] = "column"
    gap: str | None = None
```

#### Leaf Components (examples)

```python
class HeadingComponent(ComponentBase):
    type: Literal["heading"]
    content: str
    level: Literal[1, 2, 3, 4, 5, 6] = 2
    # No children field

class ButtonComponent(ComponentBase):
    type: Literal["button"]
    label: str
    variant: ButtonVariant = "default"
    on_click: ActionConfig | None = None
    disabled: str | None = None  # expression
    # No children field

class TextComponent(ComponentBase):
    type: Literal["text"]
    content: str
    # No children field
```

#### Discriminated Union

```python
AppComponent = Annotated[
    Union[
        # Containers
        RowComponent,
        ColumnComponent,
        GridComponent,
        CardComponent,
        ModalComponent,
        TabsComponent,
        TabItemComponent,
        FormGroupComponent,
        # Leaves
        HeadingComponent,
        TextComponent,
        HtmlComponent,
        ButtonComponent,
        ImageComponent,
        BadgeComponent,
        DividerComponent,
        SpacerComponent,
        TextInputComponent,
        NumberInputComponent,
        SelectComponent,
        CheckboxComponent,
        DataTableComponent,
        StatCardComponent,
        FileViewerComponent,
        ProgressComponent,
        FormEmbedComponent,
    ],
    Field(discriminator="type")
]
```

### Page Definition

```python
class PageDefinition(BaseModel):
    id: str
    name: str
    path: str
    children: list[AppComponent] = []  # Direct children, like HTML <body>
    data_sources: list[DataSourceConfig] = []
    variables: dict[str, Any] = {}
    permission: PermissionConfig | None = None
    launch_workflow_id: str | None = None
    launch_workflow_params: dict[str, Any] | None = None
```

Pages have `children` directly - no forced root container. Users add `ColumnComponent` if they want layout control.

---

## Migration Plan

### Phase 1: Backend Models

**File: `api/src/models/contracts/app_components.py`**

1. Remove `LayoutContainer` model entirely
2. Remove `LayoutContainerOrComponent` union
3. Update container components to have `children: list[AppComponent]` directly (not in props)
4. Move layout properties (gap, padding, align, etc.) from `LayoutContainer` to layout component models
5. Add `TabItemComponent` as new component type
6. Update `PageDefinition` to have `children: list[AppComponent]`

**Structural change:** Props move to top level.

Current:
```python
class CardComponent(BaseModel):
    type: Literal["card"]
    props: CardProps  # title, description, children inside props
    width: WidthOption
    # ...
```

New:
```python
class CardComponent(ComponentBase):
    type: Literal["card"]
    children: list[AppComponent] = []
    title: str | None = None
    description: str | None = None
    collapsible: bool = False
    # ... all props at top level
```

This flattening eliminates the `props` wrapper, making the JSON cleaner and validation simpler.

### Phase 2: App Builder Service

**File: `api/src/services/app_builder_service.py`**

The current service has complex `flatten_layout_tree()` and `build_layout_tree()` functions with special-case handling for each container type.

**Simplification:**

```python
def flatten_components(
    components: list[AppComponent],
    parent_id: str | None = None
) -> list[dict]:
    """Flatten nested component tree to flat rows for database storage."""
    rows = []
    for order, component in enumerate(components):
        component_dict = component.model_dump()
        children = component_dict.pop("children", [])

        rows.append({
            "component_id": component.id,
            "parent_id": parent_id,
            "type": component.type,
            "props": component_dict,  # Everything except children
            "component_order": order,
        })

        # Recursively flatten children
        if children:
            rows.extend(flatten_components(children, parent_id=component.id))

    return rows


def build_component_tree(
    flat_components: list[AppComponentORM],
    parent_id: str | None = None
) -> list[AppComponent]:
    """Build nested component tree from flat database rows."""
    children = [c for c in flat_components if c.parent_id == parent_id]
    children.sort(key=lambda c: c.component_order)

    result = []
    for comp in children:
        # Reconstruct component with nested children
        component_data = {
            "id": comp.component_id,
            "type": comp.type,
            **comp.props,  # Spread props back to top level
            "children": build_component_tree(flat_components, parent_id=comp.component_id),
        }

        # Validate through discriminated union
        validated = TypeAdapter(AppComponent).validate_python(component_data)
        result.append(validated)

    return result
```

**What's removed:**
- `isLayoutContainer()` type checks
- Special handling for Card's `props.children`
- Special handling for Modal's `props.content`
- Synthetic `tab_content` markers for Tabs
- `LayoutContainer` vs `AppComponent` branching

### Phase 3: MCP Tools

**Files:**
- `api/src/services/mcp_server/tools/apps.py`
- `api/src/services/mcp_server/tools/pages.py`
- `api/src/services/mcp_server/tools/components.py`

#### Page Operations

**`create_page` / `update_page`:**

Current:
```python
layout: LayoutContainer | None  # Separate type
```

New:
```python
children: list[AppComponent] | None  # Same type as components
```

Validation becomes uniform:
```python
if children:
    validated = [
        TypeAdapter(AppComponent).validate_python(c)
        for c in children
    ]
```

#### Component Operations

**`create_component` / `update_component`:**

No change to interface - still accepts component dict, validates through `TypeAdapter(AppComponent)`.

The simplification is internal - no special cases for container vs layout.

#### Schema Documentation

**`get_app_schema`:**

Update to reflect:
- No `LayoutContainer` type
- All components use same structure
- Container components have `children[]`
- Leaf components reject `children`

### Phase 4: File Storage / Serialization

**Files:**
- `api/src/services/file_storage/indexers/app.py`
- `api/src/services/github_sync_virtual_files.py`
- `api/src/services/git_serialization.py` (deprecate further)

#### AppIndexer (Deserialization)

**`_create_components_from_layout()` → `_create_components()`**

Current logic handles `LayoutContainer` vs `AppComponent` differently. New logic:

```python
def _create_components(
    self,
    components: list[dict],
    page_id: UUID,
    parent_id: UUID | None = None,
) -> list[AppComponentORM]:
    """Recursively create component records from nested tree."""
    records = []

    for order, comp_data in enumerate(components):
        children = comp_data.pop("children", [])

        # Validate through unified type
        validated = TypeAdapter(AppComponent).validate_python({**comp_data, "children": []})

        record = AppComponentORM(
            page_id=page_id,
            component_id=comp_data["id"],
            parent_id=parent_id,
            type=comp_data["type"],
            props=comp_data,  # Store validated props
            component_order=order,
        )
        records.append(record)

        # Recurse for children
        if children:
            records.extend(self._create_components(children, page_id, record.id))

    return records
```

#### VirtualFileProvider (Serialization)

**Current problem:** Doesn't actually serialize components (empty `children: []`).

**Fix:** Load components and build tree:

```python
def _serialize_page(self, page: AppPageORM) -> dict:
    # Build component tree from flat records
    components = build_component_tree(page.components, parent_id=None)

    return {
        "id": page.page_id,
        "title": page.title,
        "path": page.path,
        "children": [c.model_dump() for c in components],
        "data_sources": page.data_sources,
        "variables": page.variables,
        # ...
    }
```

#### JSON Format

The exported `.app.json` format becomes cleaner:

```json
{
  "id": "app-uuid",
  "name": "My App",
  "pages": [
    {
      "id": "page-1",
      "title": "Dashboard",
      "path": "/dashboard",
      "children": [
        {
          "id": "col-1",
          "type": "column",
          "gap": "md",
          "children": [
            {
              "id": "heading-1",
              "type": "heading",
              "content": "Dashboard",
              "level": 1
            },
            {
              "id": "row-1",
              "type": "row",
              "gap": "md",
              "children": [
                {
                  "id": "card-1",
                  "type": "card",
                  "title": "Stats",
                  "children": [...]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

No more `layout` wrapper, no `props` nesting - just components with children.

### Phase 5: Frontend Refactoring

**Files:**
- `client/src/components/app-builder/LayoutRenderer.tsx`
- `client/src/components/app-builder/ComponentRegistry.tsx`
- `client/src/lib/app-builder-tree.ts`
- `client/src/lib/app-builder-helpers.ts`

#### Type Changes (Auto-generated)

After backend changes, run `npm run generate:types`. The generated types will reflect:
- No `LayoutContainer` type
- `AppComponent` union includes layout types
- All container components have `children: AppComponent[]`

#### LayoutRenderer.tsx → ComponentRenderer.tsx

Current has two paths:
```typescript
if (isLayoutContainer(element)) {
  return renderLayoutContainer(element);
} else {
  return renderComponent(element);
}
```

New single path:
```typescript
function ComponentRenderer({ component, context }: Props) {
  const Component = ComponentRegistry[component.type];
  if (!Component) {
    console.warn(`Unknown component type: ${component.type}`);
    return null;
  }

  return (
    <Component
      {...component}
      context={context}
      renderChildren={(children) => (
        children?.map(child => (
          <ComponentRenderer key={child.id} component={child} context={context} />
        ))
      )}
    />
  );
}
```

Layout components (`RowComponent`, `ColumnComponent`, `GridComponent`) become regular registry entries:

```typescript
// ComponentRegistry.tsx
export const ComponentRegistry: Record<string, React.FC<any>> = {
  // Layouts
  row: RowComponent,
  column: ColumnComponent,
  grid: GridComponent,

  // Containers
  card: CardComponent,
  modal: ModalComponent,
  tabs: TabsComponent,
  'tab-item': TabItemComponent,
  'form-group': FormGroupComponent,

  // Leaves
  heading: HeadingComponent,
  text: TextComponent,
  button: ButtonComponent,
  // ...
};
```

#### app-builder-tree.ts

**Remove:**
- `isLayoutContainer()` function
- `CONTAINER_TYPES` constant (replace with type check for `children` field)
- Branching logic in `getElementChildren()`, `insertIntoTree()`, `updateInTree()`

**Simplify:**
```typescript
function getChildren(component: AppComponent): AppComponent[] {
  return 'children' in component ? component.children : [];
}

function hasChildren(component: AppComponent): boolean {
  return 'children' in component;
}

function insertChild(
  parent: AppComponent,
  child: AppComponent,
  index: number
): AppComponent {
  if (!hasChildren(parent)) {
    throw new Error(`Component type ${parent.type} cannot have children`);
  }
  const children = [...getChildren(parent)];
  children.splice(index, 0, child);
  return { ...parent, children };
}
```

#### Component Implementations

Container components receive `renderChildren` prop:

```typescript
// RowComponent.tsx
function RowComponent({
  gap,
  align,
  justify,
  children,
  renderChildren
}: RowComponentProps & { renderChildren: RenderChildrenFn }) {
  return (
    <div className={cn("flex flex-row", gapClass(gap), alignClass(align), justifyClass(justify))}>
      {renderChildren(children)}
    </div>
  );
}
```

Leaf components don't receive or use `renderChildren`:

```typescript
// ButtonComponent.tsx
function ButtonComponent({ label, variant, onClick }: ButtonComponentProps) {
  return (
    <Button variant={variant} onClick={onClick}>
      {label}
    </Button>
  );
}
```

---

## Database Migration

**No schema changes required.**

The `app_components` table already stores:
- `type: str` - works for all component types
- `props: jsonb` - stores component properties
- `parent_id: uuid` - tree structure

The change is purely in how we validate and serialize, not how we store.

**Data migration:** Existing data should work as-is. The `props` JSON structure changes slightly (properties move to top level), but this is handled during the read path by the new `build_component_tree()` function.

If needed, a migration script can normalize existing `props` structure, but it may not be necessary if we handle both formats during a transition period.

---

## Testing Strategy

### Unit Tests

1. **Model validation:**
   - Container components accept `children`
   - Leaf components reject `children`
   - Discriminated union routes correctly by `type`

2. **Tree operations:**
   - `flatten_components()` produces correct flat structure
   - `build_component_tree()` reconstructs nested tree
   - Round-trip: flatten → store → build produces identical tree

### Integration Tests

1. **MCP operations:**
   - Create page with nested children
   - Create component in container
   - Update component props
   - Move component between containers
   - Validate error messages for invalid operations (e.g., adding children to button)

2. **Serialization:**
   - Export app to JSON
   - Import app from JSON
   - Portable workflow refs work correctly

### E2E Tests

1. **App builder UI:**
   - Add components to page
   - Nest components in containers
   - Drag-and-drop reordering
   - Property editing

---

## Rollout Plan

### Step 1: Backend Models (Breaking Change)

- Update `app_components.py` with new unified model
- Update `app_builder_service.py` with simplified tree logic
- Update MCP tools
- Update serialization/indexing
- Run backend tests

### Step 2: Frontend Types

- Regenerate types: `npm run generate:types`
- Fix TypeScript compilation errors
- This will surface all places that need updates

### Step 3: Frontend Refactoring

- Refactor `LayoutRenderer` → `ComponentRenderer`
- Update `ComponentRegistry` to include layout components
- Simplify `app-builder-tree.ts`
- Update individual component implementations
- Run frontend tests

### Step 4: Data Migration (if needed)

- Assess existing app data
- Create migration script if props structure needs normalization
- Run migration in staging, then production

### Step 5: Documentation

- Update MCP schema documentation
- Update any developer docs about app structure

---

## Benefits Summary

| Area | Before | After |
|------|--------|-------|
| **Type system** | Two parallel types (LayoutContainer, AppComponent) | Single unified AppComponent |
| **Children access** | 5 different patterns | One pattern: `children[]` |
| **Validation** | Special cases per container type | Uniform discriminated union |
| **Service code** | ~400 lines with branching | ~50 lines, recursive |
| **Frontend rendering** | Two paths, `isLayoutContainer()` checks | Single recursive renderer |
| **MCP feedback** | Inconsistent error messages | Clear validation errors |
| **JSON format** | Nested `props`, `layout` wrapper | Flat properties, direct `children` |
