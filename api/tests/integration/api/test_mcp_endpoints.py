"""
Integration tests for MCP Endpoints Access Control.

Tests that MCP REST endpoints are properly protected:
- /api/mcp/config - GET, PUT, DELETE require auth + platform admin
- /api/mcp/tools - GET requires auth + platform admin
- /api/mcp/status - GET requires auth + platform admin

Uses real HTTP requests to the running API server.
"""

import pytest
import requests

from tests.fixtures.auth import (
    auth_headers,
    create_test_jwt,
)


# Base URL for test API (set by docker-compose.test.yml)
import os

TEST_API_URL = os.getenv("TEST_API_URL", "http://api:8000")


# ==================== MCP Config Endpoint Tests ====================


class TestMCPConfigEndpoint:
    """Tests for /api/mcp/config endpoint access control."""

    @pytest.mark.integration
    def test_get_config_requires_auth(self):
        """Should return 401 when no auth provided."""
        response = requests.get(f"{TEST_API_URL}/api/mcp/config")

        assert response.status_code == 401

    @pytest.mark.integration
    def test_get_config_requires_platform_admin(self):
        """Should return 403 for non-admin user."""
        # Create token for regular user (not superuser)
        token = create_test_jwt(
            email="user@org.local",
            is_superuser=False,
        )
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/config",
            headers=headers,
        )

        assert response.status_code == 403
        assert "platform admin" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_get_config_success_for_platform_admin(self):
        """Should return 200 for platform admin."""
        # Use create_test_jwt with is_superuser=True to get valid UUID
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/config",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Check response has expected fields
        assert "enabled" in data
        assert "require_platform_admin" in data
        assert "is_configured" in data

    @pytest.mark.integration
    def test_put_config_requires_auth(self):
        """Should return 401 when no auth provided for PUT."""
        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={"enabled": True},
        )

        assert response.status_code == 401

    @pytest.mark.integration
    def test_put_config_requires_platform_admin(self):
        """Should return 403 for non-admin user on PUT."""
        token = create_test_jwt(
            email="user@org.local",
            is_superuser=False,
        )
        headers = auth_headers(token)

        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={"enabled": True},
            headers=headers,
        )

        assert response.status_code == 403
        assert "platform admin" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_put_config_success_for_platform_admin(self):
        """Should return 200 for platform admin on PUT."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={
                "enabled": True,
                "require_platform_admin": True,
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    @pytest.mark.integration
    def test_delete_config_requires_auth(self):
        """Should return 401 when no auth provided for DELETE."""
        response = requests.delete(f"{TEST_API_URL}/api/mcp/config")

        assert response.status_code == 401

    @pytest.mark.integration
    def test_delete_config_requires_platform_admin(self):
        """Should return 403 for non-admin user on DELETE."""
        token = create_test_jwt(
            email="user@org.local",
            is_superuser=False,
        )
        headers = auth_headers(token)

        response = requests.delete(
            f"{TEST_API_URL}/api/mcp/config",
            headers=headers,
        )

        assert response.status_code == 403
        assert "platform admin" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_delete_config_success_for_platform_admin(self):
        """Should return 200 for platform admin on DELETE."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.delete(
            f"{TEST_API_URL}/api/mcp/config",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data


# ==================== MCP Tools Endpoint Tests ====================


