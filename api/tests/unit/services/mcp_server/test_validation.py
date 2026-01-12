"""Tests for App Builder MCP tools validation helpers."""

from src.services.mcp_server.tools.validation import (
    validate_component_props,
    validate_layout,
    validate_navigation,
)


class TestValidateLayout:
    """Tests for validate_layout function."""

    def test_valid_simple_layout(self) -> None:
        """Test a valid simple column layout."""
        layout = {
            "id": "root",
            "type": "column",
            "children": [],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is True
        assert error is None

    def test_valid_layout_with_components(self) -> None:
        """Test a valid layout with nested components."""
        layout = {
            "id": "root",
            "type": "column",
            "gap": 16,
            "padding": 24,
            "children": [
                {
                    "id": "heading1",
                    "type": "heading",
                    "props": {"text": "Welcome", "level": 1},
                },
                {
                    "id": "text1",
                    "type": "text",
                    "props": {"text": "Hello world"},
                },
            ],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is True
        assert error is None

    def test_valid_nested_layout(self) -> None:
        """Test a valid nested layout with row inside column."""
        layout = {
            "id": "root",
            "type": "column",
            "children": [
                {
                    "id": "row1",
                    "type": "row",
                    "gap": 8,
                    "children": [
                        {
                            "id": "btn1",
                            "type": "button",
                            "props": {"label": "Cancel", "action_type": "navigate"},
                        },
                        {
                            "id": "btn2",
                            "type": "button",
                            "props": {"label": "Save", "action_type": "submit"},
                        },
                    ],
                },
            ],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is True
        assert error is None

    def test_invalid_layout_missing_type(self) -> None:
        """Test invalid layout missing required 'type' field."""
        layout = {
            "id": "root",
            "children": [],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is False
        assert error is not None
        assert "type" in error.lower()

    def test_invalid_layout_wrong_type(self) -> None:
        """Test invalid layout with wrong type value."""
        layout = {
            "id": "root",
            "type": "invalid_type",
            "children": [],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is False
        assert error is not None

    def test_invalid_layout_missing_children(self) -> None:
        """Test invalid layout missing required 'children' field."""
        layout = {
            "id": "root",
            "type": "column",
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is False
        assert error is not None

    def test_invalid_layout_missing_id(self) -> None:
        """Test invalid layout missing required 'id' field."""
        layout = {
            "type": "column",
            "children": [],
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is False
        assert error is not None
        assert "id" in error.lower()


class TestValidateComponentProps:
    """Tests for validate_component_props function."""

    def test_valid_heading_props(self) -> None:
        """Test valid heading props."""
        props = {"text": "Welcome"}
        is_valid, error = validate_component_props("heading", props)
        assert is_valid is True
        assert error is None

    def test_valid_heading_props_with_level(self) -> None:
        """Test valid heading props with level."""
        props = {"text": "Welcome", "level": 1}
        is_valid, error = validate_component_props("heading", props)
        assert is_valid is True
        assert error is None

    def test_invalid_heading_props_missing_text(self) -> None:
        """Test invalid heading props missing required text."""
        props = {"level": 1}
        is_valid, error = validate_component_props("heading", props)
        assert is_valid is False
        assert error is not None
        assert "text" in error.lower()

    def test_valid_button_props(self) -> None:
        """Test valid button props."""
        props = {"label": "Click me", "action_type": "navigate"}
        is_valid, error = validate_component_props("button", props)
        assert is_valid is True
        assert error is None

    def test_invalid_button_props_missing_action_type(self) -> None:
        """Test invalid button props missing action_type."""
        props = {"label": "Click me"}
        is_valid, error = validate_component_props("button", props)
        assert is_valid is False
        assert error is not None
        assert "action" in error.lower()

    def test_invalid_button_props_wrong_action_type(self) -> None:
        """Test invalid button props with wrong action_type."""
        props = {"label": "Click me", "action_type": "invalid"}
        is_valid, error = validate_component_props("button", props)
        assert is_valid is False
        assert error is not None

    def test_valid_data_table_props(self) -> None:
        """Test valid data-table props."""
        props = {
            "data_source": "customers",
            "columns": [
                {"key": "name", "header": "Name"},
                {"key": "email", "header": "Email"},
            ],
        }
        is_valid, error = validate_component_props("data-table", props)
        assert is_valid is True
        assert error is None

    def test_invalid_data_table_props_missing_columns(self) -> None:
        """Test invalid data-table props missing columns."""
        props = {"data_source": "customers"}
        is_valid, error = validate_component_props("data-table", props)
        assert is_valid is False
        assert error is not None
        assert "columns" in error.lower()

    def test_valid_text_input_props(self) -> None:
        """Test valid text-input props."""
        props = {"field_id": "name", "label": "Name", "required": True}
        is_valid, error = validate_component_props("text-input", props)
        assert is_valid is True
        assert error is None

    def test_invalid_text_input_props_missing_field_id(self) -> None:
        """Test invalid text-input props missing field_id."""
        props = {"label": "Name"}
        is_valid, error = validate_component_props("text-input", props)
        assert is_valid is False
        assert error is not None
        assert "field" in error.lower()

    def test_valid_select_props(self) -> None:
        """Test valid select props with static options."""
        props = {
            "field_id": "status",
            "label": "Status",
            "options": [
                {"value": "active", "label": "Active"},
                {"value": "inactive", "label": "Inactive"},
            ],
        }
        is_valid, error = validate_component_props("select", props)
        assert is_valid is True
        assert error is None

    def test_valid_select_props_with_expression_options(self) -> None:
        """Test valid select props with expression options."""
        props = {
            "field_id": "category",
            "options": "{{ workflow.categories }}",
        }
        is_valid, error = validate_component_props("select", props)
        assert is_valid is True
        assert error is None

    def test_unknown_component_type_allowed(self) -> None:
        """Test that unknown component types pass validation."""
        props = {"anything": "goes"}
        is_valid, error = validate_component_props("future-component", props)
        assert is_valid is True
        assert error is None

    def test_valid_modal_props(self) -> None:
        """Test valid modal props."""
        props = {
            "title": "Add Item",
            "content": {
                "id": "modal-content",
                "type": "column",
                "children": [],
            },
        }
        is_valid, error = validate_component_props("modal", props)
        assert is_valid is True
        assert error is None

    def test_valid_card_props_with_children(self) -> None:
        """Test valid card props with children."""
        props = {
            "title": "My Card",
            "children": [
                {
                    "id": "text1",
                    "type": "text",
                    "props": {"text": "Card content"},
                },
            ],
        }
        is_valid, error = validate_component_props("card", props)
        assert is_valid is True
        assert error is None


class TestValidateNavigation:
    """Tests for validate_navigation function."""

    def test_valid_navigation_with_sidebar(self) -> None:
        """Test valid navigation with sidebar items."""
        navigation = {
            "show_sidebar": True,
            "sidebar": [
                {"id": "home", "label": "Home", "path": "/"},
                {"id": "users", "label": "Users", "icon": "users", "path": "/users"},
            ],
        }
        is_valid, error = validate_navigation(navigation)
        assert is_valid is True
        assert error is None

    def test_valid_empty_navigation(self) -> None:
        """Test valid empty navigation config."""
        navigation = {}
        is_valid, error = validate_navigation(navigation)
        assert is_valid is True
        assert error is None

    def test_valid_navigation_with_branding(self) -> None:
        """Test valid navigation with branding options."""
        navigation = {
            "show_sidebar": True,
            "show_header": True,
            "logo_url": "https://example.com/logo.png",
            "brand_color": "#ff0000",
        }
        is_valid, error = validate_navigation(navigation)
        assert is_valid is True
        assert error is None

    def test_valid_navigation_with_nested_sections(self) -> None:
        """Test valid navigation with nested section groups."""
        navigation = {
            "sidebar": [
                {
                    "id": "admin-section",
                    "label": "Administration",
                    "is_section": True,
                    "children": [
                        {"id": "users", "label": "Users", "path": "/admin/users"},
                        {"id": "settings", "label": "Settings", "path": "/admin/settings"},
                    ],
                },
            ],
        }
        is_valid, error = validate_navigation(navigation)
        assert is_valid is True
        assert error is None

    def test_invalid_navigation_item_missing_id(self) -> None:
        """Test invalid navigation with item missing id."""
        navigation = {
            "sidebar": [
                {"label": "Home", "path": "/"},
            ],
        }
        is_valid, error = validate_navigation(navigation)
        assert is_valid is False
        assert error is not None
        assert "id" in error.lower()

    def test_invalid_navigation_item_missing_label(self) -> None:
        """Test invalid navigation with item missing label."""
        navigation = {
            "sidebar": [
                {"id": "home", "path": "/"},
            ],
        }
        is_valid, error = validate_navigation(navigation)
        assert is_valid is False
        assert error is not None
        assert "label" in error.lower()


class TestValidationErrorFormatting:
    """Tests for error message formatting."""

    def test_error_includes_field_location(self) -> None:
        """Test that error messages include field location."""
        props = {"text": "Hello", "level": "invalid"}  # level should be int
        is_valid, error = validate_component_props("heading", props)
        assert is_valid is False
        assert error is not None
        assert "level" in error.lower()

    def test_error_includes_component_type(self) -> None:
        """Test that error messages include component type."""
        props = {}  # Missing required text
        is_valid, error = validate_component_props("heading", props)
        assert is_valid is False
        assert error is not None
        assert "heading" in error.lower()

    def test_multiple_errors_combined(self) -> None:
        """Test that multiple validation errors are combined."""
        layout = {
            "type": "invalid",
            # Missing id and children
        }
        is_valid, error = validate_layout(layout)
        assert is_valid is False
        assert error is not None
        # Should mention at least type issue
        assert "type" in error.lower() or "id" in error.lower()
