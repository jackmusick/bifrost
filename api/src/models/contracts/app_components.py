"""
App Builder Component Definitions

Core types for the recursive layout system and component definitions.
Pydantic models ported from client/src/lib/app-builder-types.ts

This module is the single source of truth for:
- Component types and props (ButtonComponent, HeadingComponent, etc.)
- Layout containers (LayoutContainer, LayoutType, etc.)
- Page definitions (PageDefinition, NavigationConfig, etc.)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# -----------------------------------------------------------------------------
# Literal Types
# -----------------------------------------------------------------------------

ComponentType = Literal[
    # Layout containers
    "row",
    "column",
    "grid",
    # Content containers
    "card",
    "modal",
    "tabs",
    "tab-item",
    "form-group",
    # Leaf components
    "heading",
    "text",
    "html",
    "divider",
    "spacer",
    "button",
    "stat-card",
    "image",
    "badge",
    "progress",
    "data-table",
    "file-viewer",
    "text-input",
    "number-input",
    "select",
    "checkbox",
    "form-embed",
]

ComponentWidth = Literal["auto", "full", "1/2", "1/3", "1/4", "2/3", "3/4"]

ButtonActionType = Literal["navigate", "workflow", "custom", "submit", "open-modal"]

HeadingLevel = Literal[1, 2, 3, 4, 5, 6]

LayoutAlign = Literal["start", "center", "end", "stretch"]

LayoutJustify = Literal["start", "center", "end", "between", "around"]

LayoutMaxWidth = Literal["sm", "md", "lg", "xl", "2xl", "full", "none"]

LayoutType = Literal["row", "column", "grid"]

LayoutDistribute = Literal["natural", "equal", "fit"]

LayoutOverflow = Literal["auto", "scroll", "hidden", "visible"]

LayoutSticky = Literal["top", "bottom"]

ButtonVariant = Literal["default", "destructive", "outline", "secondary", "ghost", "link"]

ButtonSize = Literal["default", "sm", "lg"]

BadgeVariant = Literal["default", "secondary", "destructive", "outline"]

TableColumnType = Literal["text", "number", "date", "badge"]

TableActionType = Literal["navigate", "workflow", "delete", "set-variable"]

OnCompleteActionType = Literal["navigate", "set-variable", "refresh-table"]

RowClickType = Literal["navigate", "select", "set-variable"]

StatCardClickType = Literal["navigate", "workflow"]

FileViewerDisplayMode = Literal["inline", "modal", "download"]

ModalSize = Literal["sm", "default", "lg", "xl", "full"]

TextInputType = Literal["text", "email", "password", "url", "tel"]

Orientation = Literal["horizontal", "vertical"]

PermissionLevel = Literal["none", "view", "edit", "admin"]


# -----------------------------------------------------------------------------
# Shared Supporting Types
# -----------------------------------------------------------------------------


class RepeatFor(BaseModel):
    """Repeat component for each item in an array."""

    model_config = {"populate_by_name": True}  # Accept both as_ and "as"

    items: str = Field(
        description='Expression that evaluates to an array (e.g., "{{ workflow.clients }}")'
    )
    item_key: str = Field(
        description='Property name to use for React key (must be unique, e.g., "id")'
    )
    as_: str = Field(
        alias="as",
        description='Variable name to access current item in expressions (e.g., "client")',
    )


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


# -----------------------------------------------------------------------------
# Layout Components (containers with children)
# Note: These use forward reference "AppComponent" which is resolved at the end
# of the file via model_rebuild() calls.
# -----------------------------------------------------------------------------


class RowComponent(ComponentBase):
    """Row layout component - horizontal flex container."""

    type: Literal["row"] = Field(default="row", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Child components"
    )
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")
    align: LayoutAlign | None = Field(default=None, description="Cross-axis alignment")
    justify: LayoutJustify | None = Field(
        default=None, description="Main-axis justification"
    )
    distribute: LayoutDistribute | None = Field(
        default=None, description="Child distribution"
    )
    max_width: LayoutMaxWidth | None = Field(default=None, description="Maximum width")
    max_height: int | None = Field(
        default=None, description="Maximum height in pixels"
    )
    overflow: LayoutOverflow | None = Field(
        default=None, description="Overflow behavior"
    )
    sticky: LayoutSticky | None = Field(
        default=None, description="Sticky positioning"
    )
    sticky_offset: int | None = Field(
        default=None, description="Sticky offset in pixels"
    )


class ColumnComponent(ComponentBase):
    """Column layout component - vertical flex container."""

    type: Literal["column"] = Field(default="column", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Child components"
    )
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")
    align: LayoutAlign | None = Field(default=None, description="Cross-axis alignment")
    max_width: LayoutMaxWidth | None = Field(default=None, description="Maximum width")
    max_height: int | None = Field(
        default=None, description="Maximum height in pixels"
    )
    overflow: LayoutOverflow | None = Field(
        default=None, description="Overflow behavior"
    )
    sticky: LayoutSticky | None = Field(
        default=None, description="Sticky positioning"
    )
    sticky_offset: int | None = Field(
        default=None, description="Sticky offset in pixels"
    )


class GridComponent(ComponentBase):
    """Grid layout component."""

    type: Literal["grid"] = Field(default="grid", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Child components"
    )
    columns: int | str = Field(default=3, description="Number of columns or template")
    gap: int | str | None = Field(default=None, description="Gap between children")
    padding: int | str | None = Field(default=None, description="Container padding")


class OnCompleteAction(BaseModel):
    """Action to execute after workflow completes."""

    type: OnCompleteActionType = Field(description="Type of action to perform")
    navigate_to: str | None = Field(
        default=None, description="Path to navigate to (for navigate type)"
    )
    variable_name: str | None = Field(
        default=None, description="Variable name to set (for set-variable type)"
    )
    variable_value: str | None = Field(
        default=None,
        description="Variable value to set, supports {{ workflow.result.* }} expressions",
    )
    data_source_key: str | None = Field(
        default=None, description="Data source key to refresh (for refresh-table type)"
    )


class TableColumn(BaseModel):
    """Table column definition."""

    key: str = Field(description="Key path into document data")
    header: str = Field(description="Column header")
    type: TableColumnType | None = Field(
        default=None, description="Column type for formatting"
    )
    width: int | Literal["auto"] | None = Field(default=None, description="Width")
    sortable: bool | None = Field(default=None, description="Sortable")
    badge_colors: dict[str, str] | None = Field(
        default=None, description="Badge color mapping for badge type"
    )


class TableActionConfirm(BaseModel):
    """Confirmation dialog for table actions."""

    title: str = Field(description="Confirmation dialog title")
    message: str = Field(description="Confirmation dialog message")
    confirm_label: str | None = Field(
        default=None, description="Confirm button label"
    )
    cancel_label: str | None = Field(default=None, description="Cancel button label")


class TableActionOnClick(BaseModel):
    """Click handler for table actions."""

    type: TableActionType = Field(description="Type of action")
    navigate_to: str | None = Field(
        default=None, description="Path to navigate to (for navigate type)"
    )
    workflow_id: str | None = Field(
        default=None, description="Workflow ID (for workflow type)"
    )
    action_params: dict[str, Any] | None = Field(
        default=None,
        description="Parameters to pass to workflow (supports {{ row.* }} expressions)",
    )
    variable_name: str | None = Field(
        default=None, description="Variable name (for set-variable type)"
    )
    variable_value: str | None = Field(
        default=None, description="Variable value (for set-variable type)"
    )

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


class TableAction(BaseModel):
    """Table action definition."""

    label: str = Field(description="Action label")
    icon: str | None = Field(default=None, description="Icon name")
    variant: Literal["default", "destructive", "outline", "ghost"] | None = Field(
        default=None, description="Button variant"
    )
    on_click: TableActionOnClick = Field(description="Action handler")
    confirm: TableActionConfirm | None = Field(
        default=None, description="Confirmation dialog"
    )
    visible: str | None = Field(default=None, description="Visibility expression")
    disabled: str | None = Field(
        default=None,
        description="Disabled expression (e.g., \"{{ row.status == 'completed' }}\")",
    )


class RowClickHandler(BaseModel):
    """Row click handler for data tables."""

    type: RowClickType = Field(description="Type of row click action")
    navigate_to: str | None = Field(
        default=None, description="Path to navigate to (for navigate type)"
    )
    variable_name: str | None = Field(
        default=None, description="Variable name (for set-variable type)"
    )


class SelectOption(BaseModel):
    """Select option definition."""

    value: str = Field(description="Option value")
    label: str = Field(description="Option display label")


class StatCardTrend(BaseModel):
    """Trend indicator for stat cards."""

    value: str = Field(description="Trend value (e.g., '+5%')")
    direction: Literal["up", "down", "neutral"] = Field(
        description="Trend direction"
    )


class StatCardOnClick(BaseModel):
    """Click handler for stat cards."""

    type: StatCardClickType = Field(description="Type of click action")
    navigate_to: str | None = Field(
        default=None, description="Path to navigate to (for navigate type)"
    )
    workflow_id: str | None = Field(
        default=None, description="Workflow ID (for workflow type)"
    )

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


class ModalFooterAction(BaseModel):
    """Footer action for modals."""

    label: str = Field(description="Action button label")
    variant: Literal["default", "destructive", "outline", "secondary", "ghost"] | None = Field(
        default=None, description="Button variant"
    )
    action_type: ButtonActionType = Field(description="Type of action")
    navigate_to: str | None = Field(
        default=None, description="Path to navigate to (for navigate type)"
    )
    workflow_id: str | None = Field(
        default=None, description="Workflow ID (for workflow type)"
    )
    action_params: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to action"
    )
    on_complete: list[OnCompleteAction] | None = Field(
        default=None, description="Action(s) to execute after workflow completes successfully"
    )
    on_error: list[OnCompleteAction] | None = Field(
        default=None, description="Action(s) to execute if workflow fails (for submit actionType)"
    )
    close_on_click: bool | None = Field(
        default=None, description="Whether clicking this action should close the modal"
    )

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


# -----------------------------------------------------------------------------
# Component Props Models
# -----------------------------------------------------------------------------


class HeadingProps(BaseModel):
    """Props for heading component."""

    text: str = Field(description="Text content (supports expressions)")
    level: HeadingLevel | None = Field(default=None, description="Heading level (1-6)")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class TextProps(BaseModel):
    """Props for text component."""

    text: str = Field(description="Text content (supports expressions)")
    label: str | None = Field(default=None, description="Optional label above text")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class HtmlProps(BaseModel):
    """Props for HTML component."""

    content: str = Field(description="HTML or JSX template content")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class CardProps(BaseModel):
    """Props for card component."""

    title: str | None = Field(default=None, description="Optional card title")
    description: str | None = Field(
        default=None, description="Optional card description"
    )
    children: list[LayoutContainerOrComponent] | None = Field(
        default=None,
        description="Card content (can be a layout container or components)",
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class DividerProps(BaseModel):
    """Props for divider component."""

    orientation: Orientation | None = Field(
        default=None, description="Divider orientation"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class SpacerProps(BaseModel):
    """Props for spacer component."""

    size: int | str | None = Field(
        default=None, description="Size in pixels or Tailwind spacing units"
    )
    height: int | str | None = Field(
        default=None, description="Alias for size - supports legacy definitions"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class ButtonProps(BaseModel):
    """Props for button component."""

    label: str = Field(description="Button label (supports expressions)")
    action_type: ButtonActionType = Field(description="Action type")
    navigate_to: str | None = Field(
        default=None, description="Navigation path for navigate action"
    )
    workflow_id: str | None = Field(
        default=None, description="Workflow ID for workflow action"
    )
    custom_action_id: str | None = Field(
        default=None, description="Custom action ID"
    )
    modal_id: str | None = Field(
        default=None, description="Modal ID to open (for open-modal action)"
    )
    action_params: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to action"
    )
    on_complete: list[OnCompleteAction] | None = Field(
        default=None, description="Action(s) to execute after workflow completes successfully"
    )
    on_error: list[OnCompleteAction] | None = Field(
        default=None, description="Action(s) to execute if workflow fails"
    )
    variant: ButtonVariant | None = Field(default=None, description="Button variant")
    size: ButtonSize | None = Field(default=None, description="Button size")
    disabled: bool | str | None = Field(
        default=None,
        description="Disabled state (boolean or expression like \"{{ row.status == 'completed' }}\")",
    )
    icon: str | None = Field(
        default=None, description="Icon name to display (from lucide-react)"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


class StatCardProps(BaseModel):
    """Props for stat-card component."""

    title: str = Field(description="Card title")
    value: str = Field(description="Value (supports expressions)")
    description: str | None = Field(default=None, description="Optional description")
    icon: str | None = Field(default=None, description="Icon name")
    trend: StatCardTrend | None = Field(default=None, description="Trend indicator")
    on_click: StatCardOnClick | None = Field(default=None, description="Click action")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class ImageProps(BaseModel):
    """Props for image component."""

    src: str = Field(description="Image source (URL or expression)")
    alt: str | None = Field(default=None, description="Alt text")
    max_width: int | str | None = Field(default=None, description="Max width")
    max_height: int | str | None = Field(default=None, description="Max height")
    object_fit: Literal["contain", "cover", "fill", "none"] | None = Field(
        default=None, description="Object fit mode"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class BadgeProps(BaseModel):
    """Props for badge component."""

    text: str = Field(description="Badge text (supports expressions)")
    variant: BadgeVariant | None = Field(default=None, description="Badge variant")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class ProgressProps(BaseModel):
    """Props for progress component."""

    value: str | int = Field(
        description="Progress value (0-100, supports expressions)"
    )
    show_label: bool | None = Field(
        default=None, description="Show percentage label"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class DataTableProps(BaseModel):
    """Props for data-table component."""

    data_source: str = Field(description="Data source - ID of a page data source")
    data_path: str | None = Field(
        default=None,
        description="Path to array within the data source result (e.g., 'clients' if result is { clients: [...] })",
    )
    columns: list[TableColumn] = Field(description="Column definitions")
    selectable: bool | None = Field(default=None, description="Enable row selection")
    searchable: bool | None = Field(default=None, description="Enable search")
    paginated: bool | None = Field(default=None, description="Enable pagination")
    page_size: int | None = Field(default=None, description="Page size")
    row_actions: list[TableAction] | None = Field(
        default=None, description="Row actions"
    )
    header_actions: list[TableAction] | None = Field(
        default=None, description="Header actions (e.g., Add New button)"
    )
    on_row_click: RowClickHandler | None = Field(
        default=None, description="Row click handler"
    )
    empty_message: str | None = Field(
        default=None, description="Empty state message"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")
    cache_key: str | None = Field(
        default=None,
        description="Cache key - if set, data persists across page navigations",
    )


class TabsProps(BaseModel):
    """Props for tabs component."""

    items: list[TabItem] = Field(description="Tab items")
    default_tab: str | None = Field(default=None, description="Default active tab ID")
    orientation: Orientation | None = Field(default=None, description="Orientation")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class FileViewerProps(BaseModel):
    """Props for file-viewer component."""

    src: str = Field(description="File URL or path (supports expressions)")
    file_name: str | None = Field(
        default=None, description="File name for display and download"
    )
    mime_type: str | None = Field(
        default=None,
        description="MIME type of the file (auto-detected if not provided)",
    )
    display_mode: FileViewerDisplayMode | None = Field(
        default=None,
        description="Display mode: inline (embed), modal (popup), or download (link)",
    )
    max_width: int | str | None = Field(
        default=None, description="Max width for inline display"
    )
    max_height: int | str | None = Field(
        default=None, description="Max height for inline display"
    )
    download_label: str | None = Field(
        default=None,
        description="Label for download button (when displayMode is 'download')",
    )
    show_download_button: bool | None = Field(
        default=None,
        description="Whether to show download button alongside inline/modal view",
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class ModalProps(BaseModel):
    """Props for modal component."""

    title: str = Field(description="Modal title")
    description: str | None = Field(default=None, description="Modal description")
    trigger_label: str | None = Field(
        default=None,
        description="Trigger button label (optional - if not provided, modal must be opened via button action)",
    )
    trigger_variant: ButtonVariant | None = Field(
        default=None, description="Trigger button variant"
    )
    trigger_size: ButtonSize | None = Field(
        default=None, description="Trigger button size"
    )
    size: ModalSize | None = Field(default=None, description="Modal size")
    content: LayoutContainer = Field(description="Content layout inside the modal")
    footer_actions: list[ModalFooterAction] | None = Field(
        default=None, description="Footer actions (optional)"
    )
    show_close_button: bool | None = Field(
        default=None, description="Show close button in header"
    )
    class_name: str | None = Field(
        default=None, description="Additional CSS classes for modal content"
    )


class TextInputProps(BaseModel):
    """Props for text-input component."""

    field_id: str = Field(
        description="Field ID for value tracking (used in {{ field.* }} expressions)"
    )
    label: str | None = Field(default=None, description="Input label")
    placeholder: str | None = Field(default=None, description="Placeholder text")
    default_value: str | None = Field(
        default=None, description="Default value (supports expressions)"
    )
    required: bool | None = Field(default=None, description="Required field")
    disabled: bool | str | None = Field(
        default=None, description="Disabled state (boolean or expression)"
    )
    input_type: TextInputType | None = Field(
        default=None, description="Input type (text, email, password, url, tel)"
    )
    min_length: int | None = Field(default=None, description="Minimum length")
    max_length: int | None = Field(default=None, description="Maximum length")
    pattern: str | None = Field(
        default=None, description="Regex pattern for validation"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class NumberInputProps(BaseModel):
    """Props for number-input component."""

    field_id: str = Field(description="Field ID for value tracking")
    label: str | None = Field(default=None, description="Input label")
    placeholder: str | None = Field(default=None, description="Placeholder text")
    default_value: int | str | None = Field(
        default=None, description="Default value (supports expressions)"
    )
    required: bool | None = Field(default=None, description="Required field")
    disabled: bool | str | None = Field(
        default=None, description="Disabled state (boolean or expression)"
    )
    min: int | None = Field(default=None, description="Minimum value")
    max: int | None = Field(default=None, description="Maximum value")
    step: int | None = Field(default=None, description="Step increment")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class SelectProps(BaseModel):
    """Props for select component."""

    field_id: str = Field(description="Field ID for value tracking")
    label: str | None = Field(default=None, description="Select label")
    placeholder: str | None = Field(default=None, description="Placeholder text")
    default_value: str | None = Field(
        default=None, description="Default value (supports expressions)"
    )
    required: bool | None = Field(default=None, description="Required field")
    disabled: bool | str | None = Field(
        default=None, description="Disabled state (boolean or expression)"
    )
    options: list[SelectOption] | str | None = Field(
        default=None,
        description='Static options or expression string like "{{ data.options }}".',
    )
    options_source: str | None = Field(
        default=None, description="Data source name for dynamic options"
    )
    value_field: str | None = Field(
        default=None, description="Field in data source for option value"
    )
    label_field: str | None = Field(
        default=None, description="Field in data source for option label"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class CheckboxProps(BaseModel):
    """Props for checkbox component."""

    field_id: str = Field(description="Field ID for value tracking")
    label: str = Field(description="Checkbox label")
    description: str | None = Field(
        default=None, description="Description text below label"
    )
    default_checked: bool | None = Field(
        default=None, description="Default checked state"
    )
    required: bool | None = Field(default=None, description="Required field")
    disabled: bool | str | None = Field(
        default=None, description="Disabled state (boolean or expression)"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class FormEmbedProps(BaseModel):
    """Props for form-embed component."""

    form_id: str = Field(description="Form ID to embed")
    show_title: bool | None = Field(
        default=None, description="Whether to show the form title"
    )
    show_description: bool | None = Field(
        default=None, description="Whether to show the form description"
    )
    show_progress: bool | None = Field(
        default=None, description="Whether to show form progress steps"
    )
    on_submit: list[OnCompleteAction] | None = Field(
        default=None, description="Actions to execute after form submission"
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")


class FormGroupProps(BaseModel):
    """Props for form-group component."""

    label: str | None = Field(default=None, description="Group label")
    description: str | None = Field(default=None, description="Group description")
    required: bool | None = Field(
        default=None, description="Whether the group fields are required"
    )
    direction: Literal["row", "column"] | None = Field(
        default=None, description="Layout direction for grouped fields"
    )
    gap: int | None = Field(default=None, description="Gap between fields")
    children: list[AppComponent] = Field(description="Child form field components")
    class_name: str | None = Field(default=None, description="Additional CSS classes")


# -----------------------------------------------------------------------------
# Component Models (with id, type, props, and common fields)
# -----------------------------------------------------------------------------


class HeadingComponent(BaseModel):
    """Heading component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["heading"] = Field(default="heading", description="Component type")
    props: HeadingProps = Field(description="Component props")
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


