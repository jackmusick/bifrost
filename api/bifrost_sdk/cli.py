"""
Bifrost SDK CLI

Command-line interface for running workflows locally.

Usage:
    python -m bifrost_sdk.cli run <workflow_file.py>

Or if installed:
    bifrost run <workflow_file.py>
"""

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable


def _load_module(file_path: Path):
    """Load a Python module from file path."""
    spec = importlib.util.spec_from_file_location("workflow_module", file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["workflow_module"] = module
    spec.loader.exec_module(module)

    return module


def _find_workflows(module) -> list[tuple[str, Callable, dict]]:
    """
    Find all @workflow decorated functions in a module.

    Returns:
        List of (name, func, metadata) tuples
    """
    workflows = []

    for attr_name in dir(module):
        obj = getattr(module, attr_name)

        # Check for workflow metadata (set by @workflow decorator)
        if callable(obj) and hasattr(obj, "_workflow_metadata"):
            metadata = obj._workflow_metadata
            workflows.append((attr_name, obj, metadata))

    return workflows


def _prompt_workflow_selection(workflows: list[tuple[str, Callable, dict]]) -> tuple[str, Callable, dict]:
    """Prompt user to select a workflow if multiple exist."""
    if len(workflows) == 1:
        return workflows[0]

    print("\n🔍 Multiple workflows found:\n")
    for i, (name, func, meta) in enumerate(workflows, 1):
        wf_name = meta.get("name", name)
        desc = meta.get("description", "No description")
        print(f"  [{i}] {wf_name}")
        print(f"      {desc}\n")

    while True:
        try:
            choice = input("Select workflow [1]: ").strip() or "1"
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                return workflows[idx]
            print("Invalid selection. Please try again.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(1)


def _prompt_parameters(metadata: dict) -> dict[str, Any]:
    """
    Prompt user for workflow parameters.

    Uses default_parameters from dev context if available.
    """
    from bifrost_sdk.client import get_client

    params = {}
    param_schema = metadata.get("parameters", [])

    if not param_schema:
        return params

    # Get defaults from dev context
    try:
        client = get_client()
        defaults = client.default_parameters
    except Exception:
        defaults = {}

    print("\n📝 Enter workflow parameters (press Enter for default):\n")

    for param in param_schema:
        param_name = param.get("name", "")
        param_type = param.get("type", "string")
        param_default = defaults.get(param_name, param.get("default"))
        param_required = param.get("required", False)
        param_desc = param.get("description", "")

        # Build prompt
        prompt_parts = [f"  {param_name}"]
        if param_desc:
            prompt_parts.append(f" ({param_desc})")
        if param_default is not None:
            prompt_parts.append(f" [{param_default}]")
        elif param_required:
            prompt_parts.append(" (required)")
        prompt_parts.append(": ")

        prompt = "".join(prompt_parts)

        while True:
            value = input(prompt).strip()

            if not value and param_default is not None:
                value = param_default
                break
            elif not value and param_required:
                print("    This parameter is required.")
                continue
            elif not value:
                break

            # Type conversion
            try:
                if param_type == "number":
                    value = float(value)
                elif param_type == "integer":
                    value = int(value)
                elif param_type == "boolean":
                    value = value.lower() in ("true", "1", "yes", "y")
                break
            except ValueError:
                print(f"    Invalid {param_type} value.")

        if value is not None and value != "":
            params[param_name] = value

    return params


def run_workflow(file_path: str):
    """
    Run a workflow from a Python file.

    Args:
        file_path: Path to Python file containing workflow
    """
    path = Path(file_path).resolve()

    if not path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    if not path.suffix == ".py":
        print(f"❌ Not a Python file: {file_path}")
        sys.exit(1)

    print(f"📂 Loading {path.name}...")

    # Add file's directory to path for imports
    sys.path.insert(0, str(path.parent))

    try:
        module = _load_module(path)
    except Exception as e:
        print(f"❌ Failed to load module: {e}")
        sys.exit(1)

    # Find workflows
    workflows = _find_workflows(module)

    if not workflows:
        print(f"❌ No @workflow decorated functions found in {path.name}")
        print("   Make sure your workflow function has the @workflow decorator.")
        sys.exit(1)

    # Select workflow
    name, func, metadata = _prompt_workflow_selection(workflows)
    wf_name = metadata.get("name", name)

    # Get parameters
    params = _prompt_parameters(metadata)

    # Run
    print(f"\n🚀 Running: {wf_name}")
    if params:
        print(f"   Parameters: {params}")
    print()

    try:
        # Check if async
        if asyncio.iscoroutinefunction(func):
            result = asyncio.run(func(**params))
        else:
            result = func(**params)

        print("\n✅ Success!")
        print(f"   Result: {result}")

    except KeyboardInterrupt:
        print("\n⚠️  Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Bifrost SDK CLI")
        print()
        print("Usage:")
        print("  bifrost run <workflow_file.py>  - Run a workflow locally")
        print()
        print("Environment variables:")
        print("  BIFROST_DEV_URL  - Bifrost API URL")
        print("  BIFROST_DEV_KEY  - Developer API key")
        sys.exit(0)

    command = sys.argv[1]

    if command == "run":
        if len(sys.argv) < 3:
            print("Usage: bifrost run <workflow_file.py>")
            sys.exit(1)
        run_workflow(sys.argv[2])

    elif command in ("-h", "--help", "help"):
        print("Bifrost SDK CLI")
        print()
        print("Commands:")
        print("  run <file.py>  - Run a workflow file locally")
        print()
        print("Examples:")
        print("  bifrost run workflows/my_workflow.py")
        print("  python -m bifrost_sdk.cli run my_workflow.py")

    else:
        print(f"Unknown command: {command}")
        print("Use 'bifrost --help' for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()
