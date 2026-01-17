# api/tests/unit/test_app_builder_service.py
"""Unit tests for simplified app builder service tree functions."""
from uuid import uuid4


def test_flatten_components_simple():
    """Flatten a simple component list with column containing heading."""
    from src.models.contracts.app_components import ColumnComponent, HeadingComponent
    from src.services.app_builder_service import flatten_components

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

    # Column assertions
    assert col_row["type"] == "column"
    assert col_row["parent_id"] is None
    assert col_row["page_id"] == page_id
    assert col_row["component_order"] == 0

    # Heading assertions
    assert heading_row["type"] == "heading"
    assert heading_row["parent_id"] == col_row["id"]
    assert heading_row["page_id"] == page_id
    assert heading_row["component_order"] == 0
    # Props should contain text
    assert heading_row["props"]["text"] == "Hello"


def test_flatten_components_nested():
    """Flatten nested containers: row > card > text."""
    from src.models.contracts.app_components import (
        CardComponent,
        RowComponent,
        TextComponent,
    )
    from src.services.app_builder_service import flatten_components

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

    # Check parent chain: row -> card -> text
    assert row_row["parent_id"] is None
    assert card_row["parent_id"] == row_row["id"]
    assert text_row["parent_id"] == card_row["id"]

    # Check card props include title
    assert card_row["props"]["title"] == "Card"


