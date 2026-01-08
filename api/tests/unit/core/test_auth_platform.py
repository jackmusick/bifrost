"""
Unit tests for PLATFORM user authentication.

Tests that PLATFORM users (engine, system) can authenticate without org_id,
while regular ORG users still require org_id in their tokens.
"""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials

from src.core.auth import get_current_user_optional
from src.core.security import create_access_token


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock(spec=Request)
    request.cookies = {}
    return request


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


def create_credentials(token: str) -> HTTPAuthorizationCredentials:
    """Create HTTP credentials from a token."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestPlatformUserTokenValidation:
    """Tests for PLATFORM user token handling without org_id."""

    @pytest.mark.asyncio
    async def test_platform_user_without_org_id_is_valid(
        self, mock_request, mock_db
    ):
        """Engine/system token without org_id should authenticate successfully."""
        user_id = str(uuid4())

        # Create token with user_type=PLATFORM but no org_id
        token = create_access_token({
            "sub": user_id,
            "email": "engine@bifrost.internal",
            "name": "Bifrost Engine",
            "user_type": "PLATFORM",
            "is_superuser": True,
            # NO org_id claim
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        assert user is not None
        assert str(user.user_id) == user_id
        assert user.organization_id is None
        assert user.user_type == "PLATFORM"
        assert user.is_superuser is True
        assert user.email == "engine@bifrost.internal"

    @pytest.mark.asyncio
    async def test_platform_user_with_org_id_is_also_valid(
        self, mock_request, mock_db
    ):
        """PLATFORM user with org_id should also work (edge case)."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        # PLATFORM user with org_id (unusual but should work)
        token = create_access_token({
            "sub": user_id,
            "email": "admin@example.com",
            "name": "Platform Admin",
            "user_type": "PLATFORM",
            "is_superuser": True,
            "org_id": org_id,  # Has org_id
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        # PLATFORM users with org_id in token still get organization_id=None
        # because PLATFORM handling is done first
        assert user is not None
        assert user.organization_id is None
        assert user.user_type == "PLATFORM"


class TestOrgUserTokenValidation:
    """Tests for regular ORG user token handling."""

    @pytest.mark.asyncio
    async def test_org_user_without_org_id_is_rejected(
        self, mock_request, mock_db
    ):
        """Regular ORG user token without org_id should be rejected."""
        user_id = str(uuid4())

        # ORG user without org_id
        token = create_access_token({
            "sub": user_id,
            "email": "user@example.com",
            "name": "Regular User",
            "user_type": "ORG",
            # NO org_id claim
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        # Should be rejected (returns None)
        assert user is None

    @pytest.mark.asyncio
    async def test_org_user_with_org_id_is_valid(
        self, mock_request, mock_db
    ):
        """Regular ORG user token with org_id should authenticate."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        token = create_access_token({
            "sub": user_id,
            "email": "user@example.com",
            "name": "Regular User",
            "user_type": "ORG",
            "org_id": org_id,
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        assert user is not None
        assert str(user.user_id) == user_id
        assert str(user.organization_id) == org_id
        assert user.user_type == "ORG"
        assert user.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_org_user_with_invalid_org_id_is_rejected(
        self, mock_request, mock_db
    ):
        """ORG user token with invalid org_id format should be rejected."""
        user_id = str(uuid4())

        token = create_access_token({
            "sub": user_id,
            "email": "user@example.com",
            "name": "Regular User",
            "user_type": "ORG",
            "org_id": "not-a-uuid",
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        assert user is None


class TestDefaultUserType:
    """Tests for default user_type handling."""

    @pytest.mark.asyncio
    async def test_missing_user_type_defaults_to_org(
        self, mock_request, mock_db
    ):
        """Token without user_type should be rejected (missing required claim)."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        # Token missing user_type (but has email)
        token = create_access_token({
            "sub": user_id,
            "email": "user@example.com",
            "name": "User",
            # NO user_type
            "org_id": org_id,
        })

        credentials = create_credentials(token)

        user = await get_current_user_optional(mock_request, credentials, mock_db)

        # Should be rejected because user_type is required
        assert user is None
