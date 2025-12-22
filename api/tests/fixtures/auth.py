"""
Test authentication helpers for integration tests.

Provides JWT token generation and HTTP header helpers for testing
authenticated endpoints with real HTTP requests to the FastAPI server.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import jwt


# Test environment JWT settings (must match src/config.py defaults and tests/conftest.py)
TEST_SECRET_KEY = "test-secret-key-for-testing-must-be-32-chars"
TEST_JWT_ISSUER = "bifrost-api"
TEST_JWT_AUDIENCE = "bifrost-client"
TEST_ALGORITHM = "HS256"

# Default test user UUIDs (stable for consistent testing)
DEFAULT_USER_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_ADMIN_ID = "00000000-0000-4000-8000-000000000099"


def create_test_jwt(
    user_id: str | None = None,
    email: str = "test@example.com",
    name: str = "Test User",
    is_superuser: bool = False,
) -> str:
    """
    Create test JWT token for authentication.

    Uses the same secret key, issuer, and audience as the test environment
    configured in tests/conftest.py and src/config.py.

    Args:
        user_id: User OID (object ID) - typically a UUID
        email: User email address
        name: User display name
        is_superuser: Whether user should have superuser/platform admin privileges

    Returns:
        str: JWT token signed with test secret

    Example:
        >>> token = create_test_jwt(email="john@acme.com", name="John Doe")
        >>> headers = auth_headers(token)
        >>> response = requests.get("/api/organizations", headers=headers)
    """
    # Use default UUID if not provided (sub must be a valid UUID for auth middleware)
    if user_id is None:
        user_id = DEFAULT_ADMIN_ID if is_superuser else DEFAULT_USER_ID

    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "user_type": "PLATFORM" if is_superuser else "ORG",
        "is_superuser": is_superuser,
        "exp": datetime.utcnow() + timedelta(hours=2),
        "iat": datetime.utcnow(),
        "iss": TEST_JWT_ISSUER,
        "aud": TEST_JWT_AUDIENCE,
        "type": "access",
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)


def create_superuser_jwt(
    user_id: str = "test-platform-admin-123",
    email: str = "admin@platform.com",
    name: str = "Platform Admin"
) -> str:
    """
    Create test JWT token for superuser/platform admin.

    Convenience function for creating superuser tokens.

    Args:
        user_id: User OID (object ID)
        email: User email address
        name: User display name

    Returns:
        str: JWT token with superuser privileges

    Example:
        >>> token = create_superuser_jwt(email="admin@platform.com")
        >>> headers = auth_headers(token)
    """
    return create_test_jwt(
        user_id=user_id,
        email=email,
        name=name,
        is_superuser=True,
    )


def auth_headers(token: str) -> dict[str, str]:
    """
    Create authorization headers with JWT token.

    Args:
        token: JWT token from create_test_jwt()

    Returns:
        dict: Headers with Authorization bearer token

    Example:
        >>> token = create_test_jwt(email="user@test.com")
        >>> headers = auth_headers(token)
        >>> response = requests.get(url, headers=headers)
    """
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def org_headers(org_id: str, token: str) -> dict[str, str]:
    """
    Create headers with organization context and authentication.

    Args:
        org_id: Organization ID
        token: JWT token from create_test_jwt()

    Returns:
        dict: Headers with auth + organization context

    Example:
        >>> token = create_test_jwt(email="user@acme.com")
        >>> headers = org_headers("org-123", token)
        >>> response = requests.post(url, json={...}, headers=headers)
    """
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-Id": org_id,
        "Content-Type": "application/json",
    }
