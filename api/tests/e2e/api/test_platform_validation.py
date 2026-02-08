"""
E2E tests for platform entity validation.

Tests validation of references between platform entities:
- Form references to workflows and data providers
- Agent references to tools, delegated agents

These tests verify that the API rejects requests with invalid references
rather than silently ignoring them.
"""

import pytest
from uuid import uuid4


@pytest.mark.e2e
class TestFormReferenceValidation:
    """Test form reference validation."""

    def test_form_create_with_invalid_workflow_id(self, e2e_client, platform_admin):
        """Creating a form with non-existent workflow_id returns 422."""
        fake_workflow_id = str(uuid4())
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form",
                "workflow_id": fake_workflow_id,
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any(fake_workflow_id in err for err in data["detail"]["errors"])

    def test_form_create_with_invalid_launch_workflow_id(self, e2e_client, platform_admin):
        """Creating a form with non-existent launch_workflow_id returns 422."""
        fake_workflow_id = str(uuid4())
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form",
                "launch_workflow_id": fake_workflow_id,
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any(fake_workflow_id in err for err in data["detail"]["errors"])

    def test_form_create_with_invalid_data_provider_id_in_field(
        self, e2e_client, platform_admin
    ):
        """Creating a form with non-existent data_provider_id in field returns 422."""
        fake_dp_id = str(uuid4())
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form",
                "form_schema": {
                    "fields": [
                        {
                            "name": "category",
                            "type": "select",
                            "label": "Category",
                            "required": True,
                            "data_provider_id": fake_dp_id,
                        }
                    ]
                },
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any(fake_dp_id in err for err in data["detail"]["errors"])

    def test_form_update_with_invalid_workflow_id(
        self, e2e_client, platform_admin
    ):
        """Updating a form with non-existent workflow_id returns 422."""
        # Create a valid form first
        create_response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Valid Form",
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        # Try to update with invalid workflow_id
        fake_workflow_id = str(uuid4())
        update_response = e2e_client.patch(
            f"/api/forms/{form_id}",
            headers=platform_admin.headers,
            json={"workflow_id": fake_workflow_id},
        )
        assert update_response.status_code == 422, f"Expected 422, got {update_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/forms/{form_id}", headers=platform_admin.headers)

    def test_form_update_with_invalid_launch_workflow_id(
        self, e2e_client, platform_admin
    ):
        """Updating a form with non-existent launch_workflow_id returns 422."""
        # Create a valid form first
        create_response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Valid Form",
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        # Try to update with invalid launch_workflow_id
        fake_workflow_id = str(uuid4())
        update_response = e2e_client.patch(
            f"/api/forms/{form_id}",
            headers=platform_admin.headers,
            json={"launch_workflow_id": fake_workflow_id},
        )
        assert update_response.status_code == 422, f"Expected 422, got {update_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/forms/{form_id}", headers=platform_admin.headers)


