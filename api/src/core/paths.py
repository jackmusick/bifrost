"""
Purpose-specific path constants.

Each service that needs local filesystem access gets its own dedicated path.
This avoids coupling between services and makes dependencies explicit.

Python modules are loaded from Redis via virtual imports, NOT from filesystem.
"""

import tempfile
import uuid
from pathlib import Path

# =============================================================================
# Purpose-Specific Paths
# =============================================================================
# Each service gets its own directory. These are created on-demand by the
# services that use them, not pre-created.

# Git operations (clone, commit, push) - persistent across operations
GIT_WORKSPACE_PATH = Path("/tmp/bifrost/git")

# Coding agent scratch space - for Claude SDK's bash/file tools
CODING_AGENT_PATH = Path("/tmp/bifrost/coding-agent")

# Temp files during workflow execution (SDK file operations)
TEMP_PATH = Path("/tmp/bifrost/temp")

# Files uploaded via form file fields
UPLOADS_PATH = Path("/tmp/bifrost/uploads")




# =============================================================================
# Ephemeral Temp Directories
# =============================================================================
# For operations that need isolated, throwaway directories


def create_ephemeral_temp_dir(prefix: str = "bifrost-") -> Path:
    """
    Create a unique temporary directory for isolated operations.

    Use this for operations that need their own sandbox and should be
    cleaned up after use (e.g., package installation, one-off scripts).

    Args:
        prefix: Prefix for the directory name

    Returns:
        Path to the created directory
    """
    return Path(tempfile.mkdtemp(prefix=prefix))


def create_session_temp_dir(session_id: str | None = None) -> Path:
    """
    Create a session-specific temporary directory.

    Args:
        session_id: Optional session ID. If not provided, generates a UUID.

    Returns:
        Path to the created directory
    """
    sid = session_id or str(uuid.uuid4())
    path = Path(f"/tmp/bifrost/sessions/{sid}")
    path.mkdir(parents=True, exist_ok=True)
    return path
