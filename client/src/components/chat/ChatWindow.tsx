/**
 * ChatWindow Component
 *
 * Main chat message display area with auto-scroll.
 * Shows messages for the active conversation.
 */

import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import { Bot, MessageSquare } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { ToolExecutionCard } from "./ToolExecutionCard";
import { ChatSystemEvent, type SystemEvent } from "./ChatSystemEvent";
import {
	useChatStore,
	useStreamingMessage,
	type StreamingMessage,
} from "@/stores/chatStore";
import { useMessages } from "@/hooks/useChat";
import { useChatStream } from "@/hooks/useChatStream";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/v1";

type MessagePublic = components["schemas"]["MessagePublic"];
type ToolCall = components["schemas"]["ToolCall"];

// Stable empty array to prevent re-render loops in Zustand selectors
const EMPTY_MESSAGES: MessagePublic[] = [];
const EMPTY_EVENTS: SystemEvent[] = [];

/** Helper component to render streaming message without Date.now() in render */
function StreamingMessageDisplay({
	conversationId,
	streamingMessage,
	onToolCallClick,
}: {
	conversationId: string;
	streamingMessage: StreamingMessage;
	onToolCallClick?: (toolCall: ToolCall) => void;
}) {
	// Use state to hold stable timestamp values
	const [timestamp] = useState(() => ({
		sequence: Date.now(),
		created_at: new Date().toISOString(),
	}));

	const hasContent =
		streamingMessage.content && streamingMessage.content.trim().length > 0;
	const toolExecutions = Object.values(streamingMessage.toolExecutions);
	const hasToolExecutions = toolExecutions.length > 0;

	// Create message for text content (without tool_calls - we render those separately)
	const message: MessagePublic = {
		id: "streaming",
		conversation_id: conversationId,
		role: "assistant",
		content: streamingMessage.content || (hasToolExecutions ? "" : "..."),
		sequence: timestamp.sequence,
		created_at: timestamp.created_at,
	};

	return (
		<div className="space-y-3">
			{/* Tool Execution Cards (streaming) */}
			{hasToolExecutions && (
				<div className="px-4 space-y-2">
					{toolExecutions.map((execution) => (
						<ToolExecutionCard
							key={execution.toolCall.id}
							executionId={execution.executionId}
							toolCall={execution.toolCall}
							isStreaming={true}
							streamingState={{
								status: execution.status,
								logs: execution.logs,
								result: execution.result,
								error: execution.error,
								durationMs: execution.durationMs,
							}}
						/>
					))}
				</div>
			)}

			{/* Text Content */}
			{(hasContent || !hasToolExecutions) && (
				<ChatMessage
					message={message}
					isStreaming={
						!hasToolExecutions || !streamingMessage.content
					}
					onToolCallClick={onToolCallClick}
				/>
			)}
		</div>
	);
}

/** Helper component to render a message with its tool execution cards */
function MessageWithToolCards({
	message,
	toolResultMessages,
	conversationId,
	onToolCallClick,
}: {
	message: MessagePublic;
	/** Map of tool_call_id -> tool result message (for getting execution_id) */
	toolResultMessages: Map<string, MessagePublic>;
	/** Conversation ID for retrieving saved tool execution state */
	conversationId: string;
	onToolCallClick?: (toolCall: ToolCall) => void;
}) {
	// Get saved tool executions for this conversation
	const getToolExecution = useChatStore((state) => state.getToolExecution);

	// Check if this message has tool calls
	const hasToolCalls = message.tool_calls && message.tool_calls.length > 0;
	if (!hasToolCalls) {
		return (
			<ChatMessage message={message} onToolCallClick={onToolCallClick} />
		);
	}

	return (
		<div className="space-y-3">
			{/* Tool Execution Cards - rendered above the text content */}
			<div className="px-4 space-y-2">
				{message.tool_calls!.map((tc) => {
					// Get the tool result message for this tool call
					const resultMsg = toolResultMessages.get(tc.id);

					// Get execution_id from the tool result message
					// Cast needed until types are regenerated after migration
					const executionId =
						(
							resultMsg as
								| { execution_id?: string | null }
								| undefined
						)?.execution_id ?? undefined;

					// Get saved tool execution state (persisted after streaming completes)
					const savedExecution = getToolExecution(
						conversationId,
						tc.id,
					);

					return (
						<ToolExecutionCard
							key={tc.id}
							executionId={executionId}
							toolCall={tc}
							execution={savedExecution}
							hasResultMessage={!!resultMsg}
						/>
					);
				})}
			</div>

			{/* Message text content (if any) */}
			{message.content && message.content.trim().length > 0 && (
				<ChatMessage
					message={message}
					onToolCallClick={onToolCallClick}
				/>
			)}
		</div>
	);
}

