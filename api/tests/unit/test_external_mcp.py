"""ORM relationship and round-trip tests for the external MCP client tables.

Touches the live test database via ``db_session`` so the migration's FK + ON
DELETE / ON UPDATE behavior is actually exercised, not just the Python
relationship() declarations.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.orm.external_mcp import (
    MCPConnection,
    MCPConnectionTool,
    MCPServer,
    UserMCPCredential,
)
from src.models.orm.oauth import OAuthProvider, OAuthToken
from src.models.orm.organizations import Organization


@pytest.mark.asyncio
async def test_mcp_server_connection_tool_relationships(
    db_session, seed_user
):
    """Create a server + connection + tool, assert all relationships traverse."""
    org = Organization(
        id=uuid4(),
        name=f"mcp-test-org-{uuid4().hex[:8]}",
        is_active=True,
        created_by="test@example.com",
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        id=uuid4(),
        name=f"test-mcp-server-{uuid4().hex[:8]}",
        server_url="https://example.com/mcp",
        organization_id=None,
        is_active=True,
    )
    db_session.add(server)
    await db_session.flush()

    connection = MCPConnection(
        id=uuid4(),
        server_id=server.id,
        organization_id=org.id,
        client_id="test-client",
        encrypted_client_secret="encrypted-blob",
        available_in_chat=True,
        available_to_autonomous=False,
    )
    db_session.add(connection)
    await db_session.flush()

    tool = MCPConnectionTool(
        id=uuid4(),
        connection_id=connection.id,
        tool_name="search",
        tool_schema={"type": "object", "properties": {}},
        enabled=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db_session.add(tool)
    await db_session.flush()

    # Reload server with eager-loaded connections + tools and verify the
    # full graph hangs together.
    result = await db_session.execute(
        select(MCPServer)
        .where(MCPServer.id == server.id)
        .options(selectinload(MCPServer.connections).selectinload(MCPConnection.tools))
    )
    reloaded = result.scalar_one()
    assert len(reloaded.connections) == 1
    loaded_conn = reloaded.connections[0]
    assert loaded_conn.id == connection.id
    assert len(loaded_conn.tools) == 1
    assert loaded_conn.tools[0].tool_name == "search"
    # Reverse direction: connection.server back-populates
    assert loaded_conn.server.id == server.id


@pytest.mark.asyncio
async def test_user_mcp_credential_relationships(db_session, seed_user):
    """Create a user credential row and verify FKs to user / connection / token."""
    org = Organization(
        id=uuid4(),
        name=f"mcp-cred-org-{uuid4().hex[:8]}",
        is_active=True,
        created_by="test@example.com",
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        id=uuid4(),
        name=f"cred-mcp-server-{uuid4().hex[:8]}",
        server_url="https://example.com/mcp",
        is_active=True,
    )
    db_session.add(server)
    await db_session.flush()

    provider = OAuthProvider(
        id=uuid4(),
        provider_name=f"mcp-provider-{uuid4().hex[:8]}",
        oauth_flow_type="authorization_code",
        client_id="client-id",
        encrypted_client_secret=b"x",
        token_url="https://example.com/token",
    )
    db_session.add(provider)
    await db_session.flush()

    connection = MCPConnection(
        id=uuid4(),
        server_id=server.id,
        organization_id=org.id,
        client_id="conn-client",
        encrypted_client_secret="encrypted-blob",
    )
    db_session.add(connection)
    await db_session.flush()

    token = OAuthToken(
        id=uuid4(),
        provider_id=provider.id,
        user_id=seed_user.id,
        encrypted_access_token=b"access",
        scopes=["read"],
    )
    db_session.add(token)
    await db_session.flush()

    cred = UserMCPCredential(
        id=uuid4(),
        user_id=seed_user.id,
        connection_id=connection.id,
        oauth_token_id=token.id,
        consent_granted_at=datetime.now(timezone.utc),
        granted_scopes=["read", "offline_access"],
    )
    db_session.add(cred)
    await db_session.flush()

    result = await db_session.execute(
        select(UserMCPCredential).where(UserMCPCredential.id == cred.id)
    )
    reloaded = result.scalar_one()
    assert reloaded.user.id == seed_user.id
    assert reloaded.connection.id == connection.id
    assert reloaded.oauth_token.id == token.id
    assert reloaded.granted_scopes == ["read", "offline_access"]


@pytest.mark.asyncio
async def test_mcp_connection_unique_per_server_and_org(db_session):
    """The (server_id, organization_id) unique constraint blocks duplicates."""
    from sqlalchemy.exc import IntegrityError

    org = Organization(
        id=uuid4(),
        name=f"mcp-unique-org-{uuid4().hex[:8]}",
        is_active=True,
        created_by="test@example.com",
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        id=uuid4(),
        name=f"unique-mcp-server-{uuid4().hex[:8]}",
        server_url="https://example.com/mcp",
        is_active=True,
    )
    db_session.add(server)
    await db_session.flush()

    db_session.add(MCPConnection(
        id=uuid4(),
        server_id=server.id,
        organization_id=org.id,
        client_id="first",
        encrypted_client_secret="enc",
    ))
    await db_session.flush()

    db_session.add(MCPConnection(
        id=uuid4(),
        server_id=server.id,
        organization_id=org.id,
        client_id="second",
        encrypted_client_secret="enc",
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()
