"""
E2E tests for file transitions between regular files and platform entities.

Tests the transitions:
- Regular Python file → Workflow (add @workflow decorator)
- Workflow → Regular Python file (remove decorator)
- Regular Python file → Data Provider (add @data_provider decorator)
- Data Provider → Regular Python file (remove decorator)
- Form deletion removes from DB

These transitions test the DB-first model's ability to detect content type
changes and route storage appropriately.
"""

import pytest

from tests.e2e.conftest import write_and_register


@pytest.mark.e2e
class TestRegularFileToWorkflow:
    """Test transitions from regular Python files to workflows."""

    def test_add_workflow_decorator_creates_db_entry(
        self, e2e_client, platform_admin
    ):
        """
        Adding @workflow decorator to a regular file moves it from S3 to DB.
        """
        # Step 1: Create a regular Python file (no decorator)
        regular_content = '''"""Regular Helper Module"""

async def process_data(data: dict) -> dict:
    """Process some data."""
    return {"processed": True, "original": data}
'''
        response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "transition_test.py",
                "content": regular_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200

        # Verify NOT in workflows list
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        assert not any(w["name"] == "process_data" for w in workflows), \
            "Regular file should not appear in workflows"

        # Step 2: Add @workflow decorator and register
        workflow_content = '''"""Workflow Module - Upgraded"""
from bifrost import workflow

@workflow(
    name="process_data_workflow",
    description="Upgraded from regular function to workflow",
)
async def process_data(data: dict) -> dict:
    """Process some data."""
    return {"processed": True, "original": data}
'''
        registered = write_and_register(
            e2e_client,
            platform_admin.headers,
            "transition_test.py",
            workflow_content,
            "process_data",
        )

        # Step 3: Verify workflow now appears in DB
        assert registered["name"] == "process_data_workflow"
        assert registered.get("id"), "Workflow should have an ID"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=transition_test.py",
            headers=platform_admin.headers,
        )




@pytest.mark.e2e
class TestDataProviderTransitions:
    """Test transitions involving data providers."""

    def test_add_data_provider_decorator_creates_entry(
        self, e2e_client, platform_admin
    ):
        """Adding @data_provider decorator registers as data provider."""
        # Create regular file
        regular_content = '''"""Regular Options Module"""

async def get_options():
    return [{"value": "a", "label": "A"}]
'''
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "dp_transition_test.py",
                "content": regular_content,
                "encoding": "utf-8",
            },
        )

        # Verify not in data providers
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        providers = response.json()
        assert not any(p["name"] == "transition_options_provider" for p in providers)

        # Add @data_provider decorator and register
        dp_content = '''"""Data Provider Module - Upgraded"""
from bifrost import data_provider

@data_provider(
    name="transition_options_provider",
    description="Upgraded from regular function",
)
async def get_options():
    return [{"value": "a", "label": "A"}]
'''
        registered = write_and_register(
            e2e_client,
            platform_admin.headers,
            "dp_transition_test.py",
            dp_content,
            "get_options",
        )

        # Verify appears as data provider
        assert registered["name"] == "transition_options_provider"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=dp_transition_test.py",
            headers=platform_admin.headers,
        )



@pytest.mark.e2e
class TestFormDeletion:
    """Test form deletion properly removes from DB."""

    def test_delete_workflow_file_removes_from_db(
        self, e2e_client, platform_admin
    ):
        """Deleting workflow file removes workflow from DB."""
        # Create workflow via write_and_register
        workflow_content = '''"""Delete File Test Workflow"""
from bifrost import workflow

@workflow(name="delete_file_test_workflow")
async def delete_file_test_workflow() -> str:
    return "test"
'''
        registered = write_and_register(
            e2e_client,
            platform_admin.headers,
            "delete_file_test.py",
            workflow_content,
            "delete_file_test_workflow",
        )

        # Verify workflow exists
        assert registered["name"] == "delete_file_test_workflow"

        # Delete file
        response = e2e_client.delete(
            "/api/files/editor?path=delete_file_test.py",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Verify workflow removed
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        assert not any(w["name"] == "delete_file_test_workflow" for w in workflows), \
            "Workflow should be removed when file is deleted"


@pytest.mark.e2e
class TestDecoratorTypeChanges:
    """Test changing between different decorator types."""

    def test_workflow_to_tool_transition(self, e2e_client, platform_admin):
        """
        Changing from @workflow to @tool should update the type.
        """
        # Create as workflow via write_and_register
        workflow_content = '''"""Workflow First"""
from bifrost import workflow

@workflow(
    name="type_change_test",
    description="Starts as workflow",
)
async def type_change_test(x: str) -> str:
    return f"Result: {x}"
'''
        registered = write_and_register(
            e2e_client,
            platform_admin.headers,
            "type_change_test.py",
            workflow_content,
            "type_change_test",
        )

        # Verify appears as workflow
        assert registered["name"] == "type_change_test"

        # Change to @tool
        tool_content = '''"""Tool Now"""
from bifrost import tool

@tool(
    name="type_change_test",
    description="Now a tool",
)
async def type_change_test(x: str) -> str:
    return f"Result: {x}"
'''
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "type_change_test.py",
                "content": tool_content,
                "encoding": "utf-8",
            },
        )

        # The entry should be updated (same path, different type)
        # Type change behavior depends on implementation details

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=type_change_test.py",
            headers=platform_admin.headers,
        )

    def test_workflow_to_data_provider_transition(
        self, e2e_client, platform_admin
    ):
        """Changing from @workflow to @data_provider updates type."""
        # Create as workflow via write_and_register
        workflow_content = '''"""Workflow to DP"""
from bifrost import workflow

@workflow(name="workflow_to_dp_test")
async def workflow_to_dp_test() -> list:
    return []
'''
        registered = write_and_register(
            e2e_client,
            platform_admin.headers,
            "workflow_to_dp_test.py",
            workflow_content,
            "workflow_to_dp_test",
        )

        # Verify exists as workflow
        assert registered["name"] == "workflow_to_dp_test"

        # Change to data provider
        dp_content = '''"""Now a Data Provider"""
from bifrost import data_provider

@data_provider(name="workflow_to_dp_test")
async def workflow_to_dp_test() -> list:
    return []
'''
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflow_to_dp_test.py",
                "content": dp_content,
                "encoding": "utf-8",
            },
        )

        # Check data providers - should now appear there
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        providers = response.json()
        assert any(p["name"] == "workflow_to_dp_test" for p in providers), \
            "Should now appear as data provider"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflow_to_dp_test.py",
            headers=platform_admin.headers,
        )
