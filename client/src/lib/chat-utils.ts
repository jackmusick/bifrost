// client/src/lib/chat-utils.ts
/**
 * Chat message utility functions for unified message model
 */

import type { components } from "@/lib/v1";

type MessagePublic = components["schemas"]["MessagePublic"];

/**
 * Extended message type with streaming state flags
 */
export interface UnifiedMessage extends MessagePublic {
  isStreaming?: boolean;
  isOptimistic?: boolean;
  isFinal?: boolean;
}

/**
 * Generate a stable UUID for client-side messages
 */
export function generateMessageId(): string {
  return crypto.randomUUID();
}

/**
 * Merge two messages, preserving content if incoming is empty
 */
export function mergeMessages(
  existing: UnifiedMessage,
  incoming: UnifiedMessage
): UnifiedMessage {
  // Preserve existing content if incoming is empty
  const shouldKeepExistingContent =
    (!incoming.content || incoming.content.trim().length === 0) &&
    existing.content &&
    existing.content.trim().length > 0;

  // Deep merge tool_calls
  const mergedToolCalls = incoming.tool_calls ?? existing.tool_calls;

  return {
    ...existing,
    ...incoming,
    content: shouldKeepExistingContent ? existing.content : incoming.content,
    tool_calls: mergedToolCalls,
    // Preserve earliest createdAt
    created_at:
      new Date(existing.created_at).getTime() <
      new Date(incoming.created_at).getTime()
        ? existing.created_at
        : incoming.created_at,
    // Use latest streaming state
    isStreaming: incoming.isStreaming ?? existing.isStreaming,
    isFinal: incoming.isFinal ?? existing.isFinal,
    isOptimistic: incoming.isOptimistic ?? existing.isOptimistic,
  };
}

/**
 * Integrate incoming messages into existing array
 * - Handles optimistic -> server message replacement
 * - Merges by ID
 * - Maintains stable sort order
 */
export function integrateMessages(
  existing: UnifiedMessage[],
  incoming: UnifiedMessage[]
): UnifiedMessage[] {
  const map = new Map<string, UnifiedMessage>();

  // 1. Load existing by stable ID
  existing.forEach((m) => map.set(m.id, m));

  // 2. Process incoming messages
  incoming.forEach((m) => {
    // Check for optimistic replacement (same content, user role)
    if (!m.isOptimistic && m.role === "user") {
      // Find and remove matching optimistic message
      for (const [key, existingMsg] of map) {
        if (
          existingMsg.isOptimistic &&
          existingMsg.role === "user" &&
          existingMsg.content === m.content
        ) {
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
    const timeDiff =
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    return timeDiff !== 0 ? timeDiff : a.id.localeCompare(b.id);
  });
}
