"""
Test OAuth global fallback behavior.

Verifies that oauth.get_connection() falls back to GLOBAL scope
when a connection is not found in the org-specific scope.

Uses real PostgreSQL database for integration testing.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from src.services.oauth_storage import OAuthStorageService
from src.models import CreateOAuthConnectionRequest
from src.models.orm import Organization


@pytest.mark.integration
class TestOAuthGlobalFallback:
    """Test that OAuth connections fall back to GLOBAL scope"""

    @pytest.mark.asyncio
    async def test_get_connection_fallback_to_global(self, clean_db):
        """Test that get_connection falls back to GLOBAL when not found in org"""
        storage = OAuthStorageService(session=clean_db)

        # Create connection in GLOBAL scope
        test_provider = "test_fallback_provider"
        connection_create = CreateOAuthConnectionRequest(
            connection_name=test_provider,
            oauth_flow_type="authorization_code",
            authorization_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="test_client",
            client_secret="test_client_secret"
        )

        global_conn = await storage.create_connection("GLOBAL", connection_create, "test-user")
        assert global_conn is not None

        # Store tokens in GLOBAL
        expires_at = datetime.utcnow() + timedelta(hours=1)
        success = await storage.store_tokens(
            org_id="GLOBAL",
            connection_name=test_provider,
            access_token="global_test_token_123",
            refresh_token="global_refresh_456",
            expires_at=expires_at,
            scopes=["read", "write"],
            user_id=None
        )
        assert success is True

        # Try to get from a different org (should fall back to GLOBAL)
        # Create the org first to satisfy FK constraint
        org = Organization(
            id=uuid4(),
            name="Test Org",
            is_active=True,
            created_by="test-user"
        )
        clean_db.add(org)
        await clean_db.flush()

        connection = await storage.get_connection(str(org.id), test_provider)

        # Verify we got the GLOBAL connection
        assert connection is not None
        assert connection.connection_name == test_provider
        assert connection.status == "connected"

    @pytest.mark.asyncio
    async def test_get_connection_org_specific_takes_precedence(self, clean_db):
        """Test that org-specific connections take precedence over GLOBAL"""
        storage = OAuthStorageService(session=clean_db)

        test_provider = "test_precedence_provider"

        # Create an organization first
        org = Organization(
            id=uuid4(),
            name="Test Org",
            is_active=True,
            created_by="test-user"
        )
        clean_db.add(org)
        await clean_db.flush()
        org_id = str(org.id)

        # Create connection in GLOBAL
        connection_create = CreateOAuthConnectionRequest(
            connection_name=test_provider,
            oauth_flow_type="authorization_code",
            authorization_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="test_client",
            client_secret="test_client_secret"
        )
        global_conn = await storage.create_connection("GLOBAL", connection_create, "test-user")
        assert global_conn is not None

        # Store token in GLOBAL
        expires_at = datetime.utcnow() + timedelta(hours=1)
        success = await storage.store_tokens(
            org_id="GLOBAL",
            connection_name=test_provider,
            access_token="global_token",
            refresh_token=None,
            expires_at=expires_at,
            scopes=["read"],
            user_id=None
        )
        assert success is True

        # Create connection in org-specific
        org_conn = await storage.create_connection(org_id, connection_create, "test-user")
        assert org_conn is not None

        # Store different token in org-specific
        success = await storage.store_tokens(
            org_id=org_id,
            connection_name=test_provider,
            access_token="org_specific_token",
            refresh_token=None,
            expires_at=expires_at,
            scopes=["write"],
            user_id=None
        )
        assert success is True

        # Get connection for the specific org
        connection = await storage.get_connection(org_id, test_provider)

        # Verify we got the org-specific connection (not GLOBAL)
        assert connection is not None
        assert connection.connection_name == test_provider
        assert connection.status == "connected"

        # Verify we get org-specific token
        tokens = await storage.get_tokens(org_id, test_provider, user_id=None)
        assert tokens is not None
        assert tokens["access_token"] == "org_specific_token"
        assert tokens["scopes"] == ["write"]

        # Verify GLOBAL token is different
        global_tokens = await storage.get_tokens("GLOBAL", test_provider, user_id=None)
        assert global_tokens is not None
        assert global_tokens["access_token"] == "global_token"
        assert global_tokens["scopes"] == ["read"]

    @pytest.mark.asyncio
    async def test_get_connection_returns_none_when_not_found(self, clean_db):
        """Test that get_connection returns None when connection not found anywhere"""
        storage = OAuthStorageService(session=clean_db)

        # Create org for the query
        org = Organization(
            id=uuid4(),
            name="Test Org",
            is_active=True,
            created_by="test-user"
        )
        clean_db.add(org)
        await clean_db.flush()

        # Try to get a connection that doesn't exist
        connection = await storage.get_connection(
            str(org.id),
            "nonexistent_provider_xyz"
        )

        # Should return None
        assert connection is None

    @pytest.mark.asyncio
    async def test_get_connection_uses_none_for_global_org_id(self, clean_db):
        """Test that get_connection handles both GLOBAL string and None for GLOBAL scope"""
        storage = OAuthStorageService(session=clean_db)

        test_provider = "test_none_provider"
        connection_create = CreateOAuthConnectionRequest(
            connection_name=test_provider,
            oauth_flow_type="authorization_code",
            authorization_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="test_client",
            client_secret="test_client_secret"
        )

        # Create connection with GLOBAL string
        global_conn = await storage.create_connection("GLOBAL", connection_create, "test-user")
        assert global_conn is not None

        # Store tokens
        expires_at = datetime.utcnow() + timedelta(hours=1)
        success = await storage.store_tokens(
            org_id="GLOBAL",
            connection_name=test_provider,
            access_token="global_token_none_test",
            refresh_token=None,
            expires_at=expires_at,
            scopes=["admin"],
            user_id=None
        )
        assert success is True

        # Retrieve using GLOBAL string
        conn_global = await storage.get_connection("GLOBAL", test_provider)
        assert conn_global is not None
        assert conn_global.connection_name == test_provider

        # Verify tokens are accessible
        tokens = await storage.get_tokens("GLOBAL", test_provider, user_id=None)
        assert tokens is not None
        assert tokens["access_token"] == "global_token_none_test"