class TextComponent(BaseModel):
    """Text component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["text"] = Field(default="text", description="Component type")
    props: TextProps = Field(description="Component props")
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


class HtmlComponent(BaseModel):
    """HTML component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["html"] = Field(default="html", description="Component type")
    props: HtmlProps = Field(description="Component props")
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


class CardComponent(ComponentBase):
    """Card container component."""

    type: Literal["card"] = Field(default="card", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Card content"
    )
    title: str | None = Field(default=None, description="Card title")
    description: str | None = Field(default=None, description="Card description")
    collapsible: bool = Field(default=False, description="Whether card is collapsible")
    default_collapsed: bool = Field(
        default=False, description="Initial collapsed state"
    )
    header_actions: list[TableAction] | None = Field(
        default=None, description="Header action buttons"
    )


class DividerComponent(BaseModel):
    """Divider component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["divider"] = Field(default="divider", description="Component type")
    props: DividerProps = Field(description="Component props")
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


class SpacerComponent(BaseModel):
    """Spacer component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["spacer"] = Field(default="spacer", description="Component type")
    props: SpacerProps = Field(description="Component props")
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


class ButtonComponent(BaseModel):
    """Button component."""

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields like children

    id: str = Field(description="Unique component identifier")
    type: Literal["button"] = Field(default="button", description="Component type")
    props: ButtonProps = Field(description="Component props")
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