interface ChatWindowProps {
	conversationId: string | undefined;
	agentName?: string | null;
	onToolCallClick?: (toolCall: ToolCall) => void;
}

// Threshold in pixels - if within this distance from bottom, consider "at bottom"
const SCROLL_THRESHOLD = 100;

export function ChatWindow({
	conversationId,
	agentName,
	onToolCallClick,
}: ChatWindowProps) {
	const messagesEndRef = useRef<HTMLDivElement>(null);
	const containerRef = useRef<HTMLDivElement>(null);

	// Track if user is at bottom of scroll area (for smart auto-scroll)
	const [isAtBottom, setIsAtBottom] = useState(true);

	// Check if scrolled to bottom
	const checkIfAtBottom = useCallback(() => {
		const container = containerRef.current;
		if (!container) return true;
		const { scrollTop, scrollHeight, clientHeight } = container;
		return scrollHeight - scrollTop - clientHeight < SCROLL_THRESHOLD;
	}, []);

	// Handle scroll events to track user position
	const handleScroll = useCallback(() => {
		setIsAtBottom(checkIfAtBottom());
	}, [checkIfAtBottom]);

	// Get messages from API and local cache
	const { data: apiMessages, isLoading: isLoadingMessages } =
		useMessages(conversationId);
	const localMessages = useChatStore(
		(state) =>
			(conversationId && state.messagesByConversation[conversationId]) ||
			EMPTY_MESSAGES,
	);
	const systemEvents = useChatStore(
		(state) =>
			(conversationId &&
				state.systemEventsByConversation[conversationId]) ||
			EMPTY_EVENTS,
	);
	const streamingMessage = useStreamingMessage();

	// Use WebSocket streaming
	const { sendMessage, isStreaming } = useChatStream({
		conversationId,
		onError: (error) => {
			console.error("[ChatWindow] Stream error:", error);
		},
	});

	// Merge API and local messages, avoiding duplicates
	const messages = useMemo(() => {
		// If we have API messages, use those as the source of truth
		if (apiMessages && apiMessages.length > 0) {
			// Only keep local messages that are:
			// 1. Still pending (temp-*) AND not yet in API (by content match)
			// 2. Have a completed-* ID not yet in API (rare race condition)
			const apiIds = new Set(apiMessages.map((m) => m.id));

			// Create a content+role hash for deduplication
			const apiContentHashes = new Set(
				apiMessages.map(
					(m) => `${m.role}:${m.content?.slice(0, 100) || ""}`,
				),
			);

			const localOnly = localMessages.filter((m) => {
				// If it's already in API by ID, skip it
				if (apiIds.has(m.id)) {
					return false;
				}

				// For temp/completed messages, check if content already exists in API
				if (m.id.startsWith("temp-") || m.id.startsWith("completed-")) {
					const contentHash = `${m.role}:${m.content?.slice(0, 100) || ""}`;
					// If same content already in API, skip (it's a duplicate)
					if (apiContentHashes.has(contentHash)) {
						return false;
					}
				}

				return true;
			});

			return [...apiMessages, ...localOnly];
		}
		return localMessages;
	}, [apiMessages, localMessages]);

	// Build a map of tool_call_id -> tool result message for reconstructing state
	const toolResultMessages = useMemo(() => {
		const map = new Map<string, MessagePublic>();
		for (const msg of messages) {
			// Tool result messages have tool_call_id set
			if (msg.tool_call_id) {
				map.set(msg.tool_call_id, msg);
			}
		}
		return map;
	}, [messages]);

	// Create a unified timeline of messages and system events
	type TimelineItem =
		| { type: "message"; data: MessagePublic; timestamp: string }
		| { type: "event"; data: SystemEvent; timestamp: string };

	const timeline = useMemo<TimelineItem[]>(() => {
		const items: TimelineItem[] = [];

		// Add messages (but filter out tool result messages - they render as part of tool cards)
		for (const msg of messages) {
			// Skip tool result messages - they're rendered as part of ToolExecutionCard
			if (msg.tool_call_id) {
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

	// Clean up local messages once API has the authoritative data
	// This prevents accumulation of temp-*/completed-* messages that could cause ordering issues
	const clearMessages = useChatStore((state) => state.clearMessages);
	const setMessages = useChatStore((state) => state.setMessages);
	useEffect(() => {
		if (!conversationId || !apiMessages || apiMessages.length === 0) return;

		// Only keep local messages that are:
		// 1. Currently being streamed (temp-* for user input not yet confirmed)
		// 2. Not matching any API message content
		const apiContentHashes = new Set(
			apiMessages.map(
				(m) => `${m.role}:${m.content?.slice(0, 100) || ""}`,
			),
		);

		const pendingMessages = localMessages.filter((m) => {
			// Keep temp messages that are NOT in API yet (user just sent)
			if (m.id.startsWith("temp-")) {
				const contentHash = `${m.role}:${m.content?.slice(0, 100) || ""}`;
				return !apiContentHashes.has(contentHash);
			}
			// Discard all completed-* messages (they should be in API now)
			if (m.id.startsWith("completed-")) {
				return false;
			}
			// Keep any other local messages
			return true;
		});

		// Only update if there's something to clean up
		if (pendingMessages.length !== localMessages.length) {
			setMessages(conversationId, pendingMessages);
		}
	}, [
		conversationId,
		apiMessages,
		localMessages,
		setMessages,
		clearMessages,
	]);

	// Auto-scroll to bottom on new messages or events (only if user is at bottom)
	useEffect(() => {
		if (isAtBottom) {
			messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
		}
	}, [timeline, streamingMessage?.content, isAtBottom]);

	// Handle send message
	const handleSendMessage = (message: string) => {
		sendMessage(message);
	};

	// Empty state
	if (!conversationId) {
		return (
			<div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-8">
				<MessageSquare className="h-12 w-12 mb-4 opacity-20" />
				<h3 className="text-lg font-medium mb-2">
					Start a conversation
				</h3>
				<p className="text-sm text-center max-w-sm">
					Click "New Chat" to start a conversation. I can help with
					questions, tasks, and more. If you need specialized
					capabilities, I'll find the right tools to help.
				</p>
			</div>
		);
	}

	// Loading state
	if (isLoadingMessages) {
		return (
			<div className="flex-1 flex flex-col">
				<div className="flex-1 p-4 space-y-4">
					{[1, 2, 3].map((i) => (
						<div key={i} className="flex gap-3">
							<Skeleton className="h-8 w-8 rounded-full" />
							<div className="space-y-2 flex-1">
								<Skeleton className="h-4 w-20" />
								<Skeleton className="h-16 w-3/4" />
							</div>
						</div>
					))}
				</div>
				<ChatInput onSend={handleSendMessage} disabled />
			</div>
		);
	}

	// Empty conversation
	if (timeline.length === 0 && !streamingMessage) {
		return (
			<div className="flex-1 flex flex-col">
				<div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-8">
					<Bot className="h-12 w-12 mb-4 opacity-20" />
					<h3 className="text-lg font-medium mb-2">
						{agentName
							? `Chat with ${agentName}`
							: "Start a conversation"}
					</h3>
					<p className="text-sm text-center max-w-sm mb-6">
						Send a message to start the conversation. The AI
						assistant will respond to your questions and help with
						tasks.
					</p>
				</div>
				<ChatInput
					onSend={handleSendMessage}
					placeholder="Send a message..."
				/>
			</div>
		);
	}

	return (
		<div className="flex-1 flex flex-col h-full overflow-hidden">
			{/* Messages Area */}
			<div
				ref={containerRef}
				onScroll={handleScroll}
				className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent"
			>
				<div className="max-w-4xl mx-auto pt-8">
					{timeline.map((item) =>
						item.type === "message" ? (
							<MessageWithToolCards
								key={item.data.id}
								message={item.data}
								toolResultMessages={toolResultMessages}
								conversationId={conversationId}
								onToolCallClick={onToolCallClick}
							/>
						) : (
							<ChatSystemEvent
								key={item.data.id}
								event={item.data}
							/>
						),
					)}

					{/* Streaming Message */}
					{streamingMessage && !streamingMessage.isComplete && (
						<StreamingMessageDisplay
							conversationId={conversationId}
							streamingMessage={streamingMessage}
							onToolCallClick={onToolCallClick}
						/>
					)}

					{/* Streaming Error - now shown inline via system events */}

					<div ref={messagesEndRef} />
				</div>
			</div>

			{/* Input Area */}
			<ChatInput
				onSend={handleSendMessage}
				isLoading={isStreaming}
				placeholder={
					agentName ? `Message ${agentName}...` : "Send a message..."
				}
			/>
		</div>
	);
}
