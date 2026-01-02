/**
 * Chat WebSocket Streaming Hook
 *
 * Provides real-time streaming chat via the shared WebSocketService.
 * Uses the chat store for state management.
 */

import { useCallback, useRef, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useChatStore } from "@/stores/chatStore";
import type { components } from "@/lib/v1";
import {
	webSocketService,
	type ChatStreamChunk,
	type ChatAgentSwitch,
	type AskUserQuestion,
} from "@/services/websocket";

type MessagePublic = components["schemas"]["MessagePublic"];

export interface PendingQuestion {
	questions: AskUserQuestion[];
	requestId: string;
}

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
	// AskUserQuestion support
	pendingQuestion: PendingQuestion | null;
	answerQuestion: (answers: Record<string, string>) => void;
	// Stop/interrupt support
	stopStreaming: () => void;
}

export function useChatStream({
	conversationId,
	onError,
	onAgentSwitch,
}: UseChatStreamOptions): UseChatStreamReturn {
	const queryClient = useQueryClient();
	const [isConnected, setIsConnected] = useState(false);
	const [pendingQuestion, setPendingQuestion] =
		useState<PendingQuestion | null>(null);

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
		completeCurrentStreamingMessage,
		completeStream,
		setStreamError,
		resetStream,
		addSystemEvent,
		saveToolExecutions,
		addMessage,
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
				case "message_start": {
					// Backend has saved the user message and generated real IDs
					// Invalidate messages query to fetch the real user message from DB
					const convId = currentConversationIdRef.current;
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
					}
					break;
				}

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
					// Just update tool state - message completion is signaled by assistant_message_end
					if (chunk.tool_result) {
						addStreamToolResult(chunk.tool_result);
					}
					break;

				case "assistant_message_start":
					// Message segment is starting - nothing to do, message is already being built
					break;

				case "assistant_message_end":
					// Message segment complete (all text and tool_calls for this message have been sent)
					// This is the deterministic signal to finalize the current streaming message
					completeCurrentStreamingMessage();
					break;

				case "done": {
					const convId = currentConversationIdRef.current;
					const storeState = useChatStore.getState();
					const streamState = storeState.streamingMessage;
					const completedMessages =
						storeState.completedStreamingMessages;

					if (convId) {
						// Save tool executions from current streaming message
						if (
							streamState &&
							Object.keys(streamState.toolExecutions).length > 0
						) {
							saveToolExecutions(
								convId,
								streamState.toolExecutions,
							);
						}
						// Save tool executions from completed streaming messages
						for (const msg of completedMessages) {
							if (Object.keys(msg.toolExecutions).length > 0) {
								saveToolExecutions(convId, msg.toolExecutions);
							}
						}
					}

					// Mark streaming complete - this keeps the streaming message visible
					// with isComplete=true until the API returns the authoritative message.
					// We intentionally don't add a local "completed-*" message to avoid
					// duplication issues during the race between local and API state.
					completeStream(chunk.message_id ?? undefined);

					// Refresh messages from API - this is the source of truth
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

				case "ask_user_question": {
					// SDK is asking user a question - show modal
					if (chunk.questions && chunk.request_id) {
						setPendingQuestion({
							questions: chunk.questions,
							requestId: chunk.request_id,
						});
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

					// Clear any pending question on error
					setPendingQuestion(null);
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
			completeCurrentStreamingMessage,
			completeStream,
			setStreamError,
			resetStream,
			onError,
			onAgentSwitch,
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

			// Add optimistic user message for immediate display
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
			const sent = webSocketService.sendChatMessage(
				conversationId,
				message,
			);
			if (!sent) {
				// Retry after connecting
				try {
					await webSocketService.connectToChat(conversationId);
					webSocketService.sendChatMessage(conversationId, message);
				} catch (error) {
					console.error(
						"[useChatStream] Failed to send message:",
						error,
					);
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

	// Answer a pending AskUserQuestion
	const answerQuestion = useCallback(
		(answers: Record<string, string>) => {
			if (!conversationId || !pendingQuestion) {
				return;
			}

			webSocketService.sendChatAnswer(
				conversationId,
				pendingQuestion.requestId,
				answers,
			);
			setPendingQuestion(null);
		},
		[conversationId, pendingQuestion],
	);

	// Stop the current streaming operation
	const stopStreaming = useCallback(() => {
		if (!conversationId) {
			return;
		}

		webSocketService.sendChatStop(conversationId);
		setPendingQuestion(null);
		resetStream();
	}, [conversationId, resetStream]);

	return {
		sendMessage,
		isConnected,
		isStreaming,
		connect,
		disconnect,
		pendingQuestion,
		answerQuestion,
		stopStreaming,
	};
}
