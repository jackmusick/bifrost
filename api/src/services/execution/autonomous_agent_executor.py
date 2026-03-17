"""Autonomous agent executor — runs agents without chat/streaming concerns.

Used for event-triggered, schedule-triggered, and SDK-triggered agent runs.
Records every step as an AgentRunStep for full observability.
"""
import json
import logging
import time
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent
from src.models.orm.agent_runs import AgentRunStep
from src.core.constants import SYSTEM_USER_ID, SYSTEM_USER_EMAIL
from src.core.pubsub import publish_agent_run_step
from src.services.execution.agent_helpers import build_agent_system_prompt, resolve_agent_tools
from src.services.llm import LLMMessage, ToolCallRequest, get_llm_client

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 50  # Hard ceiling


class AutonomousAgentExecutor:
    """Execute an agent autonomously (no streaming, no chat session).

    Handles the full tool-calling loop: LLM call -> tool dispatch -> LLM call,
    recording each step as an AgentRunStep for audit and debugging.
    """

    def __init__(self, session: AsyncSession, redis_client: aioredis.Redis | None = None):
        self.session = session
        self.redis_client = redis_client
        self._tool_workflow_id_map: dict[str, UUID] = {}

    async def run(
        self,
        agent: Agent,
        *,
        input_data: dict | None = None,
        output_schema: dict | None = None,
        run_id: str | None = None,
        _caller: dict | None = None,
    ) -> dict:
        """Execute an autonomous agent run.

        Args:
            agent: The Agent ORM instance to execute.
            input_data: Input payload (serialized as JSON in the user message).
            output_schema: Optional JSON Schema the agent should conform its output to.
            run_id: External run ID (generates one if not provided).
            caller: Optional caller metadata for context.

        Returns:
            Dict with keys: output, iterations_used, tokens_used, status, llm_model
            (and optionally "error" if status is "failed").
        """
        run_id = run_id or str(uuid4())
        step_number = 0
        iterations_used = 0
        tokens_used = 0
        max_iterations = min(agent.max_iterations or 50, MAX_ITERATIONS)
        max_tokens = agent.max_token_budget or 100000

        # Resolve tools
        tool_definitions, self._tool_workflow_id_map = await resolve_agent_tools(agent, self.session)

        # Build initial messages
        system_prompt = build_agent_system_prompt(agent, execution_context={"mode": "autonomous"})
        user_content = json.dumps(input_data) if input_data else "Run your task."
        if output_schema:
            user_content += f"\n\nRespond with JSON matching this schema:\n{json.dumps(output_schema)}"

        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_content),
        ]

        # Get LLM client
        llm_client = await get_llm_client(self.session)
        model = agent.llm_model

        # Record initial request step
        step_number += 1
        await self._record_step(run_id, step_number, "llm_request", {
            "messages_count": len(messages),
            "tools_count": len(tool_definitions),
            "model": model,
        })

        # Main loop
        final_content = ""
        status = "completed"

        while iterations_used < max_iterations:
            iterations_used += 1
            start_time = time.time()

            # Budget warning at 80%
            if iterations_used == int(max_iterations * 0.8):
                messages.append(LLMMessage(
                    role="system",
                    content="You are approaching your iteration budget. "
                            "Please wrap up your work and provide your final output.",
                ))
                step_number += 1
                await self._record_step(run_id, step_number, "budget_warning", {
                    "iterations_used": iterations_used,
                    "max_iterations": max_iterations,
                })

            # Call LLM (use complete() for non-streaming autonomous runs)
            try:
                response = await llm_client.complete(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                    model=model,
                    max_tokens=agent.llm_max_tokens,
                )
            except Exception as e:
                logger.error(f"LLM call failed in run {run_id}: {e}", exc_info=True)
                step_number += 1
                await self._record_step(run_id, step_number, "error", {
                    "error": str(e),
                    "phase": "llm_call",
                })
                return {
                    "output": None,
                    "iterations_used": iterations_used,
                    "tokens_used": tokens_used,
                    "status": "failed",
                    "llm_model": model,
                    "error": str(e),
                }

            duration_ms = int((time.time() - start_time) * 1000)
            chunk_tokens = (response.input_tokens or 0) + (response.output_tokens or 0)
            tokens_used += chunk_tokens

            # Capture the actual model name from the first LLM response
            if not model and response.model:
                model = response.model

            # Record AI usage for cost tracking
            await self._record_ai_usage(
                agent=agent,
                run_id=run_id,
                provider=llm_client.provider_name,
                model=response.model or model or "",
                input_tokens=response.input_tokens or 0,
                output_tokens=response.output_tokens or 0,
                duration_ms=duration_ms,
            )

            # Record LLM response step
            step_number += 1
            await self._record_step(run_id, step_number, "llm_response", {
                "content": (response.content or "")[:2000],
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in (response.tool_calls or [])
                ],
                "finish_reason": response.finish_reason,
            }, tokens_used=chunk_tokens, duration_ms=duration_ms)

            # No tool calls = done
            if not response.tool_calls:
                final_content = response.content or ""
                break

            # Add assistant message with tool calls to history
            messages.append(LLMMessage(
                role="assistant",
                content=response.content if response.content else None,
                tool_calls=response.tool_calls,
            ))

            # Execute tools
            for tc in response.tool_calls:
                step_number += 1
                await self._record_step(run_id, step_number, "tool_call", {
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                })

                tool_start = time.time()
                try:
                    result = await self._execute_tool(tc, agent)
                    tool_duration = int((time.time() - tool_start) * 1000)

                    step_number += 1
                    await self._record_step(run_id, step_number, "tool_result", {
                        "tool_name": tc.name,
                        "result": str(result)[:2000],
                    }, duration_ms=tool_duration)

                    messages.append(LLMMessage(
                        role="tool",
                        content=str(result),
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                    ))
                except Exception as e:
                    tool_duration = int((time.time() - tool_start) * 1000)
                    step_number += 1
                    await self._record_step(run_id, step_number, "error", {
                        "tool_name": tc.name,
                        "error": str(e),
                    }, duration_ms=tool_duration)

                    messages.append(LLMMessage(
                        role="tool",
                        content=f"Error: {e}",
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                    ))

            # Check token budget
            if tokens_used >= max_tokens:
                status = "budget_exceeded"
                step_number += 1
                await self._record_step(run_id, step_number, "budget_warning", {
                    "tokens_used": tokens_used,
                    "max_tokens": max_tokens,
                    "reason": "token_budget_exceeded",
                })
                break
        else:
            # Loop exhausted without breaking — iteration budget exceeded
            status = "budget_exceeded"

        # Parse output
        output: str | dict = final_content
        if output_schema and final_content:
            try:
                output = json.loads(final_content)
            except json.JSONDecodeError:
                pass

        return {
            "output": output,
            "iterations_used": iterations_used,
            "tokens_used": tokens_used,
            "status": status,
            "llm_model": model,
        }

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _execute_tool(self, tool_call: ToolCallRequest, agent: Agent) -> str:
        """Execute a tool call, mirroring AgentExecutor's dispatch logic."""
        # Knowledge search
        if tool_call.name == "search_knowledge" and agent.knowledge_sources:
            return await self._execute_knowledge_search(tool_call, agent)

        # Delegation
        if tool_call.name.startswith("delegate_to_"):
            return await self._execute_delegation(tool_call, agent)

        # System tools
        if tool_call.name in (agent.system_tools or []):
            return await self._execute_system_tool(tool_call, agent)

        # Workflow tools
        workflow_id = self._tool_workflow_id_map.get(tool_call.name)
        if not workflow_id:
            return f"Unknown tool: {tool_call.name}"

        from src.services.execution.service import execute_tool

        response = await execute_tool(
            workflow_id=str(workflow_id),
            workflow_name=tool_call.name,
            parameters=tool_call.arguments or {},
            user_id=SYSTEM_USER_ID,
            user_email=SYSTEM_USER_EMAIL,
            user_name=agent.name,
            org_id=str(agent.organization_id) if agent.organization_id else None,
            is_platform_admin=False,
            is_agent=True,
        )

        if not response.result:
            return "Tool executed successfully"
        if isinstance(response.result, (dict, list)):
            return json.dumps(response.result, default=str)
        return str(response.result)

    async def _execute_knowledge_search(self, tool_call: ToolCallRequest, agent: Agent) -> str:
        """Execute knowledge search using the agent's configured namespaces."""
        try:
            from src.repositories.knowledge import KnowledgeRepository
            from src.services.embeddings import get_embedding_client

            query = tool_call.arguments.get("query", "")
            limit = tool_call.arguments.get("limit", 5)

            if not query:
                return "No query provided for knowledge search"

            namespaces = agent.knowledge_sources
            if not namespaces:
                return "No knowledge sources configured for this agent"

            # Generate query embedding
            embedding_client = await get_embedding_client(self.session)
            query_embedding = await embedding_client.embed_single(query)

            # Search knowledge store
            repo = KnowledgeRepository(
                self.session, org_id=agent.organization_id, is_superuser=True
            )
            results = await repo.search(
                query_embedding=query_embedding,
                namespace=namespaces,
                limit=limit,
                fallback=True,
            )

            if not results:
                return "No relevant knowledge found."

            # Format results
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
            return json.dumps({"documents": search_results, "count": len(search_results)})

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            return f"Knowledge search error: {e}"

    async def _execute_delegation(self, tool_call: ToolCallRequest, agent: Agent) -> str:
        """Execute delegation to another agent (recursive autonomous run)."""
        task = tool_call.arguments.get("task", "")

        # Match by tool name convention: delegate_to_{name_slug}
        target_agent = None
        for d in (agent.delegated_agents or []):
            slug = f"delegate_to_{d.name.lower().replace(' ', '_')}"
            if slug == tool_call.name and d.is_active:
                target_agent = d
                break

        if not target_agent:
            return f"Delegation target for '{tool_call.name}' not found."

        # Recursive run with the delegated agent
        sub_executor = AutonomousAgentExecutor(self.session)
        sub_result = await sub_executor.run(
            agent=target_agent,
            input_data={"task": task, "_delegated_from": agent.name},
        )

        return str(sub_result.get("output", "Delegation completed with no output."))

    async def _execute_system_tool(self, tool_call: ToolCallRequest, agent: Agent) -> str:
        """Execute a system tool."""
        from src.services.mcp_server.server import MCPContext, get_system_tool_function

        func = get_system_tool_function(tool_call.name)
        if not func:
            return f"System tool '{tool_call.name}' not found"

        try:
            context = MCPContext(
                user_id=SYSTEM_USER_ID,
                org_id=str(agent.organization_id) if agent.organization_id else None,
                is_platform_admin=False,
                user_email=SYSTEM_USER_EMAIL,
                user_name=agent.name,
            )

            result = await func(context, **tool_call.arguments)

            # Extract result from FastMCP ToolResult format
            import pydantic_core

            if hasattr(result, "content") and hasattr(result, "structured_content"):
                result_data = {
                    "content": pydantic_core.to_jsonable_python(result.content),
                    "structured_content": result.structured_content,
                }
            elif hasattr(result, "content"):
                result_data = pydantic_core.to_jsonable_python(result.content)
            else:
                result_data = str(result)

            return json.dumps(result_data) if isinstance(result_data, (dict, list)) else str(result_data)

        except Exception as e:
            logger.error(f"System tool {tool_call.name} failed: {e}", exc_info=True)
            return f"System tool error: {e}"

    # ------------------------------------------------------------------
    # AI usage recording
    # ------------------------------------------------------------------

    async def _record_ai_usage(
        self,
        agent: Agent,
        run_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int | None = None,
    ) -> None:
        """Record an AI usage entry for cost tracking."""
        if not self.redis_client:
            return
        try:
            from src.services.ai_usage_service import record_ai_usage

            await record_ai_usage(
                session=self.session,
                redis_client=self.redis_client,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                agent_run_id=UUID(run_id),
                organization_id=agent.organization_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record AI usage for run {run_id}: {e}")

    # ------------------------------------------------------------------
    # Step recording
    # ------------------------------------------------------------------

    async def _record_step(
        self,
        run_id: str,
        step_number: int,
        step_type: str,
        content: dict | None = None,
        *,
        tokens_used: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Record an AgentRunStep in the database."""
        step = AgentRunStep(
            id=uuid4(),
            run_id=UUID(run_id),
            step_number=step_number,
            type=step_type,
            content=content,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
        )
        self.session.add(step)
        await self.session.flush()

        # Broadcast step for real-time updates
        try:
            await publish_agent_run_step(
                run_id=str(run_id),
                step={
                    "id": str(step.id),
                    "run_id": str(run_id),
                    "step_number": step_number,
                    "type": step_type,
                    "content": content,
                    "tokens_used": tokens_used,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            pass  # Don't fail the run if pub/sub fails
