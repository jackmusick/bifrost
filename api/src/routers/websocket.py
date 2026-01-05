"""
WebSocket Router

Provides real-time updates via WebSocket connections.
Replaces Azure Web PubSub with native FastAPI WebSockets.
"""

import asyncio
import logging
from typing import Annotated
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
            # history:user:{user_id} - Allow only for the user's own channel
            # history:GLOBAL - Allow only for platform admins
            if channel == f"history:user:{user.user_id}":
                allowed_channels.append(channel)
            elif channel == "history:GLOBAL" and user.is_superuser:
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
        elif channel.startswith("reindex:"):
            # Reindex job progress channels - platform admins only
            if user.is_superuser:
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
                    elif channel.startswith("history:"):
                        # History channels for real-time execution updates
                        # history:user:{user_id} - Allow only for the user's own channel
                        # history:GLOBAL - Allow only for platform admins
                        if channel == f"history:user:{user.user_id}" or (channel == "history:GLOBAL" and user.is_superuser):
                            if channel not in manager.connections:
                                manager.connections[channel] = set()
                            manager.connections[channel].add(websocket)
                            await websocket.send_json({
                                "type": "subscribed",
                                "channel": channel
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "channel": channel,
                                "message": "Access denied"
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

            elif data.get("type") == "chat_answer":
                # Handle user's answer to AskUserQuestion from coding mode
                conversation_id = data.get("conversation_id")
                request_id = data.get("request_id")
                answers = data.get("answers", {})

                if not conversation_id or not request_id:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Missing conversation_id or request_id"
                    })
                    continue

                # Validate access
                has_access, conversation = await can_access_conversation(user, conversation_id)
                if not has_access or not conversation:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Conversation not found or access denied"
                    })
                    continue

                # Publish answer to the coding agent's answer exchange
                await _send_coding_answer(conversation_id, request_id, answers)

            elif data.get("type") == "chat_stop":
                # Handle user's request to stop the current chat operation
                conversation_id = data.get("conversation_id")

                if not conversation_id:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Missing conversation_id"
                    })
                    continue

                # Validate access
                has_access, conversation = await can_access_conversation(user, conversation_id)
                if not has_access or not conversation:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Conversation not found or access denied"
                    })
                    continue

                # Send stop signal to coding agent
                await _send_coding_stop(conversation_id)

            elif data.get("type") == "set_mode":
                # Handle user's request to change coding mode permission mode
                conversation_id = data.get("conversation_id")
                permission_mode = data.get("permission_mode")

                if not conversation_id:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Missing conversation_id"
                    })
                    continue

                if not permission_mode:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Missing permission_mode"
                    })
                    continue

                # Validate permission mode
                if permission_mode not in ("plan", "acceptEdits"):
                    await websocket.send_json({
                        "type": "error",
                        "error": "Invalid permission_mode. Must be 'plan' or 'acceptEdits'"
                    })
                    continue

                # Validate access
                has_access, conversation = await can_access_conversation(user, conversation_id)
                if not has_access or not conversation:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Conversation not found or access denied"
                    })
                    continue

                # Send set_mode command to coding agent
                await _send_coding_set_mode(conversation_id, permission_mode)

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


