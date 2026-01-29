# Chat Message Deduplication Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix disappearing first message and duplicate message issues by implementing localId-based deduplication (Happy's pattern).

**Architecture:** Client generates `localId` for optimistic messages, sends it to backend, backend returns it in `message_start`. Client uses `localId` to match optimistic messages to server-confirmed messages, preventing duplicates and disappearances.

**Tech Stack:** TypeScript (React/Zustand), Python (FastAPI/SQLAlchemy), PostgreSQL

---

## Current Problem Flow

```
T1: User sends "Hello" → optimistic message (ID: opt-123) added
T2: message_start received → user_message_id: "srv-789" (DIFFERENT from opt-123)
T3: Can't match opt-123 to srv-789 → duplicates or disappears
```

## Solution Flow

```
T1: User sends "Hello" with localId: "loc-123" → optimistic message (ID: loc-123) added
T2: message_start received → user_message_id: "srv-789", local_id: "loc-123"
T3: Match by localId → replace optimistic with server message, no duplicates
```

---

### Task 1: Add local_id to Message ORM Model

**Files:**
- Modify: `api/src/models/orm/agents.py:217-235`
- Create: `api/alembic/versions/YYYYMMDD_HHMMSS_add_local_id_to_messages.py`

**Step 1: Add local_id field to Message model**

In `api/src/models/orm/agents.py`, after line 224 (execution_id field), add:

```python
    # Client-generated ID for optimistic update reconciliation
    local_id: Mapped[str | None] = mapped_column(String(36), default=None)
```

**Step 2: Create migration**

```bash
cd api && alembic revision -m "add_local_id_to_messages"
```

Edit the generated migration:

```python
"""add_local_id_to_messages

Revision ID: <generated>
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column('messages', sa.Column('local_id', sa.String(36), nullable=True))
    op.create_index('ix_messages_local_id', 'messages', ['local_id'])

def downgrade() -> None:
    op.drop_index('ix_messages_local_id', table_name='messages')
    op.drop_column('messages', 'local_id')
```

**Step 3: Run migration**

```bash
docker restart bifrost-dev-api-1
```

**Step 4: Commit**

```bash
git add api/src/models/orm/agents.py api/alembic/versions/*add_local_id*
git commit -m "feat(db): add local_id to messages for optimistic update reconciliation"
```

---

### Task 2: Update WebSocket to Accept and Return local_id

**Files:**
- Modify: `api/src/routers/websocket.py:400-429`
- Modify: `api/src/services/agent_executor.py:185-197`

**Step 1: Extract local_id from WebSocket message**

In `api/src/routers/websocket.py`, around line 403, change:

```python
            elif data.get("type") == "chat":
                # Handle chat message - process and stream response
                conversation_id = data.get("conversation_id")
                message_text = data.get("message", "")
```

To:

```python
            elif data.get("type") == "chat":
                # Handle chat message - process and stream response
                conversation_id = data.get("conversation_id")
                message_text = data.get("message", "")
                local_id = data.get("local_id")  # Client-generated ID for dedup
```

**Step 2: Pass local_id to _process_chat_message**

Change the asyncio.create_task call (lines 422-429):

```python
                asyncio.create_task(
                    _process_chat_message(
                        websocket=websocket,
                        user=user,
                        conversation_id=conversation_id,
                        message=message_text,
                        local_id=local_id,  # ADD THIS
                    )
                )
```

**Step 3: Update _process_chat_message signature**

In the same file, around line 528, change:

```python
async def _process_chat_message(
    websocket: WebSocket,
    user: UserPrincipal,
    conversation_id: str,
    message: str,
) -> None:
```

To:

```python
async def _process_chat_message(
    websocket: WebSocket,
    user: UserPrincipal,
    conversation_id: str,
    message: str,
    local_id: str | None = None,
) -> None:
```

**Step 4: Pass local_id to executor.chat**

Find where `executor.chat()` is called (around line 577) and add local_id:

```python
            async for chunk in executor.chat(
                agent=conversation.agent,
                conversation=conversation,
                user_message=message,
                stream=True,
                local_id=local_id,  # ADD THIS
            ):
```

**Step 5: Update AgentExecutor.chat signature**

In `api/src/services/agent_executor.py`, find the `chat` method signature and add local_id parameter:

```python
    async def chat(
        self,
        agent: Agent | None,
        conversation: Conversation,
        user_message: str,
        stream: bool = True,
        local_id: str | None = None,  # ADD THIS
    ) -> AsyncIterator[ChatStreamChunk]:
```

**Step 6: Save local_id with user message**

In `_save_message` call for user message (around line 185):

```python
            user_msg = await self._save_message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=user_message,
                local_id=local_id,  # ADD THIS
            )
```

**Step 7: Include local_id in message_start chunk**