class StatCardComponent(BaseModel):
    """Stat card component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["stat-card"] = Field(default="stat-card", description="Component type")
    props: StatCardProps = Field(description="Component props")
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


class ImageComponent(BaseModel):
    """Image component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["image"] = Field(default="image", description="Component type")
    props: ImageProps = Field(description="Component props")
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


class BadgeComponent(BaseModel):
    """Badge component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["badge"] = Field(default="badge", description="Component type")
    props: BadgeProps = Field(description="Component props")
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


class ProgressComponent(BaseModel):
    """Progress component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["progress"] = Field(default="progress", description="Component type")
    props: ProgressProps = Field(description="Component props")
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


class DataTableComponent(BaseModel):
    """Data table component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["data-table"] = Field(default="data-table", description="Component type")
    props: DataTableProps = Field(description="Component props")
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


class TabItemComponent(ComponentBase):
    """Tab item within a Tabs component."""

    type: Literal["tab-item"] = Field(default="tab-item", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Tab content"
    )
    label: str = Field(description="Tab label")
    value: str | None = Field(
        default=None, description="Tab value (defaults to label if not provided)"
    )
    icon: str | None = Field(default=None, description="Tab icon name")


class TabsComponent(ComponentBase):
    """Tabs container component."""

    type: Literal["tabs"] = Field(default="tabs", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="TabItemComponent children"
    )
    default_tab: str | None = Field(
        default=None, description="Default active tab value"
    )
    orientation: Orientation | None = Field(
        default=None, description="Tab orientation"
    )


class FileViewerComponent(BaseModel):
    """File viewer component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["file-viewer"] = Field(default="file-viewer", description="Component type")
    props: FileViewerProps = Field(description="Component props")
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


