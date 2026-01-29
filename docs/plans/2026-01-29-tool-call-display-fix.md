# Tool Call Display Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix tool call display to match Claude Code/Happy pattern - tools appear inline where they happen, grouped horizontally, persisting after refresh.

**Architecture:** Backend saves each text segment as a separate assistant message before tool calls execute. Frontend groups consecutive tool_call messages and renders them horizontally. Tool badges removed from assistant messages (single source of truth).

**Tech Stack:** Python (FastAPI, SQLAlchemy), TypeScript (React, Zustand)

---

## Task 1: Backend - Save Text Before Tools as Separate Message

**Files:**
- Modify: `api/src/services/agent_executor.py:339-352`

**Step 1: Read current implementation**

Read lines 334-365 to understand the current flow where text and tool_calls are saved together.

**Step 2: Modify to save text separately**

Replace lines 339-352:

```python
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
```

With:

```python
                # If no tool calls, we're done
                if not collected_tool_calls:
                    final_content = collected_content
                    break

                # Save text content as its own message BEFORE tools (no tool_calls embedded)
                # This ensures text appears before tools in timeline after refresh
                if collected_content:
                    text_msg = await self._save_message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=collected_content,
                        token_count_input=chunk_input_tokens,
                        token_count_output=chunk_output_tokens,
                        model=llm_client.model_name,
                    )
                    if stream:
                        yield ChatStreamChunk(
                            type="assistant_message_end",
                            message_id=str(text_msg.id),
                        )
```

**Step 3: Update LLM message history**

After the new code above, update the messages.append call (around line 354-361):

```python
                # Add assistant message to history (text + tool_calls for LLM context)
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=collected_content if collected_content else None,
                        tool_calls=collected_tool_calls,
                    )
                )
```

This keeps the LLM history correct while storing messages separately.

**Step 4: Run type check**

Run: `cd api && pyright src/services/agent_executor.py`
Expected: PASS (no new errors)

**Step 5: Commit**

```bash
git add api/src/services/agent_executor.py
git commit -m "feat(chat): save text segments before tools as separate messages"
```

---

## Task 2: Frontend - Handle assistant_message_end Event

**Files:**
- Modify: `client/src/hooks/useChatStream.ts:251-257`

**Step 1: Read current assistant_message_end handler**

Read lines 251-257 to see the current no-op handler.

**Step 2: Implement the handler**

Replace the current handler:

```typescript
			case "assistant_message_end":
				// Message segment is starting - nothing to do, message is already being built
				break;
```

With:

```typescript
			case "assistant_message_end": {
				// Text segment complete - finalize current message
				// Next delta will create a NEW message
				const convId = currentConversationIdRef.current;
				if (convId) {
					const streamingId = useChatStore.getState().streamingMessageIds[convId];
					if (streamingId) {
						useChatStore.getState().updateMessage(convId, streamingId, {
							isStreaming: false,
							isFinal: true,
						});
						useChatStore.getState().setStreamingMessageIdForConversation(convId, null);
					}
				}
				break;
			}
```

**Step 3: Update delta handler to create new message when needed**

Read lines 184-205 (delta handler). Replace with:

```typescript
			case "delta":
				if (chunk.content) {
					const convId = currentConversationIdRef.current;
					if (!convId) break;

					let streamingId = useChatStore.getState().streamingMessageIds[convId];

					// If no streaming message exists (after assistant_message_end), create new one
					if (!streamingId) {
						const newMessageId = generateMessageId();
						const newAssistantMessage: UnifiedMessage = {
							id: newMessageId,
							conversation_id: convId,
							role: "assistant",
							content: chunk.content,
							sequence: Date.now(),
							created_at: new Date().toISOString(),
							isStreaming: true,
							isOptimistic: false,
						};
						addMessage(convId, newAssistantMessage);
						useChatStore.getState().setStreamingMessageIdForConversation(convId, newMessageId);
					} else {
						// Append to existing streaming message
						const currentMessages = useChatStore.getState().messagesByConversation[convId] || [];
						const currentMsg = currentMessages.find((m) => m.id === streamingId);
						useChatStore.getState().updateMessage(convId, streamingId, {
							content: (currentMsg?.content || "") + chunk.content,
						});
					}
				}
				break;
```

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 5: Commit**

