"""
Round-trip tests for App Builder type unification.

These tests verify that:
1. Discriminated union validates correct props per component type
2. Export -> JSON -> Import preserves all data
3. snake_case serialization works correctly
"""

import json

import pytest
from pydantic import ValidationError

from src.models.contracts.app_components import (
    # Application-level types
    NavItem,
    NavigationConfig,
    PageDefinition,
    PagePermission,
    # Layout types
    LayoutContainer,
    # Component types
    HeadingComponent,
    TextComponent,
    HtmlComponent,
    CardComponent,
    DividerComponent,
    SpacerComponent,
    ButtonComponent,
    StatCardComponent,
    ImageComponent,
    BadgeComponent,
    ProgressComponent,
    DataTableComponent,
    TabsComponent,
    FileViewerComponent,
    ModalComponent,
    TextInputComponent,
    NumberInputComponent,
    SelectComponent,
    CheckboxComponent,
    FormEmbedComponent,
    FormGroupComponent,
    # Props types (for leaf components that still use props wrapper)
    HeadingProps,
    TextProps,
    HtmlProps,
    DividerProps,
    SpacerProps,
    ButtonProps,
    StatCardProps,
    ImageProps,
    BadgeProps,
    ProgressProps,
    DataTableProps,
    FileViewerProps,
    TextInputProps,
    NumberInputProps,
    SelectProps,
    CheckboxProps,
    FormEmbedProps,
    # Supporting types
    TableColumn,
    TableAction,
    TableActionOnClick,
    TableActionConfirm,
    RowClickHandler,
    SelectOption,
    StatCardTrend,
    StatCardOnClick,
    ModalFooterAction,
    OnCompleteAction,
    RepeatFor,
)
# ApplicationExport imported for potential full-app round-trip tests
# from src.models.contracts.applications import ApplicationExport


