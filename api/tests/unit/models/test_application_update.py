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


def test_application_update_ignores_unknown_navigation_fields():
    """Unknown fields in navigation are silently ignored (Pydantic default)."""
    # With extra="ignore" (default), unknown fields like 'items' are dropped
    update = ApplicationUpdate(
        navigation={"items": [{"id": "test", "label": "Test"}]}  # Wrong field name
    )
    # The navigation is accepted but 'items' is ignored, sidebar is None
    assert update.navigation is not None
    assert update.navigation.sidebar is None


def test_application_update_ignores_unknown_nested_fields():
    """Unknown fields in NavItem are silently ignored (Pydantic default)."""
    # With extra="ignore" (default), unknown fields like 'bad_field' are dropped
    update = ApplicationUpdate(
        navigation={
            "sidebar": [
                {"id": "test", "label": "Test", "bad_field": "value"}  # Unknown field
            ]
        }
    )
    # The navigation is accepted, bad_field is ignored
    assert update.navigation is not None
    assert update.navigation.sidebar is not None
    assert update.navigation.sidebar[0].id == "test"


def test_application_update_rejects_missing_required_fields():
    """Navigation items must have required fields (id, label)."""
    with pytest.raises(ValidationError):
        ApplicationUpdate(
            navigation={
                "sidebar": [{"path": "/"}]  # Missing required 'id' and 'label'
            }
        )
