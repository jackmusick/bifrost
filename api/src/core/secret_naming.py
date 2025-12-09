"""
Business logic for secret naming and validation.

This module contains pure functions for generating and validating secret names
without any external dependencies (Key Vault, Table Storage, etc.).
All functions are easily testable in isolation.
"""

import re
from uuid import uuid4


# Maximum length for Azure Key Vault secret names
MAX_SECRET_NAME_LENGTH = 127

# Pattern for valid secret name components (alphanumeric, hyphens, underscores)
VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class SecretNamingError(Exception):
    """Base exception for secret naming errors"""
    pass


class SecretNameTooLongError(SecretNamingError):
    """Raised when generated secret name exceeds maximum length"""
    pass


class InvalidSecretComponentError(SecretNamingError):
    """Raised when a secret name component contains invalid characters"""
    pass


def sanitize_scope(scope: str) -> str:
    """
    Sanitize scope value for use in secret names.

    Azure Key Vault requirements:
    - Only alphanumeric characters and dashes
    - Lowercase for consistency

    Args:
        scope: The scope value (org ID or "GLOBAL")

    Returns:
        Sanitized scope suitable for secret names (lowercase, alphanumeric + dashes)

    Examples:
        >>> sanitize_scope("GLOBAL")
        'global'
        >>> sanitize_scope("acme-corp")
        'acme-corp'
        >>> sanitize_scope("org@123")
        'org-123'
    """
    # Convert to lowercase
    sanitized = scope.lower()
    # Replace invalid characters (anything not alphanumeric or dash) with hyphens
    sanitized = re.sub(r"[^a-z0-9-]", "-", sanitized)
    # Remove consecutive hyphens
    sanitized = re.sub(r"-+", "-", sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip("-")
    return sanitized


def sanitize_name_component(component: str) -> str:
    """
    Sanitize a name component (like config key) for use in secret names.

    Azure Key Vault requirements:
    - Only alphanumeric characters and dashes
    - Lowercase for consistency

    Args:
        component: The component to sanitize (e.g., config key)

    Returns:
        Sanitized component suitable for secret names (lowercase, alphanumeric + dashes)

    Examples:
        >>> sanitize_name_component("api_key")
        'api-key'
        >>> sanitize_name_component("my.config.key")
        'my-config-key'
        >>> sanitize_name_component("Testing")
        'testing'
    """
    # Convert to lowercase
    sanitized = component.lower()
    # Replace invalid characters (anything not alphanumeric or dash) with hyphens
    sanitized = re.sub(r"[^a-z0-9-]", "-", sanitized)
    # Remove consecutive hyphens
    sanitized = re.sub(r"-+", "-", sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip("-")
    return sanitized


def generate_secret_name(scope: str, name_component: str, prefix: str = "bifrost") -> str:
    """
    Generate a secret name following the bifrost-{scope}-{component}-{uuid} convention.

    Azure Key Vault requirements:
    - Only alphanumeric characters and dashes
    - All lowercase

    Args:
        scope: The scope (org ID or "GLOBAL")
        name_component: The name component (e.g., config key, oauth connection name)
        prefix: The prefix to use (default: "bifrost")

    Returns:
        Generated secret name (lowercase, alphanumeric + dashes only)

    Raises:
        SecretNameTooLongError: If the generated name exceeds MAX_SECRET_NAME_LENGTH
        InvalidSecretComponentError: If any component contains invalid characters after sanitization

    Examples:
        >>> name = generate_secret_name("GLOBAL", "smtp_password")
        >>> name.startswith("bifrost-global-smtp-password-")
        True
        >>> len(name) <= 127
        True
    """
    # Sanitize components (converts to lowercase and replaces invalid chars)
    clean_scope = sanitize_scope(scope)
    clean_component = sanitize_name_component(name_component)
    clean_prefix = prefix.lower()

    # Validate components are not empty after sanitization
    if not clean_scope:
        raise InvalidSecretComponentError(f"Scope '{scope}' contains only invalid characters")
    if not clean_component:
        raise InvalidSecretComponentError(f"Name component '{name_component}' contains only invalid characters")

    # Generate UUID suffix
    uuid_suffix = str(uuid4())

    # Build the name with dashes (Azure Key Vault requirement)
    secret_name = f"{clean_prefix}-{clean_scope}-{clean_component}-{uuid_suffix}"

    # Validate total length
    if len(secret_name) > MAX_SECRET_NAME_LENGTH:
        raise SecretNameTooLongError(
            f"Generated secret name is {len(secret_name)} characters, "
            f"exceeds maximum of {MAX_SECRET_NAME_LENGTH}. "
            f"Try using shorter scope or component names."
        )

    return secret_name


def generate_oauth_secret_name(scope: str, connection_name: str, secret_type: str) -> str:
    """
    Generate an OAuth secret name following the bifrost-{scope}-oauth-{connection}-{type}-{uuid} convention.

    Azure Key Vault requirements:
    - Only alphanumeric characters and dashes
    - All lowercase

    Args:
        scope: The scope (org ID or "GLOBAL")
        connection_name: The OAuth connection name
        secret_type: The type of OAuth secret ("client-secret", "response", etc.)

    Returns:
        Generated OAuth secret name (lowercase, alphanumeric + dashes only)

    Raises:
        SecretNameTooLongError: If the generated name exceeds MAX_SECRET_NAME_LENGTH
        InvalidSecretComponentError: If any component contains invalid characters

    Examples:
        >>> name = generate_oauth_secret_name("acme-corp", "github", "client-secret")
        >>> name.startswith("bifrost-acme-corp-oauth-github-client-secret-")
        True
    """
    # Sanitize components (converts to lowercase and replaces invalid chars)
    clean_scope = sanitize_scope(scope)
    clean_connection = sanitize_name_component(connection_name)
    clean_type = sanitize_name_component(secret_type)

    # Validate components
    if not clean_scope:
        raise InvalidSecretComponentError(f"Scope '{scope}' contains only invalid characters")
    if not clean_connection:
        raise InvalidSecretComponentError(f"Connection name '{connection_name}' contains only invalid characters")
    if not clean_type:
        raise InvalidSecretComponentError(f"Secret type '{secret_type}' contains only invalid characters")

    # Generate UUID suffix
    uuid_suffix = str(uuid4())

    # Build the name with dashes (Azure Key Vault requirement)
    secret_name = f"bifrost-{clean_scope}-oauth-{clean_connection}-{clean_type}-{uuid_suffix}"

    # Validate total length
    if len(secret_name) > MAX_SECRET_NAME_LENGTH:
        raise SecretNameTooLongError(
            f"Generated OAuth secret name is {len(secret_name)} characters, "
            f"exceeds maximum of {MAX_SECRET_NAME_LENGTH}. "
            f"Try using shorter scope, connection, or type names."
        )

    return secret_name


def is_secret_reference(value: str) -> bool:
    """
    Check if a value looks like a secret reference (existing secret name).

    A secret reference should follow one of these patterns:
    - bifrost-{scope}-{component}-{uuid} (current format)
    - {org_id}--{secret-key} (legacy format)

    Args:
        value: The value to check

    Returns:
        True if the value looks like a secret reference, False otherwise

    Examples:
        >>> is_secret_reference("bifrost-global-api-key-a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        True
        >>> is_secret_reference("org-123--my-secret")
        True
        >>> is_secret_reference("my-actual-secret-value")
        False
        >>> is_secret_reference("just-some-password-123")
        False
    """
    # Check for new bifrost format with UUID (dash-separated)
    if value.startswith("bifrost-"):
        # Should have at least 4 parts: bifrost, scope, component, uuid
        # Split on dash but exclude the dashes within the UUID
        parts = value.split("-")
        if len(parts) >= 9:  # bifrost-scope-component-uuid (uuid has 4 dashes)
            # Last 5 parts form the UUID (8-4-4-4-12 format becomes 5 parts when split on -)
            # Reconstruct UUID from last 5 parts
            if len(parts) >= 5:
                uuid_parts = parts[-5:]
                uuid_candidate = "-".join(uuid_parts)
                # UUID format: 8-4-4-4-12 characters
                uuid_pattern = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
                return bool(uuid_pattern.match(uuid_candidate))

    # Check for legacy format: {org_id}--{secret-key}
    if "--" in value:
        parts = value.split("--")
        if len(parts) == 2:
            org_part, key_part = parts
            # Both parts should contain only valid characters
            return bool(VALID_NAME_PATTERN.match(org_part) and VALID_NAME_PATTERN.match(key_part))

    return False


