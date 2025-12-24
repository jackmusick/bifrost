/**
 * Chat WebSocket Streaming Hook
 *
 * Provides real-time streaming chat via the standard /ws/connect endpoint.
 * Uses the chat store for state management.
 */

import { useCallback, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { components } from "@/lib/v1";
import { useChatStore } from "@/stores/chatStore";

type MessagePublic = components["schemas"]["MessagePublic"];
type ToolCall = components["schemas"]["ToolCall"];

// Client-only type for streaming tool results
interface ToolResult {
	tool_call_id: string;
	tool_name: string;
	result: unknown;
	error?: string | null;
	duration_ms?: number | null;
}

// Client-only type for agent switch event
interface AgentSwitch {
	agent_id: string;
	agent_name: string;
	reason: string;
}

// Client-only type for tool execution progress
interface ToolProgress {
	tool_call_id: string;
	execution_id?: string;
	status?: "pending" | "running" | "success" | "failed" | "timeout";
	log?: {
		level: "debug" | "info" | "warning" | "error";
		message: string;
	};
}

// Client-only type for streaming chunks (not from API)
interface ChatStreamChunk {
	type:
		| "delta"
		| "tool_call"
		| "tool_progress"
		| "tool_result"
		| "agent_switch"
		| "done"
		| "error";
	conversation_id?: string;
	content?: string | null;
	tool_call?: ToolCall | null;
	tool_progress?: ToolProgress | null;
	tool_result?: ToolResult | null;
	agent_switch?: AgentSwitch | null;
	message_id?: string | null;
	token_count_input?: number | null;
	token_count_output?: number | null;
	duration_ms?: number | null;
	error?: string | null;
	execution_id?: string | null;
}

export interface UseChatStreamOptions {
	conversationId: string | undefined;
	onError?: (error: string) => void;
	onAgentSwitch?: (agentSwitch: AgentSwitch) => void;
}

export interface UseChatStreamReturn {
	sendMessage: (message: string) => void;
	isConnected: boolean;
	isStreaming: boolean;
	connect: () => void;
	disconnect: () => void;
}

export function useChatStream({
	conversationId,
	onError,
	onAgentSwitch,
}: UseChatStreamOptions): UseChatStreamReturn {
	const wsRef = useRef<WebSocket | null>(null);
	const queryClient = useQueryClient();

	const {
		isStreaming,
		isConnected,
		setConnected,
		startStreaming,
		appendStreamContent,
		addStreamToolCall,
		updateToolExecutionStatus,
		setToolExecutionId,
		addToolExecutionLog,
		addStreamToolResult,
		completeStream,
		setStreamError,
		resetStream,
		addMessage,
		addSystemEvent,
		saveToolExecutions,
	} = useChatStore();

	// Ref for reconnection flag
	const shouldReconnectRef = useRef(false);
	const currentConversationIdRef = useRef<string | undefined>(conversationId);

	// Update ref when conversationId changes
	useEffect(() => {
		currentConversationIdRef.current = conversationId;
	}, [conversationId]);

	// WebSocket message handler
	const handleMessage = useCallback(
		(event: MessageEvent) => {
			try {
				const data = JSON.parse(event.data);

				// Handle connection confirmation
				if (data.type === "connected") {
					setConnected(true);
					return;
				}

				// Handle subscription confirmation
				if (data.type === "subscribed") {
					return;
				}

				// Handle pong
				if (data.type === "pong") {
					return;
				}

				// Handle title update - refresh conversations to show new title
				if (data.type === "title_update") {
					queryClient.invalidateQueries({
						queryKey: ["get", "/api/chat/conversations"],
					});
					// Also invalidate the specific conversation
					if (data.conversation_id) {
						queryClient.invalidateQueries({
							queryKey: [
								"get",
								"/api/chat/conversations/{conversation_id}",
								{
									params: {
										path: {
											conversation_id:
												data.conversation_id,
										},
									},
								},
							],
						});
					}
					return;
				}

				// Handle chat stream chunks - only process if for current conversation
				const chunk = data as ChatStreamChunk;
				if (
					chunk.conversation_id &&
					chunk.conversation_id !== currentConversationIdRef.current
				) {
					return; // Ignore chunks for other conversations
				}

				switch (chunk.type) {
					case "delta":
						if (chunk.content) {
							appendStreamContent(chunk.content);
						}
						break;

					case "tool_call":
						if (chunk.tool_call) {
							addStreamToolCall(
								chunk.tool_call,
								chunk.execution_id ?? undefined,
							);
						}
						break;

					case "tool_progress":
						if (chunk.tool_progress) {
							const { tool_call_id, execution_id, status, log } =
								chunk.tool_progress;
							// Set execution_id if provided (needed for log streaming subscription)
							if (execution_id) {
								setToolExecutionId(tool_call_id, execution_id);
							}
							if (status) {
								updateToolExecutionStatus(tool_call_id, status);
							}
							if (log) {
								addToolExecutionLog(tool_call_id, {
									level: log.level,
									message: log.message,
									timestamp: new Date().toISOString(),
								});
							}
						}
						break;

					case "tool_result":
						if (chunk.tool_result) {
							addStreamToolResult(chunk.tool_result);
						}
						break;

					case "done": {
						// Add completed message to local cache BEFORE clearing streaming
						// This prevents the message from disappearing during the API refetch
						const convId = currentConversationIdRef.current;
						const streamState =
							useChatStore.getState().streamingMessage;

						if (convId && streamState) {
							// Save tool executions for persistence (so they show after streaming ends)
							if (
								Object.keys(streamState.toolExecutions).length >
								0
							) {
								saveToolExecutions(
									convId,
									streamState.toolExecutions,
								);
							}

							const completedMessage: MessagePublic = {
								id:
									chunk.message_id ||
									`completed-${Date.now()}`,
								conversation_id: convId,
								role: "assistant",
								content: streamState.content || "",
								tool_calls:
									streamState.toolCalls.length > 0
										? streamState.toolCalls
										: undefined,
								sequence: Date.now(),
								created_at: new Date().toISOString(),
								token_count_input:
									chunk.token_count_input ?? undefined,
								token_count_output:
									chunk.token_count_output ?? undefined,
								duration_ms: chunk.duration_ms ?? undefined,
							};
							addMessage(convId, completedMessage);
						}

						completeStream(chunk.message_id ?? undefined);

						// Refresh messages to get accurate sequence numbers
						if (convId) {
							queryClient.invalidateQueries({
								queryKey: [
									"get",
									"/api/chat/conversations/{conversation_id}/messages",
									{
										params: {
											path: { conversation_id: convId },
										},
									},
								],
							});
							queryClient.invalidateQueries({
								queryKey: ["get", "/api/chat/conversations"],
							});
						}
						break;
					}

					case "agent_switch": {
						// Agent was switched via @mention or routing
						if (chunk.agent_switch) {
							onAgentSwitch?.(chunk.agent_switch);
							// Add inline event instead of toast
							const convId = currentConversationIdRef.current;
							if (convId) {
								addSystemEvent(convId, {
									id: `event-${Date.now()}`,
									type: "agent_switch",
									timestamp: new Date().toISOString(),
									agentName: chunk.agent_switch.agent_name,
									agentId: chunk.agent_switch.agent_id,
									reason:
										chunk.agent_switch.reason === "@mention"
											? "@mention"
											: "routed",
								});
							}
						}
						break;
					}

					case "error": {
						const errorMsg =
							chunk.error || "Unknown error occurred";
						setStreamError(errorMsg);
						onError?.(errorMsg);

						// Add inline error event instead of toast
						const convId = currentConversationIdRef.current;
						if (convId) {
							addSystemEvent(convId, {
								id: `error-${Date.now()}`,
								type: "error",
								timestamp: new Date().toISOString(),
								error: errorMsg,
							});
						}

						// Clean up streaming state on error to prevent stale state
						// This ensures the next message starts fresh
						resetStream();
						break;
					}
				}
			} catch (err) {
				console.error("[useChatStream] Failed to parse message:", err);
			}
		},
		[
			queryClient,
			appendStreamContent,
			addStreamToolCall,
			updateToolExecutionStatus,
			setToolExecutionId,
			addToolExecutionLog,
			addStreamToolResult,
			completeStream,
			setStreamError,
			resetStream,
			setConnected,
			onError,
			onAgentSwitch,
			addMessage,
			addSystemEvent,
			saveToolExecutions,
		],
	);

	// Connect to WebSocket
	const connect = useCallback(() => {
		if (!conversationId) return;
		if (wsRef.current?.readyState === WebSocket.OPEN) return;

		const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
		const host = window.location.host;
		// Use standard /ws/connect with chat channel
		const wsUrl = `${protocol}//${host}/ws/connect?channels=chat:${conversationId}`;

		const ws = new WebSocket(wsUrl);

		ws.onopen = () => {
			// Connection confirmation comes via message
		};

		ws.onmessage = handleMessage;

		ws.onerror = (error) => {
			console.error("[useChatStream] WebSocket error:", error);
			setConnected(false);
		};

		ws.onclose = (event) => {
			setConnected(false);

			// Flag for reconnection on abnormal closure (not user-initiated)
			if (event.code !== 1000 && event.code !== 1001 && conversationId) {
				shouldReconnectRef.current = true;
			}
		};

		wsRef.current = ws;
	}, [conversationId, handleMessage, setConnected]);

	// Handle reconnection via effect to avoid closure issues
	useEffect(() => {
		if (shouldReconnectRef.current && conversationId) {
			shouldReconnectRef.current = false;
			const timer = setTimeout(() => {
				connect();
			}, 3000);
			return () => clearTimeout(timer);
		}
		return undefined;
	}, [conversationId, connect]);

	// Disconnect from WebSocket
	const disconnect = useCallback(() => {
		if (wsRef.current) {
			wsRef.current.close(1000, "User disconnected");
			wsRef.current = null;
		}
		setConnected(false);
		resetStream();
	}, [setConnected, resetStream]);

	// Send message via WebSocket
	const sendMessage = useCallback(
		(message: string) => {
			if (!conversationId) {
				toast.error("No conversation selected");
				return;
			}

			// Ensure connected
			if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
				// Queue the message and connect
				const connectAndSend = () => {
					const protocol =
						window.location.protocol === "https:" ? "wss:" : "ws:";
					const host = window.location.host;
					const wsUrl = `${protocol}//${host}/ws/connect?channels=chat:${conversationId}`;

					const ws = new WebSocket(wsUrl);

					ws.onopen = () => {
						// Wait for connected message before sending
					};

					ws.onmessage = (event) => {
						const data = JSON.parse(event.data);

						if (data.type === "connected") {
							setConnected(true);

							// Add optimistic user message
							const userMessage: MessagePublic = {
								id: `temp-${Date.now()}`,
								conversation_id: conversationId,
								role: "user",
								content: message,
								sequence: Date.now(),
								created_at: new Date().toISOString(),
							};
							addMessage(conversationId, userMessage);

							// Start streaming state
							startStreaming();

							// Send the chat message
							ws.send(
								JSON.stringify({
									type: "chat",
									conversation_id: conversationId,
									message,
								}),
							);
						} else {
							// Handle other messages
							handleMessage(event);
						}
					};

					ws.onerror = (error) => {
						console.error(
							"[useChatStream] WebSocket error:",
							error,
						);
						setConnected(false);
						setStreamError("Connection error");
					};

					ws.onclose = (event) => {
						setConnected(false);
						if (event.code !== 1000 && event.code !== 1001) {
							console.warn(
								"[useChatStream] Unexpected close:",
								event.code,
								event.reason,
							);
						}
					};

					wsRef.current = ws;
				};

				connectAndSend();
				return;
			}

			// Add optimistic user message
			const userMessage: MessagePublic = {
				id: `temp-${Date.now()}`,
				conversation_id: conversationId,
				role: "user",
				content: message,
				sequence: Date.now(),
				created_at: new Date().toISOString(),
			};
			addMessage(conversationId, userMessage);

			// Start streaming state
			startStreaming();

			// Send the chat message
			wsRef.current.send(
				JSON.stringify({
					type: "chat",
					conversation_id: conversationId,
					message,
				}),
			);
		},
		[
			conversationId,
			addMessage,
			startStreaming,
			handleMessage,
			setConnected,
			setStreamError,
		],
	);

	// Auto-disconnect when conversation changes or component unmounts
	useEffect(() => {
		return () => {
			disconnect();
		};
	}, [disconnect]);

	// Reconnect when conversation changes
	useEffect(() => {
		if (conversationId) {
			// Disconnect from previous and reset stream state
			if (wsRef.current) {
				wsRef.current.close(1000, "Switching conversations");
				wsRef.current = null;
			}
			resetStream();
		}
	}, [conversationId, resetStream]);

	return {
		sendMessage,
		isConnected,
		isStreaming,
		connect,
		disconnect,
	};
}
