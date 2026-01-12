"""
Validation helpers for App Builder MCP tools.

Provides Pydantic validation for layouts, components, and navigation.
"""

from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from src.models.contracts.app_components import (
    BadgeProps,
    ButtonProps,
    CardProps,
    CheckboxProps,
    DataTableProps,
    DividerProps,
    FileViewerProps,
    FormEmbedProps,
    FormGroupProps,
    HeadingProps,
    HtmlProps,
    ImageProps,
    LayoutContainer,
    ModalProps,
    NavigationConfig,
    NumberInputProps,
    ProgressProps,
    SelectProps,
    SpacerProps,
    StatCardProps,
    TabsProps,
    TextInputProps,
    TextProps,
)

# Map component types to their Props models
COMPONENT_PROPS_MAP: dict[str, type] = {
    "heading": HeadingProps,
    "text": TextProps,
    "html": HtmlProps,
    "card": CardProps,
    "divider": DividerProps,
    "spacer": SpacerProps,
    "button": ButtonProps,
    "stat-card": StatCardProps,
    "image": ImageProps,
    "badge": BadgeProps,
    "progress": ProgressProps,
    "data-table": DataTableProps,
    "tabs": TabsProps,
    "file-viewer": FileViewerProps,
    "modal": ModalProps,
    "text-input": TextInputProps,
    "number-input": NumberInputProps,
    "select": SelectProps,
    "checkbox": CheckboxProps,
    "form-embed": FormEmbedProps,
    "form-group": FormGroupProps,
}


def format_validation_errors(errors: list[ErrorDetails]) -> str:
    """
    Format Pydantic validation errors into a readable message.

    Args:
        errors: List of error details from ValidationError.errors()

    Returns:
        Human-readable error message string
    """
    messages = []
    for error in errors:
        loc = ".".join(str(part) for part in error.get("loc", []))
        msg = error.get("msg", "validation error")
        if loc:
            messages.append(f"{loc}: {msg}")
        else:
            messages.append(msg)
    return "; ".join(messages)


# Alias for backwards compatibility
_format_validation_errors = format_validation_errors


def validate_layout(layout: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a layout structure using LayoutContainer model.

    Args:
        layout: Layout dictionary to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    try:
        LayoutContainer.model_validate(layout)
        return True, None
    except ValidationError as e:
        return False, f"Invalid layout: {_format_validation_errors(e.errors())}"


def validate_component_props(component_type: str, props: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate props for a component type.

    Args:
        component_type: The component type (e.g., "heading", "button")
        props: The props dictionary to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
        Unknown component types are allowed (returns valid) to support
        newer component types the frontend may have.
    """
    props_model = COMPONENT_PROPS_MAP.get(component_type)
    if not props_model:
        # Unknown type - allow it (frontend might have newer types)
        return True, None

    try:
        props_model.model_validate(props)
        return True, None
    except ValidationError as e:
        return False, f"Invalid props for {component_type}: {_format_validation_errors(e.errors())}"


def validate_navigation(navigation: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate navigation configuration.

    Args:
        navigation: Navigation config dictionary to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    try:
        NavigationConfig.model_validate(navigation)
        return True, None
    except ValidationError as e:
        return False, f"Invalid navigation: {_format_validation_errors(e.errors())}"
