# api/tests/unit/test_unified_component_model.py
"""Unit tests for unified AppComponent model."""
import pytest
from pydantic import ValidationError


def test_row_component_accepts_children():
    """Row component should accept children list."""
    from src.models.contracts.app_components import HeadingComponent, HeadingProps, RowComponent

    # Use existing HeadingComponent structure with props wrapper
    heading = HeadingComponent(id="h1", props=HeadingProps(text="Hello"))
    row = RowComponent(id="row1", children=[heading], gap="md")

    assert row.type == "row"
    assert len(row.children) == 1
    assert row.children[0].id == "h1"


def test_button_component_rejects_children():
    """Button component should reject children field."""
    from src.models.contracts.app_components import ButtonComponent, ButtonProps

    with pytest.raises(ValidationError) as exc_info:
        # ButtonComponent uses props wrapper and should have extra="forbid" on the model
        ButtonComponent(
            id="btn1",
            props=ButtonProps(label="Click", action_type="custom"),
            children=[],  # type: ignore[call-arg]
        )

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

    # Button should parse to ButtonComponent (with props wrapper)
    btn_data = {
        "id": "b1",
        "type": "button",
        "props": {"label": "Click", "action_type": "custom"},
    }
    btn = adapter.validate_python(btn_data)
    assert btn.__class__.__name__ == "ButtonComponent"


# ============================================================================
# Task 1.2: Content Container Components Tests
# ============================================================================


def test_card_component_with_children():
    """Card should have children at top level, not in props."""
    from src.models.contracts.app_components import CardComponent, HeadingComponent, HeadingProps

    # Use HeadingComponent as child (has existing props wrapper structure)
    heading = HeadingComponent(id="h1", props=HeadingProps(text="Hello"))
    card = CardComponent(
        id="card1",
        title="My Card",
        children=[heading],
    )

    assert card.type == "card"
    assert card.title == "My Card"
    assert len(card.children) == 1


def test_card_component_with_collapsible():
    """Card should support collapsible configuration."""
    from src.models.contracts.app_components import CardComponent

    card = CardComponent(
        id="card1",
        title="Collapsible Card",
        collapsible=True,
        default_collapsed=True,
    )

    assert card.collapsible is True
    assert card.default_collapsed is True


def test_modal_component_with_children():
    """Modal should have children at top level."""
    from src.models.contracts.app_components import HeadingComponent, HeadingProps, ModalComponent

    heading = HeadingComponent(id="h1", props=HeadingProps(text="Modal content"))
    modal = ModalComponent(
        id="modal1",
        title="My Modal",
        children=[heading],
    )

    assert modal.type == "modal"
    assert len(modal.children) == 1


def test_modal_component_with_footer_actions():
    """Modal should support footer actions."""
    from src.models.contracts.app_components import ModalComponent, ModalFooterAction

    modal = ModalComponent(
        id="modal1",
        title="Confirm",
        footer_actions=[
            ModalFooterAction(label="Cancel", action_type="custom"),
            ModalFooterAction(label="Submit", action_type="submit", variant="default"),
        ],
    )

    assert len(modal.footer_actions) == 2
    assert modal.footer_actions[0].label == "Cancel"


def test_tabs_with_tab_items():
    """Tabs should contain TabItemComponent children."""
    from src.models.contracts.app_components import (
        HeadingComponent,
        HeadingProps,
        TabItemComponent,
        TabsComponent,
    )

    tab1 = TabItemComponent(
        id="tab1",
        label="First",
        value="first",
        children=[HeadingComponent(id="h1", props=HeadingProps(text="Tab 1 content"))],
    )
    tabs = TabsComponent(id="tabs1", children=[tab1])

    assert tabs.type == "tabs"
    assert len(tabs.children) == 1
    assert tabs.children[0].type == "tab-item"


def test_tab_item_value_defaults_to_none():
    """TabItem value should default to None (frontend can default to label)."""
    from src.models.contracts.app_components import TabItemComponent

    tab = TabItemComponent(id="tab1", label="First")

    assert tab.label == "First"
    assert tab.value is None


def test_form_group_with_children():
    """FormGroup should have children at top level."""
    from src.models.contracts.app_components import (
        FormGroupComponent,
        TextInputComponent,
        TextInputProps,
    )

    text_input = TextInputComponent(
        id="input1", props=TextInputProps(field_id="name", label="Name")
    )
    form_group = FormGroupComponent(
        id="group1",
        label="User Info",
        direction="row",
        children=[text_input],
    )

    assert form_group.type == "form-group"
    assert form_group.label == "User Info"
    assert len(form_group.children) == 1


def test_container_components_inherit_from_component_base():
    """Content container components should inherit from ComponentBase (have extra=forbid)."""
    from src.models.contracts.app_components import (
        CardComponent,
        FormGroupComponent,
        ModalComponent,
        TabItemComponent,
        TabsComponent,
    )

    # All should reject unknown fields due to extra="forbid" from ComponentBase
    with pytest.raises(ValidationError):
        CardComponent(id="c1", unknown_field="x")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ModalComponent(id="m1", title="Test", unknown_field="x")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TabsComponent(id="t1", unknown_field="x")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TabItemComponent(id="ti1", label="Tab", unknown_field="x")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        FormGroupComponent(id="fg1", unknown_field="x")  # type: ignore[call-arg]


def test_discriminated_union_routes_container_types():
    """AppComponent union should route container types correctly."""
    from pydantic import TypeAdapter

    from src.models.contracts.app_components import AppComponent

    adapter = TypeAdapter(AppComponent)

    # Card should parse to CardComponent
    card_data = {"id": "c1", "type": "card", "title": "Test", "children": []}
    card = adapter.validate_python(card_data)
    assert card.__class__.__name__ == "CardComponent"

    # Modal should parse to ModalComponent
    modal_data = {"id": "m1", "type": "modal", "title": "Test", "children": []}
    modal = adapter.validate_python(modal_data)
    assert modal.__class__.__name__ == "ModalComponent"

    # Tabs should parse to TabsComponent
    tabs_data = {"id": "t1", "type": "tabs", "children": []}
    tabs = adapter.validate_python(tabs_data)
    assert tabs.__class__.__name__ == "TabsComponent"

    # TabItem should parse to TabItemComponent
    tab_item_data = {"id": "ti1", "type": "tab-item", "label": "Tab 1", "children": []}
    tab_item = adapter.validate_python(tab_item_data)
    assert tab_item.__class__.__name__ == "TabItemComponent"

    # FormGroup should parse to FormGroupComponent
    form_group_data = {"id": "fg1", "type": "form-group", "children": []}
    form_group = adapter.validate_python(form_group_data)
    assert form_group.__class__.__name__ == "FormGroupComponent"
