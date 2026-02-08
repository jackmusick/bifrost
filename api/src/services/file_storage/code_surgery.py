"""
Code surgery utilities for removing function blocks from Python source files.

Uses AST to identify function boundaries (including decorators) and performs
line-level removal without modifying the rest of the file.
"""

import ast
import logging

logger = logging.getLogger(__name__)


def remove_function_from_source(source: str, function_name: str) -> str | None:
    """
    Remove a function (and its decorators) from Python source code.

    Args:
        source: The full Python source code
        function_name: Name of the function to remove

    Returns:
        New source with the function removed, or None if the function was
        the only decorated function in the file (caller should delete the file).

    Raises:
        ValueError: If the function is not found in the source
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError(f"Failed to parse source: {e}")

    # Find the target function and count all top-level functions
    target_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    top_level_functions = 0

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_functions += 1
            if node.name == function_name:
                target_node = node

    if target_node is None:
        raise ValueError(f"Function '{function_name}' not found in source")

    # If this is the only top-level function, signal to delete the whole file
    if top_level_functions == 1:
        return None

    # Determine the line range to remove (1-indexed, inclusive)
    # Start from the earliest decorator line
    start_line = target_node.lineno
    if target_node.decorator_list:
        start_line = min(d.lineno for d in target_node.decorator_list)

    end_line = target_node.end_lineno
    if end_line is None:
        raise ValueError(f"Cannot determine end line for function '{function_name}'")

    lines = source.splitlines(keepends=True)

    # Remove the function lines (convert to 0-indexed)
    new_lines = lines[:start_line - 1] + lines[end_line:]

    # Clean up excessive blank lines at the removal site
    # (collapse 3+ consecutive blank lines down to 2)
    result_lines: list[str] = []
    consecutive_blanks = 0
    for line in new_lines:
        if line.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks <= 2:
                result_lines.append(line)
        else:
            consecutive_blanks = 0
            result_lines.append(line)

    result = "".join(result_lines)

    # Ensure file ends with a newline
    if result and not result.endswith("\n"):
        result += "\n"

    return result
