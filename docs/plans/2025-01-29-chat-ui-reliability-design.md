# Chat UI Reliability Fixes - Design Document

**Date:** 2025-01-29
**Status:** Draft
**Author:** Claude (with Jack)

## Problem Summary

The Bifrost chat UI has several reliability issues:
1. **Tool placement jumping** - Tools appear at bottom during streaming, then jump to top when stream completes
2. **Messages not appearing** - Sometimes messages won't display until another message is typed
3. **Permissions not working** - AskUserQuestion card not appearing reliably (partially due to not using Agent SDK)
4. **Todos not tracking** - Todo list not persisting across refreshes

## Root Cause Analysis

### Issue 1: Tool Placement Jumping

**Current architecture:**
```
timeline (from API)          streaming messages (local)
      ↓                              ↓
[msg1, msg2, msg3]         [completedStreaming, currentStreaming]
      ↓                              ↓
    renders first              renders after timeline
```

When streaming completes, `clearCompletedStreamingMessages()` is called, removing them from the bottom. Then the API returns the message, which gets inserted into `timeline` at the correct chronological position (often near the top, since it's the newest message but sorted by timestamp).

**Reference implementation (Happy - `/Users/jack/GitHub/happy-main/packages`):**
- Messages are NEVER split between "API" and "streaming" arrays
- A single message object is updated in place via reducer
- Tools are rendered inline with their parent message
- Message timestamps are immutable after creation
- Uses `React.memo` on ToolView to prevent re-renders
- Key insight: "NEVER modify message timestamps or core properties after creation"

**Reference implementation (Claudable - `/Users/jack/GitHub/Claudable-main`):**
- Uses `integrateMessages()` function that merges by stable ID
- Tracks `isStreaming`, `isFinal`, `isOptimistic` flags on each message
- Uses content fingerprinting for ID generation when server doesn't provide one
- Maintains a `Map<string, Message>` for O(1) lookups during merge

### Issue 2: Messages Not Appearing

**Current issue:**
- Deduplication uses `content.slice(0, 100)` hash comparison
- Race condition: API message arrives before temp message is cleaned up
- React Query invalidation may be batched, causing stale renders

**Reference implementation (Claudable):**
- Uses multiple deduplication mechanisms: message ID, request ID, content fingerprint
- Tracks message lifecycle explicitly (`pending`, `processed`) via `useRef` Sets
- Uses `isOptimistic` flag to mark client-added messages
- When server confirms, replaces optimistic message by request ID
- Key pattern: `processedMessageIds`, `processedRequestIds`, `pendingMessageIds` refs

### Issue 3: Permissions/AskUserQuestion Not Working

**Current issue:**
- `pendingQuestion` state is local to `useChatStream` hook
- If component unmounts or conversation changes, question disappears
- No persistence mechanism

**Note:** Tool execution permissions (Allow/Deny for dangerous actions) require Agent SDK integration which is out of scope.

### Issue 4: Todos Not Persisting

**Current issue:**
- Todos stored in global Zustand state
- Not associated with conversation
- Lost on page refresh

---

## Proposed Architecture

### Unified Message Model

Replace the split architecture with a single message model that tracks streaming state:

```typescript
interface UnifiedMessage {
  // Identity
  id: string;                    // Stable UUID (from backend or generated)
  requestId?: string;            // Ties user message to response
  conversationId: string;

  // State flags
  isStreaming: boolean;          // Currently being streamed
  isOptimistic: boolean;         // Client-added, not confirmed by server
  isFinal: boolean;              // Streaming complete

  // Content
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: ToolCall[];
  toolExecutions?: Record<string, ToolExecutionState>;

  // Metadata
  createdAt: string;             // IMMUTABLE after creation
  updatedAt: string;
}
```

### Message Integration Flow (adapted from Claudable)

```typescript
function integrateMessages(
  existing: UnifiedMessage[],
  incoming: UnifiedMessage[]
): UnifiedMessage[] {
  const map = new Map<string, UnifiedMessage>();

  // 1. Load existing by stable ID
  existing.forEach(m => map.set(m.id, m));

  // 2. For incoming, check for optimistic replacement
  incoming.forEach(m => {
    if (!m.isOptimistic && m.requestId) {
      // Remove matching optimistic message
      for (const [key, existing] of map) {
        if (existing.requestId === m.requestId && existing.isOptimistic) {
          map.delete(key);
          break;
        }
      }
    }

    // 3. Merge with existing by ID
    const existingMsg = map.get(m.id);
    if (existingMsg) {
      map.set(m.id, mergeMessages(existingMsg, m));
    } else {
      map.set(m.id, m);
    }
  });

  // 4. Sort by createdAt + ID for stability
  return Array.from(map.values()).sort((a, b) => {
    const timeDiff = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
    return timeDiff !== 0 ? timeDiff : a.id.localeCompare(b.id);
  });
}
```

### Stable React Keys

```tsx
// ❌ Current (unstable)
{completedStreamingMessages.map((msg, index) => (
  <StreamingMessageDisplay key={`completed-streaming-${index}`} />
))}

// ✅ Fixed (stable)
{messages.map((msg) => (
  <MessageWithToolCards key={msg.id} message={msg} isStreaming={msg.isStreaming} />
))}
```

### Inline Tool Rendering

```tsx
// ❌ Current: Tools at bottom, separate from message
<>
  {timeline.map(...)}
  {completedStreamingMessages.map(...)}  // Tools jump when this clears
  {streamingMessage && <StreamingMessageDisplay />}
</>

// ✅ Fixed: Tools inline with message, single render pass
{messages.map((msg) => (
  <MessageWithToolCards
    key={msg.id}
    message={msg}
    isStreaming={msg.isStreaming}
  />
))}
```

---

## Key Files to Modify

| File | Changes |
|------|---------|
| `client/src/stores/chatStore.ts` | Unified message model, remove `completedStreamingMessages`, add `updateMessage()` action |
| `client/src/hooks/useChatStream.ts` | Update messages in place by ID, add requestId correlation |
| `client/src/components/chat/ChatWindow.tsx` | Remove separate streaming display, single render loop |
| `client/src/components/chat/MessageWithToolCards.tsx` | Accept `isStreaming` prop for inline streaming UI |
| `client/src/services/websocket.ts` | Add requestId to message payload |
| `api/src/routers/websocket.py` | Echo requestId in chunks (if not already) |

---

## Out of Scope

- Tool execution permissions (Allow/Deny for dangerous tools) - requires Agent SDK
- Multi-transport fallback (WebSocket + SSE) - current WebSocket-only approach is fine
- Todo persistence to backend - can use localStorage as interim solution

---

## Verification Criteria

After implementation:

1. **Tool stability test**: Send message with tool calls, verify tools don't jump position
2. **Message visibility test**: Send rapid messages, verify all appear without typing another
3. **Permission test**: Trigger AskUserQuestion, verify card appears and persists until answered
4. **Streaming test**: Verify streaming cursor appears in correct position throughout
5. **Error test**: Disconnect network during stream, verify partial content preserved
