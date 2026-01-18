"""
File content search for browser-based code editor.
Provides fast full-text search with regex support.
Platform admin resource - no org scoping.

Search queries the database directly:
- Workflows: search workflows.code column
- Modules: search workspace_files.content column
- Forms/Apps/Agents: search serialized JSON representations
"""

import json
import re
import time
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SearchRequest, SearchResponse, SearchResult
from src.models.orm import WorkspaceFile, Workflow, Form, Agent

logger = logging.getLogger(__name__)

# Maximum results per entity type to prevent overwhelming queries
MAX_RESULTS_PER_TYPE = 500


def _search_content(
    content: str,
    path: str,
    query: str,
    case_sensitive: bool,
    is_regex: bool,
) -> List[SearchResult]:
    """
    Search content string for matches.

    Args:
        content: Text content to search
        path: File path for results
        query: Search query (text or regex pattern)
        case_sensitive: Whether to match case-sensitively
        is_regex: Whether query is a regex pattern

    Returns:
        List of SearchResult objects
    """
    results: List[SearchResult] = []

    try:
        # Build regex pattern
        if is_regex:
            pattern = query
        else:
            # Escape special regex characters for literal search
            pattern = re.escape(query)

        # Compile regex with appropriate flags
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        # Split into lines
        lines = content.split('\n')

        # Search each line
        for line_num, line in enumerate(lines, start=1):
            # Find all matches in this line
            for match in regex.finditer(line):
                # Get context lines (previous and next)
                context_before = lines[line_num - 2] if line_num > 1 else None
                context_after = lines[line_num] if line_num < len(lines) else None

                results.append(SearchResult(
                    file_path=path,
                    line=line_num,
                    column=match.start(),
                    match_text=line,
                    context_before=context_before,
                    context_after=context_after
                ))

    except (re.error, Exception) as e:
        logger.warning(f"Error searching {path}: {e}")

    return results


async def search_files_db(
    db: AsyncSession,
    request: SearchRequest,
    root_path: str = ""
) -> SearchResponse:
    """
    Search files for content matching the query using database queries.

    Searches:
    - workflows.code for workflow Python code
    - workspace_files.content for module Python code
    - Serialized JSON for forms, apps, agents

    Args:
        db: Database session
        request: SearchRequest with query and options
        root_path: Path prefix filter (empty = all files)

    Returns:
        SearchResponse with results and metadata

    Raises:
        ValueError: If query is invalid regex
    """
    start_time = time.time()

    # Validate regex if enabled
    if request.is_regex:
        try:
            flags = 0 if request.case_sensitive else re.IGNORECASE
            re.compile(request.query, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {str(e)}")

    all_results: List[SearchResult] = []
    files_searched = 0

    # Build path filter
    path_filter = WorkspaceFile.path.like(f"{root_path}%") if root_path else True

    # Build file pattern filter if specified
    include_filter = True
    if request.include_pattern:
        # Convert glob pattern to SQL LIKE pattern
        # e.g., "**/*.py" -> "%.py", "workflows/*.py" -> "workflows/%.py"
        like_pattern = request.include_pattern.replace("**/*", "%").replace("**", "%").replace("*", "%")
        include_filter = WorkspaceFile.path.like(like_pattern)

    # 1. Search workflows (code column)
    workflow_stmt = (
        select(Workflow.id, Workflow.code, WorkspaceFile.path)
        .join(WorkspaceFile, WorkspaceFile.entity_id == Workflow.id)
        .where(
            WorkspaceFile.is_deleted == False,  # noqa: E712
            WorkspaceFile.entity_type == "workflow",
            Workflow.code.isnot(None),
            path_filter,
            include_filter,
        )
        .limit(MAX_RESULTS_PER_TYPE)
    )
    workflow_result = await db.execute(workflow_stmt)
    for row in workflow_result:
        files_searched += 1
        if row.code:
            results = _search_content(
                row.code,
                row.path,
                request.query,
                request.case_sensitive,
                request.is_regex,
            )
            all_results.extend(results)
            if len(all_results) >= request.max_results:
                break

    # 2. Search modules (workspace_files.content column)
    if len(all_results) < request.max_results:
        module_stmt = (
            select(WorkspaceFile.path, WorkspaceFile.content)
            .where(
                WorkspaceFile.is_deleted == False,  # noqa: E712
                WorkspaceFile.entity_type == "module",
                WorkspaceFile.content.isnot(None),
                path_filter,
                include_filter,
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        module_result = await db.execute(module_stmt)
        for row in module_result:
            files_searched += 1
            if row.content:
                results = _search_content(
                    row.content,
                    row.path,
                    request.query,
                    request.case_sensitive,
                    request.is_regex,
                )
                all_results.extend(results)
                if len(all_results) >= request.max_results:
                    break

    # 3. Search forms (serialize to JSON and search)
    if len(all_results) < request.max_results:
        form_stmt = (
            select(Form, WorkspaceFile.path)
            .join(WorkspaceFile, WorkspaceFile.entity_id == Form.id)
            .where(
                WorkspaceFile.is_deleted == False,  # noqa: E712
                WorkspaceFile.entity_type == "form",
                path_filter,
                include_filter,
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        form_result = await db.execute(form_stmt)
        for row in form_result:
            files_searched += 1
            # Serialize form to searchable JSON
            form_json = json.dumps({
                "name": row.Form.name,
                "description": row.Form.description,
                "workflow_id": str(row.Form.workflow_id) if row.Form.workflow_id else None,
            }, indent=2)
            results = _search_content(
                form_json,
                row.path,
                request.query,
                request.case_sensitive,
                request.is_regex,
            )
            all_results.extend(results)
            if len(all_results) >= request.max_results:
                break

    # 4. Search agents (serialize to JSON and search)
    if len(all_results) < request.max_results:
        agent_stmt = (
            select(Agent, WorkspaceFile.path)
            .join(WorkspaceFile, WorkspaceFile.entity_id == Agent.id)
            .where(
                WorkspaceFile.is_deleted == False,  # noqa: E712
                WorkspaceFile.entity_type == "agent",
                path_filter,
                include_filter,
            )
            .limit(MAX_RESULTS_PER_TYPE)
        )
        agent_result = await db.execute(agent_stmt)
        for row in agent_result:
            files_searched += 1
            # Serialize agent to searchable JSON
            agent_json = json.dumps({
                "name": row.Agent.name,
                "description": row.Agent.description,
                "system_prompt": row.Agent.system_prompt,
                "model": row.Agent.model,
            }, indent=2)
            results = _search_content(
                agent_json,
                row.path,
                request.query,
                request.case_sensitive,
                request.is_regex,
            )
            all_results.extend(results)
            if len(all_results) >= request.max_results:
                break

    # Truncate results if needed
    truncated = len(all_results) > request.max_results
    results = all_results[:request.max_results]

    # Calculate search time
    search_time_ms = int((time.time() - start_time) * 1000)

    return SearchResponse(
        query=request.query,
        total_matches=len(results),
        files_searched=files_searched,
        results=results,
        truncated=truncated,
        search_time_ms=search_time_ms
    )
