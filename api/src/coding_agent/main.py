"""
Coding Agent Service - Main Entry Point

Dedicated container for Claude Agent SDK. Runs SDK in isolation so it can
block without affecting API health checks.

Architecture:
- Consumes chat requests from RabbitMQ queue
- Streams response chunks to RabbitMQ exchange (API consumes)
- File operations handled via database-backed virtual imports
"""

import asyncio
import logging
import signal
import sys

from src.coding_agent.consumer import CodingAgentConsumer
from src.core.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class CodingAgent:
    """
    Main coding agent service class.

    Manages lifecycle of:
    - RabbitMQ consumer (chat request processing)
    """

    def __init__(self):
        self._consumer = CodingAgentConsumer()
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start all coding agent services."""
        logger.info("Starting Coding Agent service")

        # 1. Initialize database connection
        logger.info("Initializing database connection...")
        await init_db()

        # 2. Start RabbitMQ consumer for chat requests
        logger.info("Starting RabbitMQ consumer...")
        await self._consumer.start()

        logger.info("Coding Agent service started successfully")

        # 3. Wait for shutdown signal
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop all coding agent services gracefully."""
        logger.info("Stopping Coding Agent service...")

        await self._consumer.stop()

        self._shutdown_event.set()
        logger.info("Coding Agent service stopped")

    def trigger_shutdown(self) -> None:
        """Trigger graceful shutdown (called from signal handlers)."""
        self._shutdown_event.set()


async def main() -> None:
    """Main entry point for coding agent service."""
    agent = CodingAgent()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        agent.trigger_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await agent.start()
    except Exception as e:
        logger.error(f"Coding Agent service failed: {e}", exc_info=True)
        raise
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
