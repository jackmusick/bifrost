"""
Agent Repository

Repository for Agent CRUD operations with organization scoping.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.org_filter import OrgFilterType
from src.models.orm import Agent
from src.repositories.org_scoped import OrgScopedRepository


class AgentRepository(OrgScopedRepository[Agent]):
    """
    Agent repository using OrgScopedRepository.

    Agents use the CASCADE scoping pattern for org users:
    - Org-specific agents + global (NULL org_id) agents
    """

    model = Agent

    async def list_agents(
        self,
        filter_type: OrgFilterType,
        active_only: bool = True,
    ) -> list[Agent]:
        """
        List agents with specified filter type.

        Args:
            filter_type: How to filter by organization scope
            active_only: If True, only return active agents

        Returns:
            List of Agent ORM objects
        """
        query = select(self.model).options(selectinload(self.model.tools))

        if active_only:
            query = query.where(self.model.is_active.is_(True))

        query = self.apply_filter(query, filter_type, self.org_id)
        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_agent(self, agent_id: UUID) -> Agent | None:
        """
        Get agent by ID with relationships loaded.

        Args:
            agent_id: Agent UUID

        Returns:
            Agent ORM object or None if not found
        """
        result = await self.session.execute(
            select(self.model)
            .options(
                selectinload(self.model.tools),
                selectinload(self.model.delegated_agents),
                selectinload(self.model.roles),
            )
            .where(self.model.id == agent_id)
        )
        return result.scalar_one_or_none()
