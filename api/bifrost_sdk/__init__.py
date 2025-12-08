"""
Bifrost SDK

HTTP client SDK for interacting with Bifrost API.
Enables local development with VS Code debugging support.

Usage:
    # Set environment variables
    export BIFROST_DEV_URL="https://your-bifrost-instance.com"
    export BIFROST_DEV_KEY="bfsk_xxxxxxxxxxxx"

    # Use in workflow
    from bifrost_sdk import files, config, log

    async def my_workflow():
        # Read/write files
        content = await files.read("data/input.json")
        await files.write("data/output.json", result)

        # Get config values
        api_key = config.get("my_api_key")

        # Log messages
        log.info("Processing started")
"""

from bifrost_sdk.client import BifrostClient, get_client
from bifrost_sdk import files
from bifrost_sdk import config
from bifrost_sdk import log

__version__ = "1.0.0"

__all__ = [
    "BifrostClient",
    "get_client",
    "files",
    "config",
    "log",
]
