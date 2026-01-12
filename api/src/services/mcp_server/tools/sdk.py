"""
SDK Documentation MCP Tool

Generates accurate SDK documentation dynamically from actual SDK source code.
This ensures documentation is always up-to-date and accurate.
"""

import inspect
import logging
from typing import Any

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


def _extract_class_methods(cls: type) -> list[dict[str, Any]]:
    """Extract method signatures and docstrings from a class."""
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        sig = inspect.signature(method)
        # Skip 'self' parameter for instance methods
        params = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_info = {"name": param_name}
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = _format_annotation(param.annotation)
            if param.default != inspect.Parameter.empty:
                param_info["default"] = repr(param.default)
            params.append(param_info)

        return_type = None
        if sig.return_annotation != inspect.Signature.empty:
            return_type = _format_annotation(sig.return_annotation)

        docstring = method.__doc__ or ""
        # Extract first line as summary
        summary = docstring.split("\n")[0].strip() if docstring else ""

        methods.append({
            "name": name,
            "params": params,
            "return_type": return_type,
            "summary": summary,
            "docstring": docstring,
        })
    return methods


def _format_annotation(annotation: Any) -> str:
    """Format a type annotation as a string."""
    if annotation is None:
        return "None"
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    if hasattr(annotation, "__origin__"):
        # Handle generic types like list[str], dict[str, Any]
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is not None:
            origin_name = getattr(origin, "__name__", str(origin))
            if args:
                args_str = ", ".join(_format_annotation(a) for a in args)
                return f"{origin_name}[{args_str}]"
            return origin_name
    return str(annotation)


def _generate_module_docs(module_name: str, cls: type) -> str:
    """Generate markdown documentation for an SDK module."""
    methods = _extract_class_methods(cls)
    if not methods:
        return ""

    lines = [f"### {module_name}", ""]

    # Get class docstring
    if cls.__doc__:
        summary = cls.__doc__.split("\n")[0].strip()
        lines.append(summary)
        lines.append("")

    for method in methods:
        # Method signature
        params_str = ", ".join(
            f"{p['name']}: {p.get('type', 'Any')}"
            + (f" = {p['default']}" if "default" in p else "")
            for p in method["params"]
        )
        return_str = f" -> {method['return_type']}" if method["return_type"] else ""
        lines.append(f"**`{module_name}.{method['name']}({params_str}){return_str}`**")

        if method["summary"]:
            lines.append(f"  {method['summary']}")
        lines.append("")

    return "\n".join(lines)


def _generate_decorator_docs() -> str:
    """Generate documentation for SDK decorators from actual source."""
    try:
        from bifrost.decorators import workflow, tool, data_provider

        lines = ["## Decorators", ""]

        # @workflow decorator
        sig = inspect.signature(workflow)
        params = []
        for name, param in sig.parameters.items():
            if name == "_func":
                continue
            param_info = f"    {name}"
            if param.annotation != inspect.Parameter.empty:
                param_info += f": {_format_annotation(param.annotation)}"
            if param.default != inspect.Parameter.empty:
                default = param.default
                if default is None:
                    param_info += " = None"
                elif isinstance(default, str):
                    param_info += f' = "{default}"'
                else:
                    param_info += f" = {default}"
            params.append(param_info)

        lines.append("### @workflow")
        lines.append("")
        if workflow.__doc__:
            # Get the description before "Args:"
            doc_parts = workflow.__doc__.split("Args:")
            if doc_parts:
                desc = doc_parts[0].strip().split("\n")[0]
                lines.append(desc)
                lines.append("")

        lines.append("```python")
        lines.append("from bifrost import workflow")
        lines.append("")
        lines.append("@workflow(")
        lines.extend([f"{p}," for p in params])
        lines.append(")")
        lines.append("async def my_workflow(param1: str, param2: int = 10) -> dict:")
        lines.append('    """Workflow description."""')
        lines.append("    return {\"result\": \"success\"}")
        lines.append("```")
        lines.append("")

        # @tool decorator
        lines.append("### @tool")
        lines.append("")
        if tool.__doc__:
            desc = tool.__doc__.split("\n")[0].strip()
            lines.append(desc)
            lines.append("")
        lines.append("```python")
        lines.append("from bifrost import workflow  # or use the tool alias")
        lines.append("")
        lines.append('@workflow(is_tool=True, description="Search for users")')
        lines.append("async def search_users(query: str) -> list[dict]:")
        lines.append('    """Search for users."""')
        lines.append("    return []")
        lines.append("```")
        lines.append("")

        # @data_provider decorator
        lines.append("### @data_provider")
        lines.append("")
        if data_provider.__doc__:
            desc = data_provider.__doc__.split("\n")[0].strip()
            lines.append(desc)
            lines.append("")
        lines.append("```python")
        lines.append("from bifrost import data_provider")
        lines.append("")
        lines.append("@data_provider(")
        lines.append('    name="Customer List",')
        lines.append('    description="Returns customers for dropdown",')
        lines.append("    cache_ttl_seconds=300,")
        lines.append(")")
        lines.append("async def get_customers() -> list[dict]:")
        lines.append('    """Get customers for dropdown."""')
        lines.append("    return [")
        lines.append('        {"label": "Acme Corp", "value": "acme-123"},')
        lines.append("    ]")
        lines.append("```")
        lines.append("")

        return "\n".join(lines)
    except ImportError as e:
        logger.warning(f"Could not import decorators: {e}")
        return ""