async def _process_coding_mode_message(
    websocket: WebSocket,
    db: AsyncSession,
    user: UserPrincipal,
    conversation_id: str,
    conversation: Conversation,
    message: str,
) -> None:
    """
    Process a coding mode message via RabbitMQ to the coding-agent container.

    The SDK runs in a dedicated container to avoid blocking the API.

    Flow:
    1. Save user message to database
    2. Publish chat request to RabbitMQ queue
    3. Coding agent container consumes request, runs SDK
    4. Coding agent streams response chunks to RabbitMQ exchange
    5. API consumes from exchange and forwards to WebSocket
    6. Save assistant message to database
    """
    from sqlalchemy import func, select

    from src.core.system_agents import get_coding_agent
    from src.jobs.rabbitmq import consume_from_exchange, publish_message
    from src.models.enums import MessageRole
    from src.models.orm import Message
    from src.services.llm.factory import get_coding_mode_config

    CODING_AGENT_QUEUE = "coding-agent-requests"
    session_id = conversation_id  # Use conversation_id as session_id

    def get_response_exchange(sid: str) -> str:
        return f"coding.responses.{sid}"

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
        coding_agent = await get_coding_agent(db)
        system_tools = coding_agent.system_tools if coding_agent else []
        knowledge_sources = coding_agent.knowledge_sources if coding_agent else []

        # 1. Save user message first
        user_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=message,
            sequence=await get_next_sequence(),
        )
        db.add(user_msg)
        await db.flush()

        # 1b. Generate assistant message ID upfront and send message_start
        assistant_message_id = uuid4()
        await websocket.send_json({
            "type": "message_start",
            "conversation_id": conversation_id,
            "user_message_id": str(user_msg.id),
            "assistant_message_id": str(assistant_message_id),
        })

        # Build context for coding agent
        coding_context = {
            "user_id": str(user.user_id),
            "user_email": user.email or "",
            "user_name": user.name or user.email or "User",
            "org_id": str(user.organization_id) if user.organization_id else None,
            "is_platform_admin": True,
            "system_tools": system_tools,
            "knowledge_sources": knowledge_sources,
            "model": coding_config.model,
            # Note: API key is read from environment in coding agent container
        }

        # 2. Publish request to coding agent via RabbitMQ
        request_message = {
            "type": "chat",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "message": message,
            "context": coding_context,
        }
        await publish_message(CODING_AGENT_QUEUE, request_message)
        logger.info(f"Published coding request for session {session_id}")

        # 3. Stream responses from coding agent via RabbitMQ exchange
        accumulated_content = ""
        tool_calls_batch: list[dict] = []
        model_used = coding_config.model
        input_tokens = 0
        output_tokens = 0
        duration_ms = 0

        exchange_name = get_response_exchange(session_id)
        async for chunk in consume_from_exchange(exchange_name, timeout=300.0):
            chunk_type = chunk.get("type")

            if chunk_type == "delta":
                # Accumulate text content
                content = chunk.get("content")
                if content:
                    accumulated_content += content

            elif chunk_type == "tool_call" and chunk.get("tool_call"):
                tool_call = chunk["tool_call"]
                # Generate execution_id for tracking
                tool_execution_id = str(uuid4())

                # Collect tool calls for the assistant message
                tool_calls_batch.append({
                    "id": tool_call.get("id"),
                    "name": tool_call.get("name"),
                    "arguments": tool_call.get("arguments") or {},
                })

                # Send tool_call chunk to client (with execution_id)
                chunk["conversation_id"] = conversation_id
                chunk["execution_id"] = tool_execution_id
                await websocket.send_json(chunk)

                # Send tool_progress to set status to "running"
                await websocket.send_json({
                    "type": "tool_progress",
                    "conversation_id": conversation_id,
                    "tool_progress": {
                        "tool_call_id": tool_call.get("id"),
                        "execution_id": tool_execution_id,
                        "status": "running",
                    }
                })
                continue  # Skip default send - we already sent it

            elif chunk_type == "tool_result" and chunk.get("tool_result"):
                tool_result = chunk["tool_result"]
                logger.info(f"[WS] Received tool_result: tool_call_id={tool_result.get('tool_call_id')}")

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
                    content=str(tool_result.get("result")) if tool_result.get("result") else None,
                    tool_call_id=tool_result.get("tool_call_id"),
                    sequence=await get_next_sequence(),
                )
                db.add(tool_result_msg)
                await db.flush()

                # Send tool_progress success
                if tool_result.get("tool_call_id"):
                    logger.info(f"[WS] Sending tool_progress success: tool_call_id={tool_result['tool_call_id']}")
                    await websocket.send_json({
                        "type": "tool_progress",
                        "conversation_id": conversation_id,
                        "tool_progress": {
                            "tool_call_id": tool_result["tool_call_id"],
                            "status": "success",
                        }
                    })

            elif chunk_type == "ask_user_question":
                # Forward ask_user_question to client for modal display
                chunk["conversation_id"] = conversation_id
                await websocket.send_json(chunk)
                # Don't break - we wait for answer and continue streaming
                continue

            elif chunk_type == "done":
                input_tokens = chunk.get("input_tokens") or 0
                output_tokens = chunk.get("output_tokens") or 0
                duration_ms = chunk.get("duration_ms") or 0

                # Save final assistant message if we have accumulated content
                # Use pre-generated assistant_message_id
                if accumulated_content or tool_calls_batch:
                    assistant_msg = Message(
                        id=assistant_message_id,
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content if accumulated_content else None,
                        tool_calls=tool_calls_batch if tool_calls_batch else None,
                        token_count_input=input_tokens if input_tokens > 0 else None,
                        token_count_output=output_tokens if output_tokens > 0 else None,
                        duration_ms=duration_ms if duration_ms > 0 else None,
                        sequence=await get_next_sequence(),
                        model=model_used,
                    )
                    db.add(assistant_msg)

                # Commit all messages
                await db.commit()

                # Send done chunk and exit
                chunk["conversation_id"] = conversation_id
                await websocket.send_json(chunk)
                break

            elif chunk_type == "error":
                # Send error chunk and exit
                chunk["conversation_id"] = conversation_id
                await websocket.send_json(chunk)
                break

            # Send chunk to WebSocket with conversation_id for client routing
            chunk["conversation_id"] = conversation_id
            await websocket.send_json(chunk)

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


