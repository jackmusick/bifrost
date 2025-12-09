"""
Test that workflows can return list values.
"""

import pytest
from src.sdk.decorators import workflow
from src.services.execution.engine import execute, ExecutionRequest, ExecutionStatus
from src.sdk.context import Caller, Organization


class TestListReturnValue:
    """Test that workflows can return lists without encoding errors"""

    @pytest.mark.asyncio
    async def test_workflow_returns_list(self):
        """Test that a workflow can return a list successfully"""

        @workflow(
            name="list_return_workflow",
            description="Workflow that returns a list",
            category="test"
        )
        async def return_list_workflow(context):
            """Workflow that returns a simple list"""
            return [1, 2, 3, 4, 5]

        # Execute workflow
        request = ExecutionRequest(
            execution_id="test-list-exec-1",
            caller=Caller(user_id="test-user", email="test@example.com", name="Test User"),
            organization=Organization(id="test-org", name="Test Org"),
            config={},
            name="list_return_workflow",
            parameters={},
            func=return_list_workflow
        )

        result = await execute(request)

        # Verify execution succeeded
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result == [1, 2, 3, 4, 5]
        assert isinstance(result.result, list)

    @pytest.mark.asyncio
    async def test_workflow_returns_list_of_dicts(self):
        """Test that a workflow can return a list of dictionaries"""

        @workflow(
            name="list_of_dicts_workflow",
            description="Workflow that returns a list of dicts",
            category="test"
        )
        async def return_list_of_dicts(context):
            """Workflow that returns a list of dictionaries (like user data)"""
            return [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
            ]

        # Execute workflow
        request = ExecutionRequest(
            execution_id="test-list-exec-2",
            caller=Caller(user_id="test-user", email="test@example.com", name="Test User"),
            organization=Organization(id="test-org", name="Test Org"),
            config={},
            name="list_of_dicts_workflow",
            parameters={},
            func=return_list_of_dicts
        )

        result = await execute(request)

        # Verify execution succeeded
        assert result.status == ExecutionStatus.SUCCESS
        assert isinstance(result.result, list)
        assert len(result.result) == 3
        assert result.result[0]["name"] == "Alice"
        assert result.result[1]["name"] == "Bob"
        assert result.result[2]["name"] == "Charlie"

    @pytest.mark.asyncio
    async def test_workflow_returns_empty_list(self):
        """Test that a workflow can return an empty list"""

        @workflow(
            name="empty_list_workflow",
            description="Workflow that returns an empty list",
            category="test"
        )
        async def return_empty_list(context):
            """Workflow that returns an empty list"""
            return []

        # Execute workflow
        request = ExecutionRequest(
            execution_id="test-list-exec-3",
            caller=Caller(user_id="test-user", email="test@example.com", name="Test User"),
            organization=Organization(id="test-org", name="Test Org"),
            config={},
            name="empty_list_workflow",
            parameters={},
            func=return_empty_list
        )

        result = await execute(request)

        # Verify execution succeeded
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result == []
        assert isinstance(result.result, list)

    @pytest.mark.asyncio
    async def test_workflow_returns_nested_list(self):
        """Test that a workflow can return nested lists"""

        @workflow(
            name="nested_list_workflow",
            description="Workflow that returns nested lists",
            category="test"
        )
        async def return_nested_list(context):
            """Workflow that returns nested lists (matrix-like data)"""
            return [
                [1, 2, 3],
                [4, 5, 6],
                [7, 8, 9]
            ]

        # Execute workflow
        request = ExecutionRequest(
            execution_id="test-list-exec-4",
            caller=Caller(user_id="test-user", email="test@example.com", name="Test User"),
            organization=Organization(id="test-org", name="Test Org"),
            config={},
            name="nested_list_workflow",
            parameters={},
            func=return_nested_list
        )

        result = await execute(request)

        # Verify execution succeeded
        assert result.status == ExecutionStatus.SUCCESS
        assert isinstance(result.result, list)
        assert len(result.result) == 3
        assert result.result[0] == [1, 2, 3]
        assert result.result[1] == [4, 5, 6]
        assert result.result[2] == [7, 8, 9]
