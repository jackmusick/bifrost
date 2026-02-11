import { useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { webSocketService, type GitOpComplete } from "@/services/websocket";
import {
	GitBranch,
	Loader2,
	Download,
	Upload,
	RefreshCw,
	ArrowDownToLine,
	AlertCircle,
	ChevronDown,
	ChevronRight,
	History,
	Circle,
	CheckCircle2,
	Plus,
	Edit3,
	Minus,
	FileText,
	Bot,
	AppWindow,
	Workflow,
	FileCode,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
	useGitStatus,
	useGitCommits,
	useFetch,
	useCommit,
	usePull,
	usePush,
	useWorkingTreeChanges,
	useResolveConflicts,
	useFileDiff,
	type ChangedFile,
	type MergeConflict,
	type FetchResult,
	type WorkingTreeStatus,
	type CommitResult,
	type PullResult,
	type PushResult,
	type ResolveResult,
	type DiffResult,
} from "@/hooks/useGitHub";
import { useEditorStore } from "@/stores/editorStore";

/** Icon mapping for entity types */
const ENTITY_ICONS = {
	form: { icon: FileText, className: "text-green-500" },
	agent: { icon: Bot, className: "text-orange-500" },
	app: { icon: AppWindow, className: "text-purple-500" },
	workflow: { icon: Workflow, className: "text-blue-500" },
	app_file: { icon: FileCode, className: "text-gray-500" },
} as const;

/** Get icon for change type */
function getChangeIcon(changeType: string) {
	switch (changeType) {
		case "added":
		case "untracked":
			return <Plus className="h-3 w-3 text-green-500" />;
		case "modified":
			return <Edit3 className="h-3 w-3 text-blue-500" />;
		case "deleted":
			return <Minus className="h-3 w-3 text-red-500" />;
		case "renamed":
			return <Edit3 className="h-3 w-3 text-yellow-500" />;
		default:
			return <Edit3 className="h-3 w-3 text-muted-foreground" />;
	}
}

/** Get change type badge text */
function getChangeBadge(changeType: string) {
	switch (changeType) {
		case "added":
		case "untracked":
			return "A";
		case "modified":
			return "M";
		case "deleted":
			return "D";
		case "renamed":
			return "R";
		default:
			return "?";
	}
}

/**
 * Helper to run a git operation via WebSocket job pattern.
 * Queues the job, connects to WebSocket, waits for completion.
 */
async function runGitOp<T>(
	queueFn: () => Promise<{ job_id: string }>,
	resultType: string,
): Promise<T> {
	const { job_id } = await queueFn();
	if (!job_id) throw new Error("Failed to queue operation");

	await webSocketService.connectToGitSync(job_id);

	return new Promise<T>((resolve, reject) => {
		const unsub = webSocketService.onGitOpComplete(
			job_id,
			(complete: GitOpComplete) => {
				unsub();
				if (complete.status === "success" || complete.resultType === resultType) {
					if (complete.error && complete.status !== "success") {
						reject(new Error(complete.error));
					} else {
						resolve((complete.data ?? {}) as T);
					}
				} else {
					reject(new Error(complete.error || `${resultType} failed`));
				}
			},
		);
	});
}

/**
 * Source Control panel with GitHub Desktop semantics.
 * Independent Fetch, Pull, Push, Commit operations.
 */
export function SourceControlPanel() {
	// State
	const [commitMessage, setCommitMessage] = useState("");
	const [changedFiles, setChangedFiles] = useState<ChangedFile[]>([]);
	const [conflicts, setConflicts] = useState<MergeConflict[]>([]);
	const [conflictResolutions, setConflictResolutions] = useState<Record<string, "ours" | "theirs">>({});
	const [loading, setLoading] = useState<"fetching" | "committing" | "pulling" | "pushing" | "resolving" | "loading_changes" | null>(null);
	const [commitsAhead, setCommitsAhead] = useState(0);
	const [commitsBehind, setCommitsBehind] = useState(0);
	const [commits, setCommits] = useState<
		Array<{
			sha: string;
			message: string;
			author: string;
			timestamp: string;
			is_pushed: boolean;
		}>
	>([]);
	const [totalCommits, setTotalCommits] = useState(0);
	const [hasMoreCommits, setHasMoreCommits] = useState(false);

	const sidebarPanel = useEditorStore((state) => state.sidebarPanel);
	const setDiffPreview = useEditorStore((state) => state.setDiffPreview);
	const queryClient = useQueryClient();

	// Query hooks
	const { data: status, isLoading } = useGitStatus();
	const { data: commitsData, isLoading: isLoadingCommits } = useGitCommits(20, 0);

	// Operation hooks
	const fetchOp = useFetch();
	const commitOp = useCommit();
	const pullOp = usePull();
	const pushOp = usePush();
	const changesOp = useWorkingTreeChanges();
	const resolveOp = useResolveConflicts();
	const diffOp = useFileDiff();

	// Update commits state when data loads
	useEffect(() => {
		if (commitsData) {
			setCommits(commitsData.commits || []);
			setTotalCommits(commitsData.total_commits);
			setHasMoreCommits(commitsData.has_more);
		}
	}, [commitsData]);

	// Sync ahead/behind from status on first load
	useEffect(() => {
		if (status) {
			setCommitsAhead(status.commits_ahead);
			setCommitsBehind(status.commits_behind);
		}
	}, [status]);

	// Refresh helpers
	const refreshStatus = useCallback(() => {
		queryClient.invalidateQueries({ queryKey: ["get", "/api/github/status"] });
		queryClient.invalidateQueries({ queryKey: ["get", "/api/github/commits"] });
	}, [queryClient]);

	const loadChanges = useCallback(async () => {
		setLoading("loading_changes");
		try {
			const result = await runGitOp<WorkingTreeStatus>(
				() => changesOp.mutateAsync(),
				"status",
			);
			setChangedFiles(result.changed_files || []);
		} catch (error) {
			console.error("Failed to load changes:", error);
		} finally {
			setLoading(null);
		}
	}, [changesOp]);

	// --- Operations ---

	const handleFetch = useCallback(async () => {
		setLoading("fetching");
		try {
			const result = await runGitOp<FetchResult>(
				() => fetchOp.mutateAsync(),
				"fetch",
			);
			setCommitsAhead(result.commits_ahead);
			setCommitsBehind(result.commits_behind);
			toast.success(
				result.commits_behind > 0 || result.commits_ahead > 0
					? `${result.commits_behind} behind, ${result.commits_ahead} ahead`
					: "Already up to date",
			);
			// Auto-load changes after fetch
			await loadChanges();
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Fetch failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [fetchOp, loadChanges]);

	const handleCommit = useCallback(async () => {
		if (!commitMessage.trim()) {
			toast.error("Please enter a commit message");
			return;
		}
		setLoading("committing");
		try {
			const result = await runGitOp<CommitResult>(
				() => commitOp.mutateAsync(commitMessage.trim()),
				"commit",
			);
			if (result.success) {
				toast.success(`Committed ${result.files_committed} file(s)`);
				setCommitMessage("");
				setCommitsAhead((prev) => prev + 1);
				setChangedFiles([]);
				refreshStatus();
			} else {
				toast.error(result.error || "Commit failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Commit failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [commitMessage, commitOp, refreshStatus]);

	const handlePull = useCallback(async () => {
		setLoading("pulling");
		try {
			const result = await runGitOp<PullResult>(
				() => pullOp.mutateAsync(),
				"pull",
			);
			if (result.success) {
				toast.success(
					result.pulled > 0
						? `Pulled ${result.pulled} entities`
						: "Already up to date",
				);
				setCommitsBehind(0);
				setConflicts([]);
				setConflictResolutions({});
				refreshStatus();
				await loadChanges();
			} else if (result.conflicts && result.conflicts.length > 0) {
				setConflicts(result.conflicts);
				toast.warning(`${result.conflicts.length} conflict(s) need resolution`);
			} else {
				toast.error(result.error || "Pull failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Pull failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [pullOp, refreshStatus, loadChanges]);

	const handlePush = useCallback(async () => {
		setLoading("pushing");
		try {
			const result = await runGitOp<PushResult>(
				() => pushOp.mutateAsync(),
				"push",
			);
			if (result.success) {
				toast.success(
					result.pushed_commits > 0
						? `Pushed ${result.pushed_commits} commit(s)`
						: "Nothing to push",
				);
				setCommitsAhead(0);
				refreshStatus();
			} else {
				toast.error(result.error || "Push failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Push failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [pushOp, refreshStatus]);

	const handleResolveConflicts = useCallback(async () => {
		const unresolvedCount = conflicts.filter((c) => !conflictResolutions[c.path]).length;
		if (unresolvedCount > 0) {
			toast.error("Please resolve all conflicts before completing merge");
			return;
		}
		setLoading("resolving");
		try {
			const result = await runGitOp<ResolveResult>(
				() => resolveOp.mutateAsync(conflictResolutions),
				"resolve",
			);
			if (result.success) {
				toast.success(`Merge complete, imported ${result.pulled} entities`);
				setConflicts([]);
				setConflictResolutions({});
				refreshStatus();
				await loadChanges();
			} else {
				toast.error(result.error || "Resolve failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Resolve failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [conflicts, conflictResolutions, resolveOp, refreshStatus, loadChanges]);

	const handleShowDiff = useCallback(async (file: ChangedFile) => {
		setDiffPreview({
			path: file.path,
			displayName: file.display_name || file.path,
			entityType: file.entity_type || "workflow",
			localContent: null,
			remoteContent: null,
			isConflict: false,
			isLoading: true,
		});

		try {
			const result = await runGitOp<DiffResult>(
				() => diffOp.mutateAsync(file.path),
				"diff",
			);
			setDiffPreview({
				path: file.path,
				displayName: file.display_name || file.path,
				entityType: file.entity_type || "workflow",
				localContent: result.working_content ?? null,
				remoteContent: result.head_content ?? null,
				isConflict: false,
				isLoading: false,
			});
		} catch (error) {
			console.error("Failed to load diff:", error);
			setDiffPreview(null);
		}
	}, [diffOp, setDiffPreview]);

	const handleShowConflictDiff = useCallback(
		(conflict: MergeConflict) => {
			const resolution = conflictResolutions[conflict.path];
			setDiffPreview({
				path: conflict.path,
				displayName: conflict.display_name || conflict.path,
				entityType: conflict.entity_type || "workflow",
				localContent: conflict.ours_content ?? null,
				remoteContent: conflict.theirs_content ?? null,
				isConflict: true,
				isLoading: false,
				resolution,
				onResolve: (res) => {
					setConflictResolutions((prev) => ({ ...prev, [conflict.path]: res }));
					// Update diff preview resolution
					setDiffPreview((prev) => (prev ? { ...prev, resolution: res } : null));
				},
			});
		},
		[conflictResolutions, setDiffPreview],
	);

	// Auto-refresh on visibility change
	useEffect(() => {
		if (sidebarPanel !== "sourceControl") return;

		const handleVisibility = () => {
			if (!document.hidden) refreshStatus();
		};
		document.addEventListener("visibilitychange", handleVisibility);
		return () => document.removeEventListener("visibilitychange", handleVisibility);
	}, [sidebarPanel, refreshStatus]);

	// --- Render ---

	if (isLoading || !status) {
		return (
			<div className="flex h-full flex-col p-4">
				<div className="flex items-center gap-2 mb-4">
					<GitBranch className="h-5 w-5" />
					<h3 className="text-sm font-semibold">Source Control</h3>
				</div>
				<div className="flex flex-col items-center justify-center flex-1 text-center">
					<Loader2 className="h-12 w-12 text-muted-foreground mb-4 animate-spin" />
					<p className="text-sm text-muted-foreground">Loading Git status...</p>
				</div>
			</div>
		);
	}

	if (!status?.initialized) {
		if (status?.configured) {
			return (
				<div className="flex h-full flex-col p-4">
					<div className="flex items-center gap-2 mb-4">
						<GitBranch className="h-5 w-5" />
						<h3 className="text-sm font-semibold">Source Control</h3>
					</div>
					<div className="flex flex-col items-center justify-center flex-1 text-center">
						<GitBranch className="h-12 w-12 text-muted-foreground mb-4" />
						<p className="text-sm text-muted-foreground mb-2">GitHub connected</p>
						<p className="text-xs text-muted-foreground mb-4">
							Fetch to initialize your local repository
						</p>
						<Button
							onClick={handleFetch}
							disabled={!!loading}
							className="gap-2"
						>
							{loading === "fetching" ? (
								<>
									<Loader2 className="h-4 w-4 animate-spin" />
									Fetching...
								</>
							) : (
								<>
									<ArrowDownToLine className="h-4 w-4" />
									Fetch from GitHub
								</>
							)}
						</Button>
					</div>
				</div>
			);
		}

		return (
			<div className="flex h-full flex-col p-4">
				<div className="flex items-center gap-2 mb-4">
					<GitBranch className="h-5 w-5" />
					<h3 className="text-sm font-semibold">Source Control</h3>
				</div>
				<div className="flex flex-col items-center justify-center flex-1 text-center">
					<GitBranch className="h-12 w-12 text-muted-foreground mb-4" />
					<p className="text-sm text-muted-foreground mb-2">Git not initialized</p>
					<p className="text-xs text-muted-foreground">
						Configure GitHub integration in Settings
					</p>
				</div>
			</div>
		);
	}

	const hasConflicts = conflicts.length > 0;
	const resolvedCount = Object.keys(conflictResolutions).length;
	const allConflictsResolved = hasConflicts && resolvedCount === conflicts.length;

	return (
		<div className="flex h-full flex-col">
			{/* Header */}
			<div className="flex items-center justify-between p-4 border-b">
				<div className="flex items-center gap-2">
					<GitBranch className="h-5 w-5" />
					<div className="flex flex-col">
						<h3 className="text-sm font-semibold">Source Control</h3>
						{status.current_branch && (
							<span className="text-xs text-muted-foreground">
								{status.current_branch}
							</span>
						)}
					</div>
				</div>
				<button
					onClick={handleFetch}
					disabled={!!loading}
					className="p-1.5 rounded hover:bg-muted/50 transition-colors disabled:opacity-50"
					title="Fetch from remote"
				>
					{loading === "fetching" ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<RefreshCw className="h-4 w-4" />
					)}
				</button>
			</div>

			{/* Action bar */}
			{status.configured && (
				<div className="border-b px-4 py-2 flex items-center gap-2">
					{commitsBehind > 0 && (
						<Button
							size="sm"
							variant="outline"
							onClick={handlePull}
							disabled={!!loading}
							className="gap-1.5 flex-1"
						>
							{loading === "pulling" ? (
								<Loader2 className="h-3.5 w-3.5 animate-spin" />
							) : (
								<Download className="h-3.5 w-3.5" />
							)}
							Pull {commitsBehind > 0 && <span className="text-xs">↓{commitsBehind}</span>}
						</Button>
					)}
					{commitsAhead > 0 && (
						<Button
							size="sm"
							variant="outline"
							onClick={handlePush}
							disabled={!!loading}
							className="gap-1.5 flex-1"
						>
							{loading === "pushing" ? (
								<Loader2 className="h-3.5 w-3.5 animate-spin" />
							) : (
								<Upload className="h-3.5 w-3.5" />
							)}
							Push {commitsAhead > 0 && <span className="text-xs">↑{commitsAhead}</span>}
						</Button>
					)}
					{commitsBehind === 0 && commitsAhead === 0 && (
						<span className="text-xs text-muted-foreground">
							{status.last_synced
								? `Synced ${formatDistanceToNow(new Date(status.last_synced), { addSuffix: true })}`
								: "Up to date"}
						</span>
					)}
				</div>
			)}

			{/* Scrollable sections */}
			<div className="flex-1 flex flex-col min-h-0 overflow-hidden">
				{/* Merge conflicts (only after failed pull) */}
				{hasConflicts && (
					<ConflictsSection
						conflicts={conflicts}
						resolutions={conflictResolutions}
						onResolve={(path, res) =>
							setConflictResolutions((prev) => ({ ...prev, [path]: res }))
						}
						onResolveAll={(res) => {
							const all: Record<string, "ours" | "theirs"> = {};
							for (const c of conflicts) all[c.path] = res;
							setConflictResolutions(all);
						}}
						onShowDiff={handleShowConflictDiff}
						onCompleteMerge={handleResolveConflicts}
						allResolved={allConflictsResolved}
						isResolving={loading === "resolving"}
					/>
				)}

				{/* Changes (uncommitted) */}
				<ChangesSection
					changedFiles={changedFiles}
					commitMessage={commitMessage}
					onCommitMessageChange={setCommitMessage}
					onCommit={handleCommit}
					onShowDiff={handleShowDiff}
					isCommitting={loading === "committing"}
					isLoadingChanges={loading === "loading_changes"}
					disabled={!!loading}
					branch={status.current_branch || "main"}
				/>

				{/* Commits */}
				<CommitsSection
					commits={commits}
					totalCommits={totalCommits}
					hasMore={hasMoreCommits}
					isLoading={isLoadingCommits}
				/>
			</div>
		</div>
	);
}

// =============================================================================
// Sub-components
// =============================================================================

function ConflictsSection({
	conflicts,
	resolutions,
	onResolve,
	onResolveAll,
	onShowDiff,
	onCompleteMerge,
	allResolved,
	isResolving,
}: {
	conflicts: MergeConflict[];
	resolutions: Record<string, "ours" | "theirs">;
	onResolve: (path: string, resolution: "ours" | "theirs") => void;
	onResolveAll: (resolution: "ours" | "theirs") => void;
	onShowDiff: (conflict: MergeConflict) => void;
	onCompleteMerge: () => void;
	allResolved: boolean;
	isResolving: boolean;
}) {
	const [expanded, setExpanded] = useState(true);
	const resolvedCount = Object.keys(resolutions).length;

	return (
		<div className={cn("border-b flex flex-col min-h-0", expanded && "flex-1")}>
			<div className="flex items-center px-4 py-2 hover:bg-muted/30 transition-colors flex-shrink-0">
				<button
					onClick={() => setExpanded(!expanded)}
					className="flex items-center gap-2 flex-1 text-left"
				>
					{expanded ? (
						<ChevronDown className="h-4 w-4 flex-shrink-0" />
					) : (
						<ChevronRight className="h-4 w-4 flex-shrink-0" />
					)}
					<AlertCircle className="h-4 w-4 text-orange-500 flex-shrink-0" />
					<span className="text-sm font-medium flex-1 truncate">Merge Conflicts</span>
					<span
						className={cn(
							"text-xs w-10 text-center py-0.5 rounded-full flex-shrink-0",
							resolvedCount === conflicts.length
								? "bg-green-500/20 text-green-700"
								: "bg-orange-500/20 text-orange-700",
						)}
					>
						{resolvedCount}/{conflicts.length}
					</span>
				</button>
				{conflicts.length > 1 && (
					<div className="flex gap-1 ml-2">
						<button
							onClick={() => onResolveAll("ours")}
							className="px-2 py-0.5 text-xs rounded bg-muted hover:bg-muted/80 transition-colors"
							title="Keep all ours (platform)"
						>
							All Ours
						</button>
						<button
							onClick={() => onResolveAll("theirs")}
							className="px-2 py-0.5 text-xs rounded bg-muted hover:bg-muted/80 transition-colors"
							title="Accept all theirs (git)"
						>
							All Theirs
						</button>
					</div>
				)}
			</div>
			{expanded && (
				<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
					{conflicts.map((conflict) => {
						const resolution = resolutions[conflict.path];
						const entityType = conflict.entity_type as keyof typeof ENTITY_ICONS | null;
						const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
						const IconComponent = iconConfig?.icon ?? FileCode;
						const iconClassName = iconConfig?.className ?? "text-gray-500";

						return (
							<div key={conflict.path} className="py-1">
								<div
									onClick={() => onShowDiff(conflict)}
									className={cn(
										"flex items-center gap-2 text-xs py-1.5 px-2 rounded cursor-pointer",
										!resolution && "bg-orange-500/10",
										resolution && "bg-green-500/10",
									)}
								>
									<IconComponent className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />
									<span className="flex-1 truncate" title={conflict.path}>
										{conflict.display_name || conflict.path}
									</span>
								</div>
								<div className="flex gap-1 ml-6 mt-1">
									<button
										onClick={() => onResolve(conflict.path, "ours")}
										className={cn(
											"px-2 py-0.5 text-xs rounded",
											resolution === "ours"
												? "bg-blue-500 text-white"
												: "bg-muted hover:bg-muted/80",
										)}
									>
										Keep Ours
									</button>
									<button
										onClick={() => onResolve(conflict.path, "theirs")}
										className={cn(
											"px-2 py-0.5 text-xs rounded",
											resolution === "theirs"
												? "bg-blue-500 text-white"
												: "bg-muted hover:bg-muted/80",
										)}
									>
										Keep Theirs
									</button>
								</div>
							</div>
						);
					})}

					{/* Complete Merge button */}
					<div className="mt-3 pt-2 border-t">
						<Button
							size="sm"
							className="w-full gap-2"
							onClick={onCompleteMerge}
							disabled={!allResolved || isResolving}
						>
							{isResolving ? (
								<>
									<Loader2 className="h-3.5 w-3.5 animate-spin" />
									Completing Merge...
								</>
							) : (
								<>
									<CheckCircle2 className="h-3.5 w-3.5" />
									Complete Merge
								</>
							)}
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}

function ChangesSection({
	changedFiles,
	commitMessage,
	onCommitMessageChange,
	onCommit,
	onShowDiff,
	isCommitting,
	isLoadingChanges,
	disabled,
	branch,
}: {
	changedFiles: ChangedFile[];
	commitMessage: string;
	onCommitMessageChange: (msg: string) => void;
	onCommit: () => void;
	onShowDiff: (file: ChangedFile) => void;
	isCommitting: boolean;
	isLoadingChanges: boolean;
	disabled: boolean;
	branch: string;
}) {
	const [expanded, setExpanded] = useState(true);

	return (
		<div className={cn("border-t flex flex-col min-h-0", expanded && "flex-1")}>
			<button
				onClick={() => setExpanded(!expanded)}
				className="w-full px-4 py-2 flex items-center gap-2 hover:bg-muted/30 transition-colors text-left flex-shrink-0"
			>
				{expanded ? (
					<ChevronDown className="h-4 w-4 flex-shrink-0" />
				) : (
					<ChevronRight className="h-4 w-4 flex-shrink-0" />
				)}
				<Edit3 className="h-4 w-4 flex-shrink-0" />
				<span className="text-sm font-medium flex-1 truncate">Changes</span>
				<span className="text-xs text-muted-foreground bg-muted w-10 text-center py-0.5 rounded-full flex-shrink-0">
					{changedFiles.length}
				</span>
			</button>
			{expanded && (
				<div className="flex-1 flex flex-col overflow-hidden min-h-0">
					{/* Commit message + button */}
					<div className="px-4 pt-2 pb-2 flex flex-col gap-2 flex-shrink-0">
						<input
							type="text"
							value={commitMessage}
							onChange={(e) => onCommitMessageChange(e.target.value)}
							placeholder="Commit message"
							className="w-full px-2 py-1.5 text-xs bg-muted/50 border border-border rounded focus:outline-none focus:ring-1 focus:ring-ring"
							disabled={disabled}
							onKeyDown={(e) => {
								if (e.key === "Enter" && commitMessage.trim() && changedFiles.length > 0) {
									onCommit();
								}
							}}
						/>
						<Button
							size="sm"
							className="w-full gap-2"
							onClick={onCommit}
							disabled={disabled || !commitMessage.trim() || changedFiles.length === 0}
						>
							{isCommitting ? (
								<>
									<Loader2 className="h-3.5 w-3.5 animate-spin" />
									Committing...
								</>
							) : (
								`Commit to ${branch}`
							)}
						</Button>
					</div>

					{/* File list */}
					<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
						{isLoadingChanges ? (
							<div className="flex items-center justify-center py-4">
								<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
							</div>
						) : changedFiles.length === 0 ? (
							<p className="text-xs text-muted-foreground text-center py-4">
								No uncommitted changes
							</p>
						) : (
							changedFiles.map((file) => {
								const entityType = file.entity_type as keyof typeof ENTITY_ICONS | null;
								const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
								const IconComponent = iconConfig?.icon ?? FileCode;
								const iconClassName = iconConfig?.className ?? "text-gray-500";

								return (
									<div
										key={file.path}
										onClick={() => onShowDiff(file)}
										className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-muted/30 cursor-pointer"
									>
										{getChangeIcon(file.change_type)}
										<IconComponent className={cn("h-3.5 w-3.5 flex-shrink-0", iconClassName)} />
										<span className="flex-1 truncate" title={file.path}>
											{file.display_name || file.path}
										</span>
										<span
											className={cn(
												"text-xs font-mono w-4 text-center flex-shrink-0",
												file.change_type === "added" && "text-green-500",
												file.change_type === "modified" && "text-blue-500",
												file.change_type === "deleted" && "text-red-500",
											)}
										>
											{getChangeBadge(file.change_type)}
										</span>
									</div>
								);
							})
						)}
					</div>
				</div>
			)}
		</div>
	);
}

function CommitsSection({
	commits,
	totalCommits,
	hasMore,
	isLoading,
}: {
	commits: Array<{
		sha: string;
		message: string;
		author: string;
		timestamp: string;
		is_pushed: boolean;
	}>;
	totalCommits?: number;
	hasMore?: boolean;
	isLoading?: boolean;
}) {
	const [expanded, setExpanded] = useState(true);

	return (
		<div className={cn("border-t flex flex-col min-h-0", expanded && "flex-1")}>
			<button
				onClick={() => setExpanded(!expanded)}
				className="w-full px-4 py-2 flex items-center gap-2 hover:bg-muted/30 transition-colors text-left flex-shrink-0"
			>
				{expanded ? (
					<ChevronDown className="h-4 w-4 flex-shrink-0" />
				) : (
					<ChevronRight className="h-4 w-4 flex-shrink-0" />
				)}
				<History className="h-4 w-4 flex-shrink-0" />
				<span className="text-sm font-medium flex-1 truncate">Commits</span>
				<span className="text-xs text-muted-foreground bg-muted w-10 text-center py-0.5 rounded-full flex-shrink-0">
					{totalCommits ?? commits.length}
				</span>
			</button>
			{expanded && (
				<div className="flex-1 flex flex-col overflow-hidden min-h-0">
					<div className="flex-1 overflow-y-auto px-4 py-2 min-h-0">
						{isLoading && commits.length === 0 ? (
							<div className="flex flex-col items-center justify-center py-8 text-center">
								<Loader2 className="h-6 w-6 text-muted-foreground mb-2 animate-spin" />
								<p className="text-xs text-muted-foreground">Loading commits...</p>
							</div>
						) : commits.length === 0 ? (
							<div className="flex flex-col items-center justify-center py-8 text-center">
								<History className="h-6 w-6 text-muted-foreground mb-2" />
								<p className="text-xs text-muted-foreground">No commits</p>
							</div>
						) : (
							<div className="space-y-1">
								{commits.map((commit) => (
									<div
										key={commit.sha}
										className="group flex items-start gap-2 px-2 py-2 rounded hover:bg-muted/30 transition-colors"
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
												{new Date(commit.timestamp).toLocaleDateString()}
											</p>
										</div>
									</div>
								))}
								{hasMore && (
									<p className="text-xs text-center text-muted-foreground py-2">
										{(totalCommits ?? 0) - commits.length} more commits
									</p>
								)}
							</div>
						)}
					</div>
				</div>
			)}
		</div>
	);
}
