"""
Agent Executor Service

Handles the chat completion loop for AI agents, including:
- Message history management
- Tool execution via workflow runner
- Streaming responses
- Token usage tracking
- @mention agent switching
- AI-based message routing
- Agent delegation
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contracts.agents import (
    AgentSwitch,
    ChatStreamChunk,
    ToolCall,
    ToolProgress,
    ToolResult,
)
from src.models.enums import MessageRole
from src.models.orm import Agent, Conversation, Message, Workflow
from src.services.llm import (
    LLMMessage,
    ToolCallRequest,
    ToolDefinition,
    get_llm_client,
)
from src.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


# Maximum tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 10

# Fallback system prompt (used if no config set)
FALLBACK_SYSTEM_PROMPT = """You are a helpful AI assistant. You can help users with a variety of tasks including answering questions, providing information, and having general conversations.

Be concise, accurate, and helpful in your responses."""


class AgentExecutor:
    """
    Executes agent conversations with tool calling support.

    Manages the loop between:
    1. User message
    2. LLM completion (may request tool calls)
    3. Tool execution
    4. LLM completion with tool results
    5. Final response
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tool_registry = ToolRegistry(session)

    async def _switch_agent(
        self,
        conversation: Conversation,
        new_agent: Agent,
        reason: str,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        Centralized agent switching with all rule checks.

        All agent switching paths (@mention, AI routing, etc.) should funnel
        through this method to ensure consistent behavior and rule enforcement.

        Args:
            conversation: The conversation to update
            new_agent: The agent to switch to
            reason: Why the switch happened ("@mention", "routed", etc.)

        Yields:
            - agent_switch event (always)
            - coding_mode_required if agent.is_coding_mode
            - (future: other agent-specific signals)
        """
        # 1. Emit agent switch event
        yield ChatStreamChunk(
            type="agent_switch",
            agent_switch=AgentSwitch(
                agent_id=str(new_agent.id),
                agent_name=new_agent.name,
                reason=reason,
            ),
        )

        # 2. Persist to conversation
        conversation.agent_id = new_agent.id
        await self.session.flush()

        # 3. Check agent-specific rules
        if new_agent.is_coding_mode:
            yield ChatStreamChunk(
                type="coding_mode_required",
                content=f"Switching to {new_agent.name}. Coding mode required.",
            )

    async def chat(
        self,
        agent: Agent | None,
        conversation: Conversation,
        user_message: str,
        *,
        stream: bool = True,
        enable_routing: bool = True,
        is_platform_admin: bool = False,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        Process a user message and generate a response.

        This is a streaming generator that yields ChatStreamChunk objects
        as the response is generated.

        Args:
            agent: The agent handling this conversation (None for agentless chat)
            conversation: The conversation context
            user_message: The user's message text
            stream: Whether to stream the response (default True)
            enable_routing: Whether to enable @mention and AI routing (default True)
            is_platform_admin: Whether user is platform admin (enables coding agent routing)

        Yields:
            ChatStreamChunk objects with response content, tool calls, etc.
        """
        from src.services.agent_router import AgentRouter

        start_time = time.time()
        router = AgentRouter(self.session)

        try:
            # 1. Check for @mention agent switching
            if enable_routing:
                mentioned_agent = await router.parse_mention(user_message)
                if mentioned_agent:
                    # Strip @mention from message for cleaner processing
                    user_message = router.strip_mention(user_message)
                    # Switch to mentioned agent (handles events, persistence, and rule checks)
                    async for chunk in self._switch_agent(conversation, mentioned_agent, "@mention"):
                        yield chunk
                        if chunk.type == "coding_mode_required":
                            return  # Hand off to coding mode handler
                    agent = mentioned_agent

            # 2. AI-based routing for agentless chat (first message only)
            if enable_routing and agent is None:
                # Check if this is the first user message in the conversation
                is_first_message = await self._is_first_user_message(conversation.id)
                if is_first_message:
                    routed_agent = await router.route_message(
                        user_message, is_platform_admin=is_platform_admin
                    )
                    if routed_agent:
                        # Switch to routed agent (handles events, persistence, and rule checks)
                        async for chunk in self._switch_agent(conversation, routed_agent, "routed"):
                            yield chunk
                            if chunk.type == "coding_mode_required":
                                return  # Hand off to coding mode handler
                        agent = routed_agent

            # 3. Save user message
            await self._save_message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=user_message,
            )

            # 4. Get tool definitions for this agent (empty if agentless)
            tool_definitions = await self._get_agent_tools(agent) if agent else []
            logger.info(f"Agent '{agent.name if agent else 'None'}' has {len(tool_definitions)} tool definitions")
            if tool_definitions:
                logger.debug(f"Tools: {[t.name for t in tool_definitions]}")

            # 4b. Add delegation tools if agent has delegations
            if agent:
                delegation_tools = await self._get_delegation_tools(agent)
                tool_definitions.extend(delegation_tools)
                if delegation_tools:
                    logger.info(f"Added {len(delegation_tools)} delegation tools")

            # 5. Build message history
            messages = await self._build_message_history(agent, conversation)

            # 5b. Enhance system prompt with tool-use instructions if tools available
            if tool_definitions and messages and messages[0].role == "system":
                tool_names = [t.name for t in tool_definitions]
                tool_instruction = f"""

You have access to the following tools: {', '.join(tool_names)}

IMPORTANT: When the user's request can be fulfilled using one of your tools, you MUST call the tool immediately. Do not describe what you would do or say "Let me..." - instead, actually invoke the tool to perform the action. Only respond with text if you need clarification or if no tool is applicable."""
                messages[0] = LLMMessage(
                    role="system",
                    content=(messages[0].content or "") + tool_instruction,
                )

            # 4. Get LLM client
            llm_client = await get_llm_client(self.session)

            # 5. Run completion loop with tool calling
            iteration = 0
            final_content = ""
            final_tool_calls: list[ToolCall] = []
            total_input_tokens = 0
            total_output_tokens = 0

            while iteration < MAX_TOOL_ITERATIONS:
                iteration += 1

                # Stream LLM response
                collected_content = ""
                collected_tool_calls: list[ToolCallRequest] = []
                chunk_input_tokens = 0
                chunk_output_tokens = 0

                async for chunk in llm_client.stream(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                ):
                    if chunk.type == "delta" and chunk.content:
                        collected_content += chunk.content
                        if stream:
                            yield ChatStreamChunk(
                                type="delta",
                                content=chunk.content,
                            )

                    elif chunk.type == "tool_call" and chunk.tool_call:
                        collected_tool_calls.append(chunk.tool_call)
                        if stream:
                            yield ChatStreamChunk(
                                type="tool_call",
                                tool_call=ToolCall(
                                    id=chunk.tool_call.id,
                                    name=chunk.tool_call.name,
                                    arguments=chunk.tool_call.arguments,
                                ),
                            )

                    elif chunk.type == "done":
                        chunk_input_tokens = chunk.input_tokens or 0
                        chunk_output_tokens = chunk.output_tokens or 0
                        total_input_tokens += chunk_input_tokens
                        total_output_tokens += chunk_output_tokens

                    elif chunk.type == "error":
                        yield ChatStreamChunk(
                            type="error",
                            error=chunk.error,
                        )
                        return

                # If no tool calls, we're done
                if not collected_tool_calls:
                    final_content = collected_content
                    break

                # Save assistant message with tool calls
                assistant_tool_calls = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in collected_tool_calls
                ]
                await self._save_message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=collected_content if collected_content else None,
                    tool_calls=assistant_tool_calls,
                    token_count_input=chunk_input_tokens,
                    token_count_output=chunk_output_tokens,
                    model=llm_client.model_name,
                )

                # Add assistant message to history
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=collected_content if collected_content else None,
                        tool_calls=collected_tool_calls,
                    )
                )

                # Execute tools and add results to history
                for tc in collected_tool_calls:
                    tool_call = ToolCall(
                        id=tc.id,
                        name=tc.name,
                        arguments=tc.arguments,
                    )
                    final_tool_calls.append(tool_call)

                    # Generate execution_id for this tool call (for log streaming)
                    execution_id = str(uuid4())

                    # Emit running status with execution_id
                    if stream:
                        yield ChatStreamChunk(
                            type="tool_progress",
                            tool_progress=ToolProgress(
                                tool_call_id=tc.id,
                                execution_id=execution_id,
                                status="running",
                            ),
                        )

                    # Execute the tool with pre-generated execution_id
                    tool_result = await self._execute_tool(tc, agent, conversation, execution_id=execution_id)

                    if stream:
                        yield ChatStreamChunk(
                            type="tool_result",
                            tool_result=tool_result,
                        )

                    # Save tool result message with execution_id for log retrieval
                    await self._save_message(
                        conversation_id=conversation.id,
                        role=MessageRole.TOOL,
                        content=json.dumps(tool_result.result) if tool_result.result else tool_result.error,
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        execution_id=execution_id,
                        duration_ms=tool_result.duration_ms,
                    )

                    # Add tool result to message history
                    messages.append(
                        LLMMessage(
                            role="tool",
                            content=json.dumps(tool_result.result) if tool_result.result else tool_result.error,
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                        )
                    )

                # Continue loop to get LLM response with tool results

            # 6. Save final assistant message
            duration_ms = int((time.time() - start_time) * 1000)
            assistant_msg = await self._save_message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=final_content,
                token_count_input=total_input_tokens,
                token_count_output=total_output_tokens,
                model=llm_client.model_name,
                duration_ms=duration_ms,
            )

            # 6b. Record AI usage
            try:
                await self._record_ai_usage(
                    provider=llm_client.provider_name,
                    model=llm_client.model_name,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    duration_ms=duration_ms,
                    conversation_id=conversation.id,
                    message_id=assistant_msg.id,
                    organization_id=agent.organization_id if agent else None,
                    user_id=conversation.user_id,
                )
            except Exception as e:
                logger.warning(f"Failed to record AI usage: {e}")

            # 7. Yield done chunk with final content (for non-streaming mode)
            yield ChatStreamChunk(
                type="done",
                content=final_content if final_content else None,
                message_id=str(assistant_msg.id),
                token_count_input=total_input_tokens,
                token_count_output=total_output_tokens,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)
            yield ChatStreamChunk(
                type="error",
                error=str(e),
            )

    async def _get_agent_tools(self, agent: Agent) -> list[ToolDefinition]:
        """Get tool definitions for an agent from its assigned tools."""
        tools: list[ToolDefinition] = []

        # Get workflow IDs from agent_tools junction table
        tool_ids = [tool.id for tool in agent.tools]
        logger.debug(f"Agent '{agent.name}' has {len(agent.tools)} assigned tools: {tool_ids}")

        if tool_ids:
            tool_definitions = await self.tool_registry.get_tool_definitions(tool_ids)
            logger.debug(f"Tool registry returned {len(tool_definitions)} definitions for IDs {tool_ids}")

            tools.extend([
                ToolDefinition(
                    name=td.name,
                    description=td.description,
                    parameters=td.parameters,
                )
                for td in tool_definitions
            ])
        else:
            logger.info(f"Agent '{agent.name}' has no workflow tools assigned")

        # Add knowledge search tool if agent has knowledge sources
        if agent.knowledge_sources:
            knowledge_tool = self._get_knowledge_tool(agent.knowledge_sources)
            tools.append(knowledge_tool)
            logger.info(f"Agent '{agent.name}' has knowledge sources: {agent.knowledge_sources}")

        return tools

    def _get_knowledge_tool(self, namespaces: list[str]) -> ToolDefinition:
        """
        Create the built-in knowledge search tool definition.

        This tool allows agents to search their configured knowledge namespaces.
        """
        ns_list = ", ".join(namespaces)
        return ToolDefinition(
            name="search_knowledge",
            description=f"Search the knowledge base for relevant information. Searches these namespaces: {ns_list}. Use this tool when you need to find information from stored documents, policies, FAQs, or other knowledge sources.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant documents",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                    },
                },
                "required": ["query"],
            },
        )

    async def _build_message_history(
        self, agent: Agent | None, conversation: Conversation
    ) -> list[LLMMessage]:
        """Build the message history for LLM completion."""
        messages: list[LLMMessage] = []

        # Add system prompt (use agent's prompt or configurable default for agentless chat)
        if agent:
            system_prompt = agent.system_prompt
        else:
            system_prompt = await self._get_default_system_prompt()
        messages.append(
            LLMMessage(
                role="system",
                content=system_prompt,
            )
        )

        # Get conversation messages in order
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.sequence)
        )
        db_messages = result.scalars().all()

        for msg in db_messages:
            if msg.role == MessageRole.USER:
                messages.append(
                    LLMMessage(
                        role="user",
                        content=msg.content,
                    )
                )
            elif msg.role == MessageRole.ASSISTANT:
                tool_calls = None
                if msg.tool_calls:
                    tool_calls = [
                        ToolCallRequest(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=tc.get("arguments", {}),
                        )
                        for tc in msg.tool_calls
                    ]
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=msg.content,
                        tool_calls=tool_calls,
                    )
                )
            elif msg.role == MessageRole.TOOL:
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=msg.content,
                        tool_call_id=msg.tool_call_id,
                        tool_name=msg.tool_name,
                    )
                )
            elif msg.role == MessageRole.SYSTEM:
                # Skip additional system messages (we already have the prompt)
                pass

        return messages

    async def _save_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        execution_id: str | None = None,
        token_count_input: int | None = None,
        token_count_output: int | None = None,
        model: str | None = None,
        duration_ms: int | None = None,
    ) -> Message:
        """Save a message to the conversation."""
        # Get next sequence number
        result = await self.session.execute(
            select(func.coalesce(func.max(Message.sequence), 0))
            .where(Message.conversation_id == conversation_id)
        )
        max_sequence = result.scalar() or 0
        next_sequence = max_sequence + 1

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            execution_id=execution_id,
            token_count_input=token_count_input,
            token_count_output=token_count_output,
            model=model,
            duration_ms=duration_ms,
            sequence=next_sequence,
        )
        self.session.add(message)
        await self.session.flush()

        # Update conversation updated_at
        conversation_result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = conversation_result.scalar_one()
        conversation.updated_at = datetime.utcnow()
        await self.session.flush()

        return message

    async def _execute_tool(
        self,
        tool_call: ToolCallRequest,
        agent: Agent | None = None,
        conversation: Conversation | None = None,
        execution_id: str | None = None,
    ) -> ToolResult:
        """
        Execute a tool (workflow, delegation, or knowledge search) and return the result.

        This integrates with the existing workflow execution system
        and handles agent delegation and built-in knowledge search.
        """
        start_time = time.time()

        # Check if this is a knowledge search tool call
        if tool_call.name == "search_knowledge" and agent:
            return await self._execute_knowledge_search(tool_call, agent)

        # Check if this is a delegation tool call
        if tool_call.name.startswith("delegate_to_") and agent:
            return await self._execute_delegation(tool_call, agent)

        try:
            # Get the workflow for this tool
            result = await self.session.execute(
                select(Workflow)
                .where(Workflow.name == tool_call.name)
                .where(Workflow.is_tool.is_(True))
                .where(Workflow.is_active.is_(True))
            )
            workflow = result.scalar_one_or_none()

            if not workflow:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error=f"Tool '{tool_call.name}' not found",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Get user info from conversation
            user = conversation.user if conversation else None

            # Execute the workflow via execution service
            from src.services.execution.service import execute_tool

            # Get org_id from agent (workflows are not org-scoped)
            org_id = str(agent.organization_id) if agent and agent.organization_id else None

            execution_response = await execute_tool(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                parameters=tool_call.arguments or {},
                user_id=str(user.id) if user else "system",
                user_email=user.email if user else "system@bifrost.local",
                user_name=user.name if user else "System",
                org_id=org_id,
                is_platform_admin=user.is_superuser if user else False,
                execution_id=execution_id,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if execution_response.status.value == "Success":
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=execution_response.result,
                    error=None,
                    duration_ms=duration_ms,
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error=execution_response.error or "Unknown error",
                    duration_ms=duration_ms,
                )

        except Exception as e:
            logger.error(f"Tool execution error for {tool_call.name}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=None,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _get_default_system_prompt(self) -> str:
        """
        Get the default system prompt from LLM config or use fallback.
        """
        from src.services.llm_config_service import LLMConfigService

        try:
            config_service = LLMConfigService(self.session)
            config = await config_service.get_config()

            if config and config.default_system_prompt:
                return config.default_system_prompt
        except Exception as e:
            logger.warning(f"Failed to get default system prompt from config: {e}")

        return FALLBACK_SYSTEM_PROMPT

    async def _is_first_user_message(self, conversation_id: UUID) -> bool:
        """
        Check if this is the first user message in a conversation.
        Used to determine whether to apply AI routing.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role == MessageRole.USER)
        )
        count = result.scalar() or 0
        return count == 0

    async def _get_delegation_tools(self, agent: Agent) -> list[ToolDefinition]:
        """
        Get tool definitions for delegated agents.

        Each delegated agent becomes a tool that can be called to delegate
        a task to that agent.
        """
        # Get delegated agent IDs
        delegated_ids = [d.id for d in agent.delegated_agents]

        if not delegated_ids:
            return []

        # Fetch the delegated agents
        result = await self.session.execute(
            select(Agent)
            .where(Agent.id.in_(delegated_ids))
            .where(Agent.is_active.is_(True))
        )
        delegated_agents = result.scalars().all()

        tools = []
        for delegated in delegated_agents:
            # Create a tool for each delegated agent
            tool_name = f"delegate_to_{delegated.name.lower().replace(' ', '_')}"
            tools.append(
                ToolDefinition(
                    name=tool_name,
                    description=f"Delegate a task to {delegated.name}. {delegated.description or ''}",
                    parameters={
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "The task or question to delegate to this agent",
                            },
                        },
                        "required": ["task"],
                    },
                )
            )

        return tools

    async def _execute_knowledge_search(
        self,
        tool_call: ToolCallRequest,
        agent: Agent,
    ) -> ToolResult:
        """
        Execute a knowledge search using the agent's configured namespaces.

        This is a built-in tool that doesn't require a workflow.
        """
        start_time = time.time()

        try:
            from src.repositories.knowledge import KnowledgeRepository
            from src.services.embeddings import get_embedding_client

            # Get search parameters
            query = tool_call.arguments.get("query", "")
            limit = tool_call.arguments.get("limit", 5)

            if not query:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error="No query provided for knowledge search",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Get the agent's configured namespaces
            namespaces = agent.knowledge_sources
            if not namespaces:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error="No knowledge sources configured for this agent",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Generate query embedding
            embedding_client = await get_embedding_client(self.session)
            query_embedding = await embedding_client.embed_single(query)

            # Search knowledge store
            repo = KnowledgeRepository(self.session)
            results = await repo.search(
                query_embedding=query_embedding,
                namespace=namespaces,
                organization_id=agent.organization_id,
                limit=limit,
                fallback=True,  # Search org + global
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Format results for the agent
            search_results = [
                {
                    "content": doc.content,
                    "namespace": doc.namespace,
                    "score": round(doc.score, 4) if doc.score else None,
                    "key": doc.key,
                    "metadata": doc.metadata,
                }
                for doc in results
            ]

            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result={"documents": search_results, "count": len(search_results)},
                error=None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Knowledge search error: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=None,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _execute_delegation(
        self,
        tool_call: ToolCallRequest,
        agent: Agent,
    ) -> ToolResult:
        """
        Execute a delegation to another agent.

        This runs a nested agent execution and returns the result.
        """
        start_time = time.time()

        try:
            # Extract agent name from tool call name (e.g., "delegate_to_sales_agent" -> "sales agent")
            agent_name_slug = tool_call.name.replace("delegate_to_", "").replace("_", " ")

            # Find the delegated agent
            result = await self.session.execute(
                select(Agent)
                .where(Agent.name.ilike(f"%{agent_name_slug}%"))
                .where(Agent.is_active.is_(True))
            )
            delegated_agent = result.scalar_one_or_none()

            if not delegated_agent:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error=f"Delegated agent not found: {agent_name_slug}",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Get the task from arguments
            task = tool_call.arguments.get("task", "")
            if not task:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=None,
                    error="No task provided for delegation",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Execute a single-turn completion with the delegated agent
            # Note: We don't create a separate conversation for delegation
            llm_client = await get_llm_client(self.session)

            messages = [
                LLMMessage(role="system", content=delegated_agent.system_prompt),
                LLMMessage(role="user", content=task),
            ]

            # Get response (non-streaming for delegation)
            response = await llm_client.complete(messages=messages)

            duration_ms = int((time.time() - start_time) * 1000)

            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result={"response": response.content, "agent": delegated_agent.name},
                error=None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Delegation error for {tool_call.name}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=None,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _record_ai_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        """
        Record AI usage for tracking and cost calculation.

        Args:
            provider: LLM provider name (e.g., 'openai', 'anthropic')
            model: Model identifier
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            duration_ms: Request duration in milliseconds
            conversation_id: UUID of the conversation
            message_id: UUID of the generated message
            organization_id: UUID of the organization
            user_id: UUID of the user
        """
        from src.core.cache import get_shared_redis
        from src.services.ai_usage_service import record_ai_usage

        redis_client = await get_shared_redis()
        await record_ai_usage(
            session=self.session,
            redis_client=redis_client,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            conversation_id=conversation_id,
            message_id=message_id,
            organization_id=organization_id,
            user_id=user_id,
        )
