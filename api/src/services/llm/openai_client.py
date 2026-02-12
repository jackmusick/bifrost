"""
OpenAI LLM Client

Implementation of the LLM interface for OpenAI's API.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from src.services.llm.base import (
    BaseLLMClient,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolCallRequest,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    """OpenAI LLM client implementation."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.endpoint or None)

    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Non-streaming completion via OpenAI API."""
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": openai_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools

        response = await self.client.chat.completions.create(**kwargs)

        # Extract response
        choice = response.choices[0]
        message = choice.message

        # Parse tool calls if present
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            model=response.model,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Streaming completion via OpenAI API."""
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": openai_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if openai_tools:
            kwargs["tools"] = openai_tools

        # Track tool calls being built across chunks
        tool_call_builders: dict[int, dict[str, Any]] = {}
        input_tokens = None
        output_tokens = None

        try:
            async with await self.client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    # Handle usage info (comes at the end)
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Handle content delta
                    if delta.content:
                        yield LLMStreamChunk(
                            type="delta",
                            content=delta.content,
                        )

                    # Handle tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index

                            if idx not in tool_call_builders:
                                tool_call_builders[idx] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }

                            if tc_delta.id:
                                tool_call_builders[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_call_builders[idx]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_call_builders[idx]["arguments"] += tc_delta.function.arguments

                    # Handle finish reason
                    if choice.finish_reason:
                        # Emit any completed tool calls
                        for tc_data in tool_call_builders.values():
                            if tc_data["id"] and tc_data["name"]:
                                try:
                                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                                except json.JSONDecodeError:
                                    args = {}
                                    logger.warning(f"Failed to parse tool arguments: {tc_data['arguments']}")

                                yield LLMStreamChunk(
                                    type="tool_call",
                                    tool_call=ToolCallRequest(
                                        id=tc_data["id"],
                                        name=tc_data["name"],
                                        arguments=args,
                                    ),
                                )

                        # Emit done chunk
                        yield LLMStreamChunk(
                            type="done",
                            finish_reason=choice.finish_reason,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            yield LLMStreamChunk(
                type="error",
                error=str(e),
            )

    def _convert_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        """Convert LLMMessage list to OpenAI format."""
        result: list[ChatCompletionMessageParam] = []

        for msg in messages:
            if msg.role == "system":
                result.append({"role": "system", "content": msg.content or ""})

            elif msg.role == "user":
                result.append({"role": "user", "content": msg.content or ""})

            elif msg.role == "assistant":
                assistant_msg: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    assistant_msg["content"] = msg.content
                if msg.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(assistant_msg)  # type: ignore[arg-type]

            elif msg.role == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                })

        return result

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[ChatCompletionToolParam]:
        """Convert ToolDefinition list to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
