"""
File management SDK for Bifrost.

Provides async Python API for file operations with two storage modes:
- local: Local filesystem (CWD, /tmp/bifrost/temp, /tmp/bifrost/uploads)
- cloud: S3 storage (default)

Location Options:
- "workspace": Persistent workspace files (CWD in local mode, S3 bucket root in cloud mode)
- "temp": Temporary files (_tmp/ prefix in cloud, /tmp/bifrost/temp in local)
- "uploads": Files uploaded via form file fields (uploads/ prefix in cloud, /tmp/bifrost/uploads in local)

Usage:
    from bifrost import files

    # Write to workspace (cloud mode by default)
    await files.write("exports/report.csv", data)

    # Write to workspace (local mode)
    await files.write("exports/report.csv", data, mode="local")

    # Read from temp location
    content = await files.read("temp-data.txt", location="temp")

    # Read uploaded file
    content = await files.read("form_id/uuid/filename.txt", location="uploads")
"""

from typing import Literal

from .client import get_client, raise_for_status_with_detail
from ._context import resolve_scope

Location = Literal["workspace", "temp", "uploads"]
Mode = Literal["local", "cloud"]


class files:
    """
    File management operations (async).

    Provides safe file access with two storage modes:
    - local: Local filesystem (for CLI usage)
    - cloud: S3 storage (for platform execution, default)

    All operations are performed via HTTP API endpoints.
    """

    @staticmethod
    async def read(
        path: str,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> str:
        """
        Read a text file.

        Args:
            path: File path relative to location root
            location: Storage location (workspace, temp, or uploads)
            mode: Storage mode (local or cloud, default: cloud)

        Returns:
            str: File contents

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> content = await files.read("data/customers.csv")
            >>> uploaded = await files.read("form_id/uuid/file.txt", location="uploads")
        """
        client = get_client()
        response = await client.post(
            "/api/files/read",
            json={"path": path, "location": location, "mode": mode, "binary": False}
        )
        raise_for_status_with_detail(response)
        return response.json()["content"]

    @staticmethod
    async def read_bytes(
        path: str,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> bytes:
        """
        Read a binary file.

        Args:
            path: File path relative to location root
            location: Storage location (workspace, temp, or uploads)
            mode: Storage mode (local or cloud, default: cloud)

        Returns:
            bytes: File contents

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> data = await files.read_bytes("reports/report.pdf")
        """
        client = get_client()
        response = await client.post(
            "/api/files/read",
            json={"path": path, "location": location, "mode": mode, "binary": True}
        )
        raise_for_status_with_detail(response)
        import base64
        return base64.b64decode(response.json()["content"])

    @staticmethod
    async def write(
        path: str,
        content: str,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> None:
        """
        Write text to a file.

        Args:
            path: File path relative to location root
            content: Text content to write
            location: Storage location (workspace or temp)
            mode: Storage mode (local or cloud, default: cloud)

        Raises:
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> await files.write("output/report.txt", "Report data")
        """
        client = get_client()
        response = await client.post(
            "/api/files/write",
            json={"path": path, "content": content, "location": location, "mode": mode, "binary": False}
        )
        raise_for_status_with_detail(response)

    @staticmethod
    async def write_bytes(
        path: str,
        content: bytes,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> None:
        """
        Write binary data to a file.

        Args:
            path: File path relative to location root
            content: Binary content to write
            location: Storage location (workspace or temp)
            mode: Storage mode (local or cloud, default: cloud)

        Raises:
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> await files.write_bytes("uploads/image.png", image_data)
        """
        client = get_client()
        import base64
        encoded_content = base64.b64encode(content).decode('utf-8')
        response = await client.post(
            "/api/files/write",
            json={"path": path, "content": encoded_content, "location": location, "mode": mode, "binary": True}
        )
        raise_for_status_with_detail(response)

    @staticmethod
    async def list(
        directory: str = "",
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> list[str]:
        """
        List files in a directory.

        Args:
            directory: Directory path relative to location root (default: root)
            location: Storage location (workspace or temp)
            mode: Storage mode (local or cloud, default: cloud)

        Returns:
            list[str]: List of file and directory names

        Raises:
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> items = await files.list("uploads")
            >>> for item in items:
            ...     print(item)
        """
        client = get_client()
        response = await client.post(
            "/api/files/list",
            json={"directory": directory, "location": location, "mode": mode}
        )
        raise_for_status_with_detail(response)
        return response.json()["files"]

    @staticmethod
    async def delete(
        path: str,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> None:
        """
        Delete a file.

        Args:
            path: File path relative to location root
            location: Storage location (workspace or temp)
            mode: Storage mode (local or cloud, default: cloud)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> await files.delete("temp/old_file.txt", location="temp")
        """
        client = get_client()
        response = await client.post(
            "/api/files/delete",
            json={"path": path, "location": location, "mode": mode}
        )
        raise_for_status_with_detail(response)

    @staticmethod
    async def exists(
        path: str,
        location: Location = "workspace",
        mode: Mode = "cloud",
    ) -> bool:
        """
        Check if a file exists.

        Args:
            path: File path relative to location root
            location: Storage location (workspace or temp)
            mode: Storage mode (local or cloud, default: cloud)

        Returns:
            bool: True if path exists

        Raises:
            ValueError: If path is outside allowed directories

        Example:
            >>> from bifrost import files
            >>> if await files.exists("data/customers.csv"):
            ...     data = await files.read("data/customers.csv")
        """
        client = get_client()
        response = await client.post(
            "/api/files/exists",
            json={"path": path, "location": location, "mode": mode}
        )
        raise_for_status_with_detail(response)
        return response.json()["exists"]

    @staticmethod
    async def get_signed_url(
        path: str,
        method: Literal["PUT", "GET"] = "PUT",
        content_type: str = "application/octet-stream",
    ) -> dict:
        """
        Generate a presigned S3 URL for direct file upload or download.

        Args:
            path: File path (scoped automatically by org)
            method: "PUT" for upload, "GET" for download
            content_type: MIME type (only used for PUT)

        Returns:
            dict with keys: url, path, expires_in
        """
        client = get_client()
        scope = resolve_scope(None)
        response = await client.post(
            "/api/files/signed-url",
            json={"path": path, "method": method, "content_type": content_type, "scope": scope}
        )
        raise_for_status_with_detail(response)
        return response.json()
