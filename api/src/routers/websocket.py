"""
WebSocket Router

Provides real-time updates via WebSocket connections.
Replaces Azure Web PubSub with native FastAPI WebSockets.
"""

import asyncio
import logging
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth import UserPrincipal, get_current_user_ws
from src.core.database import get_db_context
from src.core.pubsub import manager
from src.models import Conversation, Execution
from src.models.orm import Agent

logger = logging.getLogger(__name__)


async def can_access_conversation(user: UserPrincipal, conversation_id: str) -> tuple[bool, Conversation | None]:
    """
    Check if user can access a conversation.

    Args:
        user: The authenticated user
        conversation_id: The conversation ID to check access for

    Returns:
        Tuple of (has_access, conversation_object)
    """
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        return False, None

    async with get_db_context() as db:
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.agent).selectinload(Agent.tools),
                selectinload(Conversation.agent).selectinload(Agent.delegated_agents),
                selectinload(Conversation.user),
            )
            .where(Conversation.id == conv_uuid)
            .where(Conversation.user_id == user.user_id)
            .where(Conversation.is_active.is_(True))
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return False, None

        return True, conversation


async def can_access_execution(user: UserPrincipal, execution_id: str) -> bool:
    """
    Check if user can access an execution (owner or superuser).

    Args:
        user: The authenticated user
        execution_id: The execution ID to check access for

    Returns:
        True if user can access, False otherwise
    """
    # Superusers can access any execution
    if user.is_superuser:
        return True

    try:
        execution_uuid = UUID(execution_id)
    except ValueError:
        return False

    async with get_db_context() as db:
        result = await db.execute(
            select(Execution.executed_by).where(Execution.id == execution_uuid)
        )
        row = result.scalar_one_or_none()

        if row is None:
            # Execution doesn't exist - allow subscription anyway
            # (they won't receive anything, and this avoids timing attacks)
            return True

        return row == user.user_id

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/connect")
async def websocket_connect(
    websocket: WebSocket,
    channels: Annotated[list[str], Query()] = [],
):
    """
    WebSocket endpoint for real-time updates.

    Connect and subscribe to channels:
    - execution:{execution_id} - Execution updates and logs
    - user:{user_id} - User notifications
    - system - System broadcasts

    Query params:
        channels: List of channels to subscribe to

    Example:
        ws://localhost:8000/ws/connect?channels=execution:abc-123&channels=user:user-456

    Messages are JSON with structure:
        {
            "type": "execution_update" | "execution_log" | "notification" | "system_event",
            ...payload
        }
    """
    # Authenticate via header (query params not supported for security)
    user = await get_current_user_ws(websocket)

    if not user:
        # Must accept before closing, otherwise client sees HTTP 403
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Filter channels - users can only subscribe to their own user channel
    # and execution channels (we'll validate execution access separately)
    allowed_channels = []
    for channel in channels:
        if channel.startswith("user:"):
            # Users can only subscribe to their own notifications
            if channel == f"user:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("execution:"):
            # Validate user has access to this execution
            execution_id = channel.split(":", 1)[1]
            if await can_access_execution(user, execution_id):
                allowed_channels.append(channel)
        elif channel.startswith("package:"):
            # Package installation channels - users can subscribe to their own
            if channel == f"package:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("git:"):
            # Git operation channels - users can subscribe to their own
            if channel == f"git:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("notification:"):
            # Notification channels - users can subscribe to their own
            if channel == f"notification:{user.user_id}":
                allowed_channels.append(channel)
            # Platform admins can subscribe to admin notifications
            elif channel == "notification:admins" and user.is_superuser:
                allowed_channels.append(channel)
        elif channel.startswith("chat:"):
            # Chat conversation channels - validate user owns the conversation
            conversation_id = channel.split(":", 1)[1]
            has_access, _ = await can_access_conversation(user, conversation_id)
            if has_access:
                allowed_channels.append(channel)
        elif channel.startswith("history:"):
            # History channels for real-time updates
            allowed_channels.append(channel)
        elif channel.startswith("local-runner:"):
            # Local runner channels - users can subscribe to their own
            if channel == f"local-runner:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("devrun:"):
            # Legacy dev run channels - users can subscribe to their own
            if channel == f"devrun:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("cli-session:"):
            # CLI session channels - allow all (session ownership validated elsewhere)
            allowed_channels.append(channel)
        elif channel.startswith("cli-sessions:"):
            # CLI sessions list channel - users can subscribe to their own
            if channel == f"cli-sessions:{user.user_id}":
                allowed_channels.append(channel)
        elif channel.startswith("event-source:"):
            # Event source channels for real-time event updates
            # Platform admins can view all, org users can view their org's sources
            # Access is validated on event delivery, so we allow subscription
            allowed_channels.append(channel)
        elif channel == "system":
            allowed_channels.append(channel)

    # Always subscribe to user's own channel
    user_channel = f"user:{user.user_id}"
    if user_channel not in allowed_channels:
        allowed_channels.append(user_channel)

    try:
        await manager.connect(websocket, allowed_channels)
        logger.info(f"WebSocket connected for user {user.user_id}, channels: {allowed_channels}")

        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "channels": allowed_channels,
            "userId": str(user.user_id)
        })

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_json()

            # Handle subscription changes
            if data.get("type") == "subscribe":
                new_channels = data.get("channels", [])
                for channel in new_channels:
                    # Validate and add subscription
                    if channel.startswith("execution:"):
                        # Validate execution access before subscribing
                        execution_id = channel.split(":", 1)[1]
                        if not await can_access_execution(user, execution_id):
                            await websocket.send_json({
                                "type": "error",
                                "channel": channel,
                                "message": "Access denied"
                            })
                            continue
                        if channel not in manager.connections:
                            manager.connections[channel] = set()
                        manager.connections[channel].add(websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "channel": channel
                        })
                    elif channel.startswith("cli-session:"):
                        if channel not in manager.connections:
                            manager.connections[channel] = set()
                        manager.connections[channel].add(websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "channel": channel
                        })
                    elif channel.startswith("event-source:"):
                        # Event source channels for real-time event updates
                        if channel not in manager.connections:
                            manager.connections[channel] = set()
                        manager.connections[channel].add(websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "channel": channel
                        })

            elif data.get("type") == "unsubscribe":
                channel = data.get("channel")
                if channel and channel in manager.connections:
                    manager.connections[channel].discard(websocket)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "channel": channel
                    })

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "chat":
                # Handle chat message - process and stream response
                conversation_id = data.get("conversation_id")
                message_text = data.get("message", "")

                if not conversation_id or not message_text:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Missing conversation_id or message"
                    })
                    continue

                # Validate access and get conversation
                has_access, conversation = await can_access_conversation(user, conversation_id)
                if not has_access or not conversation:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Conversation not found or access denied"
                    })
                    continue

                # Process chat message in background task
                asyncio.create_task(
                    _process_chat_message(
                        websocket=websocket,
                        user=user,
                        conversation_id=conversation_id,
                        message=message_text,
                    )
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected for user {user.user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/execution/{execution_id}")
async def websocket_execution(
    websocket: WebSocket,
    execution_id: str,
):
    """
    Convenience endpoint for subscribing to a single execution.

    Equivalent to connecting with channels=execution:{execution_id}
    """
    user = await get_current_user_ws(websocket)

    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Validate user has access to this execution
    if not await can_access_execution(user, execution_id):
        await websocket.close(code=4003, reason="Access denied")
        return

    channel = f"execution:{execution_id}"

    try:
        await manager.connect(websocket, [channel])
        logger.info(f"WebSocket connected to execution {execution_id}")

        await websocket.send_json({
            "type": "connected",
            "executionId": execution_id
        })

        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def _generate_conversation_title(
    db,
    conversation: Conversation,
    user_message: str,
) -> str | None:
    """
    Generate a concise title for a conversation using LLM.

    Returns the generated title or None if generation fails.
    """
    from src.services.llm import get_llm_client, LLMMessage

    try:
        llm_client = await get_llm_client(db)

        # Use a simple prompt to generate a title
        response = await llm_client.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content="Generate a very short, concise title (3-6 words max) for a conversation that starts with the following message. Respond with ONLY the title, no quotes or punctuation at the end.",
                ),
                LLMMessage(
                    role="user",
                    content=user_message,
                ),
            ],
            max_tokens=30,
            temperature=0.7,
        )

        if response.content:
            # Clean up the title - remove quotes, limit length
            title = response.content.strip().strip('"\'')
            # Truncate if too long (max 100 chars)
            if len(title) > 100:
                title = title[:97] + "..."
            return title

    except Exception as e:
        logger.warning(f"Failed to generate conversation title: {e}")

    return None


