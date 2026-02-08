"""
App file dependency parser and sync.

Parses app source code to extract references to workflows,
and syncs them to the AppFileDependency table.

Used by:
- App code file CRUD operations (app_code_files router)
- GitHub sync app file indexer
- MCP code editor tools
- Maintenance scan-app-dependencies endpoint

Patterns detected:
- useWorkflowQuery('name_or_uuid')
- useWorkflowMutation('name_or_uuid')
- useWorkflow('name_or_uuid') (legacy, kept for backward compat)

The parser extracts any string argument from these hooks, then resolves
them against the database to find matching workflows by name or UUID.
"""

import logging
import re
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.app_file_dependencies import AppFileDependency

logger = logging.getLogger(__name__)

# Regex pattern for extracting workflow references from hook calls.
# Captures any non-empty string argument (name or UUID) from:
# useWorkflowQuery('...'), useWorkflowMutation('...'), useWorkflow('...')
DEPENDENCY_PATTERN = re.compile(
    r"""(?:useWorkflow(?:Query|Mutation)?)\(\s*['"]([^'"]+)['"]\s*\)""",
    re.IGNORECASE,
)


def parse_dependencies(source: str) -> list[str]:
    """
    Parse source code and extract workflow reference strings.

    Scans for patterns like useWorkflowQuery('ref'), useWorkflowMutation('ref'),
    or useWorkflow('ref'). Returns deduplicated list of string references
    (which may be workflow names or UUIDs).

    Args:
        source: The source code to parse

    Returns:
        List of unique reference strings found in hook calls.
    """
    refs: list[str] = []
    seen: set[str] = set()

    for match in DEPENDENCY_PATTERN.finditer(source):
        ref = match.group(1)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)

    return refs


async def sync_file_dependencies(
    db: AsyncSession,
    file_id: UUID,
    source: str,
    organization_id: UUID | None = None,
) -> int:
    """
    Parse source code and sync dependencies for a file.

    Erase-and-replace pattern: delete existing dependencies, then insert new ones.
    Called after file create or update.

    Resolution strategy:
    - Query all active workflows visible to the app's org (org-scoped + global)
    - For each workflow, check if its name or str(id) appears as a hook argument
    - Store matching workflow UUIDs in app_file_dependencies

    Args:
        db: Database session
        file_id: The AppFile ID
        source: The source code to parse
        organization_id: The app's organization ID for scoping workflow lookups.
                         If None, only global workflows are checked.

    Returns:
        Number of dependencies synced
    """
    from src.models.orm.workflows import Workflow

    # Delete existing dependencies for this file
    await db.execute(
        sql_delete(AppFileDependency).where(AppFileDependency.app_file_id == file_id)
    )

    # Parse reference strings from source
    refs = parse_dependencies(source)
    if not refs:
        return 0

    # Query all active workflows visible to this org (org-scoped + global)
    scope_filter = Workflow.organization_id.is_(None)
    if organization_id is not None:
        scope_filter = or_(
            Workflow.organization_id == organization_id,
            Workflow.organization_id.is_(None),
        )

    result = await db.execute(
        select(Workflow.id, Workflow.name).where(
            Workflow.is_active.is_(True),
            scope_filter,
        )
    )
    workflows = result.all()

    # Build lookup maps: name -> UUID and str(id) -> UUID
    name_to_id: dict[str, UUID] = {}
    uuid_str_to_id: dict[str, UUID] = {}
    for wf_id, wf_name in workflows:
        name_to_id[wf_name] = wf_id
        uuid_str_to_id[str(wf_id)] = wf_id

    # Resolve refs to workflow UUIDs
    matched_ids: set[UUID] = set()
    for ref in refs:
        # Try as workflow name first, then as UUID string
        if ref in name_to_id:
            matched_ids.add(name_to_id[ref])
        elif ref in uuid_str_to_id:
            matched_ids.add(uuid_str_to_id[ref])

    # Insert dependencies
    for dep_id in matched_ids:
        dependency = AppFileDependency(
            app_file_id=file_id,
            dependency_type="workflow",
            dependency_id=dep_id,
        )
        db.add(dependency)

    if matched_ids:
        logger.debug(f"Synced {len(matched_ids)} dependencies for file {file_id}")

    return len(matched_ids)
