import { useState, useEffect, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { webSocketService, type GitOpComplete } from "@/services/websocket";
import {
	GitBranch,
	Loader2,
	RefreshCw,
	ArrowDownToLine,
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
	Undo2,
	AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	ContextMenu,
	ContextMenuContent,
	ContextMenuItem,
	ContextMenuTrigger,
} from "@/components/ui/context-menu";
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
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
	useGitStatus,
	useGitCommits,
	useFetch,
	useCommit,
	useSync,
	useAbortMerge,
	useDiscard,
	useWorkingTreeChanges,
	useResolveConflicts,
	useFileDiff,
	useCleanupOrphaned,
	type ChangedFile,
	type MergeConflict,
	type EntityChange,
	type FetchResult,
	type WorkingTreeStatus,
	type CommitResult,
	type SyncResult,
	type AbortMergeResult,
	type ResolveResult,
	type DiffResult,
	type DiscardResult,
	type PreflightResult,
} from "@/hooks/useGitHub";
import { useEditorStore } from "@/stores/editorStore";

/** Custom error that preserves the data payload from failed git operations */
class GitOpError extends Error {
	data: Record<string, unknown> | undefined;
	constructor(message: string, data?: Record<string, unknown>) {
		super(message);
		this.name = "GitOpError";
		this.data = data;
	}
}

/** Log preflight validation issues to the editor terminal */
function logPreflightToTerminal(preflight: PreflightResult, commitSucceeded: boolean) {
	if (!preflight.issues.length) return;

	const errors = preflight.issues.filter((i) => i.severity === "error");
	const warnings = preflight.issues.filter((i) => i.severity === "warning");

	const header = commitSucceeded
		? `Commit succeeded with ${warnings.length} warning(s)`
		: `Commit blocked: ${errors.length} error(s), ${warnings.length} warning(s)`;

	const logs: Array<{ level: string; message: string; source: string; timestamp: string }> = [
		{
			level: commitSucceeded ? "WARNING" : "ERROR",
			message: `[Preflight] ${header}`,
			source: "preflight",
			timestamp: new Date().toISOString(),
		},
	];

	// Show errors individually, collapse warnings into a summary by category
	const hintGroups = new Map<string, number>();
	const warningsByCategory = new Map<string, number>();

	for (const issue of preflight.issues) {
		if (issue.severity === "error") {
			logs.push({
				level: "ERROR",
				message: `${issue.path}${issue.line ? ` [Line ${issue.line}]` : ""}: ${issue.message} (${issue.category})`,
				source: "preflight",
				timestamp: new Date().toISOString(),
			});
		} else {
			warningsByCategory.set(issue.category, (warningsByCategory.get(issue.category) ?? 0) + 1);
		}
		if (issue.fix_hint) {
			hintGroups.set(issue.fix_hint, (hintGroups.get(issue.fix_hint) ?? 0) + 1);
		}
	}

	// Collapsed warning summaries by category
	for (const [category, count] of warningsByCategory) {
		logs.push({
			level: "WARNING",
			message: `${count} ${category} warning${count !== 1 ? "s" : ""}`,
			source: "preflight",
			timestamp: new Date().toISOString(),
		});
	}

	// Append deduplicated fix hints at the end (errors only)
	for (const [hint] of hintGroups) {
		const errorHintCount = preflight.issues.filter((i) => i.severity === "error" && i.fix_hint === hint).length;
		if (errorHintCount > 0) {
			const suffix = errorHintCount > 1 ? ` (${errorHintCount} issues)` : "";
			logs.push({
				level: "INFO",
				message: `-> Fix: ${hint}${suffix}`,
				source: "preflight",
				timestamp: new Date().toISOString(),
			});
		}
	}

	useEditorStore.getState().appendTerminalOutput({
		loggerOutput: logs,
		variables: {},
		status: commitSucceeded ? "Success" : "Failed",
		executionId: `preflight-${Date.now()}`,
		error: commitSucceeded ? undefined : "Preflight validation failed",
	});
}

