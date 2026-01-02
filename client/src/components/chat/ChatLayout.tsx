/**
 * ChatLayout Component
 *
 * Main container for the chat UI.
 * Provides a responsive layout with sidebar and chat window.
 */

import { useState, useEffect } from "react";
import { PanelLeftClose, PanelLeft, Cpu, DollarSign } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatSidebar } from "./ChatSidebar";
import { ChatWindow } from "./ChatWindow";
import { useChatStore } from "@/stores/chatStore";
import { useConversation, useConversationStats } from "@/hooks/useChat";
import { useUserPermissions } from "@/hooks/useUserPermissions";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type ToolCall = components["schemas"]["ToolCall"];

interface ChatLayoutProps {
	initialConversationId?: string;
	onToolCallClick?: (toolCall: ToolCall) => void;
}

export function ChatLayout({
	initialConversationId,
	onToolCallClick,
}: ChatLayoutProps) {
	const [isSidebarOpen, setIsSidebarOpen] = useState(true);

	// Get active conversation from store
	const activeConversationId = useChatStore(
		(state) => state.activeConversationId,
	);
	const setActiveConversation = useChatStore(
		(state) => state.setActiveConversation,
	);

	// Set initial conversation if provided (in effect, not during render)
	useEffect(() => {
		if (initialConversationId && !activeConversationId) {
			setActiveConversation(initialConversationId);
		}
	}, [initialConversationId, activeConversationId, setActiveConversation]);

	// Get conversation details for header
	const { data: conversation } = useConversation(
		activeConversationId ?? undefined,
	);

	// Get conversation stats for platform admins
	const conversationStats = useConversationStats(
		activeConversationId ?? undefined,
	);
	const { isPlatformAdmin } = useUserPermissions();

	// Format token count for display (e.g., 12450 -> "12.5k")
	const formatTokens = (count: number): string => {
		if (count >= 1_000_000) {
			return `${(count / 1_000_000).toFixed(1)}M`;
		}
		if (count >= 1_000) {
			return `${(count / 1_000).toFixed(1)}k`;
		}
		return count.toString();
	};

	// Format cost for display
	const formatCost = (cost: number): string => {
		if (cost < 0.01) {
			return `$${cost.toFixed(4)}`;
		}
		return `$${cost.toFixed(2)}`;
	};

	return (
		<div className="flex h-full overflow-hidden bg-background">
			{/* Sidebar Toggle (Mobile) */}
			<Button
				variant="ghost"
				size="icon-sm"
				className={cn(
					"absolute top-4 left-4 z-10 lg:hidden",
					isSidebarOpen && "hidden",
				)}
				onClick={() => setIsSidebarOpen(true)}
			>
				<PanelLeft className="h-4 w-4" />
			</Button>

			{/* Sidebar */}
			<div
				className={cn(
					"w-80 shrink-0 transition-all duration-200 ease-in-out",
					"lg:relative lg:translate-x-0",
					isSidebarOpen
						? "translate-x-0"
						: "-translate-x-full lg:w-0 lg:opacity-0",
					// Mobile overlay
					isSidebarOpen && "fixed inset-y-0 left-0 z-20 lg:relative",
				)}
			>
				<div className="relative h-full">
					<ChatSidebar className="w-80" />
					{/* Close button (Desktop) */}
					<Button
						variant="ghost"
						size="icon-sm"
						className="absolute top-4 right-2 hidden lg:flex"
						onClick={() => setIsSidebarOpen(false)}
					>
						<PanelLeftClose className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Mobile Overlay */}
			{isSidebarOpen && (
				<div
					className="fixed inset-0 bg-black/50 z-10 lg:hidden"
					onClick={() => setIsSidebarOpen(false)}
				/>
			)}

			{/* Main Content */}
			<div className="flex-1 flex flex-col min-w-0 overflow-hidden">
				{/* Header - always show when sidebar is closed or conversation is active */}
				{(!isSidebarOpen || activeConversationId) && (
					<header className="h-14 border-b flex items-center px-4 gap-4 relative z-10">
						{!isSidebarOpen && (
							<Button
								variant="ghost"
								size="icon-sm"
								className="hidden lg:flex"
								onClick={() => setIsSidebarOpen(true)}
							>
								<PanelLeft className="h-4 w-4" />
							</Button>
						)}
						{activeConversationId && (
							<>
								<div className="flex-1 min-w-0">
									<h1 className="font-medium truncate">
										{conversation?.title ||
											conversation?.agent_name ||
											"Chat"}
									</h1>
									{conversation?.agent_name &&
										conversation?.title && (
											<p className="text-xs text-muted-foreground truncate">
												with {conversation.agent_name}
											</p>
										)}
								</div>

								{/* Platform Admin: Token/Cost Stats */}
								{isPlatformAdmin &&
									conversationStats &&
									conversationStats.totalTokens > 0 && (
										<div className="hidden sm:flex items-center gap-3 text-xs text-muted-foreground shrink-0">
											{/* Model */}
											{conversationStats.model && (
												<div
													className="flex items-center gap-1"
													title="Model"
												>
													<Cpu className="h-3 w-3" />
													<span className="font-mono">
														{conversationStats.model
															.split("-")
															.slice(0, 2)
															.join("-")}
													</span>
												</div>
											)}
											{/* Tokens */}
											<div
												className="flex items-center gap-1"
												title={`Input: ${conversationStats.totalInputTokens.toLocaleString()} | Output: ${conversationStats.totalOutputTokens.toLocaleString()}`}
											>
												<span className="font-mono">
													{formatTokens(
														conversationStats.totalTokens,
													)}{" "}
													tokens
												</span>
											</div>
											{/* Cost */}
											{conversationStats.estimatedCostUsd !==
												null && (
												<div
													className="flex items-center gap-1"
													title="Estimated cost"
												>
													<DollarSign className="h-3 w-3" />
													<span className="font-mono">
														{formatCost(
															conversationStats.estimatedCostUsd,
														)}
													</span>
												</div>
											)}
										</div>
									)}
							</>
						)}
					</header>
				)}

				{/* Chat Window */}
				<ChatWindow
					conversationId={activeConversationId ?? undefined}
					agentName={conversation?.agent_name}
					onToolCallClick={onToolCallClick}
				/>
			</div>
		</div>
	);
}
