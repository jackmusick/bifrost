"""
Bifrost SDK Files Module

File operations via the Bifrost API.
"""

import base64
from typing import Any

from bifrost_sdk.client import get_client


async def read(path: str) -> str:
    """
    Read file content from workspace.

    Args:
        path: File path relative to workspace root

    Returns:
        File content as string

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()
    response = await client.get("/api/editor/files/content", params={"path": path})
    response.raise_for_status()

    data = response.json()
    content = data["content"]

    # Decode base64 if needed
    if data.get("encoding") == "base64":
        content = base64.b64decode(content).decode("utf-8")

    return content


async def read_bytes(path: str) -> bytes:
    """
    Read file content as bytes.

    Args:
        path: File path relative to workspace root

    Returns:
        File content as bytes

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()
    response = await client.get("/api/editor/files/content", params={"path": path})
    response.raise_for_status()

    data = response.json()
    content = data["content"]

    # Decode based on encoding
    if data.get("encoding") == "base64":
        return base64.b64decode(content)
    else:
        return content.encode("utf-8")


async def write(path: str, content: str | bytes) -> dict[str, Any]:
    """
    Write content to file.

    Args:
        path: File path relative to workspace root
        content: File content (string or bytes)

    Returns:
        File metadata dict

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()

    # Determine encoding
    if isinstance(content, bytes):
        payload = {
            "path": path,
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        }
    else:
        payload = {
            "path": path,
            "content": content,
            "encoding": "utf-8",
        }

    response = await client.put("/api/editor/files/content", json=payload)
    response.raise_for_status()

    return response.json()


async def list(directory: str = "") -> list[dict[str, Any]]:
    """
    List files in directory.

    Args:
        directory: Directory path (empty for root)

    Returns:
        List of file metadata dicts

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()
    response = await client.get("/api/editor/files", params={"path": directory})
    response.raise_for_status()

    return response.json()


async def delete(path: str) -> dict[str, Any]:
    """
    Delete file or folder.

    Args:
        path: File or folder path

    Returns:
        Confirmation message

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()
    response = await client.delete("/api/editor/files", params={"path": path})
    response.raise_for_status()

    return response.json()


async def exists(path: str) -> bool:
    """
    Check if file exists.

    Args:
        path: File path

    Returns:
        True if file exists
    """
    client = get_client()
    try:
        response = await client.get("/api/editor/files/content", params={"path": path})
        return response.status_code == 200
    except Exception:
        return False


# Synchronous versions for convenience


def read_sync(path: str) -> str:
    """Synchronous version of read()."""
    client = get_client()
    response = client.get_sync("/api/editor/files/content", params={"path": path})
    response.raise_for_status()

    data = response.json()
    content = data["content"]

    if data.get("encoding") == "base64":
        content = base64.b64decode(content).decode("utf-8")

    return content


def write_sync(path: str, content: str | bytes) -> dict[str, Any]:
    """Synchronous version of write()."""
    client = get_client()

    if isinstance(content, bytes):
        payload = {
            "path": path,
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        }
    else:
        payload = {
            "path": path,
            "content": content,
            "encoding": "utf-8",
        }

    response = client.post_sync("/api/editor/files/content", json=payload)
    response.raise_for_status()

    return response.json()