class TestDiscriminatedUnion:
    """Test that discriminated union validates props correctly."""

    def test_button_with_button_props_valid(self):
        """Button component with ButtonProps is valid."""
        button = ButtonComponent(
            id="btn-1",
            type="button",
            props=ButtonProps(
                label="Click Me",
                action_type="navigate",
                navigate_to="/home",
                variant="default",
                size="lg",
            ),
        )
        assert button.id == "btn-1"
        assert button.type == "button"
        assert button.props.label == "Click Me"
        assert button.props.action_type == "navigate"
        assert button.props.navigate_to == "/home"

    def test_button_with_workflow_action_valid(self):
        """Button with workflow action type is valid."""
        button = ButtonComponent(
            id="btn-workflow",
            type="button",
            props=ButtonProps(
                label="Run Workflow",
                action_type="workflow",
                workflow_id="wf-123",
                action_params={"clientId": "{{ page.clientId }}"},
                on_complete=[
                    OnCompleteAction(
                        type="navigate",
                        navigate_to="/success",
                    )
                ],
            ),
        )
        assert button.props.workflow_id == "wf-123"
        assert button.props.on_complete is not None
        assert button.props.on_complete[0].type == "navigate"

    def test_data_table_with_data_table_props_valid(self):
        """DataTable component with DataTableProps is valid."""
        table = DataTableComponent(
            id="table-1",
            type="data-table",
            props=DataTableProps(
                data_source="clients",
                columns=[
                    TableColumn(key="name", header="Name", sortable=True),
                    TableColumn(
                        key="status",
                        header="Status",
                        type="badge",
                        badge_colors={"active": "green", "inactive": "gray"},
                    ),
                ],
                searchable=True,
                paginated=True,
                page_size=10,
            ),
        )
        assert table.id == "table-1"
        assert table.type == "data-table"
        assert len(table.props.columns) == 2
        assert table.props.columns[0].key == "name"

    def test_data_table_requires_columns(self):
        """DataTable without columns fails validation."""
        # Test that missing columns field raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DataTableProps(
                data_source="clients",
                # columns is missing - should fail
            )  # type: ignore
        assert "columns" in str(exc_info.value)

        # Test that columns must be provided when constructing via dict
        with pytest.raises(ValidationError):
            DataTableProps.model_validate({"dataSource": "clients"})

    def test_data_table_with_row_actions(self):
        """DataTable with row actions validates correctly."""
        table = DataTableComponent(
            id="table-actions",
            type="data-table",
            props=DataTableProps(
                data_source="clients",
                columns=[TableColumn(key="name", header="Name")],
                row_actions=[
                    TableAction(
                        label="Edit",
                        icon="Pencil",
                        on_click=TableActionOnClick(
                            type="navigate",
                            navigate_to="/clients/{{ row.id }}/edit",
                        ),
                    ),
                    TableAction(
                        label="Delete",
                        icon="Trash",
                        variant="destructive",
                        on_click=TableActionOnClick(
                            type="workflow",
                            workflow_id="delete-client",
                            action_params={"clientId": "{{ row.id }}"},
                        ),
                        confirm=TableActionConfirm(
                            title="Delete Client",
                            message="Are you sure you want to delete {{ row.name }}?",
                        ),
                    ),
                ],
            ),
        )
        assert table.props.row_actions is not None
        assert len(table.props.row_actions) == 2
        assert table.props.row_actions[1].confirm is not None

    def test_modal_with_content_layout(self):
        """Modal component with children is valid."""
        modal = ModalComponent(
            id="modal-1",
            type="modal",
            title="Edit Client",
            description="Update client information",
            size="lg",
            children=[
                TextInputComponent(
                    id="input-name",
                    type="text-input",
                    props=TextInputProps(
                        field_id="name",
                        label="Name",
                        required=True,
                    ),
                ),
            ],
            footer_actions=[
                ModalFooterAction(
                    label="Save",
                    variant="default",
                    action_type="submit",
                    close_on_click=True,
                ),
                ModalFooterAction(
                    label="Cancel",
                    variant="outline",
                    action_type="custom",
                    close_on_click=True,
                ),
            ],
        )
        assert len(modal.children) == 1
        assert modal.footer_actions is not None
        assert len(modal.footer_actions) == 2

    def test_tabs_with_tab_items(self):
        """Tabs component with TabItemComponent children validates correctly."""
        from src.models.contracts.app_components import TabItemComponent

        tabs = TabsComponent(
            id="tabs-1",
            type="tabs",
            children=[
                TabItemComponent(
                    id="tab-overview",
                    label="Overview",
                    value="overview",
                    icon="Home",
                    children=[
                        HeadingComponent(
                            id="h1",
                            type="heading",
                            props=HeadingProps(text="Overview", level=2),
                        ),
                    ],
                ),
                TabItemComponent(
                    id="tab-details",
                    label="Details",
                    value="details",
                    children=[
                        TextComponent(
                            id="t1",
                            type="text",
                            props=TextProps(text="Details content"),
                        ),
                    ],
                ),
            ],
            default_tab="overview",
        )
        assert len(tabs.children) == 2
        assert tabs.children[0].type == "tab-item"

    def test_form_group_with_children(self):
        """FormGroup with child form components validates correctly."""
        form_group = FormGroupComponent(
            id="form-group-1",
            type="form-group",
            label="Contact Information",
            direction="row",
            gap=4,
            children=[
                TextInputComponent(
                    id="input-email",
                    type="text-input",
                    props=TextInputProps(
                        field_id="email",
                        label="Email",
                        input_type="email",
                        required=True,
                    ),
                ),
                TextInputComponent(
                    id="input-phone",
                    type="text-input",
                    props=TextInputProps(
                        field_id="phone",
                        label="Phone",
                        input_type="tel",
                    ),
                ),
            ],
        )
        assert len(form_group.children) == 2
        assert form_group.direction == "row"


