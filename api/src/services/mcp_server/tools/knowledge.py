"""
Knowledge MCP Tools

Tools for searching the Bifrost knowledge base.
"""

import json
import logging
from typing import Any

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="search_knowledge",
    name="Search Knowledge",
    description="Search the Bifrost knowledge base.",
    category=ToolCategory.KNOWLEDGE,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query text",
            },
            "namespace": {
                "type": "string",
                "description": "Optional specific namespace to search (must be accessible)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def search_knowledge(
    context: Any,
    query: str,
    namespace: str | None = None,
    limit: int = 5,
) -> str:
    """Search the knowledge base.

    Args:
        context: MCP context with user permissions
        query: Search query text
        namespace: Optional specific namespace to search (must be accessible)
        limit: Maximum number of results
    """
    from src.core.database import get_db_context
    from src.repositories.knowledge import KnowledgeRepository
    from src.services.embeddings import get_embedding_client

    logger.info(f"MCP search_knowledge called with query={query}, namespace={namespace}")

    if not query:
        return json.dumps({"error": "query is required"})

    # Validate namespace access
    accessible = context.accessible_namespaces
    if not accessible:
        return json.dumps({
            "results": [],
            "count": 0,
            "message": "No knowledge sources available. No agents with knowledge access configured.",
        })

    if namespace:
        if namespace not in accessible:
            return json.dumps({"error": f"Access denied: namespace '{namespace}' is not accessible."})
        namespaces_to_search = [namespace]
    else:
        namespaces_to_search = accessible

    try:
        async with get_db_context() as db:
            # Generate query embedding
            embedding_client = await get_embedding_client(db)
            query_embedding = await embedding_client.embed_single(query)

            # Search knowledge store
            repo = KnowledgeRepository(db)
            results = await repo.search(
                query_embedding=query_embedding,
                namespace=namespaces_to_search,
                organization_id=context.org_id if context.org_id else None,
                limit=limit,
                fallback=True,
            )

            if not results:
                return json.dumps({
                    "results": [],
                    "count": 0,
                    "message": f"No results found for query: '{query}'",
                })

            result_data = []
            for doc in results:
                result_data.append({
                    "namespace": doc.namespace,
                    "content": doc.content,
                    "score": doc.score,
                })

            return json.dumps({
                "results": result_data,
                "count": len(result_data),
            })

    except Exception as e:
        logger.exception(f"Error searching knowledge via MCP: {e}")
        return json.dumps({"error": f"Error searching knowledge: {str(e)}"})
