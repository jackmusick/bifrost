from uuid import UUID, uuid4

from src.services.dependency_graph import (
    _extract_workflows_from_props,
    GraphNode,
    GraphEdge,
    DependencyGraph,
)

UUID_A = "12345678-1234-1234-1234-123456789012"
UUID_B = "abcdefab-abcd-abcd-abcd-abcdefabcdef"


class TestExtractWorkflowsFromProps:
    def test_workflowId_at_top_level(self):
        result = _extract_workflows_from_props({"workflowId": UUID_A})
        assert result == {UUID(UUID_A)}

    def test_dataProviderId_at_top_level(self):
        result = _extract_workflows_from_props({"dataProviderId": UUID_A})
        assert result == {UUID(UUID_A)}

    def test_invalid_uuid_returns_empty(self):
        result = _extract_workflows_from_props({"workflowId": "not-a-uuid"})
        assert result == set()

    def test_nested_in_dict(self):
        result = _extract_workflows_from_props({"onClick": {"workflowId": UUID_A}})
        assert result == {UUID(UUID_A)}

    def test_list_of_dicts(self):
        obj = [{"workflowId": UUID_A}, {"workflowId": UUID_B}]
        result = _extract_workflows_from_props(obj)
        assert result == {UUID(UUID_A), UUID(UUID_B)}

    def test_deeply_nested(self):
        obj = {"rowActions": [{"onClick": {"workflowId": UUID_A}}]}
        result = _extract_workflows_from_props(obj)
        assert result == {UUID(UUID_A)}

    def test_none_returns_empty(self):
        assert _extract_workflows_from_props(None) == set()

    def test_string_returns_empty(self):
        assert _extract_workflows_from_props("string") == set()

    def test_int_returns_empty(self):
        assert _extract_workflows_from_props(42) == set()

    def test_empty_dict_returns_empty(self):
        assert _extract_workflows_from_props({}) == set()

    def test_mixed_workflowId_and_dataProviderId(self):
        obj = {
            "button": {"workflowId": UUID_A},
            "table": {"dataProviderId": UUID_B},
        }
        result = _extract_workflows_from_props(obj)
        assert result == {UUID(UUID_A), UUID(UUID_B)}

    def test_duplicate_ids_deduplicated(self):
        obj = [{"workflowId": UUID_A}, {"workflowId": UUID_A}]
        result = _extract_workflows_from_props(obj)
        assert result == {UUID(UUID_A)}

    def test_non_string_workflowId_ignored(self):
        result = _extract_workflows_from_props({"workflowId": 12345})
        assert result == set()

    def test_empty_list_returns_empty(self):
        assert _extract_workflows_from_props([]) == set()


class TestGraphNode:
    def test_constructor(self):
        org_id = uuid4()
        node = GraphNode(id="workflow:123", type="workflow", name="My WF", org_id=org_id)
        assert node.id == "workflow:123"
        assert node.type == "workflow"
        assert node.name == "My WF"
        assert node.org_id == org_id

    def test_to_dict(self):
        org_id = uuid4()
        node = GraphNode(id="form:456", type="form", name="My Form", org_id=org_id)
        assert node.to_dict() == {
            "id": "form:456",
            "type": "form",
            "name": "My Form",
            "org_id": str(org_id),
        }

    def test_to_dict_org_id_none(self):
        node = GraphNode(id="app:789", type="app", name="My App")
        assert node.to_dict()["org_id"] is None


class TestGraphEdge:
    def test_constructor(self):
        edge = GraphEdge(source="workflow:1", target="form:2", relationship="uses")
        assert edge.source == "workflow:1"
        assert edge.target == "form:2"
        assert edge.relationship == "uses"

    def test_to_dict(self):
        edge = GraphEdge(source="a", target="b", relationship="uses")
        assert edge.to_dict() == {
            "source": "a",
            "target": "b",
            "relationship": "uses",
        }


class TestDependencyGraph:
    def test_add_node(self):
        graph = DependencyGraph(root_id="workflow:1")
        node = GraphNode(id="workflow:1", type="workflow", name="WF1")
        graph.add_node(node)
        assert "workflow:1" in graph.nodes
        assert graph.nodes["workflow:1"] is node

    def test_add_node_idempotent(self):
        graph = DependencyGraph(root_id="workflow:1")
        node1 = GraphNode(id="workflow:1", type="workflow", name="First")
        node2 = GraphNode(id="workflow:1", type="workflow", name="Second")
        graph.add_node(node1)
        graph.add_node(node2)
        assert len(graph.nodes) == 1
        assert graph.nodes["workflow:1"].name == "First"

    def test_add_edge(self):
        graph = DependencyGraph(root_id="workflow:1")
        graph.add_edge("workflow:1", "form:2", "uses")
        assert len(graph.edges) == 1
        assert graph.edges[0].source == "workflow:1"
        assert graph.edges[0].target == "form:2"
        assert graph.edges[0].relationship == "uses"

    def test_add_edge_no_duplicate(self):
        graph = DependencyGraph(root_id="workflow:1")
        graph.add_edge("workflow:1", "form:2", "uses")
        graph.add_edge("workflow:1", "form:2", "uses")
        assert len(graph.edges) == 1

    def test_add_edge_different_targets(self):
        graph = DependencyGraph(root_id="workflow:1")
        graph.add_edge("workflow:1", "form:2", "uses")
        graph.add_edge("workflow:1", "form:3", "uses")
        assert len(graph.edges) == 2

    def test_to_dict(self):
        graph = DependencyGraph(root_id="workflow:1")
        org_id = uuid4()
        graph.add_node(GraphNode(id="workflow:1", type="workflow", name="WF1", org_id=org_id))
        graph.add_node(GraphNode(id="form:2", type="form", name="Form1"))
        graph.add_edge("workflow:1", "form:2", "uses")

        result = graph.to_dict()
        assert result["root_id"] == "workflow:1"
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1
        assert result["edges"][0] == {
            "source": "workflow:1",
            "target": "form:2",
            "relationship": "uses",
        }
        node_ids = {n["id"] for n in result["nodes"]}
        assert node_ids == {"workflow:1", "form:2"}

    def test_to_dict_empty_graph(self):
        graph = DependencyGraph(root_id="workflow:1")
        result = graph.to_dict()
        assert result == {"nodes": [], "edges": [], "root_id": "workflow:1"}
