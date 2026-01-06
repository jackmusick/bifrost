/**
 * Chat Store - Zustand state management for chat conversations
 *
 * Manages:
 * - Active conversation and agent selection
 * - Messages for conversations (cached locally)
 * - Streaming state for real-time responses
 * - Studio mode for debugging tool calls
 */

import { create } from "zustand";
import type { components } from "@/lib/v1";

import type {
	ToolExecutionState,
	ToolExecutionStatus,
	ToolExecutionLog,
} from "@/components/chat/ToolExecutionCard";
import type { SystemEvent } from "@/components/chat/ChatSystemEvent";
import type { TodoItem } from "@/services/websocket";

// Use generated types from API
type AgentSummary = components["schemas"]["AgentSummary"];
type ConversationSummary = components["schemas"]["ConversationSummary"];
type MessagePublic = components["schemas"]["MessagePublic"];
type ToolCall = components["schemas"]["ToolCall"];

// Re-export types for external use
export type { ToolExecutionState, ToolExecutionStatus, ToolExecutionLog };

// Client-only type for streaming tool results (legacy, kept for compatibility)
interface ToolResult {
	tool_call_id: string;
	tool_name: string;
	result: unknown;
	error?: string | null;
	duration_ms?: number | null;
}

// Streaming message state (building up response)
export interface StreamingMessage {
	content: string;
	toolCalls: ToolCall[];
	toolResults: ToolResult[];
	/** Tool executions with full state (status, logs, results) */
	toolExecutions: Record<string, ToolExecutionState>;
	isComplete: boolean;
	error?: string;
}

interface ChatState {
	// Active selections
	activeConversationId: string | null;
	activeAgentId: string | null;

	// Cached agents and conversations (for quick display)
	agents: AgentSummary[];
	conversations: ConversationSummary[];

	// Messages per conversation (cached locally)
	messagesByConversation: Record<string, MessagePublic[]>;

	// System events per conversation (agent switches, errors, etc.)
	systemEventsByConversation: Record<string, SystemEvent[]>;

	// Persisted tool executions per conversation (keyed by tool_call_id)
	// This allows us to show execution details after streaming completes
	toolExecutionsByConversation: Record<
		string,
		Record<string, ToolExecutionState>
	>;

	// Streaming state
	isStreaming: boolean;
	/** Completed streaming messages (for multi-message responses like coding mode) */
	completedStreamingMessages: StreamingMessage[];
	/** Currently building streaming message */
	streamingMessage: StreamingMessage | null;

	// Studio mode (admin feature for debugging)
	isStudioMode: boolean;
	selectedToolCallId: string | null;

	// Connection state
	isConnected: boolean;
	error: string | null;

	// Todo list from coding mode (SDK's TodoWrite tool)
	todos: TodoItem[];

	// Real message ID for streaming message (from assistant_message_id in message_start)
	// Used for seamless handoff from streaming to API message
	streamingMessageId: string | null;
}

interface ChatActions {
	// Selection actions
	setActiveConversation: (conversationId: string | null) => void;
	setActiveAgent: (agentId: string | null) => void;

	// Data actions
	setAgents: (agents: AgentSummary[]) => void;
	setConversations: (conversations: ConversationSummary[]) => void;
	addConversation: (conversation: ConversationSummary) => void;
	removeConversation: (conversationId: string) => void;
	updateConversation: (conversation: ConversationSummary) => void;

	// Message actions
	setMessages: (conversationId: string, messages: MessagePublic[]) => void;
	addMessage: (conversationId: string, message: MessagePublic) => void;
	clearMessages: (conversationId: string) => void;

	// System event actions
	addSystemEvent: (conversationId: string, event: SystemEvent) => void;
	clearSystemEvents: (conversationId: string) => void;

	// Tool execution persistence actions
	saveToolExecutions: (
		conversationId: string,
		toolExecutions: Record<string, ToolExecutionState>,
	) => void;
	getToolExecution: (
		conversationId: string,
		toolCallId: string,
	) => ToolExecutionState | undefined;

