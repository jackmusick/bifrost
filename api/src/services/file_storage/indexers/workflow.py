"""
Workflow indexer for extracting and indexing workflows and data providers from Python files.

Handles AST-based parsing to extract metadata from @workflow, @tool, and @data_provider
decorators without importing the module.
"""

import ast
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID as UUID_type, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Workflow

logger = logging.getLogger(__name__)


class WorkflowIndexer:
    """
    Indexes Python files containing workflows and data providers.

    Uses AST-based parsing to extract metadata from @workflow, @tool, and @data_provider
    decorators. Also manages deactivation protection and workflow endpoint registration.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the workflow indexer.

        Args:
            db: Database session for querying and updating workflow records
        """
        self.db = db

    async def extract_metadata(
        self,
        path: str,
        content: bytes,
    ) -> dict[str, Any] | None:
        """
        Extract workflow metadata from Python file content.

        This is a quick scan to detect if the file contains SDK decorators,
        used for entity type detection.

        Args:
            path: File path
            content: File content bytes

        Returns:
            Metadata dict if workflows/providers found, None otherwise
        """
        try:
            content_str = content.decode("utf-8", errors="replace")
        except Exception:
            return None

        # Fast regex check - if no decorator-like patterns, skip AST parsing
        if "@workflow" not in content_str and "@data_provider" not in content_str:
            return None

        # AST verification - confirm decorators are actually used
        try:
            tree = ast.parse(content_str)
        except SyntaxError:
            return None

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if decorator_info:
                    decorator_name, _ = decorator_info
                    if decorator_name in ("workflow", "data_provider", "tool"):
                        return {"has_decorators": True}

        return None

    async def index_python_file(
        self,
        path: str,
        content: bytes,
        cached_ast: ast.Module | None = None,
        cached_content_str: str | None = None,
    ) -> None:
        """
        Extract and index workflows/providers from Python file.

        Uses AST-based parsing to extract metadata from @workflow, @tool, and
        @data_provider decorators without importing the module.

        IDs are DB-only. Workflows without IDs in decorators will have IDs
        generated in the database using path + function_name as the identity key.

        Args:
            path: File path
            content: File content bytes
            cached_ast: Pre-parsed AST tree (avoids re-parsing large files)
            cached_content_str: Pre-decoded content string (avoids re-decoding)
        """
        # Use cached values if available (avoids re-decoding/re-parsing 4MB files)
        content_str = cached_content_str or content.decode("utf-8", errors="replace")

        tree = cached_ast
        if tree is None:
            try:
                tree = ast.parse(content_str, filename=path)
            except SyntaxError as e:
                logger.warning(f"Syntax error parsing {path}: {e}")
                return

        now = datetime.now(timezone.utc)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if not decorator_info:
                    continue

                decorator_name, kwargs = decorator_info

                if decorator_name in ("workflow", "tool"):
                    # @tool decorator is an alias for @workflow(is_tool=True)
                    # If using @tool, force is_tool=True
                    if decorator_name == "tool":
                        kwargs["is_tool"] = True

                    # function_name is the actual Python function name (unique per file)
                    function_name = node.name

                    # Phase 6 (DB-first): IDs are DB-only.
                    # If ID is in decorator, use it. Otherwise, look up by path + function_name
                    # or generate a new one.
                    workflow_id_str = kwargs.get("id")
                    workflow_uuid: UUID_type

                    if workflow_id_str:
                        # ID in decorator - validate and use it
                        try:
                            workflow_uuid = UUID_type(workflow_id_str)
                        except ValueError:
                            logger.warning(f"Invalid workflow id '{workflow_id_str}' in {path} - skipping indexing")
                            continue
                    else:
                        # No ID in decorator - look up existing workflow by path + function_name
                        # This is the DB-first approach: identities are in the database
                        stmt = select(Workflow).where(
                            Workflow.path == path,
                            Workflow.function_name == function_name
                        )
                        result = await self.db.execute(stmt)
                        existing_workflow = result.scalar_one_or_none()

                        if existing_workflow:
                            # Reuse existing ID
                            workflow_uuid = existing_workflow.id
                            logger.debug(
                                f"Workflow {function_name} in {path} has no ID in decorator, "
                                f"reusing existing DB ID: {workflow_uuid}"
                            )
                        else:
                            # Generate new ID
                            workflow_uuid = uuid4()
                            logger.info(
                                f"Workflow {function_name} in {path} has no ID, "
                                f"generating new DB ID: {workflow_uuid}"
                            )

                    # Get workflow name from decorator or function name
                    workflow_name = kwargs.get("name") or node.name
                    description = kwargs.get("description")

                    # If no description in decorator, try to get from docstring
                    if description is None:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            description = docstring.strip().split("\n")[0].strip()

                    category = kwargs.get("category", "General")
                    tags = kwargs.get("tags", [])
                    endpoint_enabled = kwargs.get("endpoint_enabled", False)
                    allowed_methods = kwargs.get("allowed_methods", ["POST"])
                    # Apply same logic as decorator: endpoints default to sync, others to async
                    execution_mode = kwargs.get("execution_mode")
                    if execution_mode is None:
                        execution_mode = "sync" if endpoint_enabled else "async"
                    is_tool = kwargs.get("is_tool", False)
                    tool_description = kwargs.get("tool_description")
                    time_saved = kwargs.get("time_saved", 0)
                    value = kwargs.get("value", 0.0)
                    timeout_seconds = kwargs.get("timeout_seconds", 1800)

                    # Determine type based on is_tool flag
                    workflow_type = "tool" if is_tool else "workflow"

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    stmt = insert(Workflow).values(
                        id=workflow_uuid,
                        name=workflow_name,
                        function_name=function_name,
                        path=path,
                        description=description,
                        category=category,
                        parameters_schema=parameters_schema,
                        tags=tags,
                        endpoint_enabled=endpoint_enabled,
                        allowed_methods=allowed_methods,
                        execution_mode=execution_mode,
                        type=workflow_type,
                        tool_description=tool_description,
                        timeout_seconds=timeout_seconds,
                        time_saved=time_saved,
                        value=value,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.id],
                        set_={
                            "name": workflow_name,
                            "function_name": function_name,
                            "path": path,
                            "description": description,
                            "category": category,
                            "parameters_schema": parameters_schema,
                            "tags": tags,
                            "endpoint_enabled": endpoint_enabled,
                            "allowed_methods": allowed_methods,
                            "execution_mode": execution_mode,
                            "type": workflow_type,
                            "tool_description": tool_description,
                            "timeout_seconds": timeout_seconds,
                            "time_saved": time_saved,
                            "value": value,
                            "is_active": True,
                            "last_seen_at": now,
                            "updated_at": now,
                        },
                    ).returning(Workflow)
                    result = await self.db.execute(stmt)
                    workflow = result.scalar_one()
                    logger.debug(f"Indexed workflow: {workflow_name} ({function_name}) from {path}")

                    # Refresh endpoint registration if endpoint_enabled
                    if endpoint_enabled:
                        await self.refresh_workflow_endpoint(workflow)

                    # Update Redis caches for this workflow
                    try:
                        from src.core.redis_client import get_redis_client
                        redis_client = get_redis_client()

                        # Invalidate endpoint workflow cache (keyed by name)
                        await redis_client.invalidate_endpoint_workflow_cache(workflow_name)
                        logger.debug(f"Invalidated endpoint cache for workflow: {workflow_name}")

                        # Upsert workflow metadata cache (keyed by ID)
                        await redis_client.set_workflow_metadata_cache(
                            workflow_id=str(workflow_uuid),
                            name=workflow_name,
                            file_path=path,
                            timeout_seconds=kwargs.get("timeout_seconds", 1800),
                            time_saved=time_saved,
                            value=value,
                            execution_mode=execution_mode,
                        )
                        logger.debug(f"Upserted workflow metadata cache: {workflow_name}")
                    except Exception as e:
                        logger.warning(f"Failed to update caches for workflow {workflow_name}: {e}")

                elif decorator_name == "data_provider":
                    # Get provider name from decorator (required)
                    provider_name = kwargs.get("name") or node.name
                    description = kwargs.get("description")
                    category = kwargs.get("category", "General")
                    tags = kwargs.get("tags", [])
                    timeout_seconds = kwargs.get("timeout_seconds", 300)
                    cache_ttl_seconds = kwargs.get("cache_ttl_seconds", 300)

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    # function_name is the actual Python function name (unique per file)
                    # provider_name is the display name from decorator (can have duplicates)
                    function_name = node.name

                    # Data providers are stored in workflows table with type='data_provider'
                    stmt = insert(Workflow).values(
                        name=provider_name,
                        function_name=function_name,
                        path=path,
                        description=description,
                        category=category,
                        tags=tags,
                        parameters_schema=parameters_schema,
                        type="data_provider",
                        timeout_seconds=timeout_seconds,
                        cache_ttl_seconds=cache_ttl_seconds,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.path, Workflow.function_name],
                        set_={
                            "name": provider_name,
                            "description": description,
                            "category": category,
                            "tags": tags,
                            "parameters_schema": parameters_schema,
                            "type": "data_provider",
                            "timeout_seconds": timeout_seconds,
                            "cache_ttl_seconds": cache_ttl_seconds,
                            "is_active": True,
                            "last_seen_at": now,
                            "updated_at": now,
                        },
                    ).returning(Workflow)
                    dp_result = await self.db.execute(stmt)
                    data_provider = dp_result.scalar_one()
                    logger.debug(f"Indexed data provider: {provider_name} ({function_name}) from {path}")

        # Note: workspace_files update removed — file_index is the sole search index.
        # Entity type/ID routing is handled by path conventions, not DB columns.

    async def refresh_workflow_endpoint(self, workflow: Workflow) -> None:
        """
        Refresh the dynamic endpoint registration for an endpoint-enabled workflow.

        This is called when a workflow with endpoint_enabled=True is indexed,
        allowing live updates to the OpenAPI spec without restarting the API.

        Args:
            workflow: The Workflow ORM model that was just indexed
        """
        try:
            from src.services.openapi_endpoints import refresh_workflow_endpoint
            from src.main import app

            refresh_workflow_endpoint(app, workflow)
            logger.info(f"Refreshed endpoint for workflow: {workflow.name}")
        except ImportError:
            # App not fully initialized yet (during startup)
            pass
        except Exception as e:
            # Log but don't fail the file write
            logger.warning(f"Failed to refresh endpoint for {workflow.name}: {e}")

    # ==================== AST PARSING HELPERS ====================

    def _parse_decorator(self, decorator: ast.AST) -> tuple[str, dict[str, Any]] | None:
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
                    value = self._ast_value_to_python(keyword.value)
                    if value is not None:
                        kwargs[keyword.arg] = value

            return decorator_name, kwargs

        return None

    def _ast_value_to_python(self, node: ast.AST) -> Any:
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
            return [self._ast_value_to_python(elt) for elt in node.elts]
        elif isinstance(node, ast.Dict):
            return {
                self._ast_value_to_python(k): self._ast_value_to_python(v)
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

    def _extract_parameters_from_ast(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[dict[str, Any]]:
        """
        Extract parameter metadata from function definition AST.

        Returns list of parameter dicts with: name, type, required, label, default_value
        """
        parameters: list[dict[str, Any]] = []
        args = func_node.args

        # Get defaults - they align with the end of the args list
        defaults = args.defaults
        num_defaults = len(defaults)
        num_args = len(args.args)

        for i, arg in enumerate(args.args):
            param_name = arg.arg

            # Skip 'self', 'cls', and context parameters
            if param_name in ("self", "cls", "context"):
                continue

            # Skip ExecutionContext parameter (by annotation)
            if arg.annotation:
                annotation_str = self._annotation_to_string(arg.annotation)
                if "ExecutionContext" in annotation_str:
                    continue

            # Determine if parameter has a default
            default_index = i - (num_args - num_defaults)
            has_default = default_index >= 0

            # Get default value
            default_value = None
            if has_default:
                default_node = defaults[default_index]
                default_value = self._ast_value_to_python(default_node)

            # Determine type from annotation
            ui_type = "string"
            is_optional = has_default
            options = None
            if arg.annotation:
                ui_type = self._annotation_to_ui_type(arg.annotation)
                is_optional = is_optional or self._is_optional_annotation(arg.annotation)
                options = self._extract_literal_options(arg.annotation)

            # Generate label from parameter name
            label = re.sub(r"([a-z])([A-Z])", r"\1 \2", param_name.replace("_", " ")).title()

            param_meta = {
                "name": param_name,
                "type": ui_type,
                "required": not is_optional,
                "label": label,
            }

            if default_value is not None:
                param_meta["default_value"] = default_value

            if options:
                param_meta["options"] = options

            parameters.append(param_meta)

        return parameters

    def _annotation_to_string(self, annotation: ast.AST) -> str:
        """Convert annotation AST to string representation."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Subscript):
            return f"{self._annotation_to_string(annotation.value)}[...]"
        elif isinstance(annotation, ast.Attribute):
            return f"{self._annotation_to_string(annotation.value)}.{annotation.attr}"
        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # Python 3.10+ union syntax: str | None
            left = self._annotation_to_string(annotation.left)
            right = self._annotation_to_string(annotation.right)
            return f"{left} | {right}"
        return ""

    def _annotation_to_ui_type(self, annotation: ast.AST) -> str:
        """Convert annotation AST to UI type string."""
        type_mapping = {
            "str": "string",
            "int": "int",
            "float": "float",
            "bool": "bool",
            "list": "list",
            "dict": "json",
        }

        if isinstance(annotation, ast.Name):
            return type_mapping.get(annotation.id, "json")

        elif isinstance(annotation, ast.Subscript):
            # Handle list[str], dict[str, Any], Literal[...], etc.
            if isinstance(annotation.value, ast.Name):
                base_type = annotation.value.id
                if base_type == "list":
                    return "list"
                elif base_type == "dict":
                    return "json"
                elif base_type == "Optional":
                    # Optional[str] -> string
                    if isinstance(annotation.slice, ast.Name):
                        return type_mapping.get(annotation.slice.id, "string")
                    return "string"
                elif base_type == "Literal":
                    # Literal["a", "b"] -> infer type from values
                    return self._infer_literal_type(annotation.slice)

        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # str | None -> string
            left_type = self._annotation_to_ui_type(annotation.left)
            return left_type

        return "json"

    def _infer_literal_type(self, slice_node: ast.AST) -> str:
        """Infer UI type from Literal values."""
        # Get the first value from the Literal
        if isinstance(slice_node, ast.Tuple):
            # Literal["a", "b"] - multiple values
            if slice_node.elts:
                first_val = self._ast_value_to_python(slice_node.elts[0])
            else:
                return "string"
        else:
            # Literal["a"] - single value
            first_val = self._ast_value_to_python(slice_node)

        if first_val is None:
            return "string"
        if isinstance(first_val, str):
            return "string"
        if isinstance(first_val, bool):
            return "bool"
        if isinstance(first_val, int):
            return "int"
        if isinstance(first_val, float):
            return "float"
        return "string"

    def _extract_literal_options(self, annotation: ast.AST) -> list[dict[str, str]] | None:
        """Extract options from Literal type annotation."""
        if not isinstance(annotation, ast.Subscript):
            return None
        if not isinstance(annotation.value, ast.Name):
            return None
        if annotation.value.id != "Literal":
            return None

        # Get values from the Literal
        slice_node = annotation.slice
        values = []

        if isinstance(slice_node, ast.Tuple):
            # Literal["a", "b"] - multiple values
            for elt in slice_node.elts:
                val = self._ast_value_to_python(elt)
                if val is not None:
                    values.append({"label": str(val), "value": str(val)})
        else:
            # Literal["a"] - single value
            val = self._ast_value_to_python(slice_node)
            if val is not None:
                values.append({"label": str(val), "value": str(val)})

        return values if values else None

    def _is_optional_annotation(self, annotation: ast.AST) -> bool:
        """Check if annotation represents an optional type."""
        if isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                if annotation.value.id == "Optional":
                    return True

        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # Check for str | None pattern
            right_str = self._annotation_to_string(annotation.right)
            left_str = self._annotation_to_string(annotation.left)
            if right_str == "None" or left_str == "None":
                return True

        return False

    async def delete_workflows_for_file(self, path: str) -> int:
        """
        Soft-delete all workflows associated with a file.

        Uses UPDATE (is_active=False, is_orphaned=True) instead of DELETE to avoid
        deadlocks with concurrent INSERT...ON CONFLICT indexing operations.

        Called when a file is deleted to clean up workflow records from the database.

        Args:
            path: File path that was deleted

        Returns:
            Number of workflows soft-deleted
        """
        stmt = (
            update(Workflow)
            .where(Workflow.path == path, Workflow.is_active == True)  # noqa: E712
            .values(
                is_active=False,
                is_orphaned=True,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Soft-deleted {count} workflow(s) for deleted file: {path}")

        return count
