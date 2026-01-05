"""
App Components Service

Provides CRUD operations for individual app components:
- Create, read, update, delete components
- Move components (change parent/order)
- Batch operations for efficiency
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contracts.applications import (
    AppComponentCreate,
    AppComponentMove,
    AppComponentResponse,
    AppComponentSummary,
    AppComponentUpdate,
)
from src.models.orm.applications import AppComponent

logger = logging.getLogger(__name__)


class AppComponentsService:
    """Service for individual component operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_components(
        self,
        page_db_id: UUID,
        is_draft: bool = True,
    ) -> list[AppComponentSummary]:
        """
        List all components for a page (summaries only).

        Returns component_id, type, parent_id, order - enough to decide what to fetch.
        """
        query = (
            select(AppComponent)
            .where(
                AppComponent.page_id == page_db_id,
                AppComponent.is_draft == is_draft,
            )
            .order_by(AppComponent.parent_id.nulls_first(), AppComponent.component_order)
        )
        result = await self.session.execute(query)
        components = result.scalars().all()

        return [
            AppComponentSummary(
                id=comp.id,
                component_id=comp.component_id,
                parent_id=comp.parent_id,
                type=comp.type,
                component_order=comp.component_order,
            )
            for comp in components
        ]

    async def get_component(
        self,
        page_db_id: UUID,
        component_id: str,
        is_draft: bool = True,
    ) -> AppComponent | None:
        """Get a single component by its string ID."""
        query = select(AppComponent).where(
            AppComponent.page_id == page_db_id,
            AppComponent.component_id == component_id,
            AppComponent.is_draft == is_draft,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_component_by_uuid(self, component_uuid: UUID) -> AppComponent | None:
        """Get a single component by its UUID."""
        query = select(AppComponent).where(AppComponent.id == component_uuid)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_component(
        self,
        page_db_id: UUID,
        is_draft: bool,
        data: AppComponentCreate,
    ) -> AppComponent:
        """Create a new component."""
        # Validate parent exists if specified
        if data.parent_id:
            parent = await self.get_component_by_uuid(data.parent_id)
            if not parent or parent.page_id != page_db_id:
                raise ValueError("Parent component not found or belongs to different page")

        # If order not specified, add at end
        order = data.component_order
        if order == 0:
            # Get max order among siblings
            sibling_query = select(AppComponent.component_order).where(
                AppComponent.page_id == page_db_id,
                AppComponent.parent_id == data.parent_id,
                AppComponent.is_draft == is_draft,
            ).order_by(AppComponent.component_order.desc()).limit(1)
            result = await self.session.execute(sibling_query)
            max_order = result.scalar()
            order = (max_order or 0) + 1

        component = AppComponent(
            id=uuid4(),
            page_id=page_db_id,
            component_id=data.component_id,
            parent_id=data.parent_id,
            is_draft=is_draft,
            type=data.type,
            props=data.props,
            component_order=order,
            visible=data.visible,
            width=data.width,
            loading_workflows=data.loading_workflows,
        )
        self.session.add(component)
        await self.session.flush()
        await self.session.refresh(component)

        logger.info(f"Created component '{data.component_id}' (type={data.type})")
        return component

    async def update_component(
        self,
        component: AppComponent,
        data: AppComponentUpdate,
    ) -> AppComponent:
        """Update component props and fields."""
        if data.type is not None:
            component.type = data.type
        if data.props is not None:
            component.props = data.props
        if data.component_order is not None:
            component.component_order = data.component_order
        if data.visible is not None:
            component.visible = data.visible if data.visible else None
        if data.width is not None:
            component.width = data.width if data.width else None
        if data.loading_workflows is not None:
            component.loading_workflows = data.loading_workflows if data.loading_workflows else None

        await self.session.flush()
        await self.session.refresh(component)

        logger.info(f"Updated component '{component.component_id}'")
        return component

    async def delete_component(self, component: AppComponent) -> None:
        """
        Delete a component and all its children (cascade).

        Children are automatically deleted via FK cascade.
        """
        component_id = component.component_id
        await self.session.delete(component)
        await self.session.flush()

        logger.info(f"Deleted component '{component_id}' and children")

    async def move_component(
        self,
        component: AppComponent,
        data: AppComponentMove,
    ) -> AppComponent:
        """
        Move a component to a new parent and/or position.

        1. Validate new parent exists (if not null)
        2. Update parent_id
        3. Reorder siblings at old location
        4. Insert at new position
        """
        old_parent_id = component.parent_id
        old_order = component.component_order
        new_parent_id = data.new_parent_id
        new_order = data.new_order

        # Validate new parent if specified
        if new_parent_id:
            parent = await self.get_component_by_uuid(new_parent_id)
            if not parent or parent.page_id != component.page_id:
                raise ValueError("New parent component not found or belongs to different page")
            # Prevent circular reference
            if await self._would_create_cycle(component.id, new_parent_id):
                raise ValueError("Cannot move component under its own descendant")

        # Update component
        component.parent_id = new_parent_id
        component.component_order = new_order

        # Reorder siblings at old location (close gap)
        if old_parent_id != new_parent_id or old_order != new_order:
            await self._reorder_siblings_after_remove(
                component.page_id,
                component.is_draft,
                old_parent_id,
                old_order,
                exclude_id=component.id,
            )

        # Reorder siblings at new location (make room)
        await self._reorder_siblings_after_insert(
            component.page_id,
            component.is_draft,
            new_parent_id,
            new_order,
            exclude_id=component.id,
        )

        await self.session.flush()
        await self.session.refresh(component)

        logger.info(
            f"Moved component '{component.component_id}' "
            f"from parent={old_parent_id} order={old_order} "
            f"to parent={new_parent_id} order={new_order}"
        )
        return component

    async def _would_create_cycle(self, component_id: UUID, new_parent_id: UUID) -> bool:
        """Check if moving component under new_parent would create a cycle."""
        # Walk up from new_parent to see if we reach component_id
        current_id = new_parent_id
        visited: set[UUID] = set()

        while current_id:
            if current_id == component_id:
                return True
            if current_id in visited:
                break  # Already a cycle in data, stop
            visited.add(current_id)

            query = select(AppComponent.parent_id).where(AppComponent.id == current_id)
            result = await self.session.execute(query)
            current_id = result.scalar()

        return False

    async def _reorder_siblings_after_remove(
        self,
        page_id: UUID,
        is_draft: bool,
        parent_id: UUID | None,
        removed_order: int,
        exclude_id: UUID | None = None,
    ) -> None:
        """Close the gap after removing a component."""
        query = (
            update(AppComponent)
            .where(
                AppComponent.page_id == page_id,
                AppComponent.is_draft == is_draft,
                AppComponent.parent_id == parent_id,
                AppComponent.component_order > removed_order,
            )
        )
        if exclude_id:
            query = query.where(AppComponent.id != exclude_id)
        query = query.values(component_order=AppComponent.component_order - 1)
        await self.session.execute(query)

    async def _reorder_siblings_after_insert(
        self,
        page_id: UUID,
        is_draft: bool,
        parent_id: UUID | None,
        insert_order: int,
        exclude_id: UUID | None = None,
    ) -> None:
        """Make room at insert_order by shifting siblings down."""
        query = (
            update(AppComponent)
            .where(
                AppComponent.page_id == page_id,
                AppComponent.is_draft == is_draft,
                AppComponent.parent_id == parent_id,
                AppComponent.component_order >= insert_order,
            )
        )
        if exclude_id:
            query = query.where(AppComponent.id != exclude_id)
        query = query.values(component_order=AppComponent.component_order + 1)
        await self.session.execute(query)

    async def batch_update_props(
        self,
        page_db_id: UUID,
        is_draft: bool,
        updates: list[dict[str, Any]],
    ) -> int:
        """
        Batch update multiple component props.

        Each update should have:
        - component_id: str
        - props: dict (partial update, merged with existing)

        Returns number of components updated.
        """
        count = 0
        for item in updates:
            comp_id = item.get("component_id")
            new_props = item.get("props", {})

            if not comp_id:
                continue

            component = await self.get_component(page_db_id, comp_id, is_draft)
            if component:
                # Merge props
                merged_props = {**(component.props or {}), **new_props}
                component.props = merged_props
                count += 1

        await self.session.flush()
        logger.info(f"Batch updated {count} components")
        return count

    def to_response(self, component: AppComponent) -> AppComponentResponse:
        """Convert ORM model to response model."""
        return AppComponentResponse(
            id=component.id,
            component_id=component.component_id,
            parent_id=component.parent_id,
            type=component.type,
            component_order=component.component_order,
            page_id=component.page_id,
            is_draft=component.is_draft,
            props=component.props or {},
            visible=component.visible,
            width=component.width,
            loading_workflows=component.loading_workflows,
            created_at=component.created_at,
            updated_at=component.updated_at,
        )

    def to_summary(self, component: AppComponent) -> AppComponentSummary:
        """Convert ORM model to summary model."""
        return AppComponentSummary(
            id=component.id,
            component_id=component.component_id,
            parent_id=component.parent_id,
            type=component.type,
            component_order=component.component_order,
        )
