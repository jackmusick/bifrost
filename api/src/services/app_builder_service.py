"""
App Builder Service

Provides tree operations for the App Builder:
- Flatten nested layout JSON to component rows
- Reconstruct component tree from rows
- Export/import full app definitions
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contracts.applications import (
    AppComponentNode,
    ComponentTreeNode,
    LayoutContainer,
    LayoutElement,
    PageDefinition,
    DataSourceConfig,
    PagePermissionConfig,
)
from src.models.orm.applications import AppComponent, AppPage, Application

logger = logging.getLogger(__name__)


# =============================================================================
# Tree Flattening (JSON -> Rows)
# =============================================================================


def flatten_layout_tree(
    layout: dict[str, Any],
    page_id: UUID,
    is_draft: bool,
    parent_id: UUID | None = None,
    order: int = 0,
) -> list[dict[str, Any]]:
    """
    Flatten a nested layout tree into a list of component dictionaries.

    The layout tree structure:
    {
        "type": "column",
        "gap": 16,
        "children": [
            {"id": "heading1", "type": "heading", "props": {...}},
            {"type": "row", "children": [...]},
        ]
    }

    Returns list of dicts ready to create AppComponent rows.
    """
    components: list[dict[str, Any]] = []
    layout_type = layout.get("type", "column")

    # Check if this is a layout container (has children) or a leaf component
    children = layout.get("children", [])

    if layout_type in ("row", "column", "grid"):
        # This is a layout container
        component_id = layout.get("id") or f"layout_{uuid4().hex[:8]}"
        component_uuid = uuid4()

        # Extract layout-specific props
        layout_props = {}
        for key in ("gap", "padding", "align", "justify", "columns", "autoSize", "className"):
            if key in layout:
                layout_props[key] = layout[key]

        components.append({
            "id": component_uuid,
            "page_id": page_id,
            "component_id": component_id,
            "parent_id": parent_id,
            "is_draft": is_draft,
            "type": layout_type,
            "props": layout_props,
            "component_order": order,
            "visible": layout.get("visible"),
            "width": layout.get("width"),
            "loading_workflows": layout.get("loadingWorkflows"),
        })

        # Recursively flatten children
        for idx, child in enumerate(children):
            child_components = flatten_layout_tree(
                child, page_id, is_draft, parent_id=component_uuid, order=idx
            )
            components.extend(child_components)
    else:
        # This is a leaf component (button, text, data-table, etc.)
        component_id = layout.get("id") or f"{layout_type}_{uuid4().hex[:8]}"
        component_uuid = uuid4()

        # The props are in a "props" key for leaf components
        props = layout.get("props", {})

        components.append({
            "id": component_uuid,
            "page_id": page_id,
            "component_id": component_id,
            "parent_id": parent_id,
            "is_draft": is_draft,
            "type": layout_type,
            "props": props,
            "component_order": order,
            "visible": layout.get("visible"),
            "width": layout.get("width"),
            "loading_workflows": layout.get("loadingWorkflows"),
        })

        # Some components can have children (card, modal, tabs)
        if "children" in props:
            for idx, child in enumerate(props.get("children", [])):
                child_components = flatten_layout_tree(
                    child, page_id, is_draft, parent_id=component_uuid, order=idx
                )
                components.extend(child_components)
            # Remove children from props since they're now separate rows
            props.pop("children", None)

        # Handle card content
        if layout_type == "card" and "content" in props:
            for idx, child in enumerate(props.get("content", [])):
                child_components = flatten_layout_tree(
                    child, page_id, is_draft, parent_id=component_uuid, order=idx
                )
                components.extend(child_components)
            props.pop("content", None)

        # Handle modal content
        if layout_type == "modal" and "content" in props:
            content = props.get("content")
            if isinstance(content, dict):
                child_components = flatten_layout_tree(
                    content, page_id, is_draft, parent_id=component_uuid, order=0
                )
                components.extend(child_components)
            props.pop("content", None)

        # Handle tabs items with content
        if layout_type == "tabs" and "items" in props:
            for tab_idx, tab in enumerate(props.get("items", [])):
                if "content" in tab and isinstance(tab["content"], dict):
                    # Create a container for tab content
                    tab_content_id = uuid4()
                    components.append({
                        "id": tab_content_id,
                        "page_id": page_id,
                        "component_id": f"tab_content_{tab.get('id', tab_idx)}",
                        "parent_id": component_uuid,
                        "is_draft": is_draft,
                        "type": "tab_content",
                        "props": {"tab_id": tab.get("id")},
                        "component_order": tab_idx,
                        "visible": None,
                        "width": None,
                        "loading_workflows": None,
                    })
                    child_components = flatten_layout_tree(
                        tab["content"], page_id, is_draft, parent_id=tab_content_id, order=0
                    )
                    components.extend(child_components)
                    tab["content"] = None  # Mark as moved to separate rows
            # Keep items but without nested content
            props["items"] = [
                {k: v for k, v in item.items() if k != "content" or v is not None}
                for item in props["items"]
            ]

    return components


# =============================================================================
# Tree Reconstruction (Rows -> JSON)
# =============================================================================


def build_component_tree(components: list[AppComponent]) -> list[ComponentTreeNode]:
    """
    Build a tree of ComponentTreeNode from flat component rows.

    Uses a single pass with a lookup dict to build the tree efficiently.
    """
    if not components:
        return []

    # Create lookup dict and node list
    nodes: dict[UUID, ComponentTreeNode] = {}
    root_nodes: list[ComponentTreeNode] = []

    # First pass: create all nodes
    for comp in components:
        node = ComponentTreeNode(
            id=comp.id,
            component_id=comp.component_id,
            type=comp.type,
            props=comp.props or {},
            visible=comp.visible,
            width=comp.width,
            loading_workflows=comp.loading_workflows,
            component_order=comp.component_order,
            children=[],
        )
        nodes[comp.id] = node

    # Second pass: build tree structure
    for comp in components:
        node = nodes[comp.id]
        if comp.parent_id is None:
            root_nodes.append(node)
        elif comp.parent_id in nodes:
            nodes[comp.parent_id].children.append(node)

    # Sort children by order
    for node in nodes.values():
        node.children.sort(key=lambda n: n.component_order)

    # Sort root nodes
    root_nodes.sort(key=lambda n: n.component_order)

    return root_nodes


def build_layout_tree(components: list[AppComponent]) -> LayoutContainer:
    """
    Build a typed LayoutContainer tree from flat component rows.

    Returns a properly typed LayoutContainer that matches the frontend TypeScript
    LayoutContainer interface. This is the primary function for building the tree
    that gets returned from the API.

    Uses a single pass with a lookup dict to build the tree efficiently.
    """
    if not components:
        # Return empty column layout
        return LayoutContainer(type="column", children=[])

    # First pass: create all nodes as LayoutElement (either LayoutContainer or AppComponentNode)
    nodes: dict[UUID, tuple[LayoutElement, int, UUID | None]] = {}  # id -> (node, order, parent_id)

    for comp in components:
        if comp.type in ("row", "column", "grid"):
            # Layout container
            props = comp.props or {}
            node: LayoutElement = LayoutContainer(
                type=comp.type,  # type: ignore[arg-type] - validated by ORM
                gap=props.get("gap"),
                padding=props.get("padding"),
                align=props.get("align"),
                justify=props.get("justify"),
                columns=props.get("columns"),
                auto_size=props.get("autoSize"),
                visible=comp.visible,
                class_name=props.get("className"),
                children=[],
            )
        else:
            # Leaf component
            node = AppComponentNode(
                id=comp.component_id,
                type=comp.type,
                props=comp.props or {},
                visible=comp.visible,
                width=comp.width,
                loading_workflows=comp.loading_workflows,
            )
        nodes[comp.id] = (node, comp.component_order, comp.parent_id)

    # Second pass: build tree structure
    root_nodes: list[tuple[LayoutElement, int]] = []  # (node, order)

    for comp_id, (node, order, parent_id) in nodes.items():
        if parent_id is None:
            root_nodes.append((node, order))
        elif parent_id in nodes:
            parent_node, _, _ = nodes[parent_id]
            if isinstance(parent_node, LayoutContainer):
                parent_node.children.append(node)

    # Sort children by order for all layout containers
    for node, _, _ in nodes.values():
        if isinstance(node, LayoutContainer):
            # Sort children - need to get their orders from original lookup
            child_orders: dict[int, int] = {}
            for i, child in enumerate(node.children):
                # Find original comp to get order
                for comp_id, (n, order, _) in nodes.items():
                    if n is child:
                        child_orders[i] = order
                        break
            # Sort by order
            indexed_children = [(i, node.children[i]) for i in range(len(node.children))]
            indexed_children.sort(key=lambda x: child_orders.get(x[0], 0))
            node.children = [c for _, c in indexed_children]

    # Sort root nodes by order
    root_nodes.sort(key=lambda x: x[1])

    # Return: if single root layout container, return it; otherwise wrap in column
    if len(root_nodes) == 1:
        root, _ = root_nodes[0]
        if isinstance(root, LayoutContainer):
            return root
        # Single component at root - wrap in column
        return LayoutContainer(type="column", children=[root])
    elif len(root_nodes) == 0:
        return LayoutContainer(type="column", children=[])
    else:
        # Multiple roots - wrap in column
        return LayoutContainer(type="column", children=[node for node, _ in root_nodes])


def build_page_definition(page: AppPage, components: list[AppComponent]) -> PageDefinition:
    """
    Build a PageDefinition from an AppPage and its components.

    This is the primary function for building the full page response
    that matches the frontend TypeScript PageDefinition interface.
    """
    layout = build_layout_tree(components)

    # Convert data_sources to typed list
    data_sources: list[DataSourceConfig] = []
    for ds in page.data_sources or []:
        if isinstance(ds, dict):
            data_sources.append(DataSourceConfig.model_validate(ds))

    # Convert permission to typed model
    permission: PagePermissionConfig | None = None
    if page.permission:
        permission = PagePermissionConfig.model_validate(page.permission)

    return PageDefinition(
        id=page.page_id,
        title=page.title,
        path=page.path,
        layout=layout,
        data_sources=data_sources,
        variables=page.variables or {},
        launch_workflow_id=str(page.launch_workflow_id) if page.launch_workflow_id else None,
        launch_workflow_params=page.launch_workflow_params,
        permission=permission,
    )


def tree_to_layout_json(nodes: list[ComponentTreeNode]) -> dict[str, Any]:
    """
    Convert a ComponentTreeNode tree back to the original JSON layout format.

    This reconstructs the nested layout structure for export/frontend use.
    """
    if not nodes:
        return {"type": "column", "children": []}

    def node_to_json(node: ComponentTreeNode) -> dict[str, Any]:
        if node.type in ("row", "column", "grid"):
            # Layout container
            result: dict[str, Any] = {
                "id": node.component_id,
                "type": node.type,
                **node.props,
                "children": [node_to_json(child) for child in node.children],
            }
        else:
            # Leaf component
            result = {
                "id": node.component_id,
                "type": node.type,
                "props": node.props,
            }

            # Reconstruct nested children for card, modal, tabs
            if node.children:
                if node.type == "card":
                    result["props"]["children"] = [node_to_json(c) for c in node.children]
                elif node.type == "modal":
                    # Modal has single content layout
                    if node.children:
                        result["props"]["content"] = node_to_json(node.children[0])
                elif node.type == "tabs":
                    # Reconstruct tab content
                    tab_contents = {c.props.get("tab_id"): c for c in node.children if c.type == "tab_content"}
                    items = result["props"].get("items", [])
                    for item in items:
                        tab_id = item.get("id")
                        if tab_id in tab_contents:
                            tab_content_node = tab_contents[tab_id]
                            if tab_content_node.children:
                                item["content"] = node_to_json(tab_content_node.children[0])

        # Add common fields if present
        if node.visible:
            result["visible"] = node.visible
        if node.width:
            result["width"] = node.width
        if node.loading_workflows:
            result["loadingWorkflows"] = node.loading_workflows

        return result

    # If single root, return it directly; otherwise wrap in column
    if len(nodes) == 1:
        return node_to_json(nodes[0])
    else:
        return {
            "type": "column",
            "children": [node_to_json(n) for n in nodes],
        }


# =============================================================================
# Service Class
# =============================================================================


class AppBuilderService:
    """Service for app builder tree operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_page_with_components(
        self,
        application_id: UUID,
        page_id: str,
        is_draft: bool = True,
    ) -> tuple[AppPage | None, list[ComponentTreeNode]]:
        """
        Get a page with its component tree (legacy format).

        DEPRECATED: Use get_page_definition() instead for typed responses.
        """
        # Get page
        query = select(AppPage).where(
            AppPage.application_id == application_id,
            AppPage.page_id == page_id,
            AppPage.is_draft == is_draft,
        )
        result = await self.session.execute(query)
        page = result.scalar_one_or_none()

        if not page:
            return None, []

        # Get components
        comp_query = (
            select(AppComponent)
            .where(
                AppComponent.page_id == page.id,
                AppComponent.is_draft == is_draft,
            )
            .order_by(AppComponent.parent_id.nulls_first(), AppComponent.component_order)
        )
        comp_result = await self.session.execute(comp_query)
        components = list(comp_result.scalars().all())

        # Build tree
        tree = build_component_tree(components)

        return page, tree

    async def get_page_definition(
        self,
        application_id: UUID,
        page_id: str,
        is_draft: bool = True,
    ) -> PageDefinition | None:
        """
        Get a page as a fully typed PageDefinition.

        This is the primary method for returning page data to the frontend.
        Returns a PageDefinition that serializes to camelCase JSON matching
        the frontend TypeScript PageDefinition interface.
        """
        # Get page
        query = select(AppPage).where(
            AppPage.application_id == application_id,
            AppPage.page_id == page_id,
            AppPage.is_draft == is_draft,
        )
        result = await self.session.execute(query)
        page = result.scalar_one_or_none()

        if not page:
            return None

        # Get components
        comp_query = (
            select(AppComponent)
            .where(
                AppComponent.page_id == page.id,
                AppComponent.is_draft == is_draft,
            )
            .order_by(AppComponent.parent_id.nulls_first(), AppComponent.component_order)
        )
        comp_result = await self.session.execute(comp_query)
        components = list(comp_result.scalars().all())

        # Build typed page definition
        return build_page_definition(page, components)

    async def create_page_with_layout(
        self,
        application_id: UUID,
        page_id: str,
        title: str,
        path: str,
        layout: dict[str, Any],
        is_draft: bool = True,
        **page_kwargs: Any,
    ) -> AppPage:
        """Create a page and flatten its layout into component rows."""
        # Create page
        page = AppPage(
            application_id=application_id,
            page_id=page_id,
            title=title,
            path=path,
            is_draft=is_draft,
            root_layout_type=layout.get("type", "column"),
            root_layout_config={
                k: v for k, v in layout.items()
                if k in ("gap", "padding", "align", "justify", "columns", "autoSize", "className")
            },
            **page_kwargs,
        )
        self.session.add(page)
        await self.session.flush()

        # Flatten layout to components
        component_dicts = flatten_layout_tree(layout, page.id, is_draft)

        # Create component rows
        for comp_dict in component_dicts:
            component = AppComponent(**comp_dict)
            self.session.add(component)

        await self.session.flush()
        await self.session.refresh(page)

        logger.info(f"Created page '{page_id}' with {len(component_dicts)} components")
        return page

    async def update_page_layout(
        self,
        page: AppPage,
        layout: dict[str, Any],
    ) -> None:
        """Update a page's layout by replacing all its components."""
        # Delete existing components
        comp_query = select(AppComponent).where(
            AppComponent.page_id == page.id,
            AppComponent.is_draft == page.is_draft,
        )
        result = await self.session.execute(comp_query)
        existing = list(result.scalars().all())
        for comp in existing:
            await self.session.delete(comp)

        # Update root layout config
        page.root_layout_type = layout.get("type", "column")
        page.root_layout_config = {
            k: v for k, v in layout.items()
            if k in ("gap", "padding", "align", "justify", "columns", "autoSize", "className")
        }
        page.version += 1

        # Create new components
        component_dicts = flatten_layout_tree(layout, page.id, page.is_draft)
        for comp_dict in component_dicts:
            component = AppComponent(**comp_dict)
            self.session.add(component)

        await self.session.flush()
        logger.info(f"Updated page layout with {len(component_dicts)} components")

    async def copy_page_to_live(self, draft_page: AppPage) -> AppPage:
        """Copy a draft page and its components to live."""
        # Check if live page exists
        live_query = select(AppPage).where(
            AppPage.application_id == draft_page.application_id,
            AppPage.page_id == draft_page.page_id,
            AppPage.is_draft == False,  # noqa: E712
        )
        result = await self.session.execute(live_query)
        live_page = result.scalar_one_or_none()

        if live_page:
            # Delete existing live components
            comp_query = select(AppComponent).where(
                AppComponent.page_id == live_page.id,
                AppComponent.is_draft == False,  # noqa: E712
            )
            comp_result = await self.session.execute(comp_query)
            for comp in comp_result.scalars().all():
                await self.session.delete(comp)
            await self.session.delete(live_page)

        # Create new live page
        live_page = AppPage(
            application_id=draft_page.application_id,
            page_id=draft_page.page_id,
            title=draft_page.title,
            path=draft_page.path,
            is_draft=False,
            version=draft_page.version,
            data_sources=draft_page.data_sources,
            variables=draft_page.variables,
            launch_workflow_id=draft_page.launch_workflow_id,
            launch_workflow_params=draft_page.launch_workflow_params,
            permission=draft_page.permission,
            page_order=draft_page.page_order,
            root_layout_type=draft_page.root_layout_type,
            root_layout_config=draft_page.root_layout_config,
        )
        self.session.add(live_page)
        await self.session.flush()

        # Copy components
        draft_comp_query = select(AppComponent).where(
            AppComponent.page_id == draft_page.id,
            AppComponent.is_draft == True,  # noqa: E712
        )
        draft_comp_result = await self.session.execute(draft_comp_query)
        draft_components = list(draft_comp_result.scalars().all())

        # Build mapping from draft IDs to live IDs
        id_mapping: dict[UUID, UUID] = {}

        for draft_comp in draft_components:
            live_comp_id = uuid4()
            id_mapping[draft_comp.id] = live_comp_id

        # Create live components with updated parent_ids
        for draft_comp in draft_components:
            live_parent_id = id_mapping.get(draft_comp.parent_id) if draft_comp.parent_id else None
            live_comp = AppComponent(
                id=id_mapping[draft_comp.id],
                page_id=live_page.id,
                component_id=draft_comp.component_id,
                parent_id=live_parent_id,
                is_draft=False,
                type=draft_comp.type,
                props=draft_comp.props,
                component_order=draft_comp.component_order,
                visible=draft_comp.visible,
                width=draft_comp.width,
                loading_workflows=draft_comp.loading_workflows,
            )
            self.session.add(live_comp)

        await self.session.flush()
        logger.info(f"Published page '{draft_page.page_id}' with {len(draft_components)} components")
        return live_page

    async def export_application(self, app: Application, is_draft: bool = False) -> dict[str, Any]:
        """Export full application to JSON for GitHub sync/portability."""
        from datetime import datetime

        # Get all pages
        pages_query = select(AppPage).where(
            AppPage.application_id == app.id,
            AppPage.is_draft == is_draft,
        ).order_by(AppPage.page_order)
        result = await self.session.execute(pages_query)
        pages = list(result.scalars().all())

        exported_pages = []
        for page in pages:
            # Get components for this page
            comp_query = (
                select(AppComponent)
                .where(
                    AppComponent.page_id == page.id,
                    AppComponent.is_draft == is_draft,
                )
                .order_by(AppComponent.parent_id.nulls_first(), AppComponent.component_order)
            )
            comp_result = await self.session.execute(comp_query)
            components = list(comp_result.scalars().all())

            # Build tree and convert to JSON
            tree = build_component_tree(components)
            layout = tree_to_layout_json(tree)

            exported_pages.append({
                "id": page.page_id,
                "title": page.title,
                "path": page.path,
                "dataSources": page.data_sources,
                "variables": page.variables,
                "launchWorkflowId": str(page.launch_workflow_id) if page.launch_workflow_id else None,
                "launchWorkflowParams": page.launch_workflow_params,
                "permission": page.permission,
                "layout": layout,
            })

        return {
            "name": app.name,
            "slug": app.slug,
            "description": app.description,
            "icon": app.icon,
            "navigation": app.navigation,
            "globalDataSources": app.global_data_sources,
            "globalVariables": app.global_variables,
            "permissions": app.permissions,
            "pages": exported_pages,
            "exportVersion": "1.0",
            "exportedAt": datetime.utcnow().isoformat(),
        }

    async def import_application(
        self,
        data: dict[str, Any],
        organization_id: UUID | None,
        created_by: str,
    ) -> Application:
        """Import application from JSON."""
        # Create application
        app = Application(
            name=data["name"],
            slug=data["slug"],
            description=data.get("description"),
            icon=data.get("icon"),
            organization_id=organization_id,
            created_by=created_by,
            navigation=data.get("navigation", {}),
            global_data_sources=data.get("globalDataSources", []),
            global_variables=data.get("globalVariables", {}),
            permissions=data.get("permissions", {}),
            draft_version=1,
            live_version=0,
        )
        self.session.add(app)
        await self.session.flush()

        # Import pages
        for page_order, page_data in enumerate(data.get("pages", [])):
            layout = page_data.get("layout", {"type": "column", "children": []})

            # Parse workflow ID if present
            launch_workflow_id = None
            if page_data.get("launchWorkflowId"):
                try:
                    launch_workflow_id = UUID(page_data["launchWorkflowId"])
                except (ValueError, TypeError):
                    pass

            await self.create_page_with_layout(
                application_id=app.id,
                page_id=page_data["id"],
                title=page_data["title"],
                path=page_data["path"],
                layout=layout,
                is_draft=True,
                data_sources=page_data.get("dataSources", []),
                variables=page_data.get("variables", {}),
                launch_workflow_id=launch_workflow_id,
                launch_workflow_params=page_data.get("launchWorkflowParams"),
                permission=page_data.get("permission", {}),
                page_order=page_order,
            )

        await self.session.refresh(app)
        logger.info(f"Imported application '{data['slug']}' with {len(data.get('pages', []))} pages")
        return app

    async def update_draft_definition(
        self,
        app: Application,
        definition: dict[str, Any],
    ) -> None:
        """
        Replace draft pages/components with the provided definition.

        1. Delete all existing draft pages (cascade deletes components)
        2. Create new pages/components from the definition
        """
        from sqlalchemy import delete

        # Delete existing draft pages (cascade deletes components)
        await self.session.execute(
            delete(AppPage).where(
                AppPage.application_id == app.id,
                AppPage.is_draft == True,
            )
        )
        await self.session.flush()

        # Create new pages from definition (reuses import logic)
        for page_order, page_data in enumerate(definition.get("pages", [])):
            layout = page_data.get("layout", {"type": "column", "children": []})

            # Parse workflow ID if present
            launch_workflow_id = None
            if page_data.get("launchWorkflowId"):
                try:
                    launch_workflow_id = UUID(page_data["launchWorkflowId"])
                except (ValueError, TypeError):
                    pass

            await self.create_page_with_layout(
                application_id=app.id,
                page_id=page_data.get("id", f"page_{page_order}"),
                title=page_data.get("title", f"Page {page_order + 1}"),
                path=page_data.get("path", f"/page-{page_order}"),
                layout=layout,
                is_draft=True,
                data_sources=page_data.get("dataSources", []),
                variables=page_data.get("variables", {}),
                launch_workflow_id=launch_workflow_id,
                launch_workflow_params=page_data.get("launchWorkflowParams"),
                permission=page_data.get("permission", {}),
                page_order=page_order,
            )

        logger.info(f"Updated draft for application '{app.slug}' with {len(definition.get('pages', []))} pages")
