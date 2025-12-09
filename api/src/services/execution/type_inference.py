"""
Type Inference Module

Extracts workflow parameter metadata from Python function signatures.
Eliminates the need for @param decorators by deriving all information
from type hints and default values.

Usage:
    from src.services.execution.type_inference import extract_parameters_from_signature

    @workflow
    async def my_workflow(name: str, count: int = 1, active: bool = True) -> dict:
        ...

    # Parameters are automatically derived:
    # - name: type=string, required=True, label="Name"
    # - count: type=int, required=False, default_value=1, label="Count"
    # - active: type=bool, required=False, default_value=True, label="Active"
"""

import inspect
import logging
import re
from typing import Any, Union, get_args, get_origin, get_type_hints

from src.sdk.context import ExecutionContext

logger = logging.getLogger(__name__)

# Type mapping: Python type -> UI type string
TYPE_MAPPING: dict[type, str] = {
    str: "string",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
    dict: "json",
}

# Valid UI type strings for parameter validation
VALID_PARAM_TYPES: set[str] = {"string", "int", "bool", "float", "json", "list"}


def get_ui_type(python_type: Any) -> str:
    """
    Convert Python type annotation to UI type string.

    Args:
        python_type: Python type annotation

    Returns:
        UI type string (string, int, bool, float, list, json)

    Examples:
        get_ui_type(str) -> "string"
        get_ui_type(int) -> "int"
        get_ui_type(list[str]) -> "list"
        get_ui_type(dict[str, Any]) -> "json"
        get_ui_type(str | None) -> "string"
    """
    # Handle None type
    if python_type is type(None):
        return "string"

    # Direct mapping
    if python_type in TYPE_MAPPING:
        return TYPE_MAPPING[python_type]

    # Handle generic types (list[str], dict[str, Any], etc.)
    origin = get_origin(python_type)
    if origin is list:
        return "list"
    if origin is dict:
        return "json"

    # Handle Union types (str | None, Optional[str], Union[str, None])
    if origin is Union:
        args = get_args(python_type)
        # Filter out NoneType to get the actual type
        non_none_types = [t for t in args if t is not type(None)]
        if non_none_types:
            return get_ui_type(non_none_types[0])
        return "string"

    # Handle Python 3.10+ union syntax (str | None) - UnionType
    type_name = type(python_type).__name__
    if type_name == "UnionType":
        args = get_args(python_type)
        non_none_types = [t for t in args if t is not type(None)]
        if non_none_types:
            return get_ui_type(non_none_types[0])
        return "string"

    # Fallback for Any, unknown types, or complex types
    return "json"


def is_optional_type(python_type: Any) -> bool:
    """
    Check if a type annotation indicates an optional parameter.

    Args:
        python_type: Python type annotation

    Returns:
        True if the type is Optional (Union with None)

    Examples:
        is_optional_type(str) -> False
        is_optional_type(str | None) -> True
        is_optional_type(Optional[str]) -> True
    """
    origin = get_origin(python_type)

    # Handle Union types (Optional[str] is Union[str, None])
    if origin is Union:
        args = get_args(python_type)
        return type(None) in args

    # Handle Python 3.10+ union syntax (str | None)
    type_name = type(python_type).__name__
    if type_name == "UnionType":
        args = get_args(python_type)
        return type(None) in args

    return False


def generate_label(param_name: str) -> str:
    """
    Generate human-readable label from parameter name.

    Args:
        param_name: Parameter name (e.g., "user_email", "firstName")

    Returns:
        Human-readable label (e.g., "User Email", "First Name")

    Examples:
        generate_label("user_email") -> "User Email"
        generate_label("firstName") -> "First Name"
        generate_label("api_key") -> "Api Key"
    """
    # Replace underscores with spaces
    label = param_name.replace("_", " ")
    # Handle camelCase by inserting space before capital letters
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    # Title case
    return label.title()


def extract_parameters_from_signature(func: Any) -> list[dict[str, Any]]:
    """
    Extract parameter metadata from function signature.

    Args:
        func: The workflow/data provider function

    Returns:
        List of parameter dictionaries with:
        - name: str
        - type: str (string, int, bool, float, list, json)
        - required: bool
        - label: str
        - default_value: Any (optional, only if has default)

    Note:
        - ExecutionContext parameters are excluded
        - *args and **kwargs are excluded
        - Parameters without type hints default to "string"
    """
    parameters: list[dict[str, Any]] = []

    try:
        sig = inspect.signature(func)

        # Try to get type hints (handles forward references)
        try:
            type_hints = get_type_hints(func)
        except Exception:
            type_hints = {}

        for param_name, param in sig.parameters.items():
            # Skip *args and **kwargs
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            # Get type from type hints or annotation
            param_type = type_hints.get(param_name, param.annotation)

            # Skip ExecutionContext parameter (by type or by name)
            if param_type is not inspect.Parameter.empty:
                # Check if it's ExecutionContext
                if param_type is ExecutionContext:
                    continue
                # Handle string annotations
                if isinstance(param_type, str) and "ExecutionContext" in param_type:
                    continue

            # Skip parameter named "context" without type hint (legacy support)
            if param_name == "context" and param_type is inspect.Parameter.empty:
                continue

            # Determine if parameter has a default value
            has_default = param.default is not inspect.Parameter.empty
            default_value = param.default if has_default else None

            # Determine UI type from annotation
            if param_type is inspect.Parameter.empty:
                ui_type = "string"  # Default for untyped parameters
                is_optional = has_default
            else:
                ui_type = get_ui_type(param_type)
                is_optional = is_optional_type(param_type) or has_default

            # Build parameter metadata
            param_meta: dict[str, Any] = {
                "name": param_name,
                "type": ui_type,
                "required": not is_optional,
                "label": generate_label(param_name),
            }

            # Add default_value only if it exists and is serializable
            if has_default and default_value is not None:
                # Only include primitive default values that can be serialized
                if isinstance(default_value, (str, int, float, bool, list, dict)):
                    param_meta["default_value"] = default_value

            parameters.append(param_meta)

        return parameters

    except Exception as e:
        # Log error but return empty list to avoid breaking discovery
        logger.warning(f"Failed to extract parameters from {getattr(func, '__name__', func)}: {e}")
        return []
