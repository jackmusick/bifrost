"""
Coding Mode Service

Provides a conversational coding experience for platform admins to develop
Bifrost workflows using Claude Agent SDK.

Usage:
    from src.services.coding_mode import CodingModeClient

    client = CodingModeClient(user=current_user)
    async for chunk in client.chat("Create a workflow that syncs tickets"):
        yield chunk
"""

from src.services.coding_mode.client import CodingModeClient
from src.services.coding_mode.models import CodingModeChunk, CodingModeSession

__all__ = ["CodingModeClient", "CodingModeChunk", "CodingModeSession"]