Update the ChatStreamChunk yield (around line 193):

```python
            yield ChatStreamChunk(
                type="message_start",
                user_message_id=str(user_msg.id),
                assistant_message_id=str(assistant_message_id),
                local_id=local_id,  # ADD THIS
            )
```

**Step 8: Update _save_message to accept local_id**

In the `_save_message` method signature (around line 859), add:

```python
    async def _save_message(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str | None = None,
        # ... existing params ...
        local_id: str | None = None,  # ADD THIS
    ) -> Message:
```

And in the Message creation inside that method, add:

```python
        message = Message(
            id=message_id or uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            # ... existing fields ...
            local_id=local_id,  # ADD THIS
            sequence=sequence,
        )
```

**Step 9: Commit**

```bash
git add api/src/routers/websocket.py api/src/services/agent_executor.py
git commit -m "feat(api): pass local_id through WebSocket to message storage"
```

---

### Task 3: Update ChatStreamChunk Contract

**Files:**
- Modify: `api/src/models/contracts/agents.py`

**Step 1: Add local_id to ChatStreamChunk**

Find the ChatStreamChunk class and add local_id field:

```python
class ChatStreamChunk(BaseModel):
    """Streaming chat chunk sent to client."""
    type: str  # "message_start", "content_delta", "done", etc.
    # ... existing fields ...
    local_id: str | None = None  # Client-generated ID echoed back for dedup
```

**Step 2: Commit**

```bash
git add api/src/models/contracts/agents.py
git commit -m "feat(contracts): add local_id to ChatStreamChunk"
```

---

### Task 4: Update Client WebSocket to Send local_id

**Files:**
- Modify: `client/src/services/websocket.ts:1384-1395`
- Modify: `client/src/hooks/useChatStream.ts:400-403`

**Step 1: Update sendChatMessage signature**

In `client/src/services/websocket.ts`, change:

```typescript
	sendChatMessage(conversationId: string, message: string): boolean {
		if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
			return false;
		}

		this.ws.send(
			JSON.stringify({
				type: "chat",
				conversation_id: conversationId,
				message,
			}),
		);
```

To:

```typescript
	sendChatMessage(conversationId: string, message: string, localId?: string): boolean {
		if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
			return false;
		}

		this.ws.send(
			JSON.stringify({
				type: "chat",
				conversation_id: conversationId,
				message,
				local_id: localId,
			}),
		);
```

**Step 2: Pass localId from useChatStream**

In `client/src/hooks/useChatStream.ts`, around line 400, change:

```typescript
			const sent = webSocketService.sendChatMessage(
				conversationId,
				message,
			);
```

To:

```typescript
			const sent = webSocketService.sendChatMessage(
				conversationId,
				message,
				userMessageId,  // Pass the localId
			);
```

Also update the retry path (line 407):

```typescript
					webSocketService.sendChatMessage(conversationId, message, userMessageId);
```

**Step 3: Commit**

```bash
git add client/src/services/websocket.ts client/src/hooks/useChatStream.ts
git commit -m "feat(client): send localId with chat messages"
```

---

### Task 5: Update Client to Use local_id for Deduplication

**Files:**
- Modify: `client/src/lib/chat-utils.ts:13-21, 79-122`
- Modify: `client/src/hooks/useChatStream.ts:111-157, 273-282, 384-394`

**Step 1: Add localId to UnifiedMessage type**

In `client/src/lib/chat-utils.ts`, update the interface:

```typescript
export interface UnifiedMessage extends MessagePublic {
  isStreaming?: boolean;
  isOptimistic?: boolean;
  isFinal?: boolean;
  localId?: string;  // ADD THIS - client-generated ID for dedup
  // Tool call fields (for role: "tool_call")
  tool_state?: "running" | "completed" | "error";
  tool_result?: unknown;
  tool_input?: Record<string, unknown>;
}
```

**Step 2: Rewrite integrateMessages for localId-based dedup**

Replace the entire `integrateMessages` function (lines 79-122):