	// Streaming actions
	startStreaming: () => void;
	appendStreamContent: (content: string) => void;
	addStreamToolCall: (toolCall: ToolCall, executionId?: string) => void;
	updateToolExecutionStatus: (
		toolCallId: string,
		status: ToolExecutionStatus,
	) => void;
	setToolExecutionId: (toolCallId: string, executionId: string) => void;
	addToolExecutionLog: (toolCallId: string, log: ToolExecutionLog) => void;
	addStreamToolResult: (toolResult: ToolResult) => void;
	/** Complete current streaming message and start a new one (for multi-message responses) */
	completeCurrentStreamingMessage: () => void;
	completeStream: (messageId?: string) => void;
	setStreamError: (error: string) => void;
	resetStream: () => void;
	clearCompletedStreamingMessages: () => void;

	// Studio mode actions
	toggleStudioMode: () => void;
	setStudioMode: (enabled: boolean) => void;
	selectToolCall: (toolCallId: string | null) => void;

	// Connection actions
	setConnected: (connected: boolean) => void;
	setError: (error: string | null) => void;

	// Todo list actions
	setTodos: (todos: TodoItem[]) => void;
	clearTodos: () => void;

	// Streaming message ID (for seamless handoff to API message)
	setStreamingMessageId: (id: string | null) => void;

	// Reset
	reset: () => void;
}

type ChatStore = ChatState & ChatActions;

const initialState: ChatState = {
	activeConversationId: null,
	activeAgentId: null,
	agents: [],
	conversations: [],
	systemEventsByConversation: {},
	toolExecutionsByConversation: {},
	messagesByConversation: {},
	isStreaming: false,
	completedStreamingMessages: [],
	streamingMessage: null,
	isStudioMode: false,
	selectedToolCallId: null,
	isConnected: false,
	error: null,
	todos: [],
	streamingMessageId: null,
};

