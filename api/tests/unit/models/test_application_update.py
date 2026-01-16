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


def test_application_update_navigation_validates_nested_items():
    """Navigation items should reject unknown fields."""
    with pytest.raises(ValidationError):
        ApplicationUpdate(
            navigation={
                "sidebar": [
                    {"id": "test", "label": "Test", "bad_field": "value"}  # Unknown field
                ]
            }
        )