```bash
git add client/src/hooks/useChatStream.ts
git commit -m "feat(chat): handle assistant_message_end to split text segments"
```

---

## Task 3: Frontend - Remove Tool Badges from ChatMessage

**Files:**
- Modify: `client/src/components/chat/ChatMessage.tsx:301-318`

**Step 1: Read current tool badges code**

Read lines 300-320 to see the tool_calls badge rendering.

**Step 2: Delete the tool badges section**

Remove lines 301-318:

```typescript
			{/* Tool Calls - inline badges (hidden when cards are rendered separately) */}
			{!hideToolBadges &&
				message.tool_calls &&
				message.tool_calls.length > 0 && (
					<div className="mt-3 flex flex-wrap gap-2">
						{message.tool_calls.map((tc) => (
							<Badge
								key={tc.id}
								variant="secondary"
								className="cursor-pointer hover:bg-secondary/80 transition-colors"
								onClick={() => onToolCallClick?.(tc)}
							>
								<Wrench className="h-3 w-3 mr-1" />
								{tc.name}
							</Badge>
						))}
					</div>
				)}
```

**Step 3: Remove unused imports and props**

Remove `Wrench` from imports (line 9) if no longer used.
Remove `hideToolBadges` from props interface (line 83) and destructuring (line 90).

**Step 4: Run type check and lint**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 5: Commit**

```bash
git add client/src/components/chat/ChatMessage.tsx
git commit -m "refactor(chat): remove tool badges from ChatMessage - tools are separate messages"
```

---

## Task 4: Frontend - Group Consecutive Tool Calls Horizontally

**Files:**
- Modify: `client/src/components/chat/ChatWindow.tsx:104-142`

**Step 1: Read current timeline creation**

Read lines 104-142 to understand current timeline logic.

**Step 2: Add tool_group type to TimelineItem**

Update the TimelineItem type (around line 105-107):

```typescript
	type TimelineItem =
		| { type: "message"; data: MessagePublic; timestamp: string }
		| { type: "tool_group"; data: MessagePublic[]; timestamp: string }
		| { type: "event"; data: SystemEvent; timestamp: string };
```

**Step 3: Update timeline useMemo to group tools**

Replace the timeline useMemo (lines 109-142):