@pytest.mark.e2e
class TestAgentReferenceValidation:
    """Test agent reference validation."""

    def test_agent_create_with_invalid_tool_id(self, e2e_client, platform_admin):
        """Creating an agent with non-existent tool_id returns 422."""
        fake_tool_id = str(uuid4())
        response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Test Agent",
                "description": "Test agent description",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
                "tool_ids": [fake_tool_id],
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any(fake_tool_id in err for err in data["detail"]["errors"])

    def test_agent_create_with_invalid_delegated_agent_id(self, e2e_client, platform_admin):
        """Creating an agent with non-existent delegated_agent_id returns 422."""
        fake_agent_id = str(uuid4())
        response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Test Agent",
                "description": "Test agent description",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
                "delegated_agent_ids": [fake_agent_id],
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any(fake_agent_id in err for err in data["detail"]["errors"])

    def test_agent_update_with_invalid_tool_id(self, e2e_client, platform_admin):
        """Updating an agent with non-existent tool_id returns 422."""
        # Create a valid agent first
        create_response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Valid Agent",
                "description": "Valid agent description",
                "system_prompt": "You are a valid agent.",
                "channels": ["chat"],
            },
        )
        assert create_response.status_code == 201
        agent_id = create_response.json()["id"]

        # Try to update with invalid tool_id
        fake_tool_id = str(uuid4())
        update_response = e2e_client.put(
            f"/api/agents/{agent_id}",
            headers=platform_admin.headers,
            json={"tool_ids": [fake_tool_id]},
        )
        assert update_response.status_code == 422, f"Expected 422, got {update_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/agents/{agent_id}", headers=platform_admin.headers)

    def test_agent_update_with_invalid_delegated_agent_id(self, e2e_client, platform_admin):
        """Updating an agent with non-existent delegated_agent_id returns 422."""
        # Create a valid agent first
        create_response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Valid Agent",
                "description": "Valid agent description",
                "system_prompt": "You are a valid agent.",
                "channels": ["chat"],
            },
        )
        assert create_response.status_code == 201
        agent_id = create_response.json()["id"]

        # Try to update with invalid delegated_agent_id
        fake_agent_id = str(uuid4())
        update_response = e2e_client.put(
            f"/api/agents/{agent_id}",
            headers=platform_admin.headers,
            json={"delegated_agent_ids": [fake_agent_id]},
        )
        assert update_response.status_code == 422, f"Expected 422, got {update_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/agents/{agent_id}", headers=platform_admin.headers)

    def test_agent_self_delegation_rejected(self, e2e_client, platform_admin):
        """Updating an agent to delegate to itself returns 422."""
        # Create a valid agent first
        create_response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Self-referencing Agent",
                "description": "Agent that tries to delegate to itself",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
            },
        )
        assert create_response.status_code == 201
        agent_id = create_response.json()["id"]

        # Try to add self as delegation
        update_response = e2e_client.put(
            f"/api/agents/{agent_id}",
            headers=platform_admin.headers,
            json={"delegated_agent_ids": [agent_id]},
        )
        assert update_response.status_code == 422, f"Expected 422, got {update_response.status_code}"
        data = update_response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors in response: {data}"
        assert any("itself" in err.lower() for err in data["detail"]["errors"])

        # Cleanup
        e2e_client.delete(f"/api/agents/{agent_id}", headers=platform_admin.headers)

    def test_assign_invalid_tool_to_agent(self, e2e_client, platform_admin):
        """Assigning non-existent tool to agent returns 422."""
        # Create a valid agent first
        create_response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Tool Assignment Test Agent",
                "description": "Agent for testing tool assignment",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
            },
        )
        assert create_response.status_code == 201
        agent_id = create_response.json()["id"]

        # Try to assign non-existent tool
        fake_tool_id = str(uuid4())
        assign_response = e2e_client.post(
            f"/api/agents/{agent_id}/tools",
            headers=platform_admin.headers,
            json={"workflow_ids": [fake_tool_id]},
        )
        assert assign_response.status_code == 422, f"Expected 422, got {assign_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/agents/{agent_id}", headers=platform_admin.headers)

    def test_assign_invalid_delegation_to_agent(self, e2e_client, platform_admin):
        """Assigning non-existent delegation target to agent returns 422."""
        # Create a valid agent first
        create_response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Delegation Assignment Test Agent",
                "description": "Agent for testing delegation assignment",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
            },
        )
        assert create_response.status_code == 201
        agent_id = create_response.json()["id"]

        # Try to assign non-existent delegation target
        fake_agent_id = str(uuid4())
        assign_response = e2e_client.post(
            f"/api/agents/{agent_id}/delegations",
            headers=platform_admin.headers,
            json={"agent_ids": [fake_agent_id]},
        )
        assert assign_response.status_code == 422, f"Expected 422, got {assign_response.status_code}"

        # Cleanup
        e2e_client.delete(f"/api/agents/{agent_id}", headers=platform_admin.headers)