class ModalComponent(ComponentBase):
    """Modal dialog component."""

    type: Literal["modal"] = Field(default="modal", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Modal body content"
    )
    title: str = Field(description="Modal title")
    description: str | None = Field(default=None, description="Modal description")
    trigger_label: str | None = Field(
        default=None, description="Trigger button label"
    )
    trigger_variant: ButtonVariant | None = Field(
        default=None, description="Trigger button variant"
    )
    trigger_size: ButtonSize | None = Field(
        default=None, description="Trigger button size"
    )
    size: ModalSize | None = Field(default=None, description="Modal size")
    footer_actions: list[ModalFooterAction] | None = Field(
        default=None, description="Footer actions"
    )
    show_close_button: bool | None = Field(
        default=None, description="Show close button"
    )


class TextInputComponent(BaseModel):
    """Text input component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["text-input"] = Field(default="text-input", description="Component type")
    props: TextInputProps = Field(description="Component props")
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


class NumberInputComponent(BaseModel):
    """Number input component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["number-input"] = Field(default="number-input", description="Component type")
    props: NumberInputProps = Field(description="Component props")
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


class SelectComponent(BaseModel):
    """Select component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["select"] = Field(default="select", description="Component type")
    props: SelectProps = Field(description="Component props")
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


class CheckboxComponent(BaseModel):
    """Checkbox component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["checkbox"] = Field(default="checkbox", description="Component type")
    props: CheckboxProps = Field(description="Component props")
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