export const useChatStore = create<ChatStore>((set, get) => ({
	...initialState,

	// Selection actions
	setActiveConversation: (conversationId) => {
		set({ activeConversationId: conversationId });

		// Reset streaming state when switching conversations
		if (get().isStreaming) {
			set({
				isStreaming: false,
				streamingMessage: null,
			});
		}
	},

	setActiveAgent: (agentId) => {
		set({ activeAgentId: agentId });
	},

	// Data actions
	setAgents: (agents) => {
		set({ agents });
	},

	setConversations: (conversations) => {
		set({ conversations });
	},

	addConversation: (conversation) => {
		set((state) => ({
			conversations: [conversation, ...state.conversations],
		}));
	},

	removeConversation: (conversationId) => {
		set((state) => {
			const { [conversationId]: _, ...remainingMessages } =
				state.messagesByConversation;
			return {
				conversations: state.conversations.filter(
					(c) => c.id !== conversationId,
				),
				messagesByConversation: remainingMessages,
				// Clear active if this was selected
				activeConversationId:
					state.activeConversationId === conversationId
						? null
						: state.activeConversationId,
			};
		});
	},

	updateConversation: (conversation) => {
		set((state) => ({
			conversations: state.conversations.map((c) =>
				c.id === conversation.id ? conversation : c,
			),
		}));
	},

	// Message actions
	setMessages: (conversationId, messages) => {
		set((state) => ({
			messagesByConversation: {
				...state.messagesByConversation,
				[conversationId]: messages,
			},
		}));
	},

	addMessage: (conversationId, message) => {
		set((state) => ({
			messagesByConversation: {
				...state.messagesByConversation,
				[conversationId]: [
					...(state.messagesByConversation[conversationId] || []),
					message,
				],
			},
		}));
	},

	clearMessages: (conversationId) => {
		set((state) => {
			const { [conversationId]: _, ...remaining } =
				state.messagesByConversation;
			return { messagesByConversation: remaining };
		});
	},

	// System event actions
	addSystemEvent: (conversationId, event) => {
		set((state) => ({
			systemEventsByConversation: {
				...state.systemEventsByConversation,
				[conversationId]: [
					...(state.systemEventsByConversation[conversationId] || []),
					event,
				],
			},
		}));
	},

	clearSystemEvents: (conversationId) => {
		set((state) => {
			const { [conversationId]: _, ...remaining } =
				state.systemEventsByConversation;
			return { systemEventsByConversation: remaining };
		});
	},

	// Tool execution persistence actions
	saveToolExecutions: (conversationId, toolExecutions) => {
		set((state) => ({
			toolExecutionsByConversation: {
				...state.toolExecutionsByConversation,
				[conversationId]: {
					...(state.toolExecutionsByConversation[conversationId] ||
						{}),
					...toolExecutions,
				},
			},
		}));
	},

	getToolExecution: (conversationId, toolCallId) => {
		return get().toolExecutionsByConversation[conversationId]?.[toolCallId];
	},

	// Streaming actions
	startStreaming: () => {
		set({
			isStreaming: true,
			completedStreamingMessages: [],
			streamingMessage: {
				content: "",
				toolCalls: [],
				toolResults: [],
				toolExecutions: {},
				isComplete: false,
			},
		});
	},

	appendStreamContent: (content) => {
		set((state) => ({
			streamingMessage: state.streamingMessage
				? {
						...state.streamingMessage,
						content: state.streamingMessage.content + content,
					}
				: null,
		}));
	},

	addStreamToolCall: (toolCall, executionId) => {
		set((state) => {
			if (!state.streamingMessage) return {};

			// Create tool execution state
			const toolExecution: ToolExecutionState = {
				toolCall,
				status: "pending",
				executionId,
				logs: [],
				startedAt: new Date().toISOString(),
			};

			return {
				streamingMessage: {
					...state.streamingMessage,
					toolCalls: [...state.streamingMessage.toolCalls, toolCall],
					toolExecutions: {
						...state.streamingMessage.toolExecutions,
						[toolCall.id]: toolExecution,
					},
				},
			};
		});
	},

	updateToolExecutionStatus: (toolCallId, status) => {
		set((state) => {
			// First, try to find in current streaming message
			if (state.streamingMessage) {
				const execution =
					state.streamingMessage.toolExecutions[toolCallId];
				if (execution) {
					return {
						streamingMessage: {
							...state.streamingMessage,
							toolExecutions: {
								...state.streamingMessage.toolExecutions,
								[toolCallId]: {
									...execution,
									status,
								},
							},
						},
					};
				}
			}

			// If not found, search in completed streaming messages
			const completedIndex = state.completedStreamingMessages.findIndex(
				(msg) => msg.toolExecutions[toolCallId],
			);

			if (completedIndex >= 0) {
				const completedMessages = [...state.completedStreamingMessages];
				const msg = completedMessages[completedIndex];
				const execution = msg.toolExecutions[toolCallId];

				completedMessages[completedIndex] = {
					...msg,
					toolExecutions: {
						...msg.toolExecutions,
						[toolCallId]: {
							...execution,
							status,
						},
					},
				};

				return { completedStreamingMessages: completedMessages };
			}

			// Tool not found anywhere
			return {};
		});
	},

	setToolExecutionId: (toolCallId, executionId) => {
		set((state) => {
			// First, try to find in current streaming message
			if (state.streamingMessage) {
				const execution =
					state.streamingMessage.toolExecutions[toolCallId];
				if (execution) {
					return {
						streamingMessage: {
							...state.streamingMessage,
							toolExecutions: {
								...state.streamingMessage.toolExecutions,
								[toolCallId]: {
									...execution,
									executionId,
								},
							},
						},
					};
				}
			}

			// If not found, search in completed streaming messages
			const completedIndex = state.completedStreamingMessages.findIndex(
				(msg) => msg.toolExecutions[toolCallId],
			);

			if (completedIndex >= 0) {
				const completedMessages = [...state.completedStreamingMessages];
				const msg = completedMessages[completedIndex];
				const execution = msg.toolExecutions[toolCallId];

				completedMessages[completedIndex] = {
					...msg,
					toolExecutions: {
						...msg.toolExecutions,
						[toolCallId]: {
							...execution,
							executionId,
						},
					},
				};

				return { completedStreamingMessages: completedMessages };
			}

			// Tool not found anywhere
			return {};
		});
	},

	addToolExecutionLog: (toolCallId, log) => {
		set((state) => {
			// First, try to find in current streaming message
			if (state.streamingMessage) {
				const execution =
					state.streamingMessage.toolExecutions[toolCallId];
				if (execution) {
					return {
						streamingMessage: {
							...state.streamingMessage,
							toolExecutions: {
								...state.streamingMessage.toolExecutions,
								[toolCallId]: {
									...execution,
									status: "running", // Auto-set to running when logs come in
									logs: [...execution.logs, log],
								},
							},
						},
					};
				}
			}

			// If not found, search in completed streaming messages
			const completedIndex = state.completedStreamingMessages.findIndex(
				(msg) => msg.toolExecutions[toolCallId],
			);

			if (completedIndex >= 0) {
				const completedMessages = [...state.completedStreamingMessages];
				const msg = completedMessages[completedIndex];
				const execution = msg.toolExecutions[toolCallId];

				completedMessages[completedIndex] = {
					...msg,
					toolExecutions: {
						...msg.toolExecutions,
						[toolCallId]: {
							...execution,
							status: "running", // Auto-set to running when logs come in
							logs: [...execution.logs, log],
						},
					},
				};

				return { completedStreamingMessages: completedMessages };
			}

			// Tool not found anywhere
			return {};
		});
	},

	addStreamToolResult: (toolResult) => {
		set((state) => {
			if (!state.streamingMessage) return {};

			// Update toolExecutions with result
			const execution =
				state.streamingMessage.toolExecutions[toolResult.tool_call_id];
			const updatedExecutions = execution
				? {
						...state.streamingMessage.toolExecutions,
						[toolResult.tool_call_id]: {
							...execution,
							status: toolResult.error ? "failed" : "success",
							result: toolResult.result,
							error: toolResult.error ?? undefined,
							durationMs: toolResult.duration_ms ?? undefined,
						} as ToolExecutionState,
					}
				: state.streamingMessage.toolExecutions;

			return {
				streamingMessage: {
					...state.streamingMessage,
					toolResults: [
						...state.streamingMessage.toolResults,
						toolResult,
					],
					toolExecutions: updatedExecutions,
				},
			};
		});
	},

	completeCurrentStreamingMessage: () => {
		set((state) => {
			// Only complete if there's content or tools in the current message
			if (
				!state.streamingMessage ||
				(!state.streamingMessage.content &&
					state.streamingMessage.toolCalls.length === 0)
			) {
				return {};
			}

			// Mark current message as complete and add to completed list
			const completedMessage: StreamingMessage = {
				...state.streamingMessage,
				isComplete: true,
			};

			return {
				completedStreamingMessages: [
					...state.completedStreamingMessages,
					completedMessage,
				],
				// Start fresh streaming message
				streamingMessage: {
					content: "",
					toolCalls: [],
					toolResults: [],
					toolExecutions: {},
					isComplete: false,
				},
			};
		});
	},

	completeStream: (_messageId) => {
		set((state) => ({
			isStreaming: false,
			streamingMessage: state.streamingMessage
				? {
						...state.streamingMessage,
						isComplete: true,
					}
				: null,
		}));
	},

	setStreamError: (error) => {
		set((state) => ({
			isStreaming: false,
			streamingMessage: state.streamingMessage
				? {
						...state.streamingMessage,
						isComplete: true,
						error,
					}
				: null,
		}));
	},

	resetStream: () => {
		set({
			isStreaming: false,
			completedStreamingMessages: [],
			streamingMessage: null,
			streamingMessageId: null,
		});
	},

	clearCompletedStreamingMessages: () => {
		set({ completedStreamingMessages: [] });
	},

	// Studio mode actions
	toggleStudioMode: () => {
		set((state) => ({ isStudioMode: !state.isStudioMode }));
	},

	setStudioMode: (enabled) => {
		set({ isStudioMode: enabled });
	},

	selectToolCall: (toolCallId) => {
		set({ selectedToolCallId: toolCallId });
	},

	// Connection actions
	setConnected: (connected) => {
		set({ isConnected: connected });
	},

	setError: (error) => {
		set({ error });
	},

	// Todo list actions
	setTodos: (todos) => {
		set({ todos });
	},

	clearTodos: () => {
		set({ todos: [] });
	},

	// Streaming message ID (for seamless handoff to API message)
	setStreamingMessageId: (id) => {
		set({ streamingMessageId: id });
	},

	// Reset
	reset: () => {
		set(initialState);
	},
}));

// Selector hooks for performance
export const useActiveConversation = () =>
	useChatStore((state) => state.activeConversationId);
export const useActiveAgent = () =>
	useChatStore((state) => state.activeAgentId);
export const useIsStreaming = () => useChatStore((state) => state.isStreaming);
export const useCompletedStreamingMessages = () =>
	useChatStore((state) => state.completedStreamingMessages);
export const useStreamingMessage = () =>
	useChatStore((state) => state.streamingMessage);
export const useIsStudioMode = () =>
	useChatStore((state) => state.isStudioMode);
export const useTodos = () => useChatStore((state) => state.todos);