async def _process_chat_message(
    websocket: WebSocket,
    user: UserPrincipal,
    conversation_id: str,
    message: str,
) -> None:
    """
    Process a chat message and stream the response.

    Sends streaming chunks directly to the WebSocket, then broadcasts
    the final message to the chat channel for any other subscribers.

    Routes to coding mode (Claude Agent SDK) if the agent has is_coding_mode=True.

    Args:
        websocket: The WebSocket connection
        user: The authenticated user
        conversation_id: The conversation ID
        message: The user's message
    """
    from src.services.agent_executor import AgentExecutor

    try:
        async with get_db_context() as db:
            # Re-fetch conversation with fresh session
            conv_uuid = UUID(conversation_id)
            result = await db.execute(
                select(Conversation)
                .options(
                    selectinload(Conversation.agent).selectinload(Agent.tools),
                    selectinload(Conversation.agent).selectinload(Agent.delegated_agents),
                    selectinload(Conversation.user),
                )
                .where(Conversation.id == conv_uuid)
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await websocket.send_json({
                    "type": "error",
                    "conversation_id": conversation_id,
                    "error": "Conversation not found"
                })
                return

            # Route to coding mode if agent has is_coding_mode=True
            if conversation.agent and conversation.agent.is_coding_mode:
                # Coding mode requires platform admin
                if not user.is_superuser:
                    await websocket.send_json({
                        "type": "error",
                        "conversation_id": conversation_id,
                        "error": "Coding mode requires platform admin access"
                    })
                    return

                await _process_coding_mode_message(
                    websocket=websocket,
                    db=db,
                    user=user,
                    conversation_id=conversation_id,
                    conversation=conversation,
                    message=message,
                )
                return

            # Check if conversation needs a title (no title set yet)
            needs_title = conversation.title is None

            # Execute chat
            executor = AgentExecutor(db)

            async for chunk in executor.chat(
                agent=conversation.agent,
                conversation=conversation,
                user_message=message,
                stream=True,
                is_platform_admin=user.is_superuser,
            ):
                # Check if we need to switch to coding mode
                if chunk.type == "coding_mode_required":
                    # Send agent switch event, then process via coding mode
                    chunk_data = chunk.model_dump(exclude_none=True)
                    chunk_data["conversation_id"] = conversation_id
                    await websocket.send_json(chunk_data)

                    # Re-route to coding mode handler
                    await _process_coding_mode_message(
                        websocket=websocket,
                        db=db,
                        user=user,
                        conversation_id=conversation_id,
                        conversation=conversation,
                        message=message,
                    )
                    return  # Coding mode handles its own commit

                # Send chunk to WebSocket with conversation_id for client routing
                chunk_data = chunk.model_dump(exclude_none=True)
                chunk_data["conversation_id"] = conversation_id
                await websocket.send_json(chunk_data)

            # Generate title if this is a new conversation (no title yet)
            if needs_title:
                title = await _generate_conversation_title(db, conversation, message)
                if title:
                    conversation.title = title
                    # Send title update to client
                    await websocket.send_json({
                        "type": "title_update",
                        "conversation_id": conversation_id,
                        "title": title,
                    })

            # Commit the transaction
            await db.commit()

    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "conversation_id": conversation_id,
                "error": str(e)
            })
        except Exception:
            pass  # WebSocket may be closed