def _generate_error_docs() -> str:
    """Generate documentation for SDK error classes."""
    try:
        # Import to verify they exist (used in docstring examples)
        import bifrost
        _ = (bifrost.UserError, bifrost.WorkflowError, bifrost.ValidationError,
             bifrost.IntegrationError, bifrost.ConfigurationError)

        lines = ["## Error Classes", ""]
        lines.append("Use these errors to signal different failure modes in workflows:")
        lines.append("")
        lines.append("```python")
        lines.append("from bifrost import UserError, WorkflowError, ValidationError")
        lines.append("")
        lines.append("# User-facing error (shown to user)")
        lines.append('raise UserError("Invalid email format")')
        lines.append("")
        lines.append("# Workflow execution error")
        lines.append('raise WorkflowError("Failed to process request")')
        lines.append("")
        lines.append("# Validation error")
        lines.append('raise ValidationError("Missing required field: name")')
        lines.append("")
        lines.append("# Integration error (external service failed)")
        lines.append('raise IntegrationError("HaloPSA API returned 500")')
        lines.append("")
        lines.append("# Configuration error")
        lines.append('raise ConfigurationError("Missing API_KEY configuration")')
        lines.append("```")
        lines.append("")

        return "\n".join(lines)
    except ImportError:
        return ""


def _generate_context_docs() -> str:
    """Generate documentation for execution context."""
    lines = ["## Execution Context", ""]
    lines.append("Access execution context within workflows without parameters:")
    lines.append("")
    lines.append("```python")
    lines.append("from bifrost import context")
    lines.append("")
    lines.append("@workflow")
    lines.append("async def my_workflow() -> dict:")
    lines.append("    # Access caller information")
    lines.append("    user_id = context.user_id")
    lines.append("    org_id = context.org_id")
    lines.append("    execution_id = context.execution_id")
    lines.append("    ")
    lines.append("    # Access form inputs (if triggered from form)")
    lines.append("    form_data = context.form_inputs")
    lines.append("    ")
    lines.append("    return {\"user\": user_id}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _generate_models_docs() -> str:
    """Generate documentation for SDK models."""
    try:
        # Import module to verify models exist
        import bifrost.models as _  # noqa: F401

        lines = ["## SDK Models", ""]
        lines.append("Common return types from SDK methods:")
        lines.append("")
        lines.append("| Model | Description |")
        lines.append("|-------|-------------|")
        lines.append("| `AIResponse` | AI completion response (content, tokens, model) |")
        lines.append("| `AIStreamChunk` | Streaming AI chunk (content, done, tokens) |")
        lines.append("| `ConfigData` | Configuration data with dot-notation access |")
        lines.append("| `DocumentData` | Table document with data and metadata |")
        lines.append("| `DocumentList` | Query result with documents and pagination |")
        lines.append("| `IntegrationData` | Integration config with OAuth credentials |")
        lines.append("| `KnowledgeDocument` | Knowledge base document with score |")
        lines.append("| `NamespaceInfo` | Knowledge namespace with document counts |")
        lines.append("| `OAuthCredentials` | OAuth tokens and connection details |")
        lines.append("| `TableInfo` | Table metadata (id, name, schema) |")
        lines.append("")

        return "\n".join(lines)
    except ImportError:
        return ""


@system_tool(
    id="get_sdk_schema",
    name="Get SDK Schema",
    description="Get documentation about the Bifrost SDK modules, decorators, and features. Generated from actual SDK source code.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_sdk_schema(context: Any) -> str:  # noqa: ARG001
    """Get SDK documentation generated from actual SDK source code."""
    try:
        # Import SDK modules
        from bifrost import (
            ai,
            config,
            executions,
            files,
            forms,
            integrations,
            knowledge,
            organizations,
            roles,
            tables,
            users,
            workflows,
        )

        lines = ["# Bifrost SDK Documentation", ""]
        lines.append("All SDK methods are async and must be awaited.")
        lines.append("")
        lines.append("```python")
        lines.append("from bifrost import ai, config, files, integrations, knowledge, tables")
        lines.append("from bifrost import workflow, data_provider, context")
        lines.append("from bifrost import UserError, WorkflowError, ValidationError")
        lines.append("```")
        lines.append("")

        # Generate decorator docs
        lines.append(_generate_decorator_docs())

        # Generate context docs
        lines.append(_generate_context_docs())

        # Generate error docs
        lines.append(_generate_error_docs())

        # Generate module documentation
        lines.append("## SDK Modules")
        lines.append("")

        modules = [
            ("ai", ai),
            ("config", config),
            ("executions", executions),
            ("files", files),
            ("forms", forms),
            ("integrations", integrations),
            ("knowledge", knowledge),
            ("organizations", organizations),
            ("roles", roles),
            ("tables", tables),
            ("users", users),
            ("workflows", workflows),
        ]

        for name, module in modules:
            doc = _generate_module_docs(name, module)
            if doc:
                lines.append(doc)

        # Generate models docs
        lines.append(_generate_models_docs())

        return "\n".join(lines)

    except ImportError as e:
        logger.exception(f"Error importing SDK modules: {e}")
        return f"Error generating SDK documentation: {e}"
