"""
Create Organization

General-purpose workflow to create a new Bifrost organization.
Can be used from any app or workflow that needs to create organizations.
"""

import logging

from bifrost import workflow, organizations, UserError

logger = logging.getLogger(__name__)


@workflow(
    category="Organizations",
    tags=["organizations", "admin"],
    description="Create a new Bifrost organization with optional domain.",
)
async def create_organization(
    name: str,
    domain: str | None = None,
) -> dict:
    """
    Create a new Bifrost organization.

    Args:
        name: Organization name (required)
        domain: Optional domain (e.g., "acme.com")

    Returns:
        dict with created organization details
    """
    if not name or not name.strip():
        raise UserError("Organization name is required")

    name = name.strip()

    # Clean up domain if provided
    if domain:
        domain = domain.strip().lower()
        # Remove any protocol prefix
        if domain.startswith("http://"):
            domain = domain[7:]
        elif domain.startswith("https://"):
            domain = domain[8:]
        # Remove trailing slash
        domain = domain.rstrip("/")

    logger.info(f"Creating organization: {name} (domain: {domain})")

    try:
        org = await organizations.create(
            name=name,
            domain=domain,
            is_active=True,
        )

        logger.info(f"Created organization: {org.id} - {org.name}")

        return {
            "success": True,
            "organization": {
                "id": str(org.id),
                "name": org.name,
                "domain": org.domain,
                "is_active": org.is_active,
            },
        }

    except Exception as e:
        logger.error(f"Failed to create organization: {e}")
        raise UserError(f"Failed to create organization: {str(e)}")
