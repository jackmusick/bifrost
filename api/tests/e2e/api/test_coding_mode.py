"""
E2E tests for Coding Mode (Claude Agent SDK integration).

Tests the WebSocket-based coding assistant that helps create Bifrost workflows.
Requires ANTHROPIC_API_TEST_KEY in .env.test.

Uses the unified /ws/connect endpoint with chat:{conversation_id} channel.
"""

import asyncio
import json
import logging
import pytest

logger = logging.getLogger(__name__)


@pytest.mark.e2e
class TestCodingModeE2E:
    """E2E tests for coding mode workflow creation."""

    @pytest.fixture
    def coding_agent(self, e2e_client, platform_admin):
        """Create a coding mode agent."""
        response = e2e_client.post(
            "/api/agents",
            json={
                "name": "E2E Coding Agent",
                "system_prompt": "You are a coding assistant that helps create Bifrost workflows.",
                "is_coding_mode": True,
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 201, f"Failed to create agent: {response.text}"
        agent = response.json()
        yield agent
        # Cleanup
        e2e_client.delete(f"/api/agents/{agent['id']}", headers=platform_admin.headers)

    @pytest.fixture
    def coding_conversation(self, e2e_client, platform_admin, coding_agent):
        """Create a conversation with the coding agent."""
        response = e2e_client.post(
            "/api/chat/conversations",
            json={"agent_id": coding_agent["id"]},
            headers=platform_admin.headers,
        )
        assert response.status_code == 201, f"Failed to create conversation: {response.text}"
        return response.json()

    @pytest.mark.asyncio
    async def test_coding_mode_connection(
        self,
        e2e_ws_url,
        platform_admin,
        coding_conversation,
        llm_anthropic_configured,
    ):
        """Test that coding mode WebSocket connection works via /ws/connect."""
        try:
            from websockets.asyncio.client import connect
        except ImportError:
            pytest.skip("websockets library not installed")

        conversation_id = coding_conversation["id"]
        # Use unified WebSocket endpoint with chat channel subscription
        ws_url = f"{e2e_ws_url}/ws/connect?channels=chat:{conversation_id}"

        try:
            async with connect(
                ws_url,
                additional_headers={"Authorization": f"Bearer {platform_admin.access_token}"},
            ) as ws:
                # Should receive connected message
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)

                assert data["type"] == "connected", f"Expected connected, got: {data}"
                assert "channels" in data, "Missing channels in connected message"
                assert f"chat:{conversation_id}" in data["channels"], f"Chat channel not subscribed: {data}"

                logger.info(f"Connected to WebSocket with channels: {data['channels']}")
        except Exception as e:
            pytest.fail(f"Coding mode connection failed: {e}")

    @pytest.mark.asyncio
    async def test_coding_mode_hello_world(
        self,
        e2e_ws_url,
        platform_admin,
        coding_conversation,
        llm_anthropic_configured,
    ):
        """Test that coding mode can respond to a simple request."""

        try:
            from websockets.asyncio.client import connect
        except ImportError:
            pytest.skip("websockets library not installed")

        conversation_id = coding_conversation["id"]
        # Use unified WebSocket endpoint with chat channel subscription
        ws_url = f"{e2e_ws_url}/ws/connect?channels=chat:{conversation_id}"

        async with connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {platform_admin.access_token}"},
        ) as ws:
            # Should receive connected message
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            assert data["type"] == "connected", f"Expected connected, got: {data}"
            logger.info(f"Connected with channels: {data['channels']}")

            # Send chat message using unified message format
            await ws.send(json.dumps({
                "type": "chat",
                "conversation_id": conversation_id,
                "message": "Create a simple Hello World workflow that returns {'message': 'Hello, World!'}"
            }))
            logger.info("Sent Hello World request")

            # Collect response chunks
            chunks = []
            done = False
            timeout_seconds = 120  # LLM responses can take time

            while not done:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout_seconds)
                    chunk = json.loads(msg)
                    chunks.append(chunk)

                    chunk_type = chunk.get("type")
                    logger.debug(f"Received chunk: {chunk_type}")

                    if chunk_type == "done":
                        done = True
                        logger.info(f"Received done chunk: {chunk}")
                    elif chunk_type == "error":
                        error_msg = chunk.get("error_message") or chunk.get("error")
                        pytest.fail(f"Coding mode error: {error_msg}")
                    elif chunk_type == "delta":
                        # Log content snippets for debugging
                        content = chunk.get("content", "")
                        if content:
                            logger.debug(f"Content: {content[:100]}...")

                except asyncio.TimeoutError:
                    logger.error(f"Timeout after {timeout_seconds}s. Received {len(chunks)} chunks so far.")
                    pytest.fail(f"Timeout waiting for coding mode response after {len(chunks)} chunks")

            # Verify we got content chunks
            content_chunks = [c for c in chunks if c.get("type") == "delta"]
            assert len(content_chunks) > 0, "Expected content from coding mode"

            # Verify done chunk has metrics
            done_chunk = next((c for c in chunks if c.get("type") == "done"), None)
            assert done_chunk is not None, "Missing done chunk"
            assert "duration_ms" in done_chunk, "Done chunk missing duration_ms"

            # Log summary
            total_content = "".join(c.get("content", "") for c in content_chunks)
            logger.info(
                f"Coding mode responded with {len(content_chunks)} content chunks, "
                f"{len(total_content)} chars, duration={done_chunk.get('duration_ms')}ms"
            )