@pytest.mark.e2e
class TestWorkflowTypeValidation:
    """Test that workflow type validation is enforced."""

    def test_form_accepts_tool_as_workflow_id(self, e2e_client, platform_admin):
        """Form workflow_id accepts both workflow and tool types."""
        # Create a tool via editor API with index=true for synchronous discovery
        tool_content = '''"""Test Tool for Validation"""
from bifrost import tool

@tool(
    name="validation_test_tool",
    description="A tool created for type validation testing",
)
async def validation_test_tool(query: str) -> str:
    return f"Result: {query}"
'''
        create_response = e2e_client.put(
            "/api/files/editor/content?index=true",
            headers=platform_admin.headers,
            json={
                "path": "validation_test_tool.py",
                "content": tool_content,
                "encoding": "utf-8",
            },
        )
        assert create_response.status_code == 200

        # Find the tool we just created - check all workflows including tools
        workflows_response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        assert workflows_response.status_code == 200
        workflows = workflows_response.json()

        tool = next((w for w in workflows if w.get("name") == "validation_test_tool"), None)
        assert tool is not None, "Tool should have been created"
        assert tool.get("type") == "tool", f"Should be type='tool', got {tool.get('type')}"

        # Create form with tool ID as workflow_id — tools are valid workflow targets
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form with Tool",
                "workflow_id": tool["id"],
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        form_id = response.json()["id"]

        # Cleanup
        e2e_client.delete(
            f"/api/forms/{form_id}",
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            "/api/files/editor?path=validation_test_tool.py",
            headers=platform_admin.headers,
        )

    def test_form_rejects_data_provider_as_workflow_id(self, e2e_client, platform_admin):
        """Form workflow_id must reference a workflow type, not a data_provider."""
        # Create a data provider via editor API with index=true for synchronous discovery
        dp_content = '''"""Test Data Provider for Validation"""
from bifrost import data_provider

@data_provider(
    name="validation_test_dp",
    description="A data provider created for type validation testing",
)
async def validation_test_dp() -> list:
    return [{"value": "a", "label": "A"}]
'''
        create_response = e2e_client.put(
            "/api/files/editor/content?index=true",
            headers=platform_admin.headers,
            json={
                "path": "validation_test_dp.py",
                "content": dp_content,
                "encoding": "utf-8",
            },
        )
        assert create_response.status_code == 200

        # Find the data provider we just created
        dp_response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        assert dp_response.status_code == 200
        data_providers = dp_response.json()
        dp = next((d for d in data_providers if d.get("name") == "validation_test_dp"), None)
        assert dp is not None, "Data provider should have been created"

        # Try to create form with data_provider ID as workflow_id
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form with DP",
                "workflow_id": dp["id"],
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors: {data}"
        # Should mention that it's a data_provider, not a workflow
        assert any("data_provider" in err.lower() for err in data["detail"]["errors"])

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=validation_test_dp.py",
            headers=platform_admin.headers,
        )

    def test_agent_rejects_workflow_as_tool(self, e2e_client, platform_admin):
        """Agent tool_ids must reference type='tool', not regular workflows."""
        # Create a regular workflow via editor API with index=true for synchronous discovery
        workflow_content = '''"""Test Workflow for Validation"""
from bifrost import workflow

@workflow(
    name="validation_test_workflow",
    description="A workflow created for type validation testing",
)
async def validation_test_workflow(input: str) -> str:
    return f"Processed: {input}"
'''
        create_response = e2e_client.put(
            "/api/files/editor/content?index=true",
            headers=platform_admin.headers,
            json={
                "path": "validation_test_workflow.py",
                "content": workflow_content,
                "encoding": "utf-8",
            },
        )
        assert create_response.status_code == 200

        # Find the workflow we just created
        workflows_response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        assert workflows_response.status_code == 200
        workflows = workflows_response.json()
        workflow = next((w for w in workflows if w.get("name") == "validation_test_workflow"), None)
        assert workflow is not None, "Workflow should have been created"
        assert workflow.get("type") == "workflow", f"Should be type='workflow', got {workflow.get('type')}"

        # Try to create agent with regular workflow as tool
        response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Test Agent with Wrong Tool Type",
                "description": "Testing tool type validation",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
                "tool_ids": [workflow["id"]],
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "errors" in data.get("detail", {}), f"Expected errors: {data}"
        # Should mention that it's a workflow, not a tool
        assert any("workflow" in err.lower() and "tool" in err.lower() for err in data["detail"]["errors"])

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=validation_test_workflow.py",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestMultipleValidationErrors:
    """Test that multiple validation errors are returned together."""

    def test_form_multiple_invalid_references(self, e2e_client, platform_admin):
        """Form with multiple invalid references returns all errors."""
        fake_workflow_id = str(uuid4())
        fake_launch_id = str(uuid4())
        fake_dp_id = str(uuid4())

        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Test Form with Multiple Errors",
                "workflow_id": fake_workflow_id,
                "launch_workflow_id": fake_launch_id,
                "form_schema": {
                    "fields": [
                        {
                            "name": "category",
                            "type": "select",
                            "label": "Category",
                            "required": True,
                            "data_provider_id": fake_dp_id,
                        }
                    ]
                },
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        data = response.json()
        errors = data.get("detail", {}).get("errors", [])

        # Should have at least 3 errors (one for each invalid reference)
        assert len(errors) >= 3, f"Expected at least 3 errors, got {len(errors)}: {errors}"
        assert any(fake_workflow_id in err for err in errors)
        assert any(fake_launch_id in err for err in errors)
        assert any(fake_dp_id in err for err in errors)

    def test_agent_multiple_invalid_references(self, e2e_client, platform_admin):
        """Agent with multiple invalid references returns all errors."""
        fake_tool_id = str(uuid4())
        fake_delegate_id = str(uuid4())

        response = e2e_client.post(
            "/api/agents",
            headers=platform_admin.headers,
            json={
                "name": "Test Agent with Multiple Errors",
                "description": "Testing multiple validation errors",
                "system_prompt": "You are a test agent.",
                "channels": ["chat"],
                "tool_ids": [fake_tool_id],
                "delegated_agent_ids": [fake_delegate_id],
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        data = response.json()
        errors = data.get("detail", {}).get("errors", [])

        # Should have at least 2 errors
        assert len(errors) >= 2, f"Expected at least 2 errors, got {len(errors)}: {errors}"
        assert any(fake_tool_id in err for err in errors)
        assert any(fake_delegate_id in err for err in errors)
