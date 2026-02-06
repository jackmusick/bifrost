"""
App file dependency parser and sync.

Parses app source code to extract references to workflows,
and syncs them to the AppFileDependency table.

Used by:
- App code file CRUD operations (app_code_files router)
- GitHub sync app file indexer
- MCP code editor tools

Patterns detected:
- useWorkflow('uuid')
- useWorkflow("uuid")
"""

import logging
import re
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.app_file_dependencies import AppFileDependency

logger = logging.getLogger(__name__)

# Regex pattern for extracting workflow dependencies
# Captures UUIDs from hook calls like useWorkflow('550e8400-e29b-41d4-a716-446655440000')
DEPENDENCY_PATTERNS: dict[str, re.Pattern[str]] = {
    "workflow": re.compile(r'useWorkflow\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
}


def parse_dependencies(source: str) -> list[tuple[str, UUID]]:
    """
    Parse source code and extract workflow dependencies.

    Scans for patterns like useWorkflow('uuid').
    Returns a list of (dependency_type, dependency_id) tuples.

    Args:
        source: The source code to parse

    Returns:
        List of (type, uuid) tuples. Types are: "workflow"
    """
    dependencies: list[tuple[str, UUID]] = []
    seen: set[tuple[str, str]] = set()  # Deduplicate within same file

    for dep_type, pattern in DEPENDENCY_PATTERNS.items():
        for match in pattern.finditer(source):
            uuid_str = match.group(1)
            key = (dep_type, uuid_str)

            if key not in seen:
                seen.add(key)
                try:
                    dependencies.append((dep_type, UUID(uuid_str)))
                except ValueError:
                    # Invalid UUID format, skip
                    pass

    return dependencies


async def sync_file_dependencies(db: AsyncSession, file_id: UUID, source: str) -> int:
    """
    Parse source code and sync dependencies for a file.

    Erase-and-replace pattern: delete existing dependencies, then insert new ones.
    Called after file create or update.

    Args:
        db: Database session
        file_id: The AppFile ID
        source: The source code to parse

    Returns:
        Number of dependencies synced
    """
    # Delete existing dependencies for this file
    await db.execute(
        sql_delete(AppFileDependency).where(AppFileDependency.app_file_id == file_id)
    )

    # Parse new dependencies from source
    dependencies = parse_dependencies(source)

    # Insert new dependencies
    for dep_type, dep_id in dependencies:
        dependency = AppFileDependency(
            app_file_id=file_id,
            dependency_type=dep_type,
            dependency_id=dep_id,
        )
        db.add(dependency)

    if dependencies:
        logger.debug(f"Synced {len(dependencies)} dependencies for file {file_id}")

    return len(dependencies)
