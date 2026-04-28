/**
 * ChatSidebar Component
 *
 * Primary nav stays put: + New chat, Workspaces, Toolbox (placeholder),
 * Artifacts (placeholder). When a workspace is active the `Workspaces` row
 * swaps for a workspace-identity row with an exit `×` and a settings gear.
 *
 * Recent shows:
 *   - In workspace mode → only that workspace's chats.
 *   - Unscoped → only general-pool chats (workspace_id IS NULL). Workspace
 *     chats are reachable by entering the workspace.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
	ChevronRight,
	FolderKanban,
	FolderInput,
	Hammer,
	MessageSquare,
	MoreHorizontal,
	Plus,
	Search,
	Settings2,
	Sparkles,
	Trash2,
	X,
} from "lucide-react";

import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuSub,
	DropdownMenuSubContent,
	DropdownMenuSubTrigger,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import {
	useConversations,
	useCreateConversation,
	useDeleteConversation,
} from "@/hooks/useChat";
import type { ConversationSummary } from "@/hooks/useChat";
import { cn } from "@/lib/utils";
import {
	useMoveConversation,
	useWorkspaces,
	type Workspace,
} from "@/services/workspaceService";
import { useChatStore } from "@/stores/chatStore";
import { toast } from "sonner";

interface ChatSidebarProps {
	className?: string;
	/** When set, the sidebar enters workspace mode (re-scoped). */
	activeWorkspace?: Workspace | null;
	/** Triggered when the user opens the workspace settings Sheet. */
	onOpenWorkspaceSettings?: () => void;
}