# Cache of coding mode clients by conversation_id for session continuity
_coding_clients: dict[str, Any] = {}


async def _get_or_create_coding_client(
    conversation_id: str,
    user: UserPrincipal,
    api_key: str,
    model: str,
    system_tools: list[str] | None = None,
    knowledge_sources: list[str] | None = None,
) -> Any:
    """
    Get or create a coding mode client for a conversation.

    Caches clients by conversation_id to maintain conversation context
    across multiple chat() calls within the same session.

    Args:
        conversation_id: The conversation ID (used as cache key)
        user: The authenticated user
        api_key: Anthropic API key
        model: Model to use
        system_tools: List of enabled system tool IDs from the coding agent
        knowledge_sources: List of knowledge namespaces the agent can search

    Returns:
        CodingModeClient instance
    """
    from src.services.coding_mode import CodingModeClient

    if conversation_id not in _coding_clients:
        client = CodingModeClient(
            user_id=user.user_id,
            user_email=user.email or "",
            user_name=user.name or user.email or "User",
            api_key=api_key,
            model=model,
            org_id=user.organization_id,
            is_platform_admin=True,
            session_id=conversation_id,  # Use conversation ID as session ID
            system_tools=system_tools,
            knowledge_sources=knowledge_sources,
        )
        _coding_clients[conversation_id] = client
        logger.info(f"Created new coding client for conversation {conversation_id}")
    else:
        logger.debug(f"Reusing cached coding client for conversation {conversation_id}")

    return _coding_clients[conversation_id]