class FormEmbedComponent(BaseModel):
    """Form embed component."""

    id: str = Field(description="Unique component identifier")
    type: Literal["form-embed"] = Field(default="form-embed", description="Component type")
    props: FormEmbedProps = Field(description="Component props")
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


class FormGroupComponent(ComponentBase):
    """Form group component for grouping form fields."""

    type: Literal["form-group"] = Field(default="form-group", description="Component type")
    children: list["AppComponent"] = Field(
        default_factory=list, description="Form field components"
    )
    label: str | None = Field(default=None, description="Group label")
    description: str | None = Field(default=None, description="Group description")
    required: bool | None = Field(
        default=None, description="Whether fields are required"
    )
    direction: Literal["row", "column"] | None = Field(
        default=None, description="Layout direction"
    )
    gap: int | str | None = Field(default=None, description="Gap between fields")


# -----------------------------------------------------------------------------
# Discriminated Union of All Components
# -----------------------------------------------------------------------------

AppComponent = Annotated[
    Union[
        # Layout containers (with children)
        RowComponent,
        ColumnComponent,
        GridComponent,
        # Content containers (with children)
        CardComponent,
        ModalComponent,
        TabsComponent,
        TabItemComponent,
        FormGroupComponent,
        # Leaf components (no children)
        HeadingComponent,
        TextComponent,
        HtmlComponent,
        DividerComponent,
        SpacerComponent,
        ButtonComponent,
        StatCardComponent,
        ImageComponent,
        BadgeComponent,
        ProgressComponent,
        DataTableComponent,
        FileViewerComponent,
        TextInputComponent,
        NumberInputComponent,
        SelectComponent,
        CheckboxComponent,
        FormEmbedComponent,
    ],
    Field(discriminator="type"),
]