```typescript
/**
 * Integrate incoming messages into existing array
 * - Uses localId for optimistic -> server message reconciliation
 * - Merges by ID for updates
 * - Maintains stable sort order
 */
export function integrateMessages(
  existing: UnifiedMessage[],
  incoming: UnifiedMessage[]
): UnifiedMessage[] {
  const byId = new Map<string, UnifiedMessage>();
  const byLocalId = new Map<string, UnifiedMessage>();

  // 1. Index existing messages
  existing.forEach((m) => {
    byId.set(m.id, m);
    if (m.localId) {
      byLocalId.set(m.localId, m);
    }
  });

  // 2. Process incoming messages
  incoming.forEach((m) => {
    // If incoming has localId matching an existing optimistic message,
    // this is server confirming our optimistic message - remove the optimistic
    if (m.localId && !m.isOptimistic) {
      const optimistic = byLocalId.get(m.localId);
      if (optimistic && optimistic.isOptimistic) {
        byId.delete(optimistic.id);  // Remove optimistic by its temporary ID
        byLocalId.delete(m.localId);
      }
    }

    // Merge or add
    const existingMsg = byId.get(m.id);
    if (existingMsg) {
      byId.set(m.id, mergeMessages(existingMsg, m));
    } else {
      byId.set(m.id, m);
    }

    // Track by localId for future dedup
    if (m.localId) {
      byLocalId.set(m.localId, m);
    }
  });

  // 3. Sort by createdAt + ID for stability
  return Array.from(byId.values()).sort((a, b) => {
    const timeDiff =
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    return timeDiff !== 0 ? timeDiff : a.id.localeCompare(b.id);
  });
}
```

**Step 3: Update optimistic message creation to include localId**

In `client/src/hooks/useChatStream.ts`, around line 384-394, update:

```typescript
			const userMessage: UnifiedMessage = {
				id: userMessageId,
				conversation_id: conversationId,
				role: "user",
				content: message,
				sequence: Date.now(),
				created_at: now,
				isOptimistic: true,
				localId: userMessageId,  // ADD THIS - use same ID as localId
			};
```

**Step 4: Handle local_id in message_start**

In the `message_start` handler (around line 111-157), update to use local_id:

Find where the user message is confirmed and update the message with localId:

```typescript
				case "message_start": {
					const convId = currentConversationIdRef.current;
					if (!convId) break;

					// Get local_id from chunk (echoed back from server)
					const localId = chunk.local_id;

					// If we have a localId, update the optimistic message with server ID
					if (localId && chunk.user_message_id) {
						const messages = useChatStore.getState().messagesByConversation[convId] || [];
						const optimistic = messages.find(m => m.localId === localId && m.isOptimistic);
						if (optimistic) {
							// Replace optimistic with server-confirmed version
							const confirmed: UnifiedMessage = {
								...optimistic,
								id: chunk.user_message_id,
								isOptimistic: false,
								localId: localId,  // Keep localId for reference
							};
							// Update in store
							const updated = messages.map(m =>
								m.localId === localId && m.isOptimistic ? confirmed : m
							);
							useChatStore.getState().setMessages(convId, updated);
						}
					}

					// Create assistant message (rest of existing logic)
					// ...
```

**Step 5: Remove the safety net cleanup**

Delete lines 273-282 (the setTimeout that removes optimistic messages):

```typescript
						// REMOVE THIS ENTIRE BLOCK:
						// Safety net: Clear any stale optimistic user messages after React Query settles.
						// Normally integrateMessages() handles deduplication, but this catches edge cases.
						// const convIdCaptured = convId;
						// setTimeout(() => {
						// 	const msgs = (useChatStore.getState().messagesByConversation[convIdCaptured] || []) as UnifiedMessage[];
						// 	const cleaned = msgs.filter(m => !(m.isOptimistic && m.role === "user"));
						// 	if (cleaned.length !== msgs.length) {
						// 		useChatStore.getState().setMessages(convIdCaptured, cleaned);
						// 	}
						// }, 500);
```

**Step 6: Commit**

```bash
git add client/src/lib/chat-utils.ts client/src/hooks/useChatStream.ts
git commit -m "feat(client): implement localId-based message deduplication"
```

---

### Task 6: Regenerate TypeScript Types

**Files:**
- Regenerate: `client/src/lib/v1.d.ts`

**Step 1: Regenerate types**

```bash
cd client && npm run generate:types
```

**Step 2: Verify local_id is in ChatStreamChunk type**

Check `client/src/lib/v1.d.ts` contains `local_id` in the ChatStreamChunk schema.

**Step 3: Commit**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore: regenerate TypeScript types with local_id"
```

---

### Task 7: Test and Verify

**Step 1: Restart services**

```bash
docker restart bifrost-dev-api-1
```

Wait for Vite to hot-reload client.

**Step 2: Manual test**

1. Open browser to http://localhost:3000
2. Start a new conversation
3. Send first message "Hello"
4. Verify: Message appears immediately and STAYS visible when response comes
5. Send second message "How are you?"
6. Verify: No duplicate appears
7. Verify: Both messages remain stable

**Step 3: Check console for errors**

Open browser DevTools, check for:
- No "TypeError" errors
- No React key warnings
- Messages have correct IDs in network tab

---

## Verification Checklist

- [ ] Migration applied successfully
- [ ] First message doesn't disappear when response arrives
- [ ] Second message doesn't duplicate
- [ ] Messages remain stable throughout conversation
- [ ] No console errors
- [ ] Types regenerated and compile without errors
