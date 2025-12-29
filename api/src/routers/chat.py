"""
Chat Router

Chat conversations and messaging for AI agents.
Includes both HTTP and WebSocket endpoints for streaming.

Supports two modes:
- Regular chat: Uses AgentExecutor with configured agents/tools
- Coding mode: Uses Claude Agent SDK for workflow development (platform admins only)
"""

import json
import logging
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession, get_db_context
from src.models.contracts.agents import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationPublic,
    ConversationSummary,
    MessagePublic,
)
from src.models.enums import AgentAccessLevel
from src.models.orm import Agent, AgentRole, Conversation, Message
from src.services.agent_executor import AgentExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# =============================================================================
# Conversation CRUD
# =============================================================================


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    db: DbSession,
    user: CurrentActiveUser,
) -> ConversationPublic:
    """Create a new conversation, optionally with an agent."""
    agent = None
    agent_name = None

    # If agent_id provided, verify agent exists and user has access
    if request.agent_id:
        result = await db.execute(
            select(Agent)
            .where(Agent.id == request.agent_id)
            .where(Agent.is_active.is_(True))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {request.agent_id} not found",
            )

        # Check access based on agent's access level
        has_access = await _check_agent_access(db, user, agent)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agent",
            )

        agent_name = agent.name

    # Create conversation (agent_id can be None for agentless chat)
    conversation_id = uuid4()
    now = datetime.utcnow()

    conversation = Conversation(
        id=conversation_id,
        agent_id=agent.id if agent else None,
        user_id=user.user_id,
        channel=request.channel.value,
        title=request.title,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.flush()

    return ConversationPublic(
        id=conversation.id,
        agent_id=conversation.agent_id,
        user_id=conversation.user_id,
        channel=conversation.channel,
        title=conversation.title,
        is_active=conversation.is_active,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
        agent_name=agent_name,
    )


@router.get("/conversations")
async def list_conversations(
    db: DbSession,
    user: CurrentActiveUser,
    agent_id: UUID | None = None,
    active_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationSummary]:
    """List user's conversations."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.agent))
        .where(Conversation.user_id == user.user_id)
    )

    if active_only:
        stmt = stmt.where(Conversation.is_active.is_(True))

    if agent_id:
        stmt = stmt.where(Conversation.agent_id == agent_id)

    stmt = stmt.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    conversations = result.scalars().all()

    summaries = []
    for conv in conversations:
        # Get last message preview
        last_msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.sequence.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        summaries.append(ConversationSummary(
            id=conv.id,
            agent_id=conv.agent_id,
            agent_name=conv.agent.name if conv.agent else None,
            title=conv.title,
            updated_at=conv.updated_at,
            last_message_preview=last_msg.content[:100] if last_msg and last_msg.content else None,
        ))

    return summaries


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> ConversationPublic:
    """Get conversation details."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.agent), selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.user_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Get message count
    count_result = await db.execute(
        select(func.count(Message.id))
        .where(Message.conversation_id == conversation_id)
    )
    message_count = count_result.scalar() or 0

    # Get last message time
    last_msg_result = await db.execute(
        select(Message.created_at)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence.desc())
        .limit(1)
    )
    last_message_at = last_msg_result.scalar_one_or_none()

    return ConversationPublic(
        id=conversation.id,
        agent_id=conversation.agent_id,
        user_id=conversation.user_id,
        channel=conversation.channel,
        title=conversation.title,
        is_active=conversation.is_active,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count,
        last_message_at=last_message_at,
        agent_name=conversation.agent.name if conversation.agent else None,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    """Delete a conversation (soft delete)."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.user_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    conversation.is_active = False
    conversation.updated_at = datetime.utcnow()
    await db.flush()


# =============================================================================
# Messages
# =============================================================================


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
    limit: int = 100,
    before_sequence: int | None = None,
) -> list[MessagePublic]:
    """Get messages in a conversation."""
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.user_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Get messages
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
    )

    if before_sequence is not None:
        stmt = stmt.where(Message.sequence < before_sequence)

    stmt = stmt.order_by(Message.sequence.asc()).limit(limit)

    result = await db.execute(stmt)
    messages = result.scalars().all()

    return [
        MessagePublic(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            tool_calls=[
                {"id": tc["id"], "name": tc["name"], "arguments": tc.get("arguments", {})}
                for tc in (m.tool_calls or [])
            ] if m.tool_calls else None,
            tool_call_id=m.tool_call_id,
            tool_name=m.tool_name,
            token_count_input=m.token_count_input,
            token_count_output=m.token_count_output,
            model=m.model,
            duration_ms=m.duration_ms,
            sequence=m.sequence,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: ChatRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> ChatResponse:
    """
    Send a message to a conversation (non-streaming).

    For streaming responses, use the WebSocket endpoint.
    """
    # Verify conversation and optionally get agent
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.agent).selectinload(Agent.tools),
            selectinload(Conversation.agent).selectinload(Agent.delegated_agents),
        )
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.user_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Agent is now optional - agentless chat uses default system prompt

    # Execute chat (agent may be None for agentless chat)
    executor = AgentExecutor(db)

    # Collect streaming response into a single response
    final_content = ""
    final_tool_calls = []
    final_message_id = None
    final_input_tokens = None
    final_output_tokens = None
    final_duration_ms = None

    async for chunk in executor.chat(
        agent=conversation.agent,  # May be None for agentless chat
        conversation=conversation,
        user_message=request.message,
        stream=False,
    ):
        if chunk.type == "delta" and chunk.content:
            final_content += chunk.content
        elif chunk.type == "tool_call" and chunk.tool_call:
            final_tool_calls.append(chunk.tool_call)
        elif chunk.type == "done":
            # For non-streaming, content is sent in the done chunk
            if chunk.content:
                final_content = chunk.content
            final_message_id = chunk.message_id
            final_input_tokens = chunk.token_count_input
            final_output_tokens = chunk.token_count_output
            final_duration_ms = chunk.duration_ms
        elif chunk.type == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=chunk.error or "Unknown error during chat",
            )

    await db.commit()

    return ChatResponse(
        message_id=UUID(final_message_id) if final_message_id else uuid4(),
        content=final_content,
        tool_calls=final_tool_calls if final_tool_calls else None,
        token_count_input=final_input_tokens,
        token_count_output=final_output_tokens,
        duration_ms=final_duration_ms,
    )


# =============================================================================
# WebSocket Streaming
# =============================================================================


@router.websocket("/conversations/{conversation_id}/stream")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: UUID,
    coding_mode: bool = Query(False, description="Enable coding mode (platform admins only)"),
):
    """
    WebSocket endpoint for streaming chat.

    Protocol:
    1. Client connects
    2. Server sends: {"type": "connected"}
    3. Client sends: {"message": "user message here"}
    4. Server streams: {"type": "delta", "content": "..."} chunks
    5. Server may send: {"type": "tool_call", "tool_call": {...}}
    6. Server may send: {"type": "tool_result", "tool_result": {...}}
    7. Server sends: {"type": "done", ...} when complete
    8. Client can send another message to continue

    Coding Mode (coding_mode=true):
    - Platform admins only
    - Uses Claude Agent SDK for workflow development
    - Operates in /tmp/bifrost/workspace
    - Has access to execute_workflow and list_integrations tools
    """
    await websocket.accept()

    try:
        # Get database session using context manager
        async with get_db_context() as db:
            # Verify conversation exists (basic check, user auth needed)
            result = await db.execute(
                select(Conversation)
                .options(
                    selectinload(Conversation.agent).selectinload(Agent.tools),
                    selectinload(Conversation.user),
                )
                .where(Conversation.id == conversation_id)
                .where(Conversation.is_active.is_(True))
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await websocket.send_json({"type": "error", "error": "Conversation not found"})
                await websocket.close()
                return

            # Get user for permission check
            user = conversation.user

            # Coding mode requires platform admin (superuser)
            if coding_mode:
                if not user or not user.is_superuser:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Coding mode requires platform admin access"
                    })
                    await websocket.close()
                    return

                # Extract data we need before closing session
                coding_mode_params = {
                    "conversation_id": conversation.id,
                    "user_id": user.id,
                    "user_email": user.email,
                    "user_name": user.name or user.email,
                    "org_id": user.organization_id,
                }
        # Session CLOSED here - critical to avoid holding locks during SDK operations

        if coding_mode:
            # Use coding mode client with fresh sessions for each DB operation
            await _handle_coding_mode(websocket, **coding_mode_params)
            return

        # Regular chat mode continues with the session
        async with get_db_context() as db:
            # Re-fetch conversation for regular chat
            result = await db.execute(
                select(Conversation)
                .options(
                    selectinload(Conversation.agent).selectinload(Agent.tools),
                    selectinload(Conversation.agent).selectinload(Agent.delegated_agents),
                )
                .where(Conversation.id == conversation_id)
                .where(Conversation.is_active.is_(True))
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                await websocket.send_json({"type": "error", "error": "Conversation not found"})
                await websocket.close()
                return

            # Regular chat mode
            # Agent is now optional - agentless chat uses default system prompt

            # Send connected message
            await websocket.send_json({"type": "connected", "conversation_id": str(conversation_id)})

            # Message loop
            executor = AgentExecutor(db)

            while True:
                try:
                    # Wait for message from client
                    data = await websocket.receive_json()
                    message = data.get("message", "")

                    if not message:
                        await websocket.send_json({"type": "error", "error": "Empty message"})
                        continue

                    # Stream response (agent may be None for agentless chat)
                    async for chunk in executor.chat(
                        agent=conversation.agent,  # May be None for agentless chat
                        conversation=conversation,
                        user_message=message,
                        stream=True,
                    ):
                        await websocket.send_json(chunk.model_dump(exclude_none=True))

                    # Commit the transaction after each message
                    await db.commit()

                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: {conversation_id}")
                    break
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                except Exception as e:
                    logger.error(f"WebSocket error: {e}", exc_info=True)
                    await websocket.send_json({"type": "error", "error": str(e)})

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass


async def _handle_coding_mode(
    websocket: WebSocket,
    conversation_id: UUID,
    user_id: UUID,
    user_email: str,
    user_name: str,
    org_id: UUID | None,
) -> None:
    """
    Handle coding mode WebSocket session.

    Uses Claude Agent SDK with Bifrost MCP server for workflow development.
    Requires Anthropic API key (either from main LLM config or coding override).

    Unlike regular chat, coding mode:
    - Uses Claude Agent SDK instead of direct LLM calls
    - Saves messages to DB for persistence and token tracking
    - Records AI usage for cost reporting

    IMPORTANT: This function uses short-lived database sessions for each operation
    to avoid holding row locks during long-running SDK operations. The Claude Agent
    SDK can run for minutes (tool loops, file edits, etc.), and holding a session
    open during that time would block other operations on the conversation row.
    """
    from src.core.cache import get_shared_redis
    from src.core.system_agents import get_coding_agent
    from src.models.enums import MessageRole
    from src.services.ai_usage_service import record_ai_usage
    from src.services.coding_mode import CodingModeClient
    from src.services.llm.factory import get_coding_mode_config

    # Get coding mode config and coding agent with fresh session
    async with get_db_context() as db:
        config = await get_coding_mode_config(db)
        coding_agent = await get_coding_agent(db)

    if not config:
        await websocket.send_json({
            "type": "error",
            "error": "Coding mode requires Anthropic API key",
            "error_code": "ANTHROPIC_NOT_CONFIGURED",
            "help": "Go to Settings > AI Configuration to set up Anthropic, or configure a dedicated coding API key.",
        })
        await websocket.close()
        return

    # Get enabled system tools and knowledge sources from the coding agent
    system_tools = coding_agent.system_tools if coding_agent else []
    knowledge_sources = coding_agent.knowledge_sources if coding_agent else []

    # Create coding mode client with config
    client = CodingModeClient(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        api_key=config.api_key,
        model=config.model,
        org_id=org_id,
        is_platform_admin=True,
        session_id=str(conversation_id),  # Use conversation ID as session ID
        system_tools=system_tools,
        knowledge_sources=knowledge_sources,
    )

    try:
        # Send session start
        await websocket.send_json({
            "type": "session_start",
            "session_id": client.session_id,
            "conversation_id": str(conversation_id),
            "mode": "coding",
        })

        # Message loop
        while True:
            try:
                # Wait for message from client
                data = await websocket.receive_json()
                message_text = data.get("message", "")

                if not message_text:
                    await websocket.send_json({"type": "error", "error": "Empty message"})
                    continue

                # 1. Save user message to database with fresh session
                async with get_db_context() as db:
                    # Get next sequence in same session to avoid nested sessions
                    result = await db.execute(
                        select(func.coalesce(func.max(Message.sequence), 0))
                        .where(Message.conversation_id == conversation_id)
                    )
                    next_seq = (result.scalar() or 0) + 1

                    user_msg = Message(
                        id=uuid4(),
                        conversation_id=conversation_id,
                        role=MessageRole.USER,
                        content=message_text,
                        sequence=next_seq,
                    )
                    db.add(user_msg)
                    # Context manager handles commit
                # Session closed - no locks held during SDK operations

                # 2. Stream response and accumulate for persistence
                # This can take MINUTES - no DB session held during this time
                assistant_content = ""
                tool_calls_list: list[dict] = []
                input_tokens = 0
                output_tokens = 0
                duration_ms = 0
                message_id = uuid4()

                async for chunk in client.chat(message_text):
                    # Accumulate response and handle special chunk types
                    if chunk.type == "delta" and chunk.content:
                        assistant_content += chunk.content
                        await websocket.send_json(chunk.model_dump(exclude_none=True))
                    elif chunk.type == "tool_call" and chunk.tool_call:
                        # Generate execution_id for tracking
                        tool_execution_id = str(uuid4())
                        tool_calls_list.append({
                            "id": chunk.tool_call.id,
                            "name": chunk.tool_call.name,
                            "arguments": json.dumps(chunk.tool_call.arguments or {}),
                        })
                        # Send tool_call chunk with execution_id
                        chunk_data = chunk.model_dump(exclude_none=True)
                        chunk_data["execution_id"] = tool_execution_id
                        await websocket.send_json(chunk_data)
                        # Immediately send tool_progress to set status to "running"
                        await websocket.send_json({
                            "type": "tool_progress",
                            "tool_progress": {
                                "tool_call_id": chunk.tool_call.id,
                                "execution_id": tool_execution_id,
                                "status": "running",
                            }
                        })
                    elif chunk.type == "tool_result" and chunk.tool_result:
                        # Send tool_result then mark as success
                        await websocket.send_json(chunk.model_dump(exclude_none=True))
                        # Send tool_progress with success status
                        if chunk.tool_result.tool_call_id:
                            await websocket.send_json({
                                "type": "tool_progress",
                                "tool_progress": {
                                    "tool_call_id": chunk.tool_result.tool_call_id,
                                    "status": "success",
                                }
                            })
                    elif chunk.type == "done":
                        input_tokens = chunk.input_tokens or 0
                        output_tokens = chunk.output_tokens or 0
                        duration_ms = chunk.duration_ms or 0
                        await websocket.send_json(chunk.model_dump(exclude_none=True))
                    else:
                        # Other chunk types (session_start, error, etc.)
                        await websocket.send_json(chunk.model_dump(exclude_none=True))

                # 3. Save assistant message with fresh session
                async with get_db_context() as db:
                    # Get next sequence in same session to avoid nested sessions
                    result = await db.execute(
                        select(func.coalesce(func.max(Message.sequence), 0))
                        .where(Message.conversation_id == conversation_id)
                    )
                    next_seq = (result.scalar() or 0) + 1

                    assistant_msg = Message(
                        id=message_id,
                        conversation_id=conversation_id,
                        role=MessageRole.ASSISTANT,
                        content=assistant_content or None,
                        tool_calls=tool_calls_list if tool_calls_list else None,
                        token_count_input=input_tokens if input_tokens > 0 else None,
                        token_count_output=output_tokens if output_tokens > 0 else None,
                        model=config.model,
                        duration_ms=duration_ms if duration_ms > 0 else None,
                        sequence=next_seq,
                    )
                    db.add(assistant_msg)
                    # Context manager handles commit
                # Session closed

                # 4. Record AI usage for cost tracking (if we have token counts)
                if input_tokens > 0 or output_tokens > 0:
                    try:
                        async with get_db_context() as db:
                            redis_client = await get_shared_redis()
                            await record_ai_usage(
                                session=db,
                                redis_client=redis_client,
                                provider="anthropic",
                                model=config.model,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                duration_ms=duration_ms if duration_ms > 0 else None,
                                conversation_id=conversation_id,
                                message_id=message_id,
                                user_id=user_id,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to record AI usage: {e}")

            except WebSocketDisconnect:
                logger.info(f"Coding mode WebSocket disconnected: {conversation_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON"})
            except Exception as e:
                logger.error(f"Coding mode error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "error": str(e)})
                # No rollback needed - each operation has its own committed session
    finally:
        # Clean up SDK client resources
        await client.close()


# =============================================================================
# Helper Functions
# =============================================================================


async def _check_agent_access(db: DbSession, user, agent: Agent) -> bool:
    """Check if user has access to an agent based on its access level."""
    # Authenticated agents are accessible to any logged-in user
    if agent.access_level == AgentAccessLevel.AUTHENTICATED:
        return True

    # Role-based access requires matching roles
    if agent.access_level == AgentAccessLevel.ROLE_BASED:
        # Check if user is platform admin (user.roles is list[str] from JWT)
        is_admin = user.is_superuser or any(
            role in ["Platform Admin", "Platform Owner"]
            for role in user.roles
        )
        if is_admin:
            return True

        # Check if user has any role assigned to this agent
        # user.roles is list[str] (role names), so we need to join through Role table
        if user.roles:
            from src.models.orm import Role
            result = await db.execute(
                select(AgentRole)
                .join(Role, AgentRole.role_id == Role.id)
                .where(AgentRole.agent_id == agent.id)
                .where(Role.name.in_(user.roles))
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    return False
