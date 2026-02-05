"""
Agent indexer for parsing and indexing .agent.json files.

Handles agent metadata extraction, tool/delegation synchronization, and ID alignment.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Workflow
from src.models.orm import Agent, AgentTool, AgentDelegation
from src.models.contracts.agents import AgentPublic
from src.models.contracts.refs import (
    transform_refs_for_export,
    transform_refs_for_import,
)

logger = logging.getLogger(__name__)


def _serialize_agent_to_json(
    agent: Agent,
    workflow_map: dict[str, str] | None = None
) -> bytes:
    """
    Serialize an Agent to JSON bytes using Pydantic model_dump.

    Uses AgentPublic.model_dump() with exclude=True fields auto-excluded.
    Transforms workflow refs via transform_refs_for_export().

    Args:
        agent: Agent ORM instance with tools relationship loaded
        workflow_map: Optional mapping of workflow UUID -> portable ref.
                      If provided, tool_ids are transformed.

    Returns:
        JSON serialized as UTF-8 bytes
    """
    agent_public = AgentPublic.model_validate(agent)

    # Explicitly exclude fields that shouldn't be in exported files
    # (these are runtime/database-specific, not portable)
    agent_data = agent_public.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"organization_id", "access_level", "is_system", "created_by", "created_at", "updated_at"},
    )

    # Remove empty arrays to match import format
    for key in ["delegated_agent_ids", "role_ids", "knowledge_sources", "system_tools"]:
        if key in agent_data and agent_data[key] == []:
            del agent_data[key]

    # Transform workflow UUIDs to portable refs if we have a workflow map
    if workflow_map:
        agent_data = transform_refs_for_export(agent_data, AgentPublic, workflow_map)

    # Sort list fields for deterministic serialization (DB query order is non-deterministic)
    for key in ["tool_ids", "delegated_agent_ids", "role_ids", "knowledge_sources", "system_tools", "channels"]:
        if key in agent_data and isinstance(agent_data[key], list):
            agent_data[key] = sorted(agent_data[key])

    return json.dumps(agent_data, indent=2).encode("utf-8")


class AgentIndexer:
    """
    Indexes .agent.json files and synchronizes with the database.

    Handles ID alignment, tool/delegation association, and agent definition updates.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the agent indexer.

        Args:
            db: Database session for querying and updating agent records
        """
        self.db = db

    async def index_agent(
        self,
        path: str,
        content: bytes,
        workspace_file: Any = None,
        ref_to_uuid: dict[str, str] | None = None,
    ) -> bool:
        """
        Parse and index agent from .agent.json file.

        If the JSON contains an 'id' field, uses that ID (for API-created agents).
        Otherwise generates a new ID (for files synced from git/editor).

        Updates agent definition (name, description, system_prompt, tools, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT to update existing agents.

        Args:
            path: File path
            content: File content bytes
            workspace_file: WorkspaceFile ORM instance (optional, not currently used)
            ref_to_uuid: Optional mapping of portable refs to UUIDs. If not provided,
                         builds the map from the database.

        Returns:
            True if content was modified (ID alignment), False otherwise
        """
        content_modified = False

        try:
            agent_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in agent file: {path}")
            return False

        # Remove _export if present (backwards compatibility with old files)
        # Pydantic will also ignore it during validation, but we clean it up explicitly
        agent_data.pop("_export", None)

        # Always transform portable refs to UUIDs
        # The model annotations tell us which fields contain workflow refs
        if ref_to_uuid is None:
            from src.services.file_storage.ref_translation import build_ref_to_uuid_map
            ref_to_uuid = await build_ref_to_uuid_map(self.db)
        agent_data = transform_refs_for_import(agent_data, AgentPublic, ref_to_uuid)

        name = agent_data.get("name")
        if not name:
            logger.warning(f"Agent file missing name: {path}")
            return False

        system_prompt = agent_data.get("system_prompt")
        if not system_prompt:
            logger.warning(f"Agent file missing system_prompt: {path}")
            return False

        # Use ID from JSON if present (for API-created agents), otherwise generate new
        agent_id_str = agent_data.get("id")
        if agent_id_str:
            try:
                agent_id = UUID(agent_id_str)
            except ValueError:
                logger.warning(f"Invalid agent ID in {path}: {agent_id_str}")
                agent_id = uuid4()
                agent_data["id"] = str(agent_id)
                content_modified = True
        else:
            agent_id = uuid4()
            agent_data["id"] = str(agent_id)
            content_modified = True
            logger.info(f"Injecting ID {agent_id} into agent file: {path}")

        # Agents are now "fully virtual" - their path is computed from their ID
        # (e.g., agents/{uuid}.agent.json), so we don't need a separate file_path column.
        # We just use the ID from the JSON content directly.

        # Parse channels
        channels = agent_data.get("channels", ["chat"])
        if not isinstance(channels, list):
            channels = ["chat"]

        # Get knowledge_sources (JSONB field)
        knowledge_sources = agent_data.get("knowledge_sources", [])
        if not isinstance(knowledge_sources, list):
            knowledge_sources = []

        now = datetime.utcnow()

        # Upsert agent - updates definition but NOT organization_id or access_level
        # These env-specific fields are only set via the API, not from file sync
        stmt = insert(Agent).values(
            id=agent_id,
            name=name,
            description=agent_data.get("description"),
            system_prompt=system_prompt,
            channels=channels,
            knowledge_sources=knowledge_sources,
            is_active=agent_data.get("is_active", True),
            created_by="file_sync",
        ).on_conflict_do_update(
            index_elements=[Agent.id],
            set_={
                # Update definition fields from file
                "name": name,
                "description": agent_data.get("description"),
                "system_prompt": system_prompt,
                "channels": channels,
                "knowledge_sources": knowledge_sources,
                "is_active": agent_data.get("is_active", True),
                "updated_at": now,
                # NOTE: organization_id and access_level are NOT updated
                # These are preserved from the database (env-specific)
            },
        )
        await self.db.execute(stmt)

        # Sync tool associations (tool_ids in JSON are workflow IDs)
        # Note: transform_refs_for_import already resolved portable refs to UUIDs,
        # but unresolved refs remain unchanged and will be skipped below.
        tool_ids = agent_data.get("tool_ids", [])
        if isinstance(tool_ids, list):
            # Delete existing tool associations
            await self.db.execute(
                delete(AgentTool).where(AgentTool.agent_id == agent_id)
            )
            # Create new tool associations (with existence check to prevent FK violations)
            # Track added workflow_ids to avoid duplicates (same workflow ref appears multiple times)
            added_tool_ids: set[UUID] = set()
            for tool_id_str in tool_ids:
                try:
                    workflow_id = UUID(tool_id_str)
                    # Skip if already added (dedup)
                    if workflow_id in added_tool_ids:
                        continue
                    # Check if workflow exists before creating FK relationship
                    workflow_exists = await self.db.execute(
                        select(Workflow.id).where(Workflow.id == workflow_id)
                    )
                    if workflow_exists.scalar_one_or_none():
                        self.db.add(AgentTool(agent_id=agent_id, workflow_id=workflow_id))
                        added_tool_ids.add(workflow_id)
                    else:
                        logger.warning(f"Agent {name} references non-existent workflow {workflow_id}")
                except ValueError:
                    # Not a valid UUID - likely an unresolved portable ref
                    logger.warning(f"Invalid tool_id in agent {name}: {tool_id_str}")

        # Sync delegated agent associations
        delegated_agent_ids = agent_data.get("delegated_agent_ids", [])
        if isinstance(delegated_agent_ids, list):
            # Delete existing delegations
            await self.db.execute(
                delete(AgentDelegation).where(AgentDelegation.parent_agent_id == agent_id)
            )
            # Create new delegations (with existence check to prevent FK violations)
            for child_id_str in delegated_agent_ids:
                try:
                    child_agent_id = UUID(child_id_str)
                    # Check if child agent exists before creating FK relationship
                    agent_exists = await self.db.execute(
                        select(Agent.id).where(Agent.id == child_agent_id)
                    )
                    if agent_exists.scalar_one_or_none():
                        self.db.add(AgentDelegation(parent_agent_id=agent_id, child_agent_id=child_agent_id))
                    else:
                        logger.warning(f"Agent {name} references non-existent agent {child_agent_id}")
                except ValueError:
                    logger.warning(f"Invalid delegated_agent_id in agent {name}: {child_id_str}")

        # Update workspace_files with entity routing
        from src.models import WorkspaceFile

        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="agent",
            entity_id=agent_id,
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed agent: {name} from {path}")
        return content_modified

    async def delete_agent_for_file(self, path: str) -> int:
        """
        Delete the agent associated with a file.

        Called when a file is deleted to clean up agent records from the database.
        For virtual agents, the ID is extracted from the path (agents/{uuid}.agent.json).

        Args:
            path: File path that was deleted (e.g., "agents/{uuid}.agent.json")

        Returns:
            Number of agents deleted
        """
        # Extract agent ID from path: agents/{uuid}.agent.json -> uuid
        import re
        match = re.match(r"agents/([a-f0-9-]+)\.agent\.json$", path, re.IGNORECASE)
        if not match:
            logger.warning(f"Cannot extract agent ID from path: {path}")
            return 0

        try:
            agent_id = UUID(match.group(1))
        except ValueError:
            logger.warning(f"Invalid UUID in agent path: {path}")
            return 0

        # Delete the agent by ID (cascade will delete agent_tools and agent_delegations)
        stmt = delete(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Deleted agent {agent_id} from database for deleted file: {path}")

        return count
