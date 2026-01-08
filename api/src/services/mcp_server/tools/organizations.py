"""
Organization MCP Tools

Tools for listing, creating, and getting organizations.
All organization tools are restricted (platform-admin only).
"""

import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from src.core.database import get_db_context
from src.models.orm.organizations import Organization
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="list_organizations",
    name="List Organizations",
    description="List all organizations in the platform.",
    category=ToolCategory.ORGANIZATION,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_organizations(context: Any) -> str:
    """List all organizations.

    Platform admin only. Returns id, name, domain, is_active for each org.
    """
    logger.info("MCP list_organizations called")

    try:
        async with get_db_context() as db:
            query = select(Organization).order_by(Organization.name)
            result = await db.execute(query)
            orgs = result.scalars().all()

            orgs_data = [
                {
                    "id": str(org.id),
                    "name": org.name,
                    "domain": org.domain,
                    "is_active": org.is_active,
                }
                for org in orgs
            ]

            return json.dumps({"organizations": orgs_data, "count": len(orgs_data)})

    except Exception as e:
        logger.exception(f"Error listing organizations via MCP: {e}")
        return json.dumps({"error": f"Error listing organizations: {str(e)}"})


@system_tool(
    id="get_organization",
    name="Get Organization",
    description="Get organization details by ID or domain.",
    category=ToolCategory.ORGANIZATION,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {
                "type": "string",
                "description": "Organization UUID",
            },
            "domain": {
                "type": "string",
                "description": "Organization domain (alternative to ID)",
            },
        },
        "required": [],
    },
)
async def get_organization(
    context: Any,
    organization_id: str | None = None,
    domain: str | None = None,
) -> str:
    """Get organization details by ID or domain.

    Platform admin only. Must provide at least one of organization_id or domain.
    """
    logger.info(f"MCP get_organization called with id={organization_id}, domain={domain}")

    if not organization_id and not domain:
        return json.dumps({"error": "Either organization_id or domain is required"})

    try:
        async with get_db_context() as db:
            query = select(Organization)

            if organization_id:
                try:
                    query = query.where(Organization.id == UUID(organization_id))
                except ValueError:
                    return json.dumps(
                        {"error": f"Invalid organization_id format: {organization_id}"}
                    )
            else:
                query = query.where(Organization.domain == domain)

            result = await db.execute(query)
            org = result.scalar_one_or_none()

            if not org:
                identifier = organization_id or domain
                return json.dumps({"error": f"Organization not found: {identifier}"})

            return json.dumps({
                "id": str(org.id),
                "name": org.name,
                "domain": org.domain,
                "is_active": org.is_active,
                "settings": org.settings,
                "created_at": org.created_at.isoformat() if org.created_at else None,
                "created_by": org.created_by,
                "updated_at": org.updated_at.isoformat() if org.updated_at else None,
            })

    except Exception as e:
        logger.exception(f"Error getting organization via MCP: {e}")
        return json.dumps({"error": f"Error getting organization: {str(e)}"})


@system_tool(
    id="create_organization",
    name="Create Organization",
    description="Create a new organization.",
    category=ToolCategory.ORGANIZATION,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Organization name (required)",
            },
            "domain": {
                "type": "string",
                "description": "Organization domain (optional, auto-generated from name if not provided)",
            },
        },
        "required": ["name"],
    },
)
async def create_organization(
    context: Any,
    name: str,
    domain: str | None = None,
) -> str:
    """Create a new organization.

    Platform admin only.

    Args:
        context: MCP context with user permissions
        name: Organization name (required)
        domain: Organization domain (optional, auto-generated from name if not provided)

    Returns:
        JSON with created organization details
    """
    logger.info(f"MCP create_organization called with name={name}")

    if not name:
        return json.dumps({"error": "name is required"})

    if len(name) > 255:
        return json.dumps({"error": "name must be 255 characters or less"})

    # Generate domain from name if not provided
    if not domain:
        # Convert to lowercase, replace spaces/special chars with hyphens
        domain = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    if len(domain) > 255:
        return json.dumps({"error": "domain must be 255 characters or less"})

    try:
        async with get_db_context() as db:
            # Check for duplicate domain
            existing_query = select(Organization).where(Organization.domain == domain)
            existing_result = await db.execute(existing_query)
            if existing_result.scalar_one_or_none():
                return json.dumps(
                    {"error": f"Organization with domain '{domain}' already exists"}
                )

            # Create organization
            org = Organization(
                id=uuid4(),
                name=name,
                domain=domain,
                is_active=True,
                settings={},
                created_by=context.user_email or "mcp@bifrost.local",
            )

            db.add(org)
            await db.commit()

            logger.info(f"Created organization {org.id}: {org.name}")

            return json.dumps({
                "success": True,
                "id": str(org.id),
                "name": org.name,
                "domain": org.domain,
                "is_active": org.is_active,
            })

    except Exception as e:
        logger.exception(f"Error creating organization via MCP: {e}")
        return json.dumps({"error": f"Error creating organization: {str(e)}"})
