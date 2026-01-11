"""
Workflow API Key Authentication Utilities

Provides utilities for generating workflow API keys.
Validation and management functions are in src/routers/workflow_keys.py.
"""

import hashlib
import secrets


def generate_workflow_key() -> tuple[str, str]:
    """
    Generate a cryptographically secure workflow API key.

    Returns:
        Tuple of (raw_key, hashed_key) for storage in workflows.api_key_hash
    """
    # Generate a secure, URL-safe token
    raw_key = secrets.token_urlsafe(32)

    # Hash the key for secure storage
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()

    return raw_key, hashed_key
