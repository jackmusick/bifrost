/**
 * Chat WebSocket Streaming Hook
 *
 * Provides real-time streaming chat via the shared WebSocketService.
 * Uses the chat store for state management.
 */

import { useCallback, useRef, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { components } from "@/lib/v1";
import { useChatStore } from "@/stores/chatStore";
import {
	webSocketService,
	type ChatStreamChunk,
	type ChatAgentSwitch,
} from "@/services/websocket";

type MessagePublic = components["schemas"]["MessagePublic"];

export interface UseChatStreamOptions {
	conversationId: string | undefined;
	onError?: (error: string) => void;
	onAgentSwitch?: (agentSwitch: ChatAgentSwitch) => void;
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
	const queryClient = useQueryClient();
	const [isConnected, setIsConnected] = useState(false);

	// Track current conversation for closure safety
	const currentConversationIdRef = useRef<string | undefined>(conversationId);

	// Track unsubscribe function
	const unsubscribeRef = useRef<(() => void) | null>(null);

	// Ref for handleChunk to avoid effect dependency issues
	const handleChunkRef = useRef<((chunk: ChatStreamChunk) => void) | null>(
		null,
	);

	const {
		isStreaming,
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

	// Update ref when conversationId changes
	useEffect(() => {
		currentConversationIdRef.current = conversationId;
	}, [conversationId]);

	// Handle incoming chat stream chunks
	const handleChunk = useCallback(
		(chunk: ChatStreamChunk) => {
			// Handle title update - refresh conversations to show new title
			if (chunk.type === "title_update") {
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/chat/conversations"],
				});
				if (chunk.conversation_id) {
					queryClient.invalidateQueries({
						queryKey: [
							"get",
							"/api/chat/conversations/{conversation_id}",
							{
								params: {
									path: {
										conversation_id: chunk.conversation_id,
									},
								},
							},
						],
					});
				}
				return;
			}

			// Only process chunks for current conversation
			if (
				chunk.conversation_id &&
				chunk.conversation_id !== currentConversationIdRef.current
			) {
				return;
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
					const convId = currentConversationIdRef.current;
					const streamState = useChatStore.getState().streamingMessage;

					if (convId && streamState) {
						// Save tool executions for persistence
						if (Object.keys(streamState.toolExecutions).length > 0) {
							saveToolExecutions(convId, streamState.toolExecutions);
						}

						const completedMessage: MessagePublic = {
							id: chunk.message_id || `completed-${Date.now()}`,
							conversation_id: convId,
							role: "assistant",
							content: streamState.content || "",
							tool_calls:
								streamState.toolCalls.length > 0
									? streamState.toolCalls
									: undefined,
							sequence: Date.now(),
							created_at: new Date().toISOString(),
							token_count_input: chunk.token_count_input ?? undefined,
							token_count_output: chunk.token_count_output ?? undefined,
							duration_ms: chunk.duration_ms ?? undefined,
						};
						addMessage(convId, completedMessage);
					}

					completeStream(chunk.message_id ?? undefined);

					// Refresh messages
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
					if (chunk.agent_switch) {
						onAgentSwitch?.(chunk.agent_switch);
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
					const errorMsg = chunk.error || "Unknown error occurred";
					setStreamError(errorMsg);
					onError?.(errorMsg);

					const convId = currentConversationIdRef.current;
					if (convId) {
						addSystemEvent(convId, {
							id: `error-${Date.now()}`,
							type: "error",
							timestamp: new Date().toISOString(),
							error: errorMsg,
						});
					}

					resetStream();
					break;
				}
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
			onError,
			onAgentSwitch,
			addMessage,
			addSystemEvent,
			saveToolExecutions,
		],
	);

	// Keep handleChunk ref updated for use in effects (avoids dependency issues)
	useEffect(() => {
		handleChunkRef.current = handleChunk;
	}, [handleChunk]);

	// Connect to WebSocket and subscribe to chat channel
	const connect = useCallback(async () => {
		if (!conversationId) return;

		try {
			// Connect to chat channel via shared WebSocket service
			await webSocketService.connectToChat(conversationId);

			// Subscribe to chat stream events
			unsubscribeRef.current = webSocketService.onChatStream(
				conversationId,
				handleChunk,
			);

			setIsConnected(true);
		} catch (error) {
			console.error("[useChatStream] Failed to connect:", error);
			setIsConnected(false);
		}
	}, [conversationId, handleChunk]);

	// Disconnect and unsubscribe
	const disconnect = useCallback(() => {
		if (unsubscribeRef.current) {
			unsubscribeRef.current();
			unsubscribeRef.current = null;
		}
		setIsConnected(false);
		resetStream();
	}, [resetStream]);

	// Send message via WebSocket
	const sendMessage = useCallback(
		async (message: string) => {
			if (!conversationId) {
				toast.error("No conversation selected");
				return;
			}

			// Ensure connected first
			if (!webSocketService.isConnected()) {
				await connect();
			}

			// Make sure we're subscribed to this conversation's chat stream
			if (!unsubscribeRef.current) {
				unsubscribeRef.current = webSocketService.onChatStream(
					conversationId,
					handleChunk,
				);
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
			const sent = webSocketService.sendChatMessage(conversationId, message);
			if (!sent) {
				// Retry after connecting
				try {
					await webSocketService.connectToChat(conversationId);
					webSocketService.sendChatMessage(conversationId, message);
				} catch (error) {
					console.error("[useChatStream] Failed to send message:", error);
					setStreamError("Failed to send message");
					resetStream();
				}
			}
		},
		[
			conversationId,
			connect,
			handleChunk,
			addMessage,
			startStreaming,
			setStreamError,
			resetStream,
		],
	);

	// Auto-connect when conversation changes
	useEffect(() => {
		if (conversationId) {
			// Disconnect from previous conversation
			if (unsubscribeRef.current) {
				unsubscribeRef.current();
				unsubscribeRef.current = null;
			}
			// Reset stream state directly from store (avoid dependency on resetStream)
			useChatStore.getState().resetStream();

			// Connect to new conversation
			const connectAsync = async () => {
				try {
					await webSocketService.connectToChat(conversationId);
					// Use ref for callback to avoid dependency issues
					unsubscribeRef.current = webSocketService.onChatStream(
						conversationId,
						(chunk) => handleChunkRef.current?.(chunk),
					);
					setIsConnected(true);
				} catch (error) {
					console.error("[useChatStream] Failed to connect:", error);
					setIsConnected(false);
				}
			};
			connectAsync();
		}

		return () => {
			if (unsubscribeRef.current) {
				unsubscribeRef.current();
				unsubscribeRef.current = null;
			}
		};
	}, [conversationId]); // Only depend on conversationId

	// Track connection status from service
	useEffect(() => {
		const checkConnection = () => {
			setIsConnected(webSocketService.isConnected());
		};

		// Check periodically (the service doesn't expose connection events directly)
		const interval = setInterval(checkConnection, 1000);
		checkConnection();

		return () => clearInterval(interval);
	}, []);

	return {
		sendMessage,
		isConnected,
		isStreaming,
		connect,
		disconnect,
	};
}
