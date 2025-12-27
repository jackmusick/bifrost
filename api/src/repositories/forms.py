"""
Form Repository

Repository for Form CRUD operations with organization scoping.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.org_filter import OrgFilterType
from src.models import Form as FormORM
from src.repositories.org_scoped import OrgScopedRepository


class FormRepository(OrgScopedRepository[FormORM]):
    """
    Form repository using OrgScopedRepository.

    Forms use the CASCADE scoping pattern for org users:
    - Org-specific forms + global (NULL org_id) forms
    """

    model = FormORM

    async def list_forms(
        self,
        filter_type: OrgFilterType,
        active_only: bool = True,
    ) -> list[FormORM]:
        """
        List forms with specified filter type.

        Args:
            filter_type: How to filter by organization scope
            active_only: If True, only return active forms

        Returns:
            List of Form ORM objects with fields eager-loaded
        """
        query = select(self.model).options(selectinload(self.model.fields))

        if active_only:
            query = query.where(self.model.is_active.is_(True))

        query = self.apply_filter(query, filter_type, self.org_id)
        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_form(self, form_id: UUID) -> FormORM | None:
        """
        Get form by ID with fields loaded.

        Args:
            form_id: Form UUID

        Returns:
            Form ORM object or None if not found
        """
        result = await self.session.execute(
            select(self.model)
            .options(selectinload(self.model.fields))
            .where(self.model.id == form_id)
        )
        return result.scalar_one_or_none()
