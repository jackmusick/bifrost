"""
WebSocket Router

Provides real-time updates via WebSocket connections.
Replaces Azure Web PubSub with native FastAPI WebSockets.
"""

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
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

            # Check if conversation needs a title (no title set yet)
            needs_title = conversation.title is None

            # Execute chat
            executor = AgentExecutor(db)

            async for chunk in executor.chat(
                agent=conversation.agent,
                conversation=conversation,
                user_message=message,
                stream=True,
            ):
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