```typescript
	const timeline = useMemo<TimelineItem[]>(() => {
		const items: TimelineItem[] = [];
		let currentToolGroup: MessagePublic[] = [];

		const flushToolGroup = () => {
			if (currentToolGroup.length > 0) {
				items.push({
					type: "tool_group",
					data: [...currentToolGroup],
					timestamp: currentToolGroup[0].created_at,
				});
				currentToolGroup = [];
			}
		};

		for (const msg of messages) {
			// Skip role: "tool" messages - they're for API compatibility only
			if (msg.role === "tool") {
				continue;
			}

			if (msg.role === "tool_call") {
				currentToolGroup.push(msg);
			} else {
				flushToolGroup();
				items.push({
					type: "message",
					data: msg,
					timestamp: msg.created_at,
				});
			}
		}
		flushToolGroup();

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

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 5: Commit**

```bash
git add client/src/components/chat/ChatWindow.tsx
git commit -m "feat(chat): group consecutive tool_call messages in timeline"
```

---

## Task 5: Frontend - Render Tool Groups Horizontally

**Files:**
- Modify: `client/src/components/chat/ChatWindow.tsx:229-258`
- Import: `ToolExecutionBadge` component

**Step 1: Add import for ToolExecutionBadge**

Add to imports (around line 12):

```typescript
import { ToolExecutionBadge } from "./ToolExecutionBadge";
```

**Step 2: Update timeline rendering to handle tool_group**

Replace the timeline.map section (around lines 229-258):

```typescript
					{timeline.map((item) => {
						if (item.type === "event") {
							return (
								<ChatSystemEvent
									key={item.data.id}
									event={item.data}
								/>
							);
						}

						if (item.type === "tool_group") {
							return (
								<ToolExecutionGroup key={`tools-${item.data[0].id}`}>
									{item.data.map((tc) => (
										<ToolExecutionBadge
											key={tc.id}
											toolCall={{
												id: tc.tool_call_id || tc.id,
												name: tc.tool_name || "unknown",
												arguments: tc.tool_input || {},
											}}
											status={
												tc.tool_state === "completed"
													? "success"
													: tc.tool_state === "error"
														? "failed"
														: "pending"
											}
											result={tc.tool_result}
											error={
												tc.tool_state === "error"
													? (tc.tool_result as { error?: string })?.error
													: undefined
											}
											durationMs={tc.duration_ms || undefined}
										/>
									))}
								</ToolExecutionGroup>
							);
						}

						const msg = item.data;

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

**Step 3: Remove the separate tool_call rendering**

Delete the old tool_call case (if it exists as a separate condition).

**Step 4: Remove ToolCallMessage import**

Remove `import { ToolCallMessage } from "./ToolCallMessage";` from imports (line 12).

**Step 5: Run type check and lint**

Run: `cd client && npm run tsc && npm run lint`
Expected: PASS

**Step 6: Commit**

```bash
git add client/src/components/chat/ChatWindow.tsx
git commit -m "feat(chat): render tool groups horizontally with ToolExecutionBadge"
```

---

## Task 6: Clean Up - Delete ToolCallMessage Component

**Files:**
- Delete: `client/src/components/chat/ToolCallMessage.tsx`

**Step 1: Delete the file**

```bash
rm client/src/components/chat/ToolCallMessage.tsx
```

**Step 2: Run type check to ensure no references**

Run: `cd client && npm run tsc`
Expected: PASS (no import errors)

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(chat): remove ToolCallMessage component - rendering moved to ChatWindow"
```

---

## Task 7: Regenerate TypeScript Types

**Files:**
- Regenerate: `client/src/lib/v1.d.ts`

**Step 1: Ensure dev stack is running**

Run: `docker ps --filter "name=bifrost" | grep bifrost-dev-api`
If not running: `./debug.sh`

**Step 2: Restart API to apply any model changes**

Run: `docker compose -f docker-compose.dev.yml restart api`

**Step 3: Regenerate types**

Run: `cd client && npm run generate:types`

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 5: Commit if types changed**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore: regenerate TypeScript types"
```

---

## Task 8: Full Verification

**Step 1: Run all backend checks**

```bash
cd api && pyright && ruff check .
```

Expected: PASS

**Step 2: Run all frontend checks**

```bash
cd client && npm run tsc && npm run lint
```

Expected: PASS

**Step 3: Manual test - streaming**

1. Open http://localhost:3000
2. Start a conversation with an agent that has tools
3. Ask it to do something that triggers tools
4. Watch the stream: text should appear, then tool card(s) horizontally, then more text below

**Step 4: Manual test - page refresh**

1. After tools complete, refresh the page
2. Verify tools are still positioned inline (not grouped at bottom)

**Step 5: Manual test - multiple simultaneous tools**

1. Ask agent to do something that calls multiple tools at once
2. Verify they appear in a horizontal row

---

## Verification Checklist

- [ ] `cd api && pyright` - no errors
- [ ] `cd api && ruff check .` - no errors
- [ ] `cd client && npm run tsc` - no errors
- [ ] `cd client && npm run lint` - no errors
- [ ] Manual: Tools appear inline during streaming
- [ ] Manual: Tools stay inline after page refresh
- [ ] Manual: Multiple tools appear horizontally
- [ ] Manual: No duplicate tool displays (no badges + cards)
