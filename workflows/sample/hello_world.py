from bifrost import workflow
import logging

logger = logging.getLogger(__name__)


@workflow(category="Examples")
async def hello_world(name: str):
    """A simple greeting workflow — says hi from Copilot CLI."""
    logger.info(f"Generating greeting for {name}")
    greeting = f"Hello, {name}! 👋 This workflow was written by GitHub Copilot CLI."
    return {"greeting": greeting, "name": name}
