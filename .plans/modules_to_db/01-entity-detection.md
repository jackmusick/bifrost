# Phase 1: Entity Detection

## Overview

Update entity detection to classify non-workflow Python files as `"module"` entities that get stored in the database.

## Current Behavior

**File:** `api/src/services/file_storage/entity_detector.py`

```python
def detect_python_entity_type(content: bytes) -> str | None:
    # Returns "workflow" if @workflow/@data_provider found
    # Returns None otherwise (goes to S3)
```

Currently, Python files without SDK decorators return `None`, which means they're treated as regular files and stored in S3.

## New Behavior

```python
def detect_python_entity_type(content: bytes) -> str | None:
    """
    Check if Python content has SDK decorators (@workflow, @data_provider).

    Returns:
        "workflow" if SDK decorators found
        "module" for all other valid Python files (stored in DB)
    """
    try:
        content_str = content.decode("utf-8", errors="replace")
    except Exception:
        return None  # Non-text file, not a Python module

    # Fast regex check for decorators
    if "@workflow" in content_str or "@data_provider" in content_str:
        # AST verification - confirm decorators are actually used
        try:
            tree = ast.parse(content_str)
        except SyntaxError:
            return "module"  # Syntax error but still Python - store as module

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                decorator_info = _parse_decorator(decorator)
                if decorator_info:
                    decorator_name, _ = decorator_info
                    if decorator_name in ("workflow", "data_provider"):
                        return "workflow"

    # All other Python files are modules (stored in DB)
    return "module"
```

## Key Changes

1. **Return `"module"` instead of `None`** for Python files without decorators
2. **Syntax errors still return `"module"`** - we store the content even if invalid Python
3. **All Python files now go to DB** - no more S3 for `.py` files

## Impact

- `write_file()` in `file_ops.py` will route modules to `workspace_files.content`
- S3 storage is skipped for all Python files (they're now platform entities)
- Redis cache invalidation happens on module write/delete