class TestSnakeCaseSerialization:
    """Test snake_case JSON serialization."""

    def test_button_serializes_snakecase(self):
        """Button props serialize with snake_case keys."""
        button = ButtonComponent(
            id="btn-1",
            type="button",
            props=ButtonProps(
                label="Submit",
                action_type="workflow",
                workflow_id="wf-123",
                action_params={"userId": "123"},
                on_complete=[
                    OnCompleteAction(
                        type="set-variable",
                        variable_name="result",
                        variable_value="{{ workflow.result }}",
                    )
                ],
            ),
            loading_workflows=["wf-123"],
            class_name="btn-primary",
        )
        data = button.model_dump(exclude_none=True)

        # Check snake_case keys at component level
        assert "loading_workflows" in data
        assert "class_name" in data

        # Check snake_case keys in props
        assert "action_type" in data["props"]
        assert "workflow_id" in data["props"]
        assert "action_params" in data["props"]
        assert "on_complete" in data["props"]

        # Check nested snake_case
        assert "variable_name" in data["props"]["on_complete"][0]
        assert "variable_value" in data["props"]["on_complete"][0]

    def test_layout_serializes_snakecase(self):
        """Layout container serializes with snake_case keys."""
        layout = LayoutContainer(
            id="layout-1",
            type="column",
            gap=4,
            max_width="lg",
            max_height=400,
            sticky_offset=10,
            class_name="main-layout",
            children=[
                HeadingComponent(
                    id="h1",
                    type="heading",
                    props=HeadingProps(text="Hello", level=1, class_name="title"),
                    grid_span=2,
                    repeat_for=RepeatFor(
                        items="{{ data.items }}",
                        item_key="id",
                        as_="item",
                    ),
                ),
            ],
        )
        data = layout.model_dump(exclude_none=True)

        # Check snake_case at layout level
        assert "max_width" in data
        assert "max_height" in data
        assert "sticky_offset" in data
        assert "class_name" in data

        # Check child component snake_case
        child = data["children"][0]
        assert "grid_span" in child
        assert "repeat_for" in child
        assert "item_key" in child["repeat_for"]
        # Note: "as_" is the Python field name
        assert "as_" in child["repeat_for"]

    def test_data_table_serializes_snakecase(self):
        """DataTable with all nested types serializes with snake_case."""
        table = DataTableComponent(
            id="table-1",
            type="data-table",
            props=DataTableProps(
                data_source="clients",
                data_path="data.clients",
                columns=[
                    TableColumn(
                        key="name",
                        header="Name",
                        badge_colors={"active": "green"},
                    )
                ],
                row_actions=[
                    TableAction(
                        label="Delete",
                        on_click=TableActionOnClick(
                            type="workflow",
                            workflow_id="delete",
                            action_params={"id": "{{ row.id }}"},
                        ),
                        confirm=TableActionConfirm(
                            title="Confirm",
                            message="Delete?",
                            confirm_label="Yes",
                            cancel_label="No",
                        ),
                    )
                ],
                on_row_click=RowClickHandler(
                    type="set-variable",
                    variable_name="selectedRow",
                ),
                page_size=25,
                cache_key="clients-table",
                empty_message="No clients found",
            ),
        )
        data = table.model_dump(exclude_none=True)
        props = data["props"]

        # Check snake_case in props
        assert "data_source" in props
        assert "data_path" in props
        assert "row_actions" in props
        assert "on_row_click" in props
        assert "page_size" in props
        assert "cache_key" in props
        assert "empty_message" in props

        # Check nested column snake_case
        assert "badge_colors" in props["columns"][0]

        # Check row action snake_case
        action = props["row_actions"][0]
        assert "on_click" in action
        assert "workflow_id" in action["on_click"]
        assert "action_params" in action["on_click"]
        assert "confirm_label" in action["confirm"]
        assert "cancel_label" in action["confirm"]

        # Check row click handler snake_case
        assert "variable_name" in props["on_row_click"]

    def test_stat_card_serializes_snakecase(self):
        """StatCard with trend and onClick serializes with snake_case."""
        stat = StatCardComponent(
            id="stat-1",
            type="stat-card",
            props=StatCardProps(
                title="Revenue",
                value="{{ data.revenue }}",
                trend=StatCardTrend(value="+15%", direction="up"),
                on_click=StatCardOnClick(
                    type="navigate",
                    navigate_to="/revenue",
                ),
                class_name="revenue-card",
            ),
        )
        data = stat.model_dump(exclude_none=True)
        props = data["props"]

        assert "on_click" in props
        assert "navigate_to" in props["on_click"]
        assert "class_name" in props

    def test_file_viewer_serializes_snakecase(self):
        """FileViewer serializes with snake_case."""
        viewer = FileViewerComponent(
            id="viewer-1",
            type="file-viewer",
            props=FileViewerProps(
                src="{{ data.fileUrl }}",
                file_name="document.pdf",
                mime_type="application/pdf",
                display_mode="modal",
                max_width=800,
                max_height=600,
                download_label="Download PDF",
                show_download_button=True,
            ),
        )
        data = viewer.model_dump(exclude_none=True)
        props = data["props"]

        assert "file_name" in props
        assert "mime_type" in props
        assert "display_mode" in props
        assert "max_width" in props
        assert "max_height" in props
        assert "download_label" in props
        assert "show_download_button" in props