# -----------------------------------------------------------------------------
# Simple Component Node for Internal Tree Building
# -----------------------------------------------------------------------------


class AppComponentNode(BaseModel):
    """
    Simple component node for internal tree building.

    Unlike the discriminated AppComponent union (which validates props per type),
    this model accepts any component type with untyped props. Used by
    app_builder_service.py when constructing trees from database rows.
    """

    id: str = Field(description="Unique component identifier")
    type: str = Field(description="Component type string")
    props: dict[str, Any] = Field(
        default_factory=dict, description="Component props dictionary"
    )
    visible: str | None = Field(default=None, description="Visibility expression")
    width: ComponentWidth | None = Field(default=None, description="Component width")
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


# -----------------------------------------------------------------------------
# Tab Item (needs LayoutContainer forward reference)
# -----------------------------------------------------------------------------


class TabItem(BaseModel):
    """Tab item definition."""

    id: str = Field(description="Tab ID")
    label: str = Field(description="Tab label")
    icon: str | None = Field(default=None, description="Tab icon")
    content: LayoutContainer = Field(description="Tab content (layout)")


# -----------------------------------------------------------------------------
# Layout Container
# -----------------------------------------------------------------------------


# Union for LayoutContainer children - LayoutContainer (nesting) or AppComponent (leaf)
LayoutContainerOrComponent = Union["LayoutContainer", AppComponent]