def test_flatten_components_preserves_order():
    """Flatten preserves component order within siblings."""
    from src.models.contracts.app_components import ColumnComponent, HeadingComponent
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        ColumnComponent(
            id="col1",
            children=[
                HeadingComponent(id="h1", text="First"),
                HeadingComponent(id="h2", text="Second"),
                HeadingComponent(id="h3", text="Third"),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    h1_row = next(r for r in rows if r["component_id"] == "h1")
    h2_row = next(r for r in rows if r["component_id"] == "h2")
    h3_row = next(r for r in rows if r["component_id"] == "h3")

    assert h1_row["component_order"] == 0
    assert h2_row["component_order"] == 1
    assert h3_row["component_order"] == 2


def test_flatten_components_extracts_base_fields():
    """Flatten extracts ComponentBase fields like visible, width, loading_workflows."""
    from src.models.contracts.app_components import HeadingComponent, RowComponent
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        RowComponent(
            id="row1",
            visible="{{ user.isAdmin }}",
            width="full",
            loading_workflows=["wf-1", "wf-2"],
            children=[
                HeadingComponent(id="h1", text="Title"),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)
    row_row = next(r for r in rows if r["component_id"] == "row1")

    assert row_row["visible"] == "{{ user.isAdmin }}"
    assert row_row["width"] == "full"
    assert row_row["loading_workflows"] == ["wf-1", "wf-2"]


def test_flatten_components_tabs_with_tab_items():
    """Flatten tabs component with tab-item children."""
    from src.models.contracts.app_components import (
        TabItemComponent,
        TabsComponent,
        TextComponent,
    )
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        TabsComponent(
            id="tabs1",
            default_tab="tab1",
            children=[
                TabItemComponent(
                    id="tab1",
                    label="First Tab",
                    value="first",
                    children=[
                        TextComponent(id="t1", text="Tab 1 content"),
                    ],
                ),
                TabItemComponent(
                    id="tab2",
                    label="Second Tab",
                    value="second",
                    children=[
                        TextComponent(id="t2", text="Tab 2 content"),
                    ],
                ),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    # Should have 5 rows: tabs, tab1, t1, tab2, t2
    assert len(rows) == 5

    tabs_row = next(r for r in rows if r["component_id"] == "tabs1")
    tab1_row = next(r for r in rows if r["component_id"] == "tab1")
    tab2_row = next(r for r in rows if r["component_id"] == "tab2")
    t1_row = next(r for r in rows if r["component_id"] == "t1")
    t2_row = next(r for r in rows if r["component_id"] == "t2")

    # Check parent relationships
    assert tabs_row["parent_id"] is None
    assert tab1_row["parent_id"] == tabs_row["id"]
    assert tab2_row["parent_id"] == tabs_row["id"]
    assert t1_row["parent_id"] == tab1_row["id"]
    assert t2_row["parent_id"] == tab2_row["id"]

    # Check tab-item props
    assert tab1_row["props"]["label"] == "First Tab"
    assert tab1_row["props"]["value"] == "first"


def test_flatten_components_grid_with_span():
    """Flatten grid component with children having grid_span."""
    from src.models.contracts.app_components import (
        CardComponent,
        GridComponent,
    )
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        GridComponent(
            id="grid1",
            columns=3,
            gap="md",
            children=[
                CardComponent(id="card1", title="Card 1", grid_span=2),
                CardComponent(id="card2", title="Card 2", grid_span=1),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    grid_row = next(r for r in rows if r["component_id"] == "grid1")
    card1_row = next(r for r in rows if r["component_id"] == "card1")
    card2_row = next(r for r in rows if r["component_id"] == "card2")

    # Check grid props
    assert grid_row["props"]["columns"] == 3
    assert grid_row["props"]["gap"] == "md"

    # Check grid_span is in props
    assert card1_row["props"]["grid_span"] == 2
    assert card2_row["props"]["grid_span"] == 1


def test_flatten_components_form_group():
    """Flatten form-group component with form field children."""
    from src.models.contracts.app_components import (
        FormGroupComponent,
        TextInputComponent,
    )
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        FormGroupComponent(
            id="fg1",
            label="User Info",
            direction="row",
            gap=16,
            children=[
                TextInputComponent(
                    id="input1",
                    field_id="first_name",
                    label="First Name",
                ),
                TextInputComponent(
                    id="input2",
                    field_id="last_name",
                    label="Last Name",
                ),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    assert len(rows) == 3

    fg_row = next(r for r in rows if r["component_id"] == "fg1")
    input1_row = next(r for r in rows if r["component_id"] == "input1")
    input2_row = next(r for r in rows if r["component_id"] == "input2")

    # Check parent relationships
    assert fg_row["parent_id"] is None
    assert input1_row["parent_id"] == fg_row["id"]
    assert input2_row["parent_id"] == fg_row["id"]

    # Check form-group props
    assert fg_row["props"]["label"] == "User Info"
    assert fg_row["props"]["direction"] == "row"
    assert fg_row["props"]["gap"] == 16


def test_flatten_components_modal():
    """Flatten modal component with children."""
    from src.models.contracts.app_components import (
        ModalComponent,
        TextComponent,
    )
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        ModalComponent(
            id="modal1",
            title="Confirm Action",
            description="Are you sure?",
            size="lg",
            children=[
                TextComponent(id="t1", text="Modal body content"),
            ],
        ),
    ]

    rows = flatten_components(components, page_id)

    assert len(rows) == 2

    modal_row = next(r for r in rows if r["component_id"] == "modal1")
    text_row = next(r for r in rows if r["component_id"] == "t1")

    assert modal_row["type"] == "modal"
    assert modal_row["props"]["title"] == "Confirm Action"
    assert modal_row["props"]["description"] == "Are you sure?"
    assert modal_row["props"]["size"] == "lg"

    assert text_row["parent_id"] == modal_row["id"]


def test_flatten_components_empty_children():
    """Flatten handles empty children list correctly."""
    from src.models.contracts.app_components import RowComponent
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        RowComponent(id="row1", children=[]),
    ]

    rows = flatten_components(components, page_id)

    assert len(rows) == 1
    assert rows[0]["component_id"] == "row1"
    assert rows[0]["type"] == "row"


def test_flatten_components_leaf_component_no_children():
    """Flatten handles leaf components that don't have children field."""
    from src.models.contracts.app_components import ButtonComponent
    from src.services.app_builder_service import flatten_components

    page_id = uuid4()
    components = [
        ButtonComponent(
            id="btn1",
            label="Click Me",
            action_type="workflow",
            workflow_id="wf-123",
            variant="default",
        ),
    ]

    rows = flatten_components(components, page_id)

    assert len(rows) == 1

    btn_row = rows[0]
    assert btn_row["component_id"] == "btn1"
    assert btn_row["type"] == "button"
    assert btn_row["props"]["label"] == "Click Me"
    assert btn_row["props"]["action_type"] == "workflow"
    assert btn_row["props"]["workflow_id"] == "wf-123"
