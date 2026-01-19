"""Entity type detection for platform files.

Detects whether a file should be stored in the database (platform entities)
or in S3 (regular files).

Platform entities:
- Workflows (.py with @workflow decorator)
- Data providers (.py with @data_provider decorator)
- Forms (.form.json)
- Agents (.agent.json)

Regular files go to S3.
"""

import ast
from typing import Any


def detect_platform_entity_type(path: str, content: bytes) -> str | None:
    """
    Detect if a file is a platform entity that should be stored in the database.

    Platform entities are stored in the database, not S3:
    - Workflows (.py with @workflow decorator): stored in workflows.code
    - Data providers (.py with @data_provider decorator): stored in workflows.code
    - Forms (.form.json): stored in forms table
    - Agents (.agent.json): stored in agents table

    Regular files (modules, data files, configs) go to S3.

    Args:
        path: File path
        content: File content

    Returns:
        Entity type ("workflow", "form", "agent") or None for regular files
    """
    # JSON platform entities - always go to DB
    if path.endswith(".form.json"):
        return "form"
    if path.endswith(".agent.json"):
        return "agent"

    # Python files - check for SDK decorators
    if path.endswith(".py"):
        return detect_python_entity_type(content)

    # Regular file - goes to S3
    return None


def detect_python_entity_type(content: bytes) -> str | None:
    """
    Check if Python content has SDK decorators (@workflow, @data_provider).

    Uses fast regex check first, then AST verification if needed.
    Returns "workflow" if decorators are found (includes data_provider since
    it's stored in the workflows table). Returns "module" for all other
    Python files (helper modules, utilities, etc.) - these are stored in
    workspace_files.content instead of S3.

    Args:
        content: Python file content

    Returns:
        "workflow" if SDK decorators found, "module" for other Python files
    """
    try:
        content_str = content.decode("utf-8", errors="replace")
    except Exception:
        # Non-decodable content - not a valid Python module
        return None

    # Fast regex check - if no decorator-like patterns, it's a module
    if (
        "@workflow" not in content_str
        and "@data_provider" not in content_str
        and "@tool" not in content_str
    ):
        return "module"

    # AST verification - confirm decorators are actually used
    try:
        tree = ast.parse(content_str)
    except SyntaxError:
        # Syntax error but still Python - store as module
        # The _index_python_file will report the syntax error
        return "module"

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            decorator_info = _parse_decorator(decorator)
            if decorator_info:
                decorator_name, _ = decorator_info
                if decorator_name in ("workflow", "data_provider"):
                    return "workflow"  # Both are in workflows table

    # Has @workflow/@data_provider in content but not as actual decorators
    # (e.g., in comments, strings, or as variable names) - treat as module
    return "module"


def _parse_decorator(decorator: ast.AST) -> tuple[str, dict[str, Any]] | None:
    """
    Parse a decorator AST node to extract name and keyword arguments.

    Returns:
        Tuple of (decorator_name, kwargs_dict) or None if not a workflow/provider decorator
    """
    # Handle @workflow (no parentheses)
    if isinstance(decorator, ast.Name):
        if decorator.id in ("workflow", "tool", "data_provider"):
            return decorator.id, {}
        return None

    # Handle @workflow(...) (with parentheses)
    if isinstance(decorator, ast.Call):
        if isinstance(decorator.func, ast.Name):
            decorator_name = decorator.func.id
        elif isinstance(decorator.func, ast.Attribute):
            # Handle module.workflow (e.g., bifrost.workflow)
            decorator_name = decorator.func.attr
        else:
            return None

        if decorator_name not in ("workflow", "tool", "data_provider"):
            return None

        # Extract keyword arguments
        kwargs = {}
        for keyword in decorator.keywords:
            if keyword.arg:
                value = _ast_value_to_python(keyword.value)
                kwargs[keyword.arg] = value

        return decorator_name, kwargs

    return None


def _ast_value_to_python(node: ast.AST) -> Any:
    """Convert an AST node to a Python value."""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str):  # Python 3.7 compatibility
        return node.s
    elif isinstance(node, ast.Num):  # Python 3.7 compatibility
        return node.n
    elif isinstance(node, ast.NameConstant):  # Python 3.7 compatibility
        return node.value
    elif isinstance(node, ast.List):
        return [_ast_value_to_python(elt) for elt in node.elts]
    elif isinstance(node, ast.Dict):
        return {
            _ast_value_to_python(k): _ast_value_to_python(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    elif isinstance(node, ast.Name):
        # Handle True, False, None
        if node.id == "True":
            return True
        elif node.id == "False":
            return False
        elif node.id == "None":
            return None
    return None
