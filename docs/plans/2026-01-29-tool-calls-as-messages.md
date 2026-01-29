# Tool Calls as Separate Messages - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor chat to treat each tool call as its own message with self-contained state, eliminating duplicate rendering and complex merging logic.

**Architecture:** Each tool call becomes a separate `TOOL_CALL` message (new role) with `tool_state` tracking its lifecycle. Tool results update the same message rather than creating separate `TOOL` messages for frontend display. Backend continues saving `TOOL` messages for Anthropic API compatibility, but frontend ignores them.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React, Zustand, TypeScript

---

## Overview

**Current State (Broken):**
- Tool calls are arrays embedded in assistant messages (`tool_calls: [...]`)
- Tool results are separate `role: "tool"` messages
- Tool execution state tracked separately in `toolExecutionsByConversation`
- Frontend has complex merging logic in `MessageWithToolCards`
- Race conditions cause duplicates and rendering issues

**Target State (Happy's Pattern):**
- Each tool call is its own message with `role: "tool_call"`
- State is on the message: `tool_state: 'running' | 'completed' | 'error'`
- `tool_result` stored directly on the tool_call message
- Simple list rendering - no merging needed
- `role: "tool"` messages still saved for API compatibility, but hidden from UI

---

## Task 1: Add TOOL_CALL Message Role

**Files:**
- Modify: `api/src/models/enums.py:89-94`

**Step 1: Add TOOL_CALL to MessageRole enum**

```python
class MessageRole(str, Enum):
    """Message roles in chat conversations"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    TOOL_CALL = "tool_call"  # New: represents a tool invocation
```

**Step 2: Run type check to verify**

Run: `cd api && pyright src/models/enums.py`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/models/enums.py
git commit -m "feat(chat): add TOOL_CALL message role"
```

---

## Task 2: Add Tool State Fields to Message ORM Model

**Files:**
- Modify: `api/src/models/orm/agents.py:199-241`

**Step 1: Add tool_state and tool_result columns to Message**

Add after `execution_id` field (line 224):

```python
    # Tool call state tracking (for TOOL_CALL role)
    tool_state: Mapped[str | None] = mapped_column(String(20), default=None)  # running, completed, error
    tool_result: Mapped[dict | None] = mapped_column(JSONB, default=None)  # Result data from tool execution
    tool_input: Mapped[dict | None] = mapped_column(JSONB, default=None)  # Input arguments for tool call
```

**Step 2: Run type check**

Run: `cd api && pyright src/models/orm/agents.py`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/models/orm/agents.py
git commit -m "feat(chat): add tool_state, tool_result, tool_input columns to Message"
```

---

## Task 3: Create Database Migration

**Files:**
- Create: `api/alembic/versions/xxxx_add_tool_call_fields.py`

**Step 1: Generate migration**

Run: `cd api && alembic revision -m "add_tool_call_message_fields"`

**Step 2: Edit the generated migration file**

```python
"""add_tool_call_message_fields

Revision ID: [auto-generated]
Revises: [previous]
Create Date: [auto-generated]
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '[auto-generated]'
down_revision = '[previous]'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tool_call to message_role enum
    op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'tool_call'")

    # Add new columns to messages table
    op.add_column('messages', sa.Column('tool_state', sa.String(20), nullable=True))
    op.add_column('messages', sa.Column('tool_result', postgresql.JSONB(), nullable=True))
    op.add_column('messages', sa.Column('tool_input', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'tool_input')
    op.drop_column('messages', 'tool_result')
    op.drop_column('messages', 'tool_state')
    # Note: Cannot remove enum value in PostgreSQL
```

**Step 3: Verify migration syntax**

Run: `cd api && python -c "from alembic.config import Config; from alembic import command; command.check(Config('alembic.ini'))"`
Expected: No syntax errors

**Step 4: Commit**

```bash
git add api/alembic/versions/
git commit -m "migration: add tool_call message fields"
```

---

## Task 4: Update MessagePublic Contract

**Files:**
- Modify: `api/src/models/contracts/agents.py:204-229`

**Step 1: Add tool state fields to MessagePublic**

```python
class MessagePublic(BaseModel):
    """Message output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    execution_id: str | None = Field(default=None, description="Execution ID for tool results (for fetching logs)")
    # New fields for TOOL_CALL messages
    tool_state: Literal["running", "completed", "error"] | None = Field(default=None, description="Tool execution state")
    tool_result: Any | None = Field(default=None, description="Result from tool execution")
    tool_input: dict[str, Any] | None = Field(default=None, description="Input arguments for tool call")
    token_count_input: int | None = None
    token_count_output: int | None = None
    model: str | None = None
    duration_ms: int | None = None
    sequence: int
    created_at: datetime

    @field_serializer("id", "conversation_id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)

    @field_serializer("created_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()
```

**Step 2: Run type check**

Run: `cd api && pyright src/models/contracts/agents.py`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/models/contracts/agents.py
git commit -m "feat(chat): add tool_state, tool_result, tool_input to MessagePublic"
```

---

## Task 5: Update AgentExecutor to Save Tool Calls as Messages

**Files:**
- Modify: `api/src/services/agent_executor.py:336-411`

**Step 1: Refactor tool call saving**

Replace the current tool call loop (lines 361-411) with:

```python
                # Execute tools and add results to history
                for tc in collected_tool_calls:
                    tool_call = ToolCall(
                        id=tc.id,
                        name=tc.name,
                        arguments=tc.arguments,
                    )
                    final_tool_calls.append(tool_call)

                    # Generate execution_id for this tool call
                    execution_id = str(uuid4())

                    # Save TOOL_CALL message with state "running"
                    tool_call_msg = await self._save_message(
                        conversation_id=conversation.id,
                        role=MessageRole.TOOL_CALL,
                        tool_name=tc.name,
                        tool_input=tc.arguments,
                        tool_state="running",
                        tool_call_id=tc.id,
                        execution_id=execution_id,
                    )

                    # Emit tool_call event with message ID
                    if stream:
                        yield ChatStreamChunk(
                            type="tool_call",
                            tool_call=tool_call,
                            execution_id=execution_id,
                            message_id=str(tool_call_msg.id),
                        )

                    # Emit running status
                    if stream:
                        yield ChatStreamChunk(
                            type="tool_progress",
                            tool_progress=ToolProgress(
                                tool_call_id=tc.id,
                                execution_id=execution_id,
                                status="running",
                            ),
                        )

                    # Execute the tool
                    tool_result = await self._execute_tool(tc, agent, conversation, execution_id=execution_id)

                    # Update TOOL_CALL message with result and state
                    await self._update_tool_call_message(
                        message_id=tool_call_msg.id,
                        tool_state="completed" if not tool_result.error else "error",
                        tool_result=tool_result.result if not tool_result.error else {"error": tool_result.error},
                        duration_ms=tool_result.duration_ms,
                    )

                    if stream:
                        yield ChatStreamChunk(
                            type="tool_result",
                            tool_result=tool_result,
                            message_id=str(tool_call_msg.id),
                        )

                    # Still save TOOL message for Anthropic API compatibility (history reconstruction)
                    await self._save_message(
                        conversation_id=conversation.id,
                        role=MessageRole.TOOL,
                        content=_serialize_for_json(tool_result.result) if tool_result.result else tool_result.error,
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        execution_id=execution_id,
                        duration_ms=tool_result.duration_ms,
                    )

                    # Add tool result to message history for LLM
                    messages.append(
                        LLMMessage(
                            role="tool",
                            content=_serialize_for_json(tool_result.result) if tool_result.result else tool_result.error,
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                        )
                    )
```

**Step 2: Add _update_tool_call_message method**

Add after `_save_message` method (around line 880):

```python
    async def _update_tool_call_message(
        self,
        message_id: UUID,
        tool_state: str,
        tool_result: Any | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update a TOOL_CALL message with execution result."""
        result = await self.session.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one()
        message.tool_state = tool_state
        message.tool_result = tool_result
        message.duration_ms = duration_ms
        await self.session.flush()
```

**Step 3: Remove the intermediate assistant message save**

Delete or comment out lines 341-349 (the save that bundles tool_calls on assistant message). The assistant messages with text content are still saved at the end, but tool_calls are now separate TOOL_CALL messages.

Actually, we need to keep the assistant message for LLM history reconstruction. But we should remove tool_calls from it since they're now separate messages. Update lines 337-349:

```python
                # Save assistant message (text only, tool calls are separate messages now)
                if collected_content:
                    await self._save_message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=collected_content,
                        token_count_input=chunk_input_tokens,
                        token_count_output=chunk_output_tokens,
                        model=llm_client.model_name,
                    )
```

Wait, this breaks LLM history reconstruction. Let me reconsider...

The assistant message with `tool_calls` is needed for Anthropic API. We should keep saving it, but the frontend ignores the `tool_calls` array and instead renders the TOOL_CALL messages.

So the change is: keep the existing save, but ALSO create TOOL_CALL messages. The frontend will render TOOL_CALL messages instead of parsing tool_calls from assistant messages.

**Step 3 (revised): Keep existing assistant message save, add TOOL_CALL messages**

The loop already saves assistant messages with tool_calls. Keep that. The new code in Step 1 adds TOOL_CALL messages. The frontend will filter by role.

**Step 4: Run type check**

Run: `cd api && pyright src/services/agent_executor.py`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/agent_executor.py
git commit -m "feat(chat): save tool calls as separate TOOL_CALL messages"
```

---

## Task 6: Update ChatStreamChunk to Include message_id on tool Events

**Files:**
- Modify: `api/src/models/contracts/agents.py:284-339`

**Step 1: Verify message_id field exists on ChatStreamChunk**

The `message_id` field already exists (line 319). Verify it can be used for tool_call and tool_result events.

No changes needed - the field is already present.

**Step 2: Commit (if any changes)**

Skip if no changes.

---

## Task 7: Regenerate TypeScript Types

**Files:**
- Regenerate: `client/src/lib/v1.d.ts`

**Step 1: Ensure dev stack is running**

Run: `docker ps --filter "name=bifrost" | grep bifrost-dev-api`
If not running: `./debug.sh`

**Step 2: Regenerate types**

Run: `cd client && npm run generate:types`

**Step 3: Verify new types**

Check that `v1.d.ts` contains:
- `MessageRole` includes `"tool_call"`
- `MessagePublic` has `tool_state`, `tool_result`, `tool_input`

**Step 4: Commit**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore: regenerate TypeScript types for tool_call messages"
```

---

## Task 8: Simplify useChatStream Hook

**Files:**
- Modify: `client/src/hooks/useChatStream.ts:183-219`

**Step 1: Update tool_call handler**

Replace the current tool_call handler (lines 183-200) with:

```typescript
case "tool_call":
    if (chunk.tool_call && chunk.message_id) {
        const convId = currentConversationIdRef.current;
        if (convId) {
            // Add TOOL_CALL message directly
            const toolCallMessage: UnifiedMessage = {
                id: chunk.message_id,
                conversation_id: convId,
                role: "tool_call",
                content: null,
                tool_name: chunk.tool_call.name,
                tool_input: chunk.tool_call.arguments,
                tool_state: "running",
                tool_call_id: chunk.tool_call.id,
                execution_id: chunk.execution_id || null,
                sequence: Date.now(),
                created_at: new Date().toISOString(),
            };
            addMessage(convId, toolCallMessage);
        }
    }
    break;
```

**Step 2: Update tool_result handler**

Replace the current tool_result handler (lines 209-211) with:

```typescript
case "tool_result":
    if (chunk.tool_result && chunk.message_id) {
        const convId = currentConversationIdRef.current;
        if (convId) {
            // Update the TOOL_CALL message with result
            useChatStore.getState().updateMessage(convId, chunk.message_id, {
                tool_state: chunk.tool_result.error ? "error" : "completed",
                tool_result: chunk.tool_result.error
                    ? { error: chunk.tool_result.error }
                    : chunk.tool_result.result,
                duration_ms: chunk.tool_result.duration_ms,
            });
        }
    }
    break;
```

**Step 3: Remove tool_progress handler (or keep for logs)**

The tool_progress handler can remain for log streaming if needed, but it no longer needs to update a separate tracking structure.

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 5: Commit**

```bash
git add client/src/hooks/useChatStream.ts
git commit -m "feat(chat): update useChatStream to handle tool_call messages directly"
```

---

## Task 9: Simplify ChatWindow Rendering

**Files:**
- Modify: `client/src/components/chat/ChatWindow.tsx`

**Step 1: Remove MessageWithToolCards complexity**

Replace the `MessageWithToolCards` component (lines 32-139) with a simpler approach. Actually, we can keep it but simplify the logic significantly.

**Step 2: Update timeline filtering**

Replace lines 232-265 with:

```typescript
const timeline = useMemo<TimelineItem[]>(() => {
    const items: TimelineItem[] = [];

    for (const msg of messages) {
        // Skip tool result messages (role: "tool") - they're for API compatibility only
        if (msg.role === "tool") {
            continue;
        }
        items.push({
            type: "message",
            data: msg,
            timestamp: msg.created_at,
        });
    }

    // Add system events
    for (const event of systemEvents) {
        items.push({
            type: "event",
            data: event,
            timestamp: event.timestamp,
        });
    }

    // Sort by timestamp
    items.sort(
        (a, b) =>
            new Date(a.timestamp).getTime() -
            new Date(b.timestamp).getTime(),
    );

    return items;
}, [messages, systemEvents]);
```

**Step 3: Update message rendering**

Replace the timeline rendering (lines 352-371) with:

```typescript
{timeline.map((item) => {
    if (item.type === "event") {
        return <ChatSystemEvent key={item.data.id} event={item.data} />;
    }

    const msg = item.data;

    // Render tool_call messages with ToolExecutionBadge
    if (msg.role === "tool_call") {
        return (
            <ToolCallMessage
                key={msg.id}
                message={msg}
            />
        );
    }

    // Render user/assistant messages normally
    return (
        <ChatMessage
            key={msg.id}
            message={msg}
            onToolCallClick={onToolCallClick}
            isStreaming={
                (msg as UnifiedMessage).isStreaming ||
                msg.id === streamingMessageId
            }
        />
    );
})}
```

**Step 4: Run type check and lint**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 5: Commit**

```bash
git add client/src/components/chat/ChatWindow.tsx
git commit -m "feat(chat): simplify ChatWindow to render tool_call messages directly"
```

---

## Task 10: Create ToolCallMessage Component

**Files:**
- Create: `client/src/components/chat/ToolCallMessage.tsx`

**Step 1: Create the component**

```typescript
/**
 * ToolCallMessage Component
 *
 * Renders a tool_call message with its state and result.
 */

import type { components } from "@/lib/v1";
import { ToolExecutionBadge } from "./ToolExecutionBadge";
import { ToolExecutionGroup } from "./ToolExecutionGroup";

type MessagePublic = components["schemas"]["MessagePublic"];

interface ToolCallMessageProps {
    message: MessagePublic;
}

export function ToolCallMessage({ message }: ToolCallMessageProps) {
    // Map tool_state to ToolExecutionBadge status
    const status = message.tool_state === "completed"
        ? "success"
        : message.tool_state === "error"
        ? "failed"
        : "pending";

    return (
        <ToolExecutionGroup>
            <ToolExecutionBadge
                toolCall={{
                    id: message.tool_call_id || message.id,
                    name: message.tool_name || "unknown",
                    arguments: message.tool_input || {},
                }}
                status={status}
                result={message.tool_result}
                error={message.tool_state === "error" ? message.tool_result?.error : undefined}
                durationMs={message.duration_ms || undefined}
            />
        </ToolExecutionGroup>
    );
}
```

**Step 2: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 3: Commit**

```bash
git add client/src/components/chat/ToolCallMessage.tsx
git commit -m "feat(chat): add ToolCallMessage component for tool_call rendering"
```

---

## Task 11: Remove toolExecutionsByConversation from Chat Store

**Files:**
- Modify: `client/src/stores/chatStore.ts`

**Step 1: Remove toolExecutionsByConversation state**

Remove from `ChatState` interface (lines 46-51):

```typescript
// DELETE THESE LINES:
// Persisted tool executions per conversation (keyed by tool_call_id)
// This allows us to show execution details after streaming completes
toolExecutionsByConversation: Record<
    string,
    Record<string, ToolExecutionState>
>;
```

**Step 2: Remove from initialState**

Remove from `initialState` (around line 148):

```typescript
// DELETE THIS LINE:
toolExecutionsByConversation: {},
```

**Step 3: Remove related actions**

Remove `saveToolExecutions` and `getToolExecution` from `ChatActions` interface and implementation.

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS (with some errors in files still using these - fix in next steps)

**Step 5: Commit**

```bash
git add client/src/stores/chatStore.ts
git commit -m "refactor(chat): remove toolExecutionsByConversation from store"
```

---

## Task 12: Update chat-utils.ts

**Files:**
- Modify: `client/src/lib/chat-utils.ts`

**Step 1: Add tool fields to UnifiedMessage interface**

Update the interface (lines 13-17):

```typescript
export interface UnifiedMessage extends MessagePublic {
    isStreaming?: boolean;
    isOptimistic?: boolean;
    isFinal?: boolean;
    // Tool call fields (for role: "tool_call")
    tool_state?: "running" | "completed" | "error";
    tool_result?: unknown;
    tool_input?: Record<string, unknown>;
}
```

**Step 2: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 3: Commit**

```bash
git add client/src/lib/chat-utils.ts
git commit -m "feat(chat): add tool fields to UnifiedMessage interface"
```

---

## Task 13: Clean Up Unused Imports and Code

**Files:**
- Modify: `client/src/components/chat/ChatWindow.tsx`

**Step 1: Remove MessageWithToolCards if no longer used**

If the simplified rendering doesn't use `MessageWithToolCards`, remove the component definition (lines 32-139).

**Step 2: Remove unused imports**

Remove any imports that are no longer needed (e.g., `getToolExecution` from store).

**Step 3: Run lint**

Run: `cd client && npm run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add client/src/components/chat/ChatWindow.tsx
git commit -m "refactor(chat): remove unused MessageWithToolCards and imports"
```

---

## Task 14: Run Full Test Suite

**Files:**
- Test: All modified files

**Step 1: Run backend tests**

Run: `./test.sh`
Expected: All tests pass

**Step 2: Run frontend type check and lint**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 3: Run backend type check and lint**

Run: `cd api && pyright && ruff check .`
Expected: PASS

**Step 4: Commit any fixes**

If tests fail, fix and commit.

---

## Task 15: Manual Testing

**Step 1: Start dev stack**

Run: `./debug.sh`

**Step 2: Test single tool call**

1. Send a message that triggers one tool
2. Verify tool message appears with "running" state (spinner)
3. Verify tool message updates to "completed" (green) when done
4. Verify response text appears as separate message
5. Verify no duplicates

**Step 3: Test multiple tool calls**

1. Send a message that triggers multiple tools
2. Verify each tool has its own message
3. Verify tools update independently
4. Verify final response appears after all tools complete

**Step 4: Test page refresh**

1. Trigger a tool call, wait for completion
2. Refresh the page
3. Verify tool call messages load correctly with saved state

**Step 5: Document any issues**

Note any bugs found for follow-up fixes.

---

## Verification Checklist

- [ ] `cd api && pyright` - no errors
- [ ] `cd api && ruff check .` - no errors
- [ ] `cd client && npm run tsc` - no errors
- [ ] `cd client && npm run lint` - no errors
- [ ] `./test.sh` - all tests pass
- [ ] Manual test: single tool call works
- [ ] Manual test: multiple tool calls work
- [ ] Manual test: page refresh preserves state
- [ ] No duplicate tool rendering
- [ ] Tool state updates in real-time

---

## Rollback Plan

If issues are found after deployment:

1. The `role: "tool"` messages are still being saved, so API compatibility is maintained
2. Frontend can be reverted to read from `tool_calls` array on assistant messages
3. Database migration only adds columns (no data loss on rollback)
