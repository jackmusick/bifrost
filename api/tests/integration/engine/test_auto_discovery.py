"""
Integration tests for workflow dynamic discovery
Tests that workflows are automatically discovered from workspace directories
"""


from shared.discovery import scan_all_workflows, load_workflow


class TestDynamicDiscovery:
    """Test workflow dynamic discovery system"""

    def test_test_workflow_discovered(self):
        """Test that test_workflow is discovered dynamically"""
        workflows = scan_all_workflows()
        workflow_names = [w.name for w in workflows]

        # Workflow should be discovered
        assert "test_workflow" in workflow_names

        # Get workflow metadata
        workflow = next((w for w in workflows if w.name == "test_workflow"), None)
        assert workflow is not None
        assert workflow.name == "test_workflow"
        assert workflow.description == "Simple test workflow for validation"
        assert workflow.category == "testing"
        assert "test" in workflow.tags
        assert "example" in workflow.tags

    def test_test_workflow_parameters(self):
        """Test that test_workflow has correct parameters extracted from function signature"""
        workflows = scan_all_workflows()
        workflow = next((w for w in workflows if w.name == "test_workflow"), None)
        assert workflow is not None

        assert len(workflow.parameters) == 2

        # Check parameter names in order
        param_names = [p.name for p in workflow.parameters]
        assert param_names == ["name", "count"]

        # Check name parameter (extracted from function signature)
        name_param = workflow.parameters[0]
        assert name_param.name == "name"
        assert name_param.type == "string"
        assert name_param.required is True
        # Label defaults to title-cased name when extracted from signature
        assert name_param.label == "Name"

        # Check count parameter with default (extracted from function signature)
        count_param = workflow.parameters[1]
        assert count_param.name == "count"
        assert count_param.type == "int"
        assert count_param.required is False
        assert count_param.default_value == 1
        # Label defaults to title-cased name when extracted from signature
        assert count_param.label == "Count"

    def test_workflow_function_loadable(self):
        """Test that discovered workflow function is loadable"""
        result = load_workflow("test_workflow")

        # Function and metadata should be returned
        assert result is not None
        workflow_func, metadata = result
        assert workflow_func is not None
        assert callable(workflow_func)
        assert metadata.name == "test_workflow"

    def test_scan_returns_multiple_workflows(self):
        """Test that scanning returns multiple workflows from platform"""
        workflows = scan_all_workflows()

        # Should find multiple workflows
        assert len(workflows) >= 1

        # All workflows should have required fields
        for workflow in workflows:
            assert workflow.name is not None
            assert workflow.description is not None
