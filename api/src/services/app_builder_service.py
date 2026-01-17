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

from src.models.contracts.applications import ComponentTreeNode
from src.models.contracts.app_components import (
    AppComponent as AppComponentModel,
    DataSourceConfig,
    LayoutContainer,
    LayoutContainerOrComponent,
    PageDefinition,
    PagePermission,
)
from src.models.orm.applications import AppComponent, AppPage, Application, AppVersion

logger = logging.getLogger(__name__)


# =============================================================================
# Tree Flattening (JSON -> Rows)
# =============================================================================


def flatten_layout_tree(
    layout: LayoutContainer | dict[str, Any],
    page_id: UUID,
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

    Raises:
        ValidationError: If component props fail Pydantic validation.

    Note:
        Accepts both LayoutContainer (for validated inputs) and dict (for
        recursive calls with child elements which may be components).
    """
    # Convert LayoutContainer to dict for uniform processing
    if isinstance(layout, LayoutContainer):
        layout = layout.model_dump(exclude_none=True, by_alias=True)

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
        for key in ("gap", "padding", "align", "justify", "columns", "distribute", "maxHeight", "overflow", "sticky", "stickyOffset", "className", "style"):
            if key in layout:
                layout_props[key] = layout[key]

        components.append({
            "id": component_uuid,
            "page_id": page_id,
            "component_id": component_id,
            "parent_id": parent_id,
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
                child, page_id, parent_id=component_uuid, order=idx
            )
            components.extend(child_components)
    else:
        # This is a leaf component (button, text, data-table, etc.)
        component_id = layout.get("id") or f"{layout_type}_{uuid4().hex[:8]}"
        component_uuid = uuid4()

        # The props are in a "props" key for leaf components
        props = layout.get("props", {})

        # Validate props through the discriminated union (AppComponentModel)
        # This routes to the correct component model based on 'type' field
        # and ensures field names are correct (e.g., data_source not dataSource)
        from pydantic import TypeAdapter

        component_data = {
            "id": component_id,
            "type": layout_type,
            "props": props,
        }
        adapter = TypeAdapter(AppComponentModel)
        validated_component = adapter.validate_python(component_data)
        validated_props = validated_component.props.model_dump(exclude_none=True)

        components.append({
            "id": component_uuid,
            "page_id": page_id,
            "component_id": component_id,
            "parent_id": parent_id,
            "type": layout_type,
            "props": validated_props,
            "component_order": order,
            "visible": layout.get("visible"),
            "width": layout.get("width"),
            "loading_workflows": layout.get("loadingWorkflows"),
        })

        # Some components can have children (card, modal, tabs)
        if "children" in props:
            for idx, child in enumerate(props.get("children", [])):
                child_components = flatten_layout_tree(
                    child, page_id, parent_id=component_uuid, order=idx
                )
                components.extend(child_components)
            # Remove children from props since they're now separate rows
            props.pop("children", None)

        # Handle card content
        if layout_type == "card" and "content" in props:
            for idx, child in enumerate(props.get("content", [])):
                child_components = flatten_layout_tree(
                    child, page_id, parent_id=component_uuid, order=idx
                )
                components.extend(child_components)
            props.pop("content", None)

        # Handle modal content
        if layout_type == "modal" and "content" in props:
            content = props.get("content")
            if isinstance(content, dict):
                child_components = flatten_layout_tree(
                    content, page_id, parent_id=component_uuid, order=0
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
                        "type": "tab_content",
                        "props": {"tab_id": tab.get("id")},
                        "component_order": tab_idx,
                        "visible": None,
                        "width": None,
                        "loading_workflows": None,
                    })
                    child_components = flatten_layout_tree(
                        tab["content"], page_id, parent_id=tab_content_id, order=0
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
# New Unified Tree Flattening (AppComponent list -> Rows)
# =============================================================================


# Container types that have children in the unified model
CONTAINER_TYPES = frozenset(
    ["row", "column", "grid", "card", "modal", "tabs", "tab-item", "form-group"]
)

# Base fields from ComponentBase that should be stored at row level, not in props
BASE_FIELDS = frozenset(["id", "type", "children", "visible", "width", "loading_workflows"])


def flatten_components(
    components: list[AppComponentModel],
    page_id: UUID,
    parent_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Flatten nested component tree to flat rows for database storage.

    Each component becomes one row. Container components have their children
    recursively flattened with parent_id pointing to the container's row.

    This function works with the unified AppComponent model where:
    - All components extend ComponentBase
    - Container components (row, column, grid, card, modal, tabs, tab-item, form-group)
      have children: list[AppComponent] at the top level
    - Leaf components have no children field
    - Props are top-level fields, not nested under a 'props' key

    Args:
        components: List of AppComponent instances (from discriminated union)
        page_id: Page UUID for all rows
        parent_id: Parent component UUID (None for root level)

    Returns:
        List of dicts ready for AppComponent ORM creation with:
        - id: UUID for this row
        - page_id: Page UUID
        - component_id: Original component ID string
        - parent_id: Parent row UUID (None for root)
        - type: Component type string
        - props: Dict of component-specific properties
        - component_order: Order among siblings
        - visible: Visibility expression (extracted from base fields)
        - width: Component width (extracted from base fields)
        - loading_workflows: List of workflow IDs (extracted from base fields)
    """
    rows: list[dict[str, Any]] = []

    for order, component in enumerate(components):
        component_uuid = uuid4()

        # Dump component to dict, excluding children (handled separately via recursion)
        component_dict = component.model_dump(exclude_none=True, exclude={"children"})

        # Extract base identifiers
        component_id = component_dict.pop("id")
        component_type = component_dict.pop("type")

        # Extract base fields that are stored at row level
        visible = component_dict.pop("visible", None)
        width = component_dict.pop("width", None)
        loading_workflows = component_dict.pop("loading_workflows", None)

        # Everything remaining becomes props
        props = component_dict

        rows.append(
            {
                "id": component_uuid,
                "page_id": page_id,
                "component_id": component_id,
                "parent_id": parent_id,
                "type": component_type,
                "props": props,
                "component_order": order,
                "visible": visible,
                "width": width,
                "loading_workflows": loading_workflows,
            }
        )

        # Recursively flatten children if this is a container component
        if hasattr(component, "children") and component.children:
            child_rows = flatten_components(
                component.children,  # type: ignore[arg-type]
                page_id,
                parent_id=component_uuid,
            )
            rows.extend(child_rows)

    return rows


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


def _layout_element_to_dict(node: LayoutContainerOrComponent) -> dict[str, Any]:
    """
    Convert a LayoutContainerOrComponent back to dict for embedding in props.

    Used to reconstruct card/modal/tabs children that are stored as separate
    component rows but need to be returned as nested dicts in props.
    """
    if isinstance(node, LayoutContainer):
        result: dict[str, Any] = {"id": node.id, "type": node.type}
        if node.gap is not None:
            result["gap"] = node.gap
        if node.padding is not None:
            result["padding"] = node.padding
        if node.align is not None:
            result["align"] = node.align
        if node.justify is not None:
            result["justify"] = node.justify
        if node.columns is not None:
            result["columns"] = node.columns
        if node.distribute is not None:
            result["distribute"] = node.distribute
        if node.max_height is not None:
            result["maxHeight"] = node.max_height
        if node.overflow is not None:
            result["overflow"] = node.overflow
        if node.sticky is not None:
            result["sticky"] = node.sticky
        if node.sticky_offset is not None:
            result["stickyOffset"] = node.sticky_offset
        if node.max_width is not None:
            result["maxWidth"] = node.max_width
        if node.visible is not None:
            result["visible"] = node.visible
        if node.class_name is not None:
            result["className"] = node.class_name
        if node.children:
            result["children"] = [_layout_element_to_dict(c) for c in node.children]
        return result
    else:
        # AppComponent (discriminated union) - serialize via model_dump
        return node.model_dump(exclude_none=True, by_alias=True)


def build_layout_tree(components: list[AppComponent]) -> LayoutContainer:
    """
    Build a typed LayoutContainer tree from flat component rows.

    Returns a properly typed LayoutContainer that matches the frontend TypeScript
    LayoutContainer interface. This is the primary function for building the tree
    that gets returned from the API.

    Uses a single pass with a lookup dict to build the tree efficiently.
    """
    from pydantic import TypeAdapter

    if not components:
        # Return empty column layout
        return LayoutContainer(id=f"layout_{uuid4().hex[:8]}", type="column", children=[])

    # First pass: create all nodes as LayoutContainerOrComponent
    nodes: dict[UUID, tuple[LayoutContainerOrComponent, int, UUID | None]] = {}  # id -> (node, order, parent_id)

    for comp in components:
        if comp.type in ("row", "column", "grid"):
            # Layout container
            props = comp.props or {}
            node: LayoutContainerOrComponent = LayoutContainer(
                id=comp.component_id,  # Include component_id for API operations
                type=comp.type,  # type: ignore[arg-type] - validated by ORM
                gap=props.get("gap"),
                padding=props.get("padding"),
                align=props.get("align"),
                justify=props.get("justify"),
                columns=props.get("columns"),
                distribute=props.get("distribute"),
                max_height=props.get("maxHeight"),
                overflow=props.get("overflow"),
                sticky=props.get("sticky"),
                sticky_offset=props.get("stickyOffset"),
                max_width=props.get("maxWidth"),
                visible=comp.visible,
                class_name=props.get("className"),
                style=props.get("style"),
                children=[],
            )
        else:
            # Leaf component - validate through discriminated union
            component_data = {
                "id": comp.component_id,
                "type": comp.type,
                "props": comp.props or {},
                "visible": comp.visible,
                "width": comp.width,
                "loading_workflows": comp.loading_workflows,
            }
            adapter = TypeAdapter(AppComponentModel)
            node = adapter.validate_python(component_data)
        nodes[comp.id] = (node, comp.component_order, comp.parent_id)

    # Second pass: build tree structure
    # Track children for container-like leaf components (card, modal, tabs)
    container_children: dict[UUID, list[tuple[LayoutContainerOrComponent, int]]] = {}
    root_nodes: list[tuple[LayoutContainerOrComponent, int]] = []  # (node, order)

    for comp_id, (node, order, parent_id) in nodes.items():
        if parent_id is None:
            root_nodes.append((node, order))
        elif parent_id in nodes:
            parent_node, _, _ = nodes[parent_id]
            if isinstance(parent_node, LayoutContainer):
                parent_node.children.append(node)
            else:
                # Track children for container-like leaf components
                if parent_id not in container_children:
                    container_children[parent_id] = []
                container_children[parent_id].append((node, order))

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

    # Third pass: reconstruct props.children for container-like leaf components
    # (card, modal, tabs store children in props rather than as layout children)
    for comp_id, children_list in container_children.items():
        parent_node, _, _ = nodes[comp_id]
        if not isinstance(parent_node, LayoutContainer):
            # Sort children by order
            children_list.sort(key=lambda x: x[1])

            parent_type = parent_node.type
            if parent_type == "card":
                # Card stores children in props.children as dicts
                parent_node.props.children = [
                    _layout_element_to_dict(child) for child, _ in children_list
                ]
            elif parent_type == "modal":
                # Modal stores single content layout in props.content
                if children_list:
                    content_dict = _layout_element_to_dict(children_list[0][0])
                    parent_node.props.content = LayoutContainer.model_validate(content_dict)
            elif parent_type == "tabs":
                # Tabs: tab_content children need to be matched to items
                tab_contents: dict[str, LayoutContainerOrComponent] = {}
                for child, _ in children_list:
                    if not isinstance(child, LayoutContainer) and child.type == "tab_content":
                        # Internal tab_content marker - extract tab_id from props
                        tab_id = getattr(child.props, "tab_id", None) if hasattr(child, "props") else None
                        if tab_id:
                            tab_contents[tab_id] = child

                if parent_node.props.items:
                    for item in parent_node.props.items:
                        tab_id = item.id
                        if tab_id in tab_contents:
                            tab_content_node = tab_contents[tab_id]
                            # Get children of the tab_content from container_children
                            tab_content_id = None
                            for cid, (n, _, _) in nodes.items():
                                if n is tab_content_node:
                                    tab_content_id = cid
                                    break
                            if tab_content_id and tab_content_id in container_children:
                                tab_children = container_children[tab_content_id]
                                tab_children.sort(key=lambda x: x[1])
                                if tab_children:
                                    content_dict = _layout_element_to_dict(tab_children[0][0])
                                    item.content = LayoutContainer.model_validate(content_dict)

    # Return: if single root layout container, return it; otherwise wrap in column
    if len(root_nodes) == 1:
        root, _ = root_nodes[0]
        if isinstance(root, LayoutContainer):
            return root
        # Single component at root - wrap in column
        return LayoutContainer(id=f"layout_{uuid4().hex[:8]}", type="column", children=[root])
    elif len(root_nodes) == 0:
        return LayoutContainer(id=f"layout_{uuid4().hex[:8]}", type="column", children=[])
    else:
        # Multiple roots - wrap in column
        return LayoutContainer(id=f"layout_{uuid4().hex[:8]}", type="column", children=[node for node, _ in root_nodes])


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
    permission: PagePermission | None = None
    if page.permission:
        permission = PagePermission.model_validate(page.permission)

    return PageDefinition(
        id=page.page_id,
        title=page.title,
        path=page.path,
        layout=layout,
        data_sources=data_sources,
        variables=page.variables or {},
        launch_workflow_id=str(page.launch_workflow_id) if page.launch_workflow_id else None,
        launch_workflow_params=page.launch_workflow_params,
        launch_workflow_data_source_id=page.launch_workflow_data_source_id,
        permission=permission,
    )


def tree_to_layout_json(nodes: list[ComponentTreeNode]) -> dict[str, Any]:
    """
    Convert a ComponentTreeNode tree back to the original JSON layout format.

    This reconstructs the nested layout structure for export/frontend use.
    """
    if not nodes:
        return {"id": f"layout_{uuid4().hex[:8]}", "type": "column", "children": []}

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
            "id": f"layout_{uuid4().hex[:8]}",
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
        version_id: UUID,
    ) -> tuple[AppPage | None, list[ComponentTreeNode]]:
        """
        Get a page with its component tree (legacy format).

        Requires version_id to specify which version of the page to get.

        DEPRECATED: Use get_page_definition() instead for typed responses.
        """

        query = select(AppPage).where(
            AppPage.application_id == application_id,
            AppPage.page_id == page_id,
            AppPage.version_id == version_id,
        )
        result = await self.session.execute(query)
        page = result.scalar_one_or_none()

        if not page:
            return None, []

        # Get components for this page (components belong to page by page_id FK)
        comp_query = (
            select(AppComponent)
            .where(AppComponent.page_id == page.id)
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
        version_id: UUID | None = None,
    ) -> PageDefinition | None:
        """
        Get a page as a fully typed PageDefinition.

        Requires version_id to specify which version of the page to get.

        This is the primary method for returning page data to the frontend.
        Returns a PageDefinition that serializes to camelCase JSON matching
        the frontend TypeScript PageDefinition interface.
        """
        if version_id is None:
            raise ValueError("version_id is required")

        query = select(AppPage).where(
            AppPage.application_id == application_id,
            AppPage.page_id == page_id,
            AppPage.version_id == version_id,
        )
        result = await self.session.execute(query)
        page = result.scalar_one_or_none()

        if not page:
            return None

        # Get components for this page (components belong to page by page_id FK)
        comp_query = (
            select(AppComponent)
            .where(AppComponent.page_id == page.id)
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
        layout: LayoutContainer | dict[str, Any],
        version_id: UUID | None = None,
        **page_kwargs: Any,
    ) -> AppPage:
        """Create a page and flatten its layout into component rows.

        The page will be linked to the specified version_id.

        Args:
            layout: Either a validated LayoutContainer or a raw dict.
                   If dict, it will be validated through LayoutContainer.
        """
        # Validate layout if it's a raw dict
        if isinstance(layout, dict):
            layout = LayoutContainer.model_validate(layout)

        # Create page (root layout is now just the first component row)
        page = AppPage(
            application_id=application_id,
            page_id=page_id,
            title=title,
            path=path,
            version_id=version_id,
            **page_kwargs,
        )
        self.session.add(page)
        await self.session.flush()

        # Flatten layout to components
        component_dicts = flatten_layout_tree(layout, page.id)

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
        layout: LayoutContainer | dict[str, Any],
    ) -> None:
        """Update a page's layout by replacing all its components.

        Args:
            layout: Either a validated LayoutContainer or a raw dict.
                   If dict, it will be validated through LayoutContainer.
        """
        # Validate layout if it's a raw dict
        if isinstance(layout, dict):
            layout = LayoutContainer.model_validate(layout)

        # Delete existing components for this page
        comp_query = select(AppComponent).where(
            AppComponent.page_id == page.id,
        )
        result = await self.session.execute(comp_query)
        existing = list(result.scalars().all())
        for comp in existing:
            await self.session.delete(comp)

        # Flush deletes before inserting new components to avoid unique constraint violations
        await self.session.flush()

        # Create new components (root layout is now just the first component row)
        component_dicts = flatten_layout_tree(layout, page.id)
        for comp_dict in component_dicts:
            component = AppComponent(**comp_dict)
            self.session.add(component)

        await self.session.flush()
        logger.info(f"Updated page layout with {len(component_dicts)} components")

    async def copy_page_to_version(
        self,
        source_page: AppPage,
        target_version_id: UUID,
    ) -> AppPage:
        """Copy a page and its components to a new version.

        Pages are linked to versions via version_id.
        """
        # Create new page linked to target version
        new_page = AppPage(
            application_id=source_page.application_id,
            page_id=source_page.page_id,
            title=source_page.title,
            path=source_page.path,
            version_id=target_version_id,
            data_sources=source_page.data_sources,
            variables=source_page.variables,
            launch_workflow_id=source_page.launch_workflow_id,
            launch_workflow_params=source_page.launch_workflow_params,
            launch_workflow_data_source_id=source_page.launch_workflow_data_source_id,
            permission=source_page.permission,
            page_order=source_page.page_order,
            root_layout_type=source_page.root_layout_type,
            root_layout_config=source_page.root_layout_config,
        )
        self.session.add(new_page)
        await self.session.flush()

        # Copy components
        source_comp_query = select(AppComponent).where(
            AppComponent.page_id == source_page.id,
        )
        source_comp_result = await self.session.execute(source_comp_query)
        source_components = list(source_comp_result.scalars().all())

        # Build mapping from source IDs to new IDs
        id_mapping: dict[UUID, UUID] = {}
        for comp in source_components:
            id_mapping[comp.id] = uuid4()

        # Create new components with updated parent_ids
        for comp in source_components:
            new_parent_id = id_mapping.get(comp.parent_id) if comp.parent_id else None
            new_comp = AppComponent(
                id=id_mapping[comp.id],
                page_id=new_page.id,
                component_id=comp.component_id,
                parent_id=new_parent_id,
                type=comp.type,
                props=comp.props,
                component_order=comp.component_order,
                visible=comp.visible,
                width=comp.width,
                loading_workflows=comp.loading_workflows,
            )
            self.session.add(new_comp)

        await self.session.flush()
        logger.info(f"Copied page '{source_page.page_id}' to version {target_version_id}")
        return new_page

    async def copy_version(
        self,
        app: Application,
        source_version_id: UUID,
    ) -> AppVersion:
        """Create a new version by copying all pages from a source version.

        This is used during publish to create a new version from the draft.
        """
        # Create new version
        new_version = AppVersion(application_id=app.id)
        self.session.add(new_version)
        await self.session.flush()

        # Get all pages from source version
        pages_query = select(AppPage).where(
            AppPage.version_id == source_version_id,
        ).order_by(AppPage.page_order)
        result = await self.session.execute(pages_query)
        source_pages = list(result.scalars().all())

        # Copy each page to the new version
        for page in source_pages:
            await self.copy_page_to_version(page, new_version.id)

        logger.info(
            f"Created version {new_version.id} for app {app.id} "
            f"with {len(source_pages)} pages"
        )
        return new_version

    async def export_application(
        self,
        app: Application,
        version_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Export full application to JSON for GitHub sync/portability.

        Args:
            app: The application to export
            version_id: Version to export. Defaults to draft_version_id if not specified.
        """
        from datetime import datetime

        # Use draft version if not specified
        target_version_id = version_id or app.draft_version_id
        if not target_version_id:
            raise ValueError("No version to export. Application has no draft version.")

        # Get all pages for this version
        pages_query = select(AppPage).where(
            AppPage.application_id == app.id,
            AppPage.version_id == target_version_id,
        ).order_by(AppPage.page_order)
        result = await self.session.execute(pages_query)
        pages = list(result.scalars().all())

        exported_pages = []
        for page in pages:
            # Get components for this page (components belong to page by page_id)
            comp_query = (
                select(AppComponent)
                .where(AppComponent.page_id == page.id)
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
            permissions=data.get("permissions", {}),
        )
        self.session.add(app)
        await self.session.flush()

        # Create initial draft version
        draft_version = AppVersion(application_id=app.id)
        self.session.add(draft_version)
        await self.session.flush()

        # Link app to draft version
        app.draft_version_id = draft_version.id
        await self.session.flush()  # Ensure draft_version_id is persisted

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
                version_id=draft_version.id,
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

        if not app.draft_version_id:
            raise ValueError("Application has no draft version")

        # Delete existing draft pages (cascade deletes components)
        await self.session.execute(
            delete(AppPage).where(
                AppPage.application_id == app.id,
                AppPage.version_id == app.draft_version_id,
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
                version_id=app.draft_version_id,
                data_sources=page_data.get("dataSources", []),
                variables=page_data.get("variables", {}),
                launch_workflow_id=launch_workflow_id,
                launch_workflow_params=page_data.get("launchWorkflowParams"),
                permission=page_data.get("permission", {}),
                page_order=page_order,
            )

        logger.info(f"Updated draft for application '{app.slug}' with {len(definition.get('pages', []))} pages")

    async def publish_with_versioning(self, app: Application) -> AppVersion:
        """Publish the application using the new versioning system.

        Creates a new version by copying all pages from the draft version,
        then sets this new version as the active (live) version.

        Returns the newly created active version.
        """
        from datetime import datetime

        if not app.draft_version_id:
            raise ValueError("Application has no draft version to publish")

        # Create new version from draft
        new_version = await self.copy_version(app, app.draft_version_id)

        # Set as active version
        app.active_version_id = new_version.id
        app.published_at = datetime.utcnow()

        await self.session.flush()
        logger.info(f"Published app {app.slug} with new active version {new_version.id}")
        return new_version

    async def rollback_to_version(self, app: Application, version_id: UUID) -> None:
        """Rollback the application's active version to a previous version.

        Sets the specified version as the new active version.
        The draft version remains unchanged.
        """
        from datetime import datetime

        # Verify the version exists and belongs to this app
        version_query = select(AppVersion).where(
            AppVersion.id == version_id,
            AppVersion.application_id == app.id,
        )
        result = await self.session.execute(version_query)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError(f"Version {version_id} not found for application {app.id}")

        # Set as active version
        app.active_version_id = version_id
        app.published_at = datetime.utcnow()

        await self.session.flush()
        logger.info(f"Rolled back app {app.slug} to version {version_id}")