class TestMCPToolsEndpoint:
    """Tests for /api/mcp/tools endpoint access control."""

    @pytest.mark.integration
    def test_list_tools_requires_auth(self):
        """Should return 401 when no auth provided."""
        response = requests.get(f"{TEST_API_URL}/api/mcp/tools")

        assert response.status_code == 401

    @pytest.mark.integration
    def test_list_tools_requires_platform_admin(self):
        """Should return 403 for non-admin user."""
        token = create_test_jwt(
            email="user@org.local",
            is_superuser=False,
        )
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/tools",
            headers=headers,
        )

        assert response.status_code == 403
        assert "platform admin" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_list_tools_success_for_platform_admin(self):
        """Should return 200 for platform admin."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/tools",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)

    @pytest.mark.integration
    def test_list_tools_returns_all_system_tools(self):
        """Should return all available system tools."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/tools",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        tools = data["tools"]

        # Expected system tool IDs
        expected_tools = [
            "execute_workflow",
            "list_workflows",
            "list_integrations",
            "list_forms",
            "get_form_schema",
            "validate_form_schema",
            "search_knowledge",
        ]

        tool_ids = [t["id"] for t in tools]
        for expected_id in expected_tools:
            assert expected_id in tool_ids, f"Missing tool: {expected_id}"

    @pytest.mark.integration
    def test_list_tools_returns_tool_info(self):
        """Should return complete tool info for each tool."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/tools",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        tools = data["tools"]

        # Check first tool has required fields
        assert len(tools) > 0
        first_tool = tools[0]
        assert "id" in first_tool
        assert "name" in first_tool
        assert "description" in first_tool
        assert "is_system" in first_tool


# ==================== MCP Status Endpoint Tests ====================


class TestMCPStatusEndpoint:
    """Tests for /api/mcp/status endpoint access control."""

    @pytest.mark.integration
    def test_status_requires_auth(self):
        """Should return 401 when no auth provided."""
        response = requests.get(f"{TEST_API_URL}/api/mcp/status")

        assert response.status_code == 401

    @pytest.mark.integration
    def test_status_requires_platform_admin(self):
        """Should return 403 for non-admin user."""
        token = create_test_jwt(
            email="user@org.local",
            is_superuser=False,
        )
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/status",
            headers=headers,
        )

        assert response.status_code == 403
        assert "platform admin" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_status_success_for_platform_admin(self):
        """Should return 200 for platform admin."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        response = requests.get(
            f"{TEST_API_URL}/api/mcp/status",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "available"
        assert "user_id" in data
        assert "is_platform_admin" in data
        assert "tools_count" in data
        assert "tools" in data


# ==================== Config Whitelist/Blacklist Tests ====================


class TestMCPConfigToolFiltering:
    """Tests for MCP config tool whitelist/blacklist functionality."""

    @pytest.fixture(autouse=True)
    def reset_config(self):
        """Reset MCP config before and after each test."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        # Reset before test
        requests.delete(f"{TEST_API_URL}/api/mcp/config", headers=headers)

        yield

        # Reset after test
        requests.delete(f"{TEST_API_URL}/api/mcp/config", headers=headers)

    @pytest.mark.integration
    def test_config_saves_allowed_tool_ids(self):
        """Should save allowed_tool_ids to config."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        # Save config with allowed tools
        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={
                "enabled": True,
                "require_platform_admin": True,
                "allowed_tool_ids": ["execute_workflow", "list_workflows"],
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed_tool_ids"] == ["execute_workflow", "list_workflows"]

        # Verify it persisted
        response = requests.get(f"{TEST_API_URL}/api/mcp/config", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["allowed_tool_ids"] == ["execute_workflow", "list_workflows"]

    @pytest.mark.integration
    def test_config_saves_blocked_tool_ids(self):
        """Should save blocked_tool_ids to config."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        # Save config with blocked tools
        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={
                "enabled": True,
                "require_platform_admin": True,
                "blocked_tool_ids": ["search_knowledge"],
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["blocked_tool_ids"] == ["search_knowledge"]

        # Verify it persisted
        response = requests.get(f"{TEST_API_URL}/api/mcp/config", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["blocked_tool_ids"] == ["search_knowledge"]

    @pytest.mark.integration
    def test_config_allows_null_for_all_tools(self):
        """Should allow null allowed_tool_ids to mean all tools."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        # Save config with null allowed tools
        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={
                "enabled": True,
                "require_platform_admin": True,
                "allowed_tool_ids": None,
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed_tool_ids"] is None

    @pytest.mark.integration
    def test_config_tracks_configured_by(self):
        """Should track who configured the settings."""
        token = create_test_jwt(email="admin@test.com", is_superuser=True)
        headers = auth_headers(token)

        response = requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={"enabled": True},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_configured"] is True
        assert data["configured_by"] == "admin@test.com"
        assert data["configured_at"] is not None

    @pytest.mark.integration
    def test_delete_resets_to_defaults(self):
        """Should reset to defaults after delete."""
        token = create_test_jwt(is_superuser=True)
        headers = auth_headers(token)

        # First save a custom config
        requests.put(
            f"{TEST_API_URL}/api/mcp/config",
            json={
                "enabled": False,
                "require_platform_admin": False,
                "allowed_tool_ids": ["execute_workflow"],
            },
            headers=headers,
        )

        # Delete it
        response = requests.delete(
            f"{TEST_API_URL}/api/mcp/config",
            headers=headers,
        )
        assert response.status_code == 200

        # Get config should return defaults
        response = requests.get(f"{TEST_API_URL}/api/mcp/config", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True  # Default
        assert data["require_platform_admin"] is True  # Default
        assert data["is_configured"] is False
