"""
Schema-to-Markdown Utilities for MCP Tools.

Converts Pydantic models to markdown documentation using Field descriptions.
Used by get_*_schema tools to generate documentation from models.
"""

from typing import Any

from pydantic import BaseModel


def model_to_markdown(model_class: type[BaseModel], title: str | None = None) -> str:
    """
    Convert a Pydantic model to markdown documentation using Field descriptions.

    Args:
        model_class: The Pydantic model class to document
        title: Optional title for the section (defaults to model class name)

    Returns:
        Markdown string with a table of fields
    """
    schema = model_class.model_json_schema()
    defs = schema.get("$defs", {})

    # Handle $ref schemas - when model has recursive types, it references itself in $defs
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        if ref_name in defs:
            schema = defs[ref_name]

    lines = []
    lines.append(f"## {title or model_class.__name__}")
    lines.append("")
    lines.append("| Field | Type | Required | Description |")
    lines.append("|-------|------|----------|-------------|")

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for name, prop in properties.items():
        field_type = _format_type(prop, defs)
        is_required = "Yes" if name in required else "No"
        description = prop.get("description", "")
        # Escape pipe characters in description for markdown tables
        description = description.replace("|", "\\|")
        lines.append(f"| {name} | {field_type} | {is_required} | {description} |")

    return "\n".join(lines)


def _format_type(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    """
    Format JSON Schema type for display.

    Handles refs, anyOf, allOf, arrays, and basic types.
    """
    if "$ref" in prop:
        ref = prop["$ref"].split("/")[-1]
        return ref
    if "anyOf" in prop:
        types = [_format_type(t, defs) for t in prop["anyOf"] if t.get("type") != "null"]
        return " \\| ".join(types) if types else "any"
    if "allOf" in prop:
        return _format_type(prop["allOf"][0], defs)
    if "type" in prop:
        t = prop["type"]
        if t == "array":
            items = prop.get("items", {})
            item_type = _format_type(items, defs)
            return f"array[{item_type}]"
        return t
    if "enum" in prop:
        # Handle enum types - show the allowed values
        values = prop.get("enum", [])
        if len(values) <= 5:
            return f"enum: {', '.join(str(v) for v in values)}"
        return "enum"
    if "const" in prop:
        return f"const: {prop['const']}"
    return "any"


def models_to_markdown(
    models: list[tuple[type[BaseModel], str | None]], title: str
) -> str:
    """
    Convert multiple models to markdown documentation.

    Args:
        models: List of (model_class, optional_title) tuples
        title: Main title for the documentation

    Returns:
        Markdown string with all models documented
    """
    lines = [f"# {title}", ""]
    for model_class, model_title in models:
        lines.append(model_to_markdown(model_class, model_title))
        lines.append("")
    return "\n".join(lines)