async def _send_coding_answer(
    conversation_id: str,
    request_id: str,
    answers: dict[str, str],
) -> None:
    """
    Send user's answer to AskUserQuestion to the coding agent.

    Publishes the answer to the coding agent's answer exchange.

    Args:
        conversation_id: Conversation ID (used as session_id)
        request_id: The request_id from the ask_user_question chunk
        answers: Map of question text to selected answer label(s)
    """
    from src.jobs.rabbitmq import publish_to_exchange

    session_id = conversation_id
    answer_exchange = f"coding.answers.{session_id}"

    answer_message = {
        "type": "answer",
        "request_id": request_id,
        "answers": answers,
    }

    await publish_to_exchange(answer_exchange, answer_message)
    logger.info(f"Published answer for request {request_id} to session {session_id}")


async def _send_coding_stop(conversation_id: str) -> None:
    """
    Send stop signal to the coding agent.

    Publishes a stop message to the coding agent's answer exchange.

    Args:
        conversation_id: Conversation ID (used as session_id)
    """
    from src.jobs.rabbitmq import publish_to_exchange

    session_id = conversation_id
    answer_exchange = f"coding.answers.{session_id}"

    stop_message = {
        "type": "stop",
    }

    await publish_to_exchange(answer_exchange, stop_message)
    logger.info(f"Published stop signal for session {session_id}")


async def _send_coding_set_mode(conversation_id: str, permission_mode: str) -> None:
    """
    Send set_mode command to the coding agent.

    Publishes a set_mode message to the coding agent's request queue.

    Args:
        conversation_id: Conversation ID (used as session_id)
        permission_mode: New permission mode ("plan" or "acceptEdits")
    """
    from src.jobs.rabbitmq import publish_message

    CODING_AGENT_QUEUE = "coding-agent-requests"
    session_id = conversation_id

    set_mode_message = {
        "type": "set_mode",
        "session_id": session_id,
        "conversation_id": conversation_id,
        "permission_mode": permission_mode,
    }

    await publish_message(CODING_AGENT_QUEUE, set_mode_message)
    logger.info(f"Published set_mode ({permission_mode}) for session {session_id}")