export function ChatSidebar({
	className,
	activeWorkspace,
	onOpenWorkspaceSettings,
}: ChatSidebarProps) {
	const navigate = useNavigate();
	const [searchTerm, setSearchTerm] = useState("");
	const [deleteTarget, setDeleteTarget] =
		useState<ConversationSummary | null>(null);

	const { activeConversationId, setActiveConversation, setActiveAgent } =
		useChatStore();

	const inWorkspaceMode = !!activeWorkspace;

	// Pool filter: in workspace mode → that workspace; else → general pool only.
	const { data: conversations, isLoading: isLoadingConversations } =
		useConversations(
			inWorkspaceMode
				? { workspaceId: activeWorkspace.id }
				: { pool: "general" },
		);

	const createConversation = useCreateConversation();
	const deleteConversation = useDeleteConversation();
	const moveConversation = useMoveConversation();
	const { data: workspacesForMove } = useWorkspaces();

	const filteredConversations = conversations?.filter((c) => {
		if (!searchTerm) return true;
		const term = searchTerm.toLowerCase();
		return (
			c.title?.toLowerCase().includes(term) ||
			c.agent_name?.toLowerCase().includes(term) ||
			c.last_message_preview?.toLowerCase().includes(term)
		);
	});

	const handleNewChat = () => {
		setActiveAgent(null);
		createConversation.mutate(
			{
				body: {
					channel: "chat",
					...(activeWorkspace
						? { workspace_id: activeWorkspace.id }
						: {}),
				},
			},
			{
				onSuccess: (data) => {
					navigate(
						activeWorkspace
							? `/chat/${data.id}?workspace=${activeWorkspace.id}`
							: `/chat/${data.id}`,
					);
				},
			},
		);
	};

	const handleSelectConversation = (conv: ConversationSummary) => {
		setActiveConversation(conv.id);
		setActiveAgent(conv.agent_id ?? null);
		navigate(
			inWorkspaceMode
				? `/chat/${conv.id}?workspace=${activeWorkspace.id}`
				: `/chat/${conv.id}`,
		);
	};

	const handleDeleteConfirm = () => {
		if (deleteTarget) {
			const wasActive = activeConversationId === deleteTarget.id;
			deleteConversation.mutate({
				params: { path: { conversation_id: deleteTarget.id } },
			});
			setDeleteTarget(null);
			if (wasActive) {
				navigate(
					inWorkspaceMode
						? `/chat?workspace=${activeWorkspace.id}`
						: "/chat",
				);
			}
		}
	};

	const handleMove = (conv: ConversationSummary, target: string | null) => {
		moveConversation.mutate(
			{
				params: { path: { conversation_id: conv.id } },
				body: { workspace_id: target },
			},
			{
				onSuccess: () => {
					toast.success(
						target
							? "Moved to workspace"
							: "Moved to general chats",
					);
				},
				onError: (err) =>
					toast.error("Move failed", {
						description: (err as Error)?.message,
					}),
			},
		);
	};

	const formatTime = (dateStr: string) => {
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMs / 3600000);
		const diffDays = Math.floor(diffMs / 86400000);
		if (diffMins < 1) return "now";
		if (diffMins < 60) return `${diffMins}m`;
		if (diffHours < 24) return `${diffHours}h`;
		if (diffDays < 7) return `${diffDays}d`;
		return date.toLocaleDateString();
	};

	const navRowClass =
		"flex items-center gap-2.5 px-2.5 py-1.5 rounded-md w-full text-left text-sm transition-colors hover:bg-accent";

	// Move-to candidates: every workspace the user can see.
	const moveTargets = workspacesForMove ?? [];

	return (
		<TooltipProvider delayDuration={300}>
			<div
				className={cn(
					"flex flex-col h-full bg-muted/30 border-r w-72",
					className,
				)}
			>
				{/* === Top block — primary nav (always visible) =============== */}
				<div className="p-3 border-b space-y-1">
					<button
						type="button"
						onClick={handleNewChat}
						disabled={createConversation.isPending}
						className={cn(navRowClass, "font-medium")}
					>
						<Plus className="h-4 w-4" />
						<span>New chat</span>
					</button>

					{/* Workspace identity row (replaces "Workspaces" while inside one) */}
					{inWorkspaceMode && activeWorkspace ? (
						<div
							className={cn(
								navRowClass,
								"bg-accent/50 cursor-default hover:bg-accent/50 gap-2",
							)}
						>
							<FolderKanban className="h-4 w-4 text-primary shrink-0" />
							<span className="font-medium truncate flex-1">
								{activeWorkspace.name}
							</span>
							{onOpenWorkspaceSettings && (
								<Tooltip>
									<TooltipTrigger asChild>
										<Button
											variant="ghost"
											size="icon-sm"
											className="size-6 shrink-0"
											onClick={onOpenWorkspaceSettings}
										>
											<Settings2 className="h-3.5 w-3.5" />
										</Button>
									</TooltipTrigger>
									<TooltipContent>
										Workspace settings
									</TooltipContent>
								</Tooltip>
							)}
							<Tooltip>
								<TooltipTrigger asChild>
									<Button
										variant="ghost"
										size="icon-sm"
										className="size-6 shrink-0"
										onClick={() => navigate("/chat")}
									>
										<X className="h-3.5 w-3.5" />
									</Button>
								</TooltipTrigger>
								<TooltipContent>Exit workspace</TooltipContent>
							</Tooltip>
						</div>
					) : (
						<button
							type="button"
							onClick={() => navigate("/workspaces")}
							className={navRowClass}
						>
							<FolderKanban className="h-4 w-4" />
							<span>Workspaces</span>
						</button>
					)}

					<Tooltip>
						<TooltipTrigger asChild>
							<button
								type="button"
								disabled
								className={cn(
									navRowClass,
									"opacity-50 cursor-not-allowed hover:bg-transparent",
								)}
							>
								<Hammer className="h-4 w-4" />
								<span>Toolbox</span>
							</button>
						</TooltipTrigger>
						<TooltipContent>Coming soon</TooltipContent>
					</Tooltip>
					<Tooltip>
						<TooltipTrigger asChild>
							<button
								type="button"
								disabled
								className={cn(
									navRowClass,
									"opacity-50 cursor-not-allowed hover:bg-transparent",
								)}
							>
								<Sparkles className="h-4 w-4" />
								<span>Artifacts</span>
							</button>
						</TooltipTrigger>
						<TooltipContent>Coming soon</TooltipContent>
					</Tooltip>
				</div>

				{/* === Search ================================================ */}
				<div className="p-3 border-b">
					<div className="relative">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
						<Input
							placeholder={
								inWorkspaceMode
									? "Search this workspace..."
									: "Search chats..."
							}
							value={searchTerm}
							onChange={(e) => setSearchTerm(e.target.value)}
							className="pl-9 h-8 text-sm"
						/>
					</div>
				</div>

				{/* === Recent ================================================ */}
				<div className="flex-1 overflow-y-auto p-3 pt-2">
					<h3 className="text-[10px] font-medium tracking-wider uppercase text-muted-foreground mb-2 px-1">
						Recent
					</h3>
					{isLoadingConversations ? (
						<div className="space-y-2">
							{[1, 2, 3].map((i) => (
								<Skeleton key={i} className="h-12 w-full" />
							))}
						</div>
					) : filteredConversations &&
					  filteredConversations.length > 0 ? (
						<div className="space-y-0.5">
							{filteredConversations.map((conv) => (
								<div
									key={conv.id}
									className={cn(
										"group flex items-start gap-2 px-2.5 py-1.5 rounded-md cursor-pointer hover:bg-accent transition-colors",
										activeConversationId === conv.id &&
											"bg-accent",
									)}
									onClick={() =>
										handleSelectConversation(conv)
									}
								>
									<MessageSquare className="size-3.5 mt-0.5 text-muted-foreground shrink-0" />
									<div className="flex-1 min-w-0">
										<div className="flex items-center justify-between gap-2">
											<span className="font-medium text-sm truncate">
												{conv.title ||
													conv.agent_name ||
													"Untitled"}
											</span>
											<span className="text-[10px] opacity-0 group-hover:opacity-70 shrink-0 text-muted-foreground">
												{formatTime(conv.updated_at)}
											</span>
										</div>
										{conv.last_message_preview && (
											<p className="text-xs text-muted-foreground truncate">
												{conv.last_message_preview}
											</p>
										)}
									</div>
									<DropdownMenu>
										<DropdownMenuTrigger asChild>
											<Button
												variant="ghost"
												size="icon-sm"
												className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
												onClick={(e) =>
													e.stopPropagation()
												}
											>
												<MoreHorizontal className="h-3 w-3" />
											</Button>
										</DropdownMenuTrigger>
										<DropdownMenuContent
											align="end"
											onClick={(e) => e.stopPropagation()}
										>
											<DropdownMenuSub>
												<DropdownMenuSubTrigger>
													<FolderInput className="h-3.5 w-3.5 mr-2" />
													<span>Move to</span>
													<ChevronRight className="ml-auto h-3 w-3" />
												</DropdownMenuSubTrigger>
												<DropdownMenuSubContent>
													{conv.workspace_id && (
														<DropdownMenuItem
															onClick={() =>
																handleMove(
																	conv,
																	null,
																)
															}
														>
															General chats
														</DropdownMenuItem>
													)}
													{moveTargets
														.filter(
															(w) =>
																w.id !==
																conv.workspace_id,
														)
														.map((w) => (
															<DropdownMenuItem
																key={w.id}
																onClick={() =>
																	handleMove(
																		conv,
																		w.id,
																	)
																}
															>
																<FolderKanban className="h-3.5 w-3.5 mr-2 text-muted-foreground" />
																{w.name}
															</DropdownMenuItem>
														))}
													{moveTargets.length === 0 && (
														<DropdownMenuItem disabled>
															No workspaces yet
														</DropdownMenuItem>
													)}
												</DropdownMenuSubContent>
											</DropdownMenuSub>
											<DropdownMenuSeparator />
											<DropdownMenuItem
												onClick={() =>
													setDeleteTarget(conv)
												}
												className="text-destructive focus:text-destructive"
											>
												<Trash2 className="h-3.5 w-3.5 mr-2" />
												Delete chat
											</DropdownMenuItem>
										</DropdownMenuContent>
									</DropdownMenu>
								</div>
							))}
						</div>
					) : (
						<p className="text-sm text-muted-foreground py-2 px-1">
							{searchTerm
								? "No matching chats"
								: inWorkspaceMode
									? "No chats in this workspace yet"
									: "No chats yet"}
						</p>
					)}
				</div>

				<AlertDialog
					open={!!deleteTarget}
					onOpenChange={(open) => !open && setDeleteTarget(null)}
				>
					<AlertDialogContent>
						<AlertDialogHeader>
							<AlertDialogTitle>Delete chat?</AlertDialogTitle>
							<AlertDialogDescription>
								This will delete the chat "
								{deleteTarget?.title ||
									deleteTarget?.agent_name ||
									"Untitled"}
								". This action cannot be undone.
							</AlertDialogDescription>
						</AlertDialogHeader>
						<AlertDialogFooter>
							<AlertDialogCancel>Cancel</AlertDialogCancel>
							<AlertDialogAction
								onClick={handleDeleteConfirm}
								className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
							>
								Delete
							</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>
			</div>
		</TooltipProvider>
	);
}
