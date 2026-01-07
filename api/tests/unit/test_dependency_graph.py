"""
Unit tests for the DependencyGraphService.
"""

from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.dependency_graph import (
    DependencyGraphService,
    DependencyGraph,
    GraphNode,
    GraphEdge,
)


class TestDependencyGraph:
    """Tests for the DependencyGraph data structure."""

    def test_add_node_new(self):
        """Test adding a new node to the graph."""
        graph = DependencyGraph("root:123")
        node = GraphNode("workflow:123", "workflow", "Test Workflow")

        graph.add_node(node)

        assert "workflow:123" in graph.nodes
        assert graph.nodes["workflow:123"].name == "Test Workflow"

    def test_add_node_duplicate(self):
        """Test that duplicate nodes are not added."""
        graph = DependencyGraph("root:123")
        node1 = GraphNode("workflow:123", "workflow", "First")
        node2 = GraphNode("workflow:123", "workflow", "Second")

        graph.add_node(node1)
        graph.add_node(node2)

        assert len(graph.nodes) == 1
        assert graph.nodes["workflow:123"].name == "First"

    def test_add_edge(self):
        """Test adding an edge to the graph."""
        graph = DependencyGraph("root:123")

        graph.add_edge("workflow:123", "form:456", "uses")

        assert len(graph.edges) == 1
        assert graph.edges[0].source == "workflow:123"
        assert graph.edges[0].target == "form:456"
        assert graph.edges[0].relationship == "uses"

    def test_add_edge_duplicate(self):
        """Test that duplicate edges are not added."""
        graph = DependencyGraph("root:123")

        graph.add_edge("workflow:123", "form:456", "uses")
        graph.add_edge("workflow:123", "form:456", "uses")

        assert len(graph.edges) == 1

    def test_to_dict(self):
        """Test serializing graph to dictionary."""
        graph = DependencyGraph("workflow:123")
        graph.add_node(GraphNode("workflow:123", "workflow", "Test Workflow"))
        graph.add_node(GraphNode("form:456", "form", "Test Form"))
        graph.add_edge("form:456", "workflow:123", "uses")

        result = graph.to_dict()

        assert result["root_id"] == "workflow:123"
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1


class TestGraphNode:
    """Tests for the GraphNode class."""

    def test_to_dict_without_org(self):
        """Test serializing node without organization."""
        node = GraphNode("workflow:123", "workflow", "Test Workflow")

        result = node.to_dict()

        assert result["id"] == "workflow:123"
        assert result["type"] == "workflow"
        assert result["name"] == "Test Workflow"
        assert result["org_id"] is None

    def test_to_dict_with_org(self):
        """Test serializing node with organization."""
        org_id = uuid4()
        node = GraphNode("form:456", "form", "Test Form", org_id)

        result = node.to_dict()

        assert result["id"] == "form:456"
        assert result["type"] == "form"
        assert result["name"] == "Test Form"
        assert result["org_id"] == str(org_id)


class TestGraphEdge:
    """Tests for the GraphEdge class."""

    def test_to_dict(self):
        """Test serializing edge to dictionary."""
        edge = GraphEdge("workflow:123", "form:456", "uses")

        result = edge.to_dict()

        assert result["source"] == "workflow:123"
        assert result["target"] == "form:456"
        assert result["relationship"] == "uses"


class TestDependencyGraphService:
    """Tests for the DependencyGraphService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        """Create a service instance with mock db."""
        return DependencyGraphService(mock_db)

    @pytest.mark.asyncio
    async def test_build_graph_clamps_depth_min(self, service, mock_db):
        """Test that depth is clamped to minimum of 1."""
        # Mock the entity fetch to return None (entity not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        entity_id = uuid4()

        # Depth 0 should be clamped to 1
        graph = await service.build_graph("workflow", entity_id, depth=0)

        # Graph should be empty since entity wasn't found
        assert len(graph.nodes) == 0

    @pytest.mark.asyncio
    async def test_build_graph_clamps_depth_max(self, service, mock_db):
        """Test that depth is clamped to maximum of 5."""
        # Mock the entity fetch to return None (entity not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        entity_id = uuid4()

        # Depth 10 should be clamped to 5
        graph = await service.build_graph("workflow", entity_id, depth=10)

        # Graph should be empty since entity wasn't found
        assert len(graph.nodes) == 0

    @pytest.mark.asyncio
    async def test_fetch_entity_node_workflow(self, service, mock_db):
        """Test fetching a workflow entity node."""
        entity_id = uuid4()
        org_id = uuid4()

        # Mock workflow entity
        mock_workflow = MagicMock()
        mock_workflow.id = entity_id
        mock_workflow.name = "Test Workflow"
        mock_workflow.organization_id = org_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_db.execute.return_value = mock_result

        node = await service._fetch_entity_node("workflow", entity_id)

        assert node is not None
        assert node.id == f"workflow:{entity_id}"
        assert node.type == "workflow"
        assert node.name == "Test Workflow"
        assert node.org_id == org_id

    @pytest.mark.asyncio
    async def test_fetch_entity_node_not_found(self, service, mock_db):
        """Test fetching an entity that doesn't exist."""
        entity_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        node = await service._fetch_entity_node("workflow", entity_id)

        assert node is None

    @pytest.mark.asyncio
    async def test_get_dependencies_agent(self, service, mock_db):
        """Test getting dependencies for an agent (uses workflows)."""
        agent_id = uuid4()
        workflow_id = uuid4()

        # Mock agent_tools query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [workflow_id]
        mock_db.execute.return_value = mock_result

        deps = await service._get_dependencies("agent", agent_id)

        assert len(deps) == 1
        assert deps[0] == ("workflow", workflow_id, "uses")

    @pytest.mark.asyncio
    async def test_get_dependencies_deduplicates(self, service, mock_db):
        """Test that duplicate dependencies are removed."""
        agent_id = uuid4()
        workflow_id = uuid4()

        # Return same workflow ID twice
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [workflow_id, workflow_id]
        mock_db.execute.return_value = mock_result

        deps = await service._get_dependencies("agent", agent_id)

        # Should be deduplicated to 1
        assert len(deps) == 1
