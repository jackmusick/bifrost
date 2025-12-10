import { useState } from "react";
import {
	History,
	ChevronDown,
	ChevronRight,
	Circle,
	CheckCircle2,
	Loader2,
	X,
	Trash2,
} from "lucide-react";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
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
import type { CommitInfo } from "@/hooks/useGitHub";

interface CommitsListProps {
	commits: CommitInfo[];
	totalCommits?: number;
	hasMore?: boolean;
	isLoading?: boolean;
	onDiscardAll?: () => Promise<void>;
	onDiscardCommit?: (commitSha: string) => Promise<void>;
	onLoadMore?: () => void;
}

export function CommitsList({
	commits,
	totalCommits,
	hasMore = false,
	isLoading = false,
	onDiscardAll,
	onDiscardCommit,
	onLoadMore,
}: CommitsListProps) {
	const [isOpen, setIsOpen] = useState(true);
	const [hoveredCommit, setHoveredCommit] = useState<string | null>(null);
	const [isDiscarding, setIsDiscarding] = useState(false);
	const [showDiscardAllDialog, setShowDiscardAllDialog] = useState(false);
	const [commitToDiscard, setCommitToDiscard] = useState<CommitInfo | null>(
		null,
	);

	const unpushedCommits = commits.filter((c) => !c.is_pushed);
	const hasUnpushedCommits = unpushedCommits.length > 0;

	const handleDiscardAll = async () => {
		if (!onDiscardAll) return;
		setIsDiscarding(true);
		setShowDiscardAllDialog(false);
		try {
			await onDiscardAll();
		} finally {
			setIsDiscarding(false);
		}
	};

	const handleDiscardCommit = async (commit: CommitInfo) => {
		if (!onDiscardCommit) return;
		setIsDiscarding(true);
		setCommitToDiscard(null);
		try {
			await onDiscardCommit(commit.sha);
		} finally {
			setIsDiscarding(false);
		}
	};

	return (
		<Collapsible
			open={isOpen}
			onOpenChange={setIsOpen}
			className="flex flex-col min-h-0"
		>
			<CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-2 hover:bg-muted/50 transition-colors border-b flex-shrink-0">
				<div className="flex items-center gap-2">
					{isOpen ? (
						<ChevronDown className="h-4 w-4" />
					) : (
						<ChevronRight className="h-4 w-4" />
					)}
					<History className="h-4 w-4" />
					<span className="text-sm font-medium">
						Commits ({totalCommits ?? commits.length})
					</span>
				</div>
			</CollapsibleTrigger>
			<CollapsibleContent className="flex-1 min-h-0 flex flex-col">
				{/* Discard All button */}
				{hasUnpushedCommits && onDiscardAll && isOpen && (
					<div className="px-4 pt-2 pb-1 flex-shrink-0">
						<Button
							variant="outline"
							size="sm"
							className="w-full text-xs"
							onClick={() => setShowDiscardAllDialog(true)}
							disabled={isDiscarding || isLoading}
						>
							{isDiscarding ? (
								<Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
							) : (
								<Trash2 className="h-3 w-3 mr-1.5" />
							)}
							Discard All Unpushed ({unpushedCommits.length})
						</Button>
					</div>
				)}

				<div className="flex-1 overflow-y-auto px-4 py-2 min-h-0">
					{/* Only show full-page spinner on initial load (no commits yet) */}
					{isLoading && commits.length === 0 ? (
						<div className="flex flex-col items-center justify-center py-8 text-center">
							<Loader2 className="h-6 w-6 text-muted-foreground mb-2 animate-spin" />
							<p className="text-xs text-muted-foreground">
								Loading commits...
							</p>
						</div>
					) : commits.length === 0 ? (
						<div className="flex flex-col items-center justify-center py-8 text-center">
							<History className="h-6 w-6 text-muted-foreground mb-2" />
							<p className="text-xs text-muted-foreground">
								No commits
							</p>
						</div>
					) : (
						<div className="space-y-1">
							{commits.map((commit) => (
								<div
									key={commit.sha}
									className="group flex items-start gap-2 px-2 py-2 rounded hover:bg-muted/30 transition-colors relative"
									onMouseEnter={() =>
										setHoveredCommit(commit.sha)
									}
									onMouseLeave={() => setHoveredCommit(null)}
								>
									{commit.is_pushed ? (
										<CheckCircle2 className="h-3.5 w-3.5 text-green-500 flex-shrink-0 mt-0.5" />
									) : (
										<Circle className="h-3.5 w-3.5 text-yellow-500 flex-shrink-0 mt-0.5" />
									)}
									<div className="flex-1 min-w-0">
										<p className="text-xs font-medium truncate">
											{commit.message}
										</p>
										<p className="text-xs text-muted-foreground">
											{commit.author} ·{" "}
											{new Date(
												commit.timestamp,
											).toLocaleDateString()}
										</p>
									</div>
									{/* Individual discard button - only for unpushed commits */}
									{!commit.is_pushed &&
										onDiscardCommit &&
										hoveredCommit === commit.sha && (
											<button
												onClick={(e) => {
													e.stopPropagation();
													setCommitToDiscard(commit);
												}}
												disabled={isDiscarding}
												className="p-1 rounded hover:bg-destructive/10 transition-colors disabled:opacity-50"
												title="Discard this commit and all newer commits"
											>
												<X className="h-3.5 w-3.5 text-destructive" />
											</button>
										)}
								</div>
							))}

							{/* Load More button - show inline spinner when loading more */}
							{hasMore && onLoadMore && (
								<button
									onClick={onLoadMore}
									disabled={isLoading}
									className="w-full px-2 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
								>
									{isLoading && (
										<Loader2 className="h-3 w-3 animate-spin" />
									)}
									{isLoading ? "Loading..." : "Load More"}
								</button>
							)}
						</div>
					)}
				</div>
			</CollapsibleContent>

			{/* Discard All Confirmation Dialog */}
			<AlertDialog
				open={showDiscardAllDialog}
				onOpenChange={setShowDiscardAllDialog}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Discard all unpushed commits?
						</AlertDialogTitle>
						<AlertDialogDescription>
							This will permanently discard{" "}
							{unpushedCommits.length} unpushed commit
							{unpushedCommits.length !== 1 ? "s" : ""} and reset
							your local branch to match the remote. This action
							cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDiscardAll}
							className="bg-destructive hover:bg-destructive/90"
						>
							Discard All
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Discard Commit Confirmation Dialog */}
			<AlertDialog
				open={commitToDiscard !== null}
				onOpenChange={(open) => !open && setCommitToDiscard(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Discard this commit?
						</AlertDialogTitle>
						<AlertDialogDescription>
							This will permanently discard "
							{commitToDiscard?.message}" and all newer commits by
							resetting to its parent. This action cannot be
							undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() =>
								commitToDiscard &&
								handleDiscardCommit(commitToDiscard)
							}
							className="bg-destructive hover:bg-destructive/90"
						>
							Discard Commit
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</Collapsible>
	);
}