class TestRoundTrip:
    """Test export -> JSON -> import preserves all data."""

    def test_simple_page_roundtrip(self):
        """Simple page layout survives round-trip."""
        page = PageDefinition(
            id="page-home",
            title="Home",
            path="/",
            layout=LayoutContainer(
                id="home-layout",
                type="column",
                gap=4,
                padding=6,
                children=[
                    HeadingComponent(
                        id="h1",
                        type="heading",
                        props=HeadingProps(text="Welcome", level=1),
                    ),
                    TextComponent(
                        id="t1",
                        type="text",
                        props=TextProps(
                            text="Welcome to the app", label="Greeting"
                        ),
                    ),
                ],
            ),
        )

        # Export to JSON
        exported = page.model_dump(exclude_none=True)
        json_str = json.dumps(exported)

        # Import from JSON
        imported_data = json.loads(json_str)
        imported_page = PageDefinition.model_validate(imported_data)

        # Verify all data preserved
        assert imported_page.id == page.id
        assert imported_page.title == "Home"
        assert imported_page.path == "/"
        assert imported_page.layout.type == "column"
        assert len(imported_page.layout.children) == 2

    def test_complex_nested_layout_roundtrip(self):
        """Complex nested layout survives round-trip."""
        from src.models.contracts.app_components import TabItemComponent

        page = PageDefinition(
            id="page-dashboard",
            title="Dashboard",
            path="/dashboard",
            variables={"selectedClient": None, "refreshCount": 0},
            launch_workflow_id="load-dashboard",
            launch_workflow_params={"includeStats": True},
            launch_workflow_data_source_id="dashboardData",
            layout=LayoutContainer(
                id="dashboard-layout",
                type="column",
                gap=6,
                children=[
                    # Header row with stats
                    LayoutContainer(
                        id="stats-row",
                        type="row",
                        gap=4,
                        distribute="equal",
                        children=[
                            StatCardComponent(
                                id="stat-clients",
                                type="stat-card",
                                props=StatCardProps(
                                    title="Clients",
                                    value="{{ dashboardData.clientCount }}",
                                    icon="Users",
                                ),
                            ),
                            StatCardComponent(
                                id="stat-revenue",
                                type="stat-card",
                                props=StatCardProps(
                                    title="Revenue",
                                    value="{{ dashboardData.revenue }}",
                                    trend=StatCardTrend(
                                        value="+12%", direction="up"
                                    ),
                                ),
                            ),
                        ],
                    ),
                    # Tabs with nested content (new structure: children with TabItemComponent)
                    TabsComponent(
                        id="main-tabs",
                        type="tabs",
                        default_tab="clients",
                        children=[
                            TabItemComponent(
                                id="tab-clients",
                                label="Clients",
                                value="clients",
                                icon="Users",
                                children=[
                                    DataTableComponent(
                                        id="clients-table",
                                        type="data-table",
                                        props=DataTableProps(
                                            data_source="dashboardData",
                                            data_path="clients",
                                            columns=[
                                                TableColumn(
                                                    key="name",
                                                    header="Name",
                                                ),
                                                TableColumn(
                                                    key="status",
                                                    header="Status",
                                                    type="badge",
                                                ),
                                            ],
                                            searchable=True,
                                            paginated=True,
                                            row_actions=[
                                                TableAction(
                                                    label="Edit",
                                                    on_click=TableActionOnClick(
                                                        type="navigate",
                                                        navigate_to="/clients/{{ row.id }}",
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # Modal component (new structure: children instead of props.content)
                    ModalComponent(
                        id="add-client-modal",
                        type="modal",
                        title="Add Client",
                        trigger_label="Add New Client",
                        trigger_variant="default",
                        size="lg",
                        children=[
                            TextInputComponent(
                                id="client-name",
                                type="text-input",
                                props=TextInputProps(
                                    field_id="clientName",
                                    label="Client Name",
                                    required=True,
                                ),
                            ),
                            SelectComponent(
                                id="client-type",
                                type="select",
                                props=SelectProps(
                                    field_id="clientType",
                                    label="Type",
                                    options=[
                                        SelectOption(
                                            value="enterprise",
                                            label="Enterprise",
                                        ),
                                        SelectOption(
                                            value="smb",
                                            label="SMB",
                                        ),
                                    ],
                                ),
                            ),
                        ],
                        footer_actions=[
                            ModalFooterAction(
                                label="Create",
                                action_type="submit",
                                workflow_id="create-client",
                                on_complete=[
                                    OnCompleteAction(
                                        type="refresh-table",
                                        data_source_key="clients-table",
                                    )
                                ],
                                close_on_click=True,
                            ),
                        ],
                    ),
                ],
            ),
            permission=PagePermission(
                allowed_roles=["admin", "manager"],
                redirect_to="/unauthorized",
            ),
        )

        # Export to JSON
        exported = page.model_dump(exclude_none=True)
        json_str = json.dumps(exported)

        # Import from JSON
        imported_data = json.loads(json_str)
        imported_page = PageDefinition.model_validate(imported_data)

        # Verify structure preserved
        assert imported_page.launch_workflow_id == "load-dashboard"
        assert imported_page.launch_workflow_params == {"includeStats": True}
        assert imported_page.variables == {"selectedClient": None, "refreshCount": 0}
        assert imported_page.permission is not None
        assert imported_page.permission.allowed_roles == ["admin", "manager"]

        # Verify nested layout
        layout = imported_page.layout
        assert len(layout.children) == 3

        # Verify tabs with nested content (new structure)
        tabs = layout.children[1]
        assert tabs.type == "tabs"  # type: ignore
        assert len(tabs.children) == 1  # type: ignore

        # Verify modal (new structure)
        modal = layout.children[2]
        assert modal.type == "modal"  # type: ignore
        assert modal.footer_actions is not None  # type: ignore
        assert modal.footer_actions[0].on_complete is not None  # type: ignore

    def test_export_excludes_none_values(self):
        """Export dict excludes None values."""
        page = PageDefinition(
            id="page-1",
            title="Page",
            path="/",
            layout=LayoutContainer(
                id="layout-1",
                type="column",
                # gap, padding, etc are None
                children=[
                    HeadingComponent(
                        id="h1",
                        type="heading",
                        props=HeadingProps(text="Title"),
                        # level, class_name, etc are None
                    ),
                ],
            ),
        )

        exported = page.model_dump(exclude_none=True)

        # None values should be excluded
        assert "variables" not in exported
        assert "launch_workflow_id" not in exported
        assert "permission" not in exported

        layout = exported["layout"]
        assert "gap" not in layout
        assert "padding" not in layout
        assert "max_width" not in layout

        component = layout["children"][0]
        assert "level" not in component["props"]
        assert "class_name" not in component["props"]


class TestAllComponentTypes:
    """Test each component type can be created and round-tripped."""

    @pytest.mark.parametrize(
        "component_type,component_class,props_class,props_data",
        [
            (
                "heading",
                HeadingComponent,
                HeadingProps,
                {"text": "Hello World", "level": 2, "class_name": "title"},
            ),
            (
                "text",
                TextComponent,
                TextProps,
                {"text": "Body text", "label": "Description"},
            ),
            (
                "html",
                HtmlComponent,
                HtmlProps,
                {"content": "<div>Custom HTML</div>", "class_name": "custom"},
            ),
            (
                "divider",
                DividerComponent,
                DividerProps,
                {"orientation": "horizontal"},
            ),
            (
                "spacer",
                SpacerComponent,
                SpacerProps,
                {"size": 24, "height": 16},
            ),
            (
                "button",
                ButtonComponent,
                ButtonProps,
                {
                    "label": "Click",
                    "action_type": "navigate",
                    "navigate_to": "/home",
                    "variant": "default",
                    "size": "lg",
                    "icon": "ArrowRight",
                },
            ),
            (
                "image",
                ImageComponent,
                ImageProps,
                {
                    "src": "/image.png",
                    "alt": "Image",
                    "max_width": 400,
                    "object_fit": "cover",
                },
            ),
            (
                "badge",
                BadgeComponent,
                BadgeProps,
                {"text": "New", "variant": "secondary"},
            ),
            (
                "progress",
                ProgressComponent,
                ProgressProps,
                {"value": 75, "show_label": True},
            ),
            (
                "file-viewer",
                FileViewerComponent,
                FileViewerProps,
                {
                    "src": "/doc.pdf",
                    "file_name": "document.pdf",
                    "display_mode": "inline",
                },
            ),
            (
                "text-input",
                TextInputComponent,
                TextInputProps,
                {
                    "field_id": "email",
                    "label": "Email",
                    "input_type": "email",
                    "required": True,
                    "min_length": 5,
                },
            ),
            (
                "number-input",
                NumberInputComponent,
                NumberInputProps,
                {
                    "field_id": "age",
                    "label": "Age",
                    "min": 0,
                    "max": 120,
                    "step": 1,
                },
            ),
            (
                "checkbox",
                CheckboxComponent,
                CheckboxProps,
                {
                    "field_id": "agree",
                    "label": "I agree",
                    "description": "Terms and conditions",
                    "default_checked": False,
                },
            ),
            (
                "form-embed",
                FormEmbedComponent,
                FormEmbedProps,
                {
                    "form_id": "form-123",
                    "show_title": True,
                    "show_progress": True,
                },
            ),
        ],
    )
    def test_component_roundtrip(
        self, component_type, component_class, props_class, props_data
    ):
        """Each component type survives round-trip."""
        # Create component with props
        props = props_class(**props_data)
        component = component_class(
            id=f"{component_type}-test",
            type=component_type,
            props=props,
            width="1/2",
            visible="{{ data.show }}",
            class_name="test-class",
        )

        # Export to JSON
        exported = component.model_dump(exclude_none=True)
        json_str = json.dumps(exported)

        # Import from JSON
        imported_data = json.loads(json_str)
        imported = component_class.model_validate(imported_data)

        # Verify basic fields
        assert imported.id == f"{component_type}-test"
        assert imported.type == component_type
        assert imported.width == "1/2"
        assert imported.visible == "{{ data.show }}"
        assert imported.class_name == "test-class"

    def test_card_with_children_roundtrip(self):
        """Card component with children survives round-trip."""
        card = CardComponent(
            id="card-1",
            type="card",
            title="Card Title",
            description="Card description",
            children=[
                HeadingComponent(
                    id="card-heading",
                    type="heading",
                    props=HeadingProps(text="Inner Heading", level=3),
                ),
                TextComponent(
                    id="card-text",
                    type="text",
                    props=TextProps(text="Card body text"),
                ),
            ],
        )

        # Round-trip
        exported = card.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported_data = json.loads(json_str)
        imported = CardComponent.model_validate(imported_data)

        assert imported.title == "Card Title"
        assert imported.children is not None
        assert len(imported.children) == 2
        # Children are validated as discriminated union
        assert imported.children[0].type == "heading"  # type: ignore
        assert imported.children[1].type == "text"  # type: ignore

    def test_stat_card_with_all_options_roundtrip(self):
        """StatCard with trend and onClick survives round-trip."""
        stat = StatCardComponent(
            id="stat-1",
            type="stat-card",
            props=StatCardProps(
                title="Monthly Revenue",
                value="{{ data.revenue }}",
                description="Last 30 days",
                icon="DollarSign",
                trend=StatCardTrend(value="+15.3%", direction="up"),
                on_click=StatCardOnClick(
                    type="workflow",
                    workflow_id="view-revenue-details",
                ),
            ),
        )

        exported = stat.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported_data = json.loads(json_str)
        imported = StatCardComponent.model_validate(imported_data)

        assert imported.props.trend is not None
        assert imported.props.trend.value == "+15.3%"
        assert imported.props.trend.direction == "up"
        assert imported.props.on_click is not None
        assert imported.props.on_click.type == "workflow"

    def test_select_with_static_options_roundtrip(self):
        """Select with static options survives round-trip."""
        select = SelectComponent(
            id="select-1",
            type="select",
            props=SelectProps(
                field_id="country",
                label="Country",
                placeholder="Select a country",
                options=[
                    SelectOption(value="us", label="United States"),
                    SelectOption(value="uk", label="United Kingdom"),
                    SelectOption(value="ca", label="Canada"),
                ],
                required=True,
            ),
        )

        exported = select.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported_data = json.loads(json_str)
        imported = SelectComponent.model_validate(imported_data)

        assert imported.props.options is not None
        assert len(imported.props.options) == 3  # type: ignore
        assert imported.props.options[0].value == "us"  # type: ignore

    def test_select_with_dynamic_options_roundtrip(self):
        """Select with dynamic options source survives round-trip."""
        select = SelectComponent(
            id="select-dynamic",
            type="select",
            props=SelectProps(
                field_id="client",
                label="Client",
                options_source="clientsData",
                value_field="id",
                label_field="name",
            ),
        )

        exported = select.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported_data = json.loads(json_str)
        imported = SelectComponent.model_validate(imported_data)

        assert imported.props.options_source == "clientsData"
        assert imported.props.value_field == "id"
        assert imported.props.label_field == "name"

    def test_data_table_full_roundtrip(self):
        """DataTable with all features survives round-trip."""
        table = DataTableComponent(
            id="full-table",
            type="data-table",
            props=DataTableProps(
                data_source="apiData",
                data_path="results.items",
                columns=[
                    TableColumn(
                        key="name",
                        header="Name",
                        sortable=True,
                        width=200,
                    ),
                    TableColumn(
                        key="status",
                        header="Status",
                        type="badge",
                        badge_colors={
                            "active": "green",
                            "pending": "yellow",
                            "inactive": "gray",
                        },
                    ),
                    TableColumn(
                        key="createdAt",
                        header="Created",
                        type="date",
                    ),
                ],
                selectable=True,
                searchable=True,
                paginated=True,
                page_size=25,
                row_actions=[
                    TableAction(
                        label="View",
                        icon="Eye",
                        on_click=TableActionOnClick(
                            type="navigate",
                            navigate_to="/items/{{ row.id }}",
                        ),
                    ),
                    TableAction(
                        label="Delete",
                        icon="Trash",
                        variant="destructive",
                        on_click=TableActionOnClick(
                            type="workflow",
                            workflow_id="delete-item",
                            action_params={"itemId": "{{ row.id }}"},
                        ),
                        confirm=TableActionConfirm(
                            title="Delete Item",
                            message="Are you sure?",
                            confirm_label="Delete",
                            cancel_label="Cancel",
                        ),
                        disabled="{{ row.isProtected }}",
                    ),
                ],
                header_actions=[
                    TableAction(
                        label="Add New",
                        icon="Plus",
                        on_click=TableActionOnClick(
                            type="navigate",
                            navigate_to="/items/new",
                        ),
                    ),
                ],
                on_row_click=RowClickHandler(
                    type="set-variable",
                    variable_name="selectedItem",
                ),
                empty_message="No items found",
                cache_key="items-table",
            ),
        )

        exported = table.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported_data = json.loads(json_str)
        imported = DataTableComponent.model_validate(imported_data)

        # Verify all features preserved
        assert len(imported.props.columns) == 3
        assert imported.props.columns[1].badge_colors is not None
        assert imported.props.row_actions is not None
        assert len(imported.props.row_actions) == 2
        assert imported.props.row_actions[1].confirm is not None
        assert imported.props.header_actions is not None
        assert imported.props.on_row_click is not None
        assert imported.props.cache_key == "items-table"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_repeat_for_serialization(self):
        """RepeatFor with 'as' alias serializes correctly."""
        repeat = RepeatFor(
            items="{{ workflow.clients }}",
            item_key="id",
            as_="client",  # Using as_ in Python
        )

        data = repeat.model_dump()
        assert "as_" in data  # Serialized as "as_" in snake_case mode
        assert data["as_"] == "client"
        assert "item_key" in data

        # Round-trip
        json_str = json.dumps(data)
        imported = RepeatFor.model_validate(json.loads(json_str))
        assert imported.as_ == "client"

    def test_component_with_repeat_for(self):
        """Component with repeatFor survives round-trip."""
        card = CardComponent(
            id="repeated-card",
            type="card",
            title="{{ item.name }}",
            repeat_for=RepeatFor(
                items="{{ data.items }}",
                item_key="id",
                as_="item",
            ),
        )

        exported = card.model_dump(exclude_none=True)
        assert "repeat_for" in exported
        assert exported["repeat_for"]["as_"] == "item"

        json_str = json.dumps(exported)
        imported = CardComponent.model_validate(json.loads(json_str))
        assert imported.repeat_for is not None
        assert imported.repeat_for.as_ == "item"

    def test_expression_strings_preserved(self):
        """Expression strings like {{ data.value }} are preserved."""
        button = ButtonComponent(
            id="dynamic-btn",
            type="button",
            props=ButtonProps(
                label="{{ page.buttonLabel }}",
                action_type="workflow",
                workflow_id="{{ page.workflowId }}",
                disabled="{{ page.isDisabled }}",
            ),
            visible="{{ data.showButton }}",
        )

        exported = button.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported = ButtonComponent.model_validate(json.loads(json_str))

        assert imported.props.label == "{{ page.buttonLabel }}"
        assert imported.props.workflow_id == "{{ page.workflowId }}"
        assert imported.props.disabled == "{{ page.isDisabled }}"
        assert imported.visible == "{{ data.showButton }}"

    def test_deeply_nested_layouts(self):
        """Deeply nested layouts survive round-trip."""
        layout = LayoutContainer(
            id="level-1",
            type="column",
            children=[
                LayoutContainer(
                    id="level-2",
                    type="row",
                    children=[
                        LayoutContainer(
                            id="level-3",
                            type="grid",
                            columns=3,
                            children=[
                                LayoutContainer(
                                    id="level-4",
                                    type="column",
                                    children=[
                                        HeadingComponent(
                                            id="deep-heading",
                                            type="heading",
                                            props=HeadingProps(
                                                text="Deep nested", level=4
                                            ),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

        exported = layout.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported = LayoutContainer.model_validate(json.loads(json_str))

        # Navigate to deeply nested component
        level_2 = imported.children[0]
        assert level_2.type == "row"  # type: ignore
        level_3 = level_2.children[0]  # type: ignore
        assert level_3.type == "grid"  # type: ignore
        level_4 = level_3.children[0]  # type: ignore
        assert level_4.type == "column"  # type: ignore
        heading = level_4.children[0]  # type: ignore
        assert heading.type == "heading"  # type: ignore
        assert heading.props.text == "Deep nested"  # type: ignore

    def test_navigation_with_nested_items(self):
        """Navigation with nested section items survives round-trip."""
        nav = NavigationConfig(
            sidebar=[
                NavItem(id="home", label="Home", icon="Home", path="/"),
                NavItem(
                    id="admin-section",
                    label="Administration",
                    icon="Settings",
                    is_section=True,
                    children=[
                        NavItem(id="users", label="Users", icon="Users", path="/users"),
                        NavItem(
                            id="roles", label="Roles", icon="Shield", path="/roles"
                        ),
                    ],
                ),
            ],
            show_sidebar=True,
            show_header=True,
            brand_color="#3B82F6",
        )

        exported = nav.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported = NavigationConfig.model_validate(json.loads(json_str))

        assert imported.sidebar is not None
        assert len(imported.sidebar) == 2
        assert imported.sidebar[1].is_section is True
        assert imported.sidebar[1].children is not None
        assert len(imported.sidebar[1].children) == 2

    def test_empty_children_list(self):
        """Empty children list is valid and preserved."""
        layout = LayoutContainer(
            id="empty-layout",
            type="column",
            children=[],
        )

        exported = layout.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported = LayoutContainer.model_validate(json.loads(json_str))

        assert imported.children == []

    def test_mixed_layout_and_component_children(self):
        """Layout with mixed LayoutContainer and Component children works."""
        layout = LayoutContainer(
            id="mixed-parent",
            type="column",
            children=[
                HeadingComponent(
                    id="h1",
                    type="heading",
                    props=HeadingProps(text="Title"),
                ),
                LayoutContainer(
                    id="nested-row",
                    type="row",
                    children=[
                        ButtonComponent(
                            id="btn1",
                            type="button",
                            props=ButtonProps(label="Left", action_type="navigate"),
                        ),
                        ButtonComponent(
                            id="btn2",
                            type="button",
                            props=ButtonProps(label="Right", action_type="navigate"),
                        ),
                    ],
                ),
                TextComponent(
                    id="t1",
                    type="text",
                    props=TextProps(text="Footer text"),
                ),
            ],
        )

        exported = layout.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        imported = LayoutContainer.model_validate(json.loads(json_str))

        assert len(imported.children) == 3
        assert imported.children[0].type == "heading"  # type: ignore
        assert imported.children[1].type == "row"  # type: ignore
        assert imported.children[2].type == "text"  # type: ignore

        # Verify nested row
        nested_row = imported.children[1]
        assert len(nested_row.children) == 2  # type: ignore