/** Log entity changes to the editor terminal */
function logEntityChangesToTerminal(changes: EntityChange[], context: "commit" | "sync") {
	if (!changes.length) return;

	const added = changes.filter((c) => c.action === "added");
	const updated = changes.filter((c) => c.action === "updated");
	const removed = changes.filter((c) => c.action === "removed");

	const countParts: string[] = [];
	if (added.length) countParts.push(`${added.length} added`);
	if (updated.length) countParts.push(`${updated.length} updated`);
	if (removed.length) countParts.push(`${removed.length} removed`);

	const label = context === "commit" ? "Commit" : "Sync";
	const header = `${label} — ${changes.length} entity change(s): ${countParts.join(", ")}`;

	const symbols = { added: "+", updated: "~", removed: "-" } as const;
	const levels = { added: "INFO", updated: "INFO", removed: "WARNING" } as const;
	const timestamp = new Date().toISOString();

	const logs: Array<{ level: string; message: string; source: string; timestamp: string }> = [
		{ level: "INFO", message: `[Entity Changes] ${header}`, source: "entity-changes", timestamp },
	];

	for (const change of changes) {
		const sym = symbols[change.action];
		const suffix = change.reason ? `  (${change.reason})` : "";
		logs.push({
			level: levels[change.action],
			message: `  ${sym} ${change.entity_type.padEnd(14)} ${change.name}${suffix}`,
			source: "entity-changes",
			timestamp,
		});
	}

	useEditorStore.getState().appendTerminalOutput({
		loggerOutput: logs,
		variables: {},
		status: "Success",
		error: undefined,
		executionId: `entity-changes-${Date.now()}`,
	});
}

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
	queueFn: (jobId: string) => Promise<{ job_id: string }>,
	resultType: string,
): Promise<T> {
	// Generate job_id client-side and subscribe BEFORE queueing to avoid
	// race condition where fast operations (e.g. diff) complete before
	// the WebSocket subscription is active.
	const job_id = crypto.randomUUID();

	await webSocketService.connectToGitSync(job_id);

	// Stream progress messages immediately; accumulate sync log summaries for final flush
	const syncLogs: Array<{ level: string; message: string; source: string; timestamp: string }> = [];
	const executionId = `git-${resultType}-${job_id.slice(0, 8)}`;

	const unsubLog = webSocketService.onGitSyncLog(job_id, (log) => {
		syncLogs.push({
			level: log.level,
			message: log.message,
			source: "git",
			timestamp: new Date().toISOString(),
		});
	});

	let hadProgress = false;
	const unsubProgress = webSocketService.onGitProgress(job_id, (progress) => {
		hadProgress = true;
		// Stream each progress message immediately to the terminal
		const pct = progress.total > 0
			? `[${Math.round((progress.current / progress.total) * 100)}%] `
			: "";
		useEditorStore.getState().streamTerminalLog(
			executionId,
			{
				level: "INFO",
				message: `${pct}${progress.phase}`,
				source: "git",
				timestamp: new Date().toISOString(),
			},
			"Running",
		);
	});

	const resultPromise = new Promise<T>((resolve, reject) => {
		const unsub = webSocketService.onGitOpComplete(
			job_id,
			(complete: GitOpComplete) => {
				unsub();
				unsubLog();
				unsubProgress();

				// Treat "needs_confirmation" as a non-error status — the caller
				// handles the confirmation flow, not the terminal.
				const isOk = complete.status === "success" || complete.status === "needs_confirmation";

				// Only emit terminal logs if there was visible activity (progress
				// messages or sync logs). Silent operations like "status" produce
				// no output and shouldn't clutter the terminal.
				const hadOutput = syncLogs.length > 0 || hadProgress;
				if (hadOutput || !isOk) {
					const finalStatus = isOk ? "Success" : "Failed";
					for (const log of syncLogs) {
						useEditorStore.getState().streamTerminalLog(executionId, log, finalStatus);
					}
					const opLabel = resultType === "sync" ? "Sync"
						: resultType === "fetch" ? "Fetch"
						: resultType === "commit" ? "Commit"
						: resultType.charAt(0).toUpperCase() + resultType.slice(1);
					useEditorStore.getState().streamTerminalLog(
						executionId,
						{
							level: isOk ? "INFO" : "WARNING",
							message: isOk
								? `${opLabel} complete`
								: `${opLabel} failed: ${complete.error || "unknown error"}`,
							source: "git",
							timestamp: new Date().toISOString(),
						},
						finalStatus,
					);
				}

				if (isOk || complete.resultType === resultType) {
					if (complete.error && !isOk) {
						reject(new GitOpError(complete.error, complete.data as Record<string, unknown>));
					} else {
						resolve((complete.data ?? {}) as T);
					}
				} else {
					reject(new GitOpError(complete.error || `${resultType} failed`, complete.data as Record<string, unknown>));
				}
			},
		);
	});

	// Now queue the operation — the WebSocket listener is already active
	await queueFn(job_id);

	return resultPromise;
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
	const [loading, setLoading] = useState<"fetching" | "committing" | "syncing" | "resolving" | "loading_changes" | null>(null);

	const [commitsAhead, setCommitsAhead] = useState(0);
	const [commitsBehind, setCommitsBehind] = useState(0);
	const [needsSync, setNeedsSync] = useState(false);
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
	const [showCleanupPrompt, setShowCleanupPrompt] = useState(false);
	const [orphanedCount, setOrphanedCount] = useState(0);
	const [pendingDeletes, setPendingDeletes] = useState<EntityChange[]>([]);

	const sidebarPanel = useEditorStore((state) => state.sidebarPanel);
	const setDiffPreview = useEditorStore((state) => state.setDiffPreview);
	const queryClient = useQueryClient();
	const diffCacheRef = useRef<Map<string, DiffResult>>(new Map());

	// Query hooks
	const { data: status, isLoading } = useGitStatus();
	const { data: commitsData, isLoading: isLoadingCommits } = useGitCommits(20, 0);

	// Operation hooks
	const fetchOp = useFetch();
	const commitOp = useCommit();
	const syncOp = useSync();
	const abortMergeOp = useAbortMerge();
	const changesOp = useWorkingTreeChanges();
	const resolveOp = useResolveConflicts();
	const diffOp = useFileDiff();
	const discardOp = useDiscard();
	const cleanupOp = useCleanupOrphaned();

	// Update commits state when data loads. Adjust during render with a
	// previous-reference sentinel rather than via setState-in-effect.
	const [prevCommitsDataRef, setPrevCommitsDataRef] =
		useState<typeof commitsData>(undefined);
	if (commitsData && prevCommitsDataRef !== commitsData) {
		setPrevCommitsDataRef(commitsData);
		setCommits(commitsData.commits || []);
		setTotalCommits(commitsData.total_commits);
		setHasMoreCommits(commitsData.has_more);
	}

	// Refresh helpers
	const refreshStatus = useCallback(() => {
		queryClient.invalidateQueries({ queryKey: ["get", "/api/github/status"] });
		queryClient.invalidateQueries({ queryKey: ["get", "/api/github/commits"] });
	}, [queryClient]);

	const loadChanges = useCallback(async () => {
		setLoading("loading_changes");
		try {
			const result = await runGitOp<WorkingTreeStatus>(
				(jobId) => changesOp.mutateAsync(jobId),
				"status",
			);
			setChangedFiles(result.changed_files || []);
			// Surface conflicts from real git state (or clear if resolved)
			setConflicts(result.conflicts ?? []);
			// Update ahead/behind from real git status
			setCommitsAhead(result.commits_ahead);
			setCommitsBehind(result.commits_behind);
		} catch (error) {
			console.error("Failed to load changes:", error);
		} finally {
			setLoading(null);
		}
	}, [changesOp]);

	// Load real git status (ahead/behind/conflicts) when panel mounts
	// The lightweight /status endpoint only provides initialized/configured/branch — not real git state
	const hasLoadedRef = useRef(false);
	useEffect(() => {
		if (status?.initialized && !hasLoadedRef.current) {
			hasLoadedRef.current = true;
			loadChanges();
		}
	}, [status?.initialized, loadChanges]);

	// Clear diff cache when changed files list changes (after fetch, commit, pull, discard)
	useEffect(() => {
		diffCacheRef.current.clear();
	}, [changedFiles]);

	// --- Operations ---

	const handleFetch = useCallback(async () => {
		setLoading("fetching");
		try {
			const result = await runGitOp<FetchResult>(
				(jobId) => fetchOp.mutateAsync(jobId),
				"fetch",
			);
			toast.success(
				result.commits_behind > 0 || result.commits_ahead > 0
					? `${result.commits_behind} behind, ${result.commits_ahead} ahead`
					: "Already up to date",
			);
			if (result.commits_behind > 0) setNeedsSync(true);
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
		setShowCleanupPrompt(false);
		try {
			const result = await runGitOp<CommitResult>(
				(jobId) => commitOp.mutateAsync(commitMessage.trim(), jobId),
				"commit",
			);
			if (result.success) {
				toast.success(`Committed ${result.files_committed} file(s)`);
				setCommitMessage("");
				setChangedFiles([]);
				await loadChanges();
				refreshStatus();
				if (result.preflight?.issues?.length) {
					logPreflightToTerminal(result.preflight, true);
				}
				if (result.entity_changes?.length) {
					logEntityChangesToTerminal(result.entity_changes, "commit");
				}
			} else {
				toast.error(result.error || "Commit failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Commit failed: ${msg}`);
			if (error instanceof GitOpError && error.data) {
				const commitData = error.data as unknown as CommitResult;
				if (commitData.preflight?.issues?.length) {
					logPreflightToTerminal(commitData.preflight, false);
					// Check for auto-fixable issues and show cleanup prompt
					const fixableCount = commitData.preflight.issues.filter(
						(i) => i.auto_fixable,
					).length;
					if (fixableCount > 0) {
						setShowCleanupPrompt(true);
						setOrphanedCount(fixableCount);
					}
				}
			}
		} finally {
			setLoading(null);
		}
	}, [commitMessage, commitOp, loadChanges, refreshStatus]);

	const handleCleanupAndRetry = useCallback(async () => {
		setLoading("committing");
		try {
			const result = await cleanupOp.mutateAsync({});
			const cleaned = result.cleaned ?? [];
			const count = result.count ?? 0;

			// Log cleanup results to terminal
			const logs = [
				{
					level: "INFO",
					message: `[Cleanup] Removed ${count} orphaned reference(s)`,
					source: "preflight",
					timestamp: new Date().toISOString(),
				},
				...cleaned.map((e: { entity_type: string; entity_name: string; path: string }) => ({
					level: "INFO",
					message: `   Deactivated ${e.entity_type}: ${e.entity_name} (${e.path})`,
					source: "preflight",
					timestamp: new Date().toISOString(),
				})),
			];
			useEditorStore.getState().appendTerminalOutput({
				loggerOutput: logs,
				variables: {},
				status: "Success",
				error: undefined,
				executionId: `cleanup-${Date.now()}`,
			});

			setShowCleanupPrompt(false);
			setOrphanedCount(0);

			// Re-commit automatically
			toast.success(`Cleaned ${count} orphaned reference(s), retrying commit...`);
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Cleanup failed: ${msg}`);
			setLoading(null);
			return;
		}

		// Retry the commit
		try {
			const result = await runGitOp<CommitResult>(
				(jobId) => commitOp.mutateAsync(commitMessage.trim(), jobId),
				"commit",
			);
			if (result.success) {
				toast.success(`Committed ${result.files_committed} file(s)`);
				setCommitMessage("");
				setChangedFiles([]);
				await loadChanges();
				refreshStatus();
				if (result.preflight?.issues?.length) {
					logPreflightToTerminal(result.preflight, true);
				}
			} else {
				toast.error(result.error || "Commit failed after cleanup");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Commit failed after cleanup: ${msg}`);
			if (error instanceof GitOpError && error.data) {
				const commitData = error.data as unknown as CommitResult;
				if (commitData.preflight?.issues?.length) {
					logPreflightToTerminal(commitData.preflight, false);
				}
			}
		} finally {
			setLoading(null);
		}
	}, [cleanupOp, commitOp, commitMessage, loadChanges, refreshStatus]);

	const handleSync = useCallback(async (confirmDeletes = false) => {
		setLoading("syncing");
		try {
			const result = await runGitOp<SyncResult>(
				(jobId) => syncOp.mutateAsync(jobId, confirmDeletes ? { confirm_deletes: true } : undefined),
				"sync",
			);
			if (result.needs_delete_confirmation && result.pending_deletes?.length) {
				setPendingDeletes(result.pending_deletes);
				toast.warning(`${result.pending_deletes.length} entity deletion(s) require confirmation`);
			} else if (result.success) {
				const parts = [];
				if (result.pushed_commits > 0) parts.push(`pushed ${result.pushed_commits} commit(s)`);
				if (result.entities_imported > 0) parts.push(`imported ${result.entities_imported} entities`);
				toast.success(parts.length > 0 ? `Sync complete: ${parts.join(", ")}` : "Already up to date");
				setNeedsSync(false);
				setConflicts([]);
				setConflictResolutions({});
				setPendingDeletes([]);
				refreshStatus();
				await loadChanges();
				if (result.entity_changes?.length) {
					logEntityChangesToTerminal(result.entity_changes, "sync");
				}
			} else if (result.conflicts && result.conflicts.length > 0) {
				setConflicts(result.conflicts);
				toast.warning(`${result.conflicts.length} conflict(s) need resolution`);
			} else {
				toast.error(result.error || "Sync failed");
			}
		} catch (error) {
			// Check if this is a conflict or delete-confirmation result
			if (error instanceof GitOpError && error.data) {
				const syncData = error.data as unknown as SyncResult;
				if (syncData.needs_delete_confirmation && syncData.pending_deletes?.length) {
					setPendingDeletes(syncData.pending_deletes);
					toast.warning(`${syncData.pending_deletes.length} entity deletion(s) require confirmation`);
					return;
				}
				if (syncData.conflicts && syncData.conflicts.length > 0) {
					setConflicts(syncData.conflicts);
					toast.warning(`${syncData.conflicts.length} conflict(s) need resolution`);
					return;
				}
			}
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Sync failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [syncOp, refreshStatus, loadChanges]);

	const handleAbortMerge = useCallback(async () => {
		setLoading("resolving");
		try {
			const result = await runGitOp<AbortMergeResult>(
				(jobId) => abortMergeOp.mutateAsync(jobId),
				"abort_merge",
			);
			if (result.success) {
				toast.success("Merge aborted");
				setConflicts([]);
				setConflictResolutions({});
				refreshStatus();
				await loadChanges();
			} else {
				toast.error(result.error || "Abort merge failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Abort merge failed: ${msg}`);
		} finally {
			setLoading(null);
		}
	}, [abortMergeOp, refreshStatus, loadChanges]);

	const handleResolveConflicts = useCallback(async () => {
		const unresolvedCount = conflicts.filter((c) => !conflictResolutions[c.path]).length;
		if (unresolvedCount > 0) {
			toast.error("Please resolve all conflicts before completing merge");
			return;
		}
		setLoading("resolving");
		try {
			const result = await runGitOp<ResolveResult>(
				(jobId) => resolveOp.mutateAsync(conflictResolutions, jobId),
				"resolve",
			);
			if (result.success) {
				toast.success("Merge complete — push to sync changes");
				setConflicts([]);
				setConflictResolutions({});
				setCommitsAhead(result.commits_ahead ?? 0);
				setCommitsBehind(result.commits_behind ?? 0);
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
		// Check cache first
		const cached = diffCacheRef.current.get(file.path);
		if (cached) {
			setDiffPreview({
				path: file.path,
				displayName: file.display_name || file.path,
				entityType: file.entity_type || "workflow",
				localContent: cached.working_content ?? null,
				remoteContent: cached.head_content ?? null,
				isConflict: false,
				isLoading: false,
			});
			return;
		}

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
				(jobId) => diffOp.mutateAsync(file.path, jobId),
				"diff",
			);
			// Store in cache
			diffCacheRef.current.set(file.path, result);
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
				conflictType: conflict.conflict_type,
				onResolve: (res) => {
					setConflictResolutions((prev) => ({ ...prev, [conflict.path]: res }));
					// Update diff preview resolution
					setDiffPreview((prev) => (prev ? { ...prev, resolution: res } : null));
				},
			});
		},
		[conflictResolutions, setDiffPreview],
	);

	const handleDiscard = useCallback(async (file: ChangedFile) => {
		try {
			const result = await runGitOp<DiscardResult>(
				(jobId) => discardOp.mutateAsync([file.path], jobId),
				"discard",
			);
			if (result.success) {
				toast.success(`Discarded changes to ${file.display_name || file.path}`);
				setChangedFiles((prev) => prev.filter((f) => f.path !== file.path));
				setNeedsSync(true);
				await loadChanges();
				refreshStatus();
			} else {
				toast.error(result.error || "Discard failed");
			}
		} catch (error) {
			const msg = error instanceof Error ? error.message : String(error);
			toast.error(`Discard failed: ${msg}`);
		}
	}, [discardOp, loadChanges, refreshStatus]);

	const handleDiscardAll = useCallback(async () => {
		if (changedFiles.length === 0) return;
		try {
			const result = await runGitOp<DiscardResult>(
				(jobId) => discardOp.mutateAsync(changedFiles.map((f) => f.path), jobId),
				"discard",
			);
			if (result.success) {
				toast.success(`Discarded all ${changedFiles.length} changes`);
				setChangedFiles([]);
				setNeedsSync(true);
				await loadChanges();
				refreshStatus();
			} else {
				toast.error(result.error || "Discard all failed");
			}
		} catch (error) {
			if (error instanceof Error) {
				toast.error(error.message);
			}
		}
	}, [changedFiles, discardOp, loadChanges, refreshStatus]);

	// Auto-refresh on visibility change
	useEffect(() => {
		if (sidebarPanel !== "sourceControl") return;

		const handleVisibility = () => {
			if (!document.hidden) {
				refreshStatus();
				loadChanges();
			}
		};
		document.addEventListener("visibilitychange", handleVisibility);
		return () => document.removeEventListener("visibilitychange", handleVisibility);
	}, [sidebarPanel, refreshStatus, loadChanges]);

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

			{/* Scrollable sections */}
			<div className="flex-1 flex flex-col min-h-0 overflow-hidden">
				{/* Merge banner + unified list when conflicts exist */}
				{hasConflicts && (
					<MergeBanner
						conflictCount={conflicts.length}
						resolvedCount={resolvedCount}
						onAbortMerge={handleAbortMerge}
						isResolving={loading === "resolving"}
					/>
				)}

				{/* Changes (uncommitted) — includes conflicts in unified list when merging */}
				<ChangesSection
					changedFiles={changedFiles}
					conflicts={hasConflicts ? conflicts : []}
					conflictResolutions={conflictResolutions}
					onShowConflictDiff={handleShowConflictDiff}
					onResolveConflict={(path, res) => {
						setConflictResolutions((prev) => ({ ...prev, [path]: res }));
						setDiffPreview((prev) =>
							prev?.path === path ? { ...prev, resolution: res } : prev,
						);
					}}
					commitMessage={commitMessage}
					onCommitMessageChange={setCommitMessage}
					onCommit={handleCommit}
					onCompleteMerge={handleResolveConflicts}
					allConflictsResolved={allConflictsResolved}
					onSync={handleSync}
					onShowDiff={handleShowDiff}
					onDiscard={handleDiscard}
					onDiscardAll={handleDiscardAll}
					commitsBehind={commitsBehind}
					commitsAhead={commitsAhead}
					needsSync={needsSync}
					loading={loading}

					disabled={!!loading}
					branch={status.current_branch || "main"}
					showCleanupPrompt={showCleanupPrompt}
					orphanedCount={orphanedCount}
					onCleanupAndRetry={handleCleanupAndRetry}
					onDismissCleanup={() => setShowCleanupPrompt(false)}
					pendingDeletes={pendingDeletes}
					onConfirmDeletes={() => handleSync(true)}
					onDismissDeletes={() => setPendingDeletes([])}
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

/** Merge banner — shown above the file list when conflicts exist */
function MergeBanner({
	conflictCount,
	resolvedCount,
	onAbortMerge,
	isResolving,
}: {
	conflictCount: number;
	resolvedCount: number;
	onAbortMerge: () => void;
	isResolving: boolean;
}) {
	const unresolvedCount = conflictCount - resolvedCount;
	return (
		<div className="px-4 py-2.5 border-b bg-orange-500/10 flex-shrink-0">
			<div className="flex items-center gap-2">
				<AlertTriangle className="h-4 w-4 text-orange-500 flex-shrink-0" />
				<span className="text-xs font-medium text-orange-700 dark:text-orange-400 flex-1">
					{unresolvedCount > 0
						? `${unresolvedCount} conflict${unresolvedCount !== 1 ? "s" : ""} — resolve to continue`
						: "All conflicts resolved"}
				</span>
				<button
					onClick={onAbortMerge}
					disabled={isResolving}
					className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
				>
					Abort Merge
				</button>
			</div>
		</div>
	);
}

function ChangesSection({
	changedFiles,
	conflicts,
	conflictResolutions,
	onShowConflictDiff,
	onResolveConflict,
	commitMessage,
	onCommitMessageChange,
	onCommit,
	onCompleteMerge,
	allConflictsResolved,
	onSync,
	onShowDiff,
	onDiscard,
	onDiscardAll,
	commitsBehind,
	commitsAhead,
	needsSync,
	loading,
	disabled,
	branch,
	showCleanupPrompt,
	orphanedCount,
	onCleanupAndRetry,
	onDismissCleanup,
	pendingDeletes,
	onConfirmDeletes,
	onDismissDeletes,
}: {
	changedFiles: ChangedFile[];
	conflicts: MergeConflict[];
	conflictResolutions: Record<string, "ours" | "theirs">;
	onShowConflictDiff: (conflict: MergeConflict) => void;
	onResolveConflict: (path: string, resolution: "ours" | "theirs") => void;
	commitMessage: string;
	onCommitMessageChange: (msg: string) => void;
	onCommit: () => void;
	onCompleteMerge: () => void;
	allConflictsResolved: boolean;
	onSync: (confirmDeletes?: boolean) => void;
	onShowDiff: (file: ChangedFile) => void;
	onDiscard: (file: ChangedFile) => void;
	onDiscardAll: () => void;
	commitsBehind: number;
	commitsAhead: number;
	needsSync: boolean;
	loading: "fetching" | "committing" | "syncing" | "resolving" | "loading_changes" | null;
	disabled: boolean;
	branch: string;
	showCleanupPrompt?: boolean;
	orphanedCount?: number;
	onCleanupAndRetry?: () => void;
	onDismissCleanup?: () => void;
	pendingDeletes?: EntityChange[];
	onConfirmDeletes?: () => void;
	onDismissDeletes?: () => void;
}) {
	const [expanded, setExpanded] = useState(true);
	const [showDiscardAllConfirm, setShowDiscardAllConfirm] = useState(false);

	const hasConflicts = conflicts.length > 0;
	const hasChanges = changedFiles.length > 0;
	const canCommit = hasChanges && commitMessage.trim().length > 0;
	const totalItems = conflicts.length + changedFiles.length;

	return (
		<div className={cn("border-t flex flex-col min-h-0", expanded && "flex-1")}>
			<ContextMenu>
				<ContextMenuTrigger asChild>
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
							{totalItems}
						</span>
					</button>
				</ContextMenuTrigger>
				<ContextMenuContent className="z-[200]">
					<ContextMenuItem
						disabled={!hasChanges || disabled}
						onClick={() => setShowDiscardAllConfirm(true)}
					>
						<Undo2 className="h-4 w-4 mr-2" />
						Discard All Changes
					</ContextMenuItem>
				</ContextMenuContent>
			</ContextMenu>
			{expanded && (
				<div className="flex-1 flex flex-col overflow-hidden min-h-0">
					{/* Commit message input (shown when there are uncommitted changes) */}
					{hasChanges && (
						<div className="px-4 pt-2 pb-2 flex-shrink-0">
							<input
								type="text"
								value={commitMessage}
								onChange={(e) => onCommitMessageChange(e.target.value)}
								placeholder="Commit message"
								className="w-full px-2 py-1.5 text-xs bg-muted/50 border border-border rounded-none focus:outline-none focus:ring-1 focus:ring-ring"
								disabled={disabled}
								onKeyDown={(e) => {
									if (e.key === "Enter" && canCommit) {
										onCommit();
									}
								}}
							/>
						</div>
					)}

					{/* Morphing sync button */}
					<div className="px-4 pb-2 flex-shrink-0 flex flex-col gap-1">
						{hasConflicts ? (
							/* Complete Merge button replaces normal commit/push when conflicts exist */
							<Button
								size="sm"
								className="w-full gap-2 rounded-none"
								onClick={onCompleteMerge}
								disabled={disabled || !allConflictsResolved}
							>
								{loading === "resolving" ? (
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
						) : (
							<>
								{hasChanges && (
									<Button
										size="sm"
										className="w-full gap-2 rounded-none"
										onClick={onCommit}
										disabled={disabled || !canCommit}
									>
										{loading === "committing" ? (
											<>
												<Loader2 className="h-3.5 w-3.5 animate-spin" />
												Committing...
											</>
										) : (
											`Commit to ${branch}`
										)}
									</Button>
								)}
								{(commitsBehind > 0 || commitsAhead > 0 || needsSync) && (
									<div className="flex flex-col gap-0.5">
										<Button
											size="sm"
											variant={hasChanges ? "outline" : "default"}
											className="w-full gap-2 rounded-none"
											onClick={() => onSync()}
											disabled={disabled || (hasChanges && (commitsAhead > 0 || commitsBehind > 0))}
											title={hasChanges && (commitsAhead > 0 || commitsBehind > 0) ? "Commit your changes before syncing" : undefined}
										>
											{loading === "syncing" ? (
												<>
													<Loader2 className="h-3.5 w-3.5 animate-spin" />
													Syncing...
												</>
											) : (
												<>
													<RefreshCw className="h-3.5 w-3.5" />
													Sync origin
													{commitsBehind > 0 && ` ↓${commitsBehind}`}
													{commitsAhead > 0 && ` ↑${commitsAhead}`}
												</>
											)}
										</Button>
										{hasChanges && (commitsAhead > 0 || commitsBehind > 0) && (
											<p className="text-[10px] text-muted-foreground text-center">Commit changes before syncing</p>
										)}
									</div>
								)}
							</>
						)}
					</div>

					{/* Orphaned cleanup banner */}
					{showCleanupPrompt && (
						<div className="mx-4 mb-2 p-2.5 rounded border border-yellow-500/30 bg-yellow-500/10 flex-shrink-0">
							<div className="flex items-start gap-2">
								<AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
								<div className="flex-1 min-w-0">
									<p className="text-xs font-medium text-yellow-700">
										{orphanedCount} orphaned reference(s) found
									</p>
									<p className="text-xs text-muted-foreground mt-0.5">
										Some entities reference files that no longer exist.
									</p>
									<div className="flex gap-2 mt-2">
										<Button
											size="sm"
											variant="default"
											className="h-6 text-xs px-2 rounded-none"
											onClick={onCleanupAndRetry}
											disabled={disabled}
										>
											{loading === "committing" ? (
												<>
													<Loader2 className="h-3 w-3 animate-spin mr-1" />
													Cleaning up...
												</>
											) : (
												"Clean up & Retry"
											)}
										</Button>
										<Button
											size="sm"
											variant="ghost"
											className="h-6 text-xs px-2 rounded-none"
											onClick={onDismissCleanup}
											disabled={disabled}
										>
											Dismiss
										</Button>
									</div>
								</div>
							</div>
						</div>
					)}

					{/* Pending deletes confirmation banner */}
					{pendingDeletes && pendingDeletes.length > 0 && (
						<div className="mx-4 mb-2 p-2.5 rounded border border-red-500/30 bg-red-500/10 flex-shrink-0">
							<div className="flex items-start gap-2">
								<AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
								<div className="flex-1 min-w-0">
									<p className="text-xs font-medium text-red-700">
										{pendingDeletes.length} entity deletion(s) pending
									</p>
									<p className="text-xs text-muted-foreground mt-0.5">
										Sync requires deleting entities removed from the repo.
									</p>
									<ul className="text-xs text-muted-foreground mt-1 space-y-0.5">
										{pendingDeletes.slice(0, 5).map((d, i) => (
											<li key={i} className="flex items-center gap-1">
												<Minus className="h-3 w-3 text-red-500 flex-shrink-0" />
												<span className="truncate">{d.entity_type}: {d.name}</span>
											</li>
										))}
										{pendingDeletes.length > 5 && (
											<li className="text-muted-foreground/70">
												...and {pendingDeletes.length - 5} more
											</li>
										)}
									</ul>
									<div className="flex gap-2 mt-2">
										<Button
											size="sm"
											variant="destructive"
											className="h-6 text-xs px-2 rounded-none"
											onClick={onConfirmDeletes}
											disabled={disabled}
										>
											{loading === "syncing" ? (
												<>
													<Loader2 className="h-3 w-3 animate-spin mr-1" />
													Deleting...
												</>
											) : (
												"Confirm & Sync"
											)}
										</Button>
										<Button
											size="sm"
											variant="ghost"
											className="h-6 text-xs px-2 rounded-none"
											onClick={onDismissDeletes}
											disabled={disabled}
										>
											Dismiss
										</Button>
									</div>
								</div>
							</div>
						</div>
					)}

					{/* File list */}
					<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
						{loading === "loading_changes" ? (
							<div className="flex items-center justify-center py-4">
								<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
							</div>
						) : totalItems === 0 ? (
							<p className="text-xs text-muted-foreground text-center py-4">
								No uncommitted changes
							</p>
						) : (
							<>
								{/* Conflict files first */}
								{conflicts.map((conflict) => {
									const resolution = conflictResolutions[conflict.path];
									const entityType = conflict.entity_type as keyof typeof ENTITY_ICONS | null;
									const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
									const IconComponent = iconConfig?.icon ?? FileCode;
									const iconClassName = iconConfig?.className ?? "text-gray-500";

									return (
										<div
											key={`conflict-${conflict.path}`}
											onClick={() => onShowConflictDiff(conflict)}
											className={cn(
												"group flex items-center gap-1.5 text-xs py-1.5 px-2 rounded cursor-pointer",
												!resolution && "border-l-2 border-orange-500 hover:bg-orange-500/5",
												resolution && "border-l-2 border-green-500 hover:bg-green-500/5",
											)}
										>
											{resolution ? (
												<CheckCircle2 className="h-3 w-3 text-green-500 flex-shrink-0" />
											) : (
												<AlertTriangle className="h-3 w-3 text-orange-500 flex-shrink-0" />
											)}
											<IconComponent className={cn("h-3.5 w-3.5 flex-shrink-0", iconClassName)} />
											<span className="flex-1 truncate" title={conflict.path}>
												{conflict.display_name || conflict.path}
											</span>
											<span className={cn(
												"flex-shrink-0 flex items-center gap-0.5",
												resolution ? "flex" : "hidden group-hover:flex",
											)}>
												<button
													onClick={(e) => {
														e.stopPropagation();
														onResolveConflict(conflict.path, "ours");
													}}
													className={cn(
														"px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors",
														resolution === "ours"
															? "bg-blue-500/20 text-blue-400"
															: "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
													)}
													title="Keep local version"
												>
													Local
												</button>
												<button
													onClick={(e) => {
														e.stopPropagation();
														onResolveConflict(conflict.path, "theirs");
													}}
													className={cn(
														"px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors",
														resolution === "theirs"
															? "bg-purple-500/20 text-purple-400"
															: "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
													)}
													title="Keep remote version"
												>
													Remote
												</button>
											</span>
										</div>
									);
								})}
								{/* Then normal changed files */}
								{changedFiles.map((file) => {
									const entityType = file.entity_type as keyof typeof ENTITY_ICONS | null;
									const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
									const IconComponent = iconConfig?.icon ?? FileCode;
									const iconClassName = iconConfig?.className ?? "text-gray-500";

									return (
										<div
											key={file.path}
											onClick={() => onShowDiff(file)}
											className="group flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-muted/30 cursor-pointer"
										>
											{getChangeIcon(file.change_type)}
											<IconComponent className={cn("h-3.5 w-3.5 flex-shrink-0", iconClassName)} />
											<span className="flex-1 truncate" title={file.path}>
												{file.display_name || file.path}
											</span>
											{!hasConflicts && (
												<button
													onClick={(e) => {
														e.stopPropagation();
														onDiscard(file);
													}}
													className="hidden group-hover:block p-0.5 rounded hover:bg-muted/80 flex-shrink-0"
													title="Discard changes"
												>
													<Undo2 className="h-3 w-3 text-muted-foreground" />
												</button>
											)}
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
								})}
							</>
						)}
					</div>
				</div>
			)}

			<AlertDialog open={showDiscardAllConfirm} onOpenChange={setShowDiscardAllConfirm}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Discard All Changes?</AlertDialogTitle>
						<AlertDialogDescription>
							This will discard all {changedFiles.length} uncommitted change(s). This cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={onDiscardAll}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Discard All
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
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
