"""
Simple Greeting Workflow

A basic workflow for testing form submission and execution.
"""

import logging

from bifrost import workflow, context

logger = logging.getLogger(__name__)


@workflow(
    name="simple_greeting",
    description="Simple greeting workflow",
    category="testing",
    tags=["test", "greeting"]
)
async def simple_greeting(
    name: str,
    greeting_type: str = "Hello",
    include_timestamp: bool = False
) -> dict:
    """
    Simple greeting workflow that creates a personalized greeting.

    Args:
        name: Name to greet
        greeting_type: Type of greeting (default: "Hello")
        include_timestamp: Whether to include timestamp

    Returns:
        Dictionary with greeting message
    """
    import datetime

    greeting = f"{greeting_type}, {name}!"

    if include_timestamp:
        timestamp = datetime.datetime.utcnow().isoformat()
        greeting += f" (at {timestamp})"

    logger.info(f"Generated greeting: {greeting}")

    return {
        "greeting": greeting,
        "name": name,
        "greeting_type": greeting_type,
        "org_id": context.org_id
    }