async def _cleanup_coding_client(conversation_id: str) -> None:
    """
    Clean up a coding mode client when conversation ends.

    Should be called when WebSocket disconnects or conversation is deleted.
    """
    if conversation_id in _coding_clients:
        client = _coding_clients.pop(conversation_id)
        try:
            await client.close()
            logger.info(f"Cleaned up coding client for conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Error cleaning up coding client: {e}")


async def _process_coding_mode_message(
    websocket: WebSocket,
    db: AsyncSession,
    user: UserPrincipal,
    conversation_id: str,
    conversation: Conversation,
    message: str,
) -> None:
    """
    Process a coding mode message using Claude Agent SDK.

    Uses the Bifrost MCP server for workflow development capabilities.
    Persists all messages to database for conversation history.
    """
    from sqlalchemy import func, select

    from src.models.enums import MessageRole
    from src.models.orm import Message
    from src.services.llm.factory import get_coding_mode_config

    async def get_next_sequence() -> int:
        """Get the next sequence number for this conversation."""
        result = await db.execute(
            select(func.coalesce(func.max(Message.sequence), 0))
            .where(Message.conversation_id == conversation.id)
        )
        return (result.scalar() or 0) + 1

    try:
        # Get coding mode config
        coding_config = await get_coding_mode_config(db)
        if not coding_config:
            await websocket.send_json({
                "type": "error",
                "conversation_id": conversation_id,
                "error": "Coding mode not configured. Please configure Anthropic API key in Settings > AI."
            })
            return

        # Get coding agent to retrieve its enabled system_tools and knowledge_sources
        from src.core.system_agents import get_coding_agent

        coding_agent = await get_coding_agent(db)
        system_tools = coding_agent.system_tools if coding_agent else []
        knowledge_sources = coding_agent.knowledge_sources if coding_agent else []

        # Save user message first
        user_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=message,
            sequence=await get_next_sequence(),
        )
        db.add(user_msg)
        await db.flush()

        # Get or create coding mode client from cache
        client = await _get_or_create_coding_client(
            conversation_id=conversation_id,
            user=user,
            api_key=coding_config.api_key,
            model=coding_config.model,
            system_tools=system_tools,
            knowledge_sources=knowledge_sources,
        )

        # Accumulators for message persistence
        accumulated_content = ""
        tool_calls_batch: list[dict] = []  # Collect tool calls for assistant message
        model_used = coding_config.model

        # Stream response from coding mode client
        async for chunk in client.chat(message):
            chunk_type = chunk.type

            if chunk_type == "delta":
                # Accumulate text content
                if chunk.content:
                    accumulated_content += chunk.content

            elif chunk_type == "tool_call" and chunk.tool_call:
                # Generate execution_id for tracking
                tool_execution_id = str(uuid4())

                # Collect tool calls for the assistant message
                tool_calls_batch.append({
                    "id": chunk.tool_call.id,
                    "name": chunk.tool_call.name,
                    "arguments": chunk.tool_call.arguments or {},
                })

                # Send tool_call chunk to client immediately (with execution_id)
                chunk_data = chunk.model_dump(exclude_none=True)
                chunk_data["conversation_id"] = conversation_id
                chunk_data["execution_id"] = tool_execution_id
                await websocket.send_json(chunk_data)

                # Immediately send tool_progress to set status to "running"
                # This enables the frontend to show the tool as actively executing
                await websocket.send_json({
                    "type": "tool_progress",
                    "conversation_id": conversation_id,
                    "tool_progress": {
                        "tool_call_id": chunk.tool_call.id,
                        "execution_id": tool_execution_id,
                        "status": "running",
                    }
                })
                continue  # Skip default send - we already sent it

            elif chunk_type == "tool_result" and chunk.tool_result:
                # If we have accumulated assistant content + tool calls, save as assistant message
                if accumulated_content or tool_calls_batch:
                    assistant_msg = Message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content if accumulated_content else None,
                        tool_calls=tool_calls_batch if tool_calls_batch else None,
                        sequence=await get_next_sequence(),
                        model=model_used,
                    )
                    db.add(assistant_msg)
                    await db.flush()
                    accumulated_content = ""
                    tool_calls_batch = []

                # Save tool result as separate message
                tool_result_msg = Message(
                    conversation_id=conversation.id,
                    role=MessageRole.TOOL,
                    content=str(chunk.tool_result.result) if chunk.tool_result.result else None,
                    tool_call_id=chunk.tool_result.tool_call_id,
                    sequence=await get_next_sequence(),
                )
                db.add(tool_result_msg)
                await db.flush()

            elif chunk_type == "done":
                # Save final assistant message if we have accumulated content
                if accumulated_content or tool_calls_batch:
                    assistant_msg = Message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content if accumulated_content else None,
                        tool_calls=tool_calls_batch if tool_calls_batch else None,
                        token_count_input=chunk.input_tokens,
                        token_count_output=chunk.output_tokens,
                        duration_ms=chunk.duration_ms,
                        sequence=await get_next_sequence(),
                        model=model_used,
                    )
                    db.add(assistant_msg)

                # Commit all messages
                await db.commit()

            # Send chunk to WebSocket with conversation_id for client routing
            chunk_data = chunk.model_dump(exclude_none=True)
            chunk_data["conversation_id"] = conversation_id
            await websocket.send_json(chunk_data)

        # Check if conversation needs a title (no title set yet)
        if conversation.title is None:
            title = await _generate_conversation_title(db, conversation, message)
            if title:
                conversation.title = title
                await db.commit()
                # Send title update to client
                await websocket.send_json({
                    "type": "title_update",
                    "conversation_id": conversation_id,
                    "title": title,
                })

    except Exception as e:
        logger.error(f"Coding mode error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "conversation_id": conversation_id,
            "error": str(e)
        })