class LayoutContainer(BaseModel):
    """Layout container for organizing components."""

    id: str = Field(
        default_factory=lambda: f"layout_{__import__('uuid').uuid4().hex[:8]}",
        description='Unique identifier for API operations (e.g., "layout_abc123")'
    )
    type: LayoutType = Field(description="Layout type")
    gap: int | None = Field(
        default=None, description="Gap between children (in pixels or Tailwind units)"
    )
    padding: int | None = Field(
        default=None, description="Padding (in pixels or Tailwind units)"
    )
    align: LayoutAlign | None = Field(default=None, description="Cross-axis alignment")
    justify: LayoutJustify | None = Field(
        default=None, description="Main-axis justification"
    )
    columns: int | None = Field(
        default=None, description="Grid column count (for grid type)"
    )
    distribute: LayoutDistribute | None = Field(
        default=None,
        description=(
            "Controls how children fill available space (primarily for row layouts). "
            '"natural" (default): Children keep their natural size (standard CSS flexbox). '
            '"equal": Children expand equally to fill space (flex-1). '
            '"fit": Children fit content, no stretch.'
        ),
    )
    max_width: LayoutMaxWidth | None = Field(
        default=None,
        description=(
            "Constrains the max-width of the layout container. "
            'Values: "sm" (384px), "md" (448px), "lg" (512px), "xl" (576px), "2xl" (672px), '
            '"full"/"none" (no constraint). '
            'Recommended: Use "lg" for pages containing forms to prevent them from stretching too wide.'
        ),
    )
    max_height: int | None = Field(
        default=None,
        description=(
            "Maximum height of the container (in pixels). "
            "Used with overflow to create scrollable containers."
        ),
    )
    overflow: LayoutOverflow | None = Field(
        default=None,
        description=(
            "How content outside bounds behaves. "
            "Use with maxHeight to create scrollable containers."
        ),
    )
    sticky: LayoutSticky | None = Field(
        default=None,
        description=(
            "Sticky positioning - pins container to top or bottom when scrolling. "
            "Useful for headers, sidebars, or action bars."
        ),
    )
    sticky_offset: int | None = Field(
        default=None,
        description="Offset from edge when sticky (in pixels). Default: 0",
    )
    class_name: str | None = Field(default=None, description="Additional CSS classes")
    style: dict[str, Any] | None = Field(
        default=None, description="Inline CSS styles (camelCase properties)"
    )
    visible: str | None = Field(default=None, description="Visibility expression")
    children: list[LayoutContainerOrComponent] = Field(description="Child elements")


# Rebuild models for forward references
LayoutContainer.model_rebuild()
TabItem.model_rebuild()
CardProps.model_rebuild()
ModalProps.model_rebuild()
TabsProps.model_rebuild()
FormGroupProps.model_rebuild()

# Rebuild layout components that reference AppComponent
RowComponent.model_rebuild()
ColumnComponent.model_rebuild()
GridComponent.model_rebuild()

# Rebuild content container components that reference AppComponent
CardComponent.model_rebuild()
ModalComponent.model_rebuild()
TabsComponent.model_rebuild()
TabItemComponent.model_rebuild()
FormGroupComponent.model_rebuild()

# Alias for internal tree building (LayoutContainer or simple AppComponentNode)
LayoutElement = Union[LayoutContainer, AppComponentNode]


# -----------------------------------------------------------------------------
# Page and Navigation Types
# -----------------------------------------------------------------------------


class LaunchWorkflowConfig(BaseModel):
    """Configuration for page launch workflow."""

    workflow_id: str = Field(description="Workflow ID to execute on page mount")
    params: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to the workflow"
    )
    data_source_id: str | None = Field(
        default=None, description="Data source ID for accessing workflow results"
    )

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str, info: Any) -> str:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


DataSourceType = Literal["api", "static", "computed", "data-provider", "workflow"]


