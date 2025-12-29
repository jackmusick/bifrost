"""
Tests for MCP JSON-RPC protocol endpoint at /mcp.

These tests verify the FastMCP server is properly mounted and accepting
authenticated requests via the JSON-RPC 2.0 protocol.
"""

import os

import pytest
import requests

from tests.fixtures.auth import create_test_jwt

TEST_API_URL = os.getenv("TEST_API_URL", "http://api:8000")

# MCP Streamable HTTP transport requires this Accept header
MCP_ACCEPT_HEADER = "application/json, text/event-stream"


def mcp_headers(token: str) -> dict[str, str]:
    """Create headers for MCP requests with proper Accept header."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": MCP_ACCEPT_HEADER,
    }


@pytest.mark.integration
class TestMCPProtocol:
    """Test MCP JSON-RPC 2.0 protocol endpoint."""

    def test_mcp_requires_auth(self):
        """POST /mcp without auth should return 401."""
        response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": MCP_ACCEPT_HEADER,
            },
        )
        assert response.status_code == 401

    def test_mcp_initialize_success(self):
        """POST /mcp with valid admin token should return initialize response."""
        token = create_test_jwt(is_superuser=True)
        headers = mcp_headers(token)

        response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == 1
        assert "result" in data
        # Verify server info is present
        result = data["result"]
        assert "serverInfo" in result
        assert "protocolVersion" in result

    def test_mcp_list_tools(self):
        """Should be able to list available tools."""
        token = create_test_jwt(is_superuser=True)
        headers = mcp_headers(token)

        # First initialize to get session ID
        init_response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers=headers,
        )
        assert init_response.status_code == 200

        # Get session ID from response header
        session_id = init_response.headers.get("mcp-session-id")
        assert session_id is not None, "MCP session ID should be returned"

        # Then list tools with session ID
        headers["Mcp-Session-Id"] = session_id
        response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "tools" in result
        # Should have some tools available
        tools = result["tools"]
        assert len(tools) > 0
        # Check for expected tool names
        tool_names = [t["name"] for t in tools]
        assert "execute_workflow" in tool_names
        assert "list_workflows" in tool_names

    def test_mcp_non_admin_denied(self):
        """Non-admin users should be denied MCP access by default."""
        # Create non-superuser token
        token = create_test_jwt(is_superuser=False)
        headers = mcp_headers(token)

        response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers=headers,
        )

        # Should be denied - either 401 (invalid token) or 403 (forbidden)
        assert response.status_code in [401, 403]

    def test_mcp_invalid_token_rejected(self):
        """Invalid token should be rejected."""
        headers = {
            "Authorization": "Bearer invalid_token_here",
            "Content-Type": "application/json",
            "Accept": MCP_ACCEPT_HEADER,
        }

        response = requests.post(
            f"{TEST_API_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers=headers,
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestMCPDiscovery:
    """Test MCP OAuth discovery endpoints."""

    def test_oauth_authorization_server_metadata(self):
        """OAuth authorization server metadata should be available."""
        response = requests.get(
            f"{TEST_API_URL}/.well-known/oauth-authorization-server"
        )
        assert response.status_code == 200
        data = response.json()
        assert "issuer" in data
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data

    def test_oauth_protected_resource_metadata(self):
        """OAuth protected resource metadata should be available."""
        response = requests.get(
            f"{TEST_API_URL}/.well-known/oauth-protected-resource/mcp"
        )
        assert response.status_code == 200
        data = response.json()
        assert "resource" in data
        assert "authorization_servers" in data