class DataSourceConfig(BaseModel):
    """Data source configuration for pages.

    Defines how data is fetched and made available to page components.
    """

    id: str = Field(description="Unique identifier for this data source")
    type: DataSourceType = Field(description="Type of data source")
    endpoint: str | None = Field(
        default=None, description="API endpoint (for 'api' type)"
    )
    data: Any | None = Field(default=None, description="Static data (for 'static' type)")
    expression: str | None = Field(
        default=None, description="Computed expression (for 'computed' type)"
    )
    data_provider_id: str | None = Field(
        default=None, description="Data provider ID (for 'data-provider' type)"
    )
    workflow_id: str | None = Field(
        default=None, description="Workflow ID (for 'workflow' type)"
    )
    input_params: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to the data source"
    )
    auto_refresh: bool | None = Field(
        default=None, description="Whether to auto-refresh data"
    )
    refresh_interval: int | None = Field(
        default=None, description="Refresh interval in milliseconds"
    )

    @field_serializer("workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


class PagePermission(BaseModel):
    """Page-level permission configuration."""

    allowed_roles: list[str] | None = Field(
        default=None,
        description="Roles that can access this page (* for all authenticated users)",
    )
    access_expression: str | None = Field(
        default=None, description="Permission expression for dynamic access control"
    )
    redirect_to: str | None = Field(
        default=None, description="Redirect path if access denied"
    )


class PageDefinition(BaseModel):
    """Page definition for the app builder."""

    id: str = Field(description="Page identifier")
    title: str = Field(description="Page title")
    path: str = Field(description="Page path/route")
    layout: LayoutContainer = Field(description="Page layout")
    data_sources: list[DataSourceConfig] = Field(
        default_factory=list, description="Data sources configured for this page"
    )
    variables: dict[str, Any] | None = Field(
        default=None, description="Initial page variables"
    )
    launch_workflow_id: str | None = Field(
        default=None,
        description="Workflow to execute on page mount (results available as {{ workflow.<dataSourceId> }})",
    )
    launch_workflow_params: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to the launch workflow"
    )
    launch_workflow_data_source_id: str | None = Field(
        default=None,
        description="Data source ID for accessing workflow results (defaults to workflow function name)",
    )
    launch_workflow: LaunchWorkflowConfig | None = Field(
        default=None, description="Alternative nested format for launch workflow configuration"
    )
    styles: str | None = Field(
        default=None, description="Page-level CSS styles (scoped to this page)"
    )
    permission: PagePermission | None = Field(
        default=None, description="Page-level permission configuration"
    )

    @field_serializer("launch_workflow_id")
    def serialize_workflow_ref(self, value: str | None, info: Any) -> str | None:
        """Transform UUID to portable ref using serialization context."""
        if not value or not info.context:
            return value
        workflow_map = info.context.get("workflow_map", {})
        return workflow_map.get(value, value)


class PermissionRule(BaseModel):
    """Permission rule for app access control."""

    role: str = Field(
        description='Role that has this permission (e.g., "admin", "user", "*" for all)'
    )
    level: Literal["view", "edit", "admin"] = Field(
        description="Permission level: view, edit, admin"
    )


class PermissionConfig(BaseModel):
    """Permission configuration for an application."""

    public: bool | None = Field(
        default=None, description="Whether the app is public (no auth required)"
    )
    default_level: PermissionLevel | None = Field(
        default=None, description="Default permission level for authenticated users"
    )
    rules: list[PermissionRule] | None = Field(
        default=None, description="Role-based permission rules"
    )


class NavItem(BaseModel):
    """Navigation item for sidebar/navbar."""

    id: str = Field(description="Item identifier (usually page ID)")
    label: str = Field(description="Display label")
    icon: str | None = Field(default=None, description="Icon name (lucide icon)")
    path: str | None = Field(default=None, description="Navigation path")
    visible: str | None = Field(default=None, description="Visibility expression")
    order: int | None = Field(default=None, description="Order in navigation")
    is_section: bool | None = Field(
        default=None, description="Whether this is a section header (group)"
    )
    children: list[NavItem] | None = Field(
        default=None, description="Child items for section groups"
    )


# Rebuild for forward reference
NavItem.model_rebuild()


class NavigationConfig(BaseModel):
    """Navigation configuration for the application."""

    sidebar: list[NavItem] | None = Field(
        default=None, description="Sidebar navigation items"
    )
    show_sidebar: bool | None = Field(
        default=None, description="Whether to show the sidebar"
    )
    show_header: bool | None = Field(
        default=None, description="Whether to show the header"
    )
    logo_url: str | None = Field(default=None, description="Custom logo URL")
    brand_color: str | None = Field(default=None, description="Brand color (hex)")


# -----------------------------------------------------------------------------
# Type Guards (as functions)
# -----------------------------------------------------------------------------


def is_layout_container(element: LayoutContainer | AppComponent) -> bool:
    """Check if an element is a LayoutContainer."""
    return element.type in ("row", "column", "grid")


def is_app_component(element: LayoutContainer | AppComponent) -> bool:
    """Check if an element is an AppComponent."""
    return not is_layout_container(element)


CONTAINER_TYPES = ("row", "column", "grid", "card", "modal", "tabs", "tab-item", "form-group")


def can_have_children(element: LayoutContainer | AppComponent) -> bool:
    """Check if an element type can have children."""
    return element.type in CONTAINER_TYPES
