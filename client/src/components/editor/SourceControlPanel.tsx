import { useState, useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { webSocketService, type GitProgress, type GitPreviewComplete } from "@/services/websocket";
import {
	GitBranch,
	Check,
	Loader2,
	Download,
	Upload,
	RefreshCw,
	ArrowDownToLine,
	AlertCircle,
	FileWarning,
	ChevronDown,
	ChevronRight,
	History,
	Circle,
	CheckCircle2,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import {
	useGitStatus,
	useGitCommits,
	useSyncPreview,
	useSyncExecute,
	type SyncPreviewResponse,
	type SyncAction,
	type SyncConflictInfo,
	type OrphanInfo,
} from "@/hooks/useGitHub";
import { useEditorStore } from "@/stores/editorStore";
import { EntitySyncItem } from "./EntitySyncItem";
import { groupSyncActions, groupConflicts } from "./groupSyncActions";

/**
 * Source Control panel for Git/GitHub integration
 * Shows changed files, allows commit/push, pull from GitHub, and conflict resolution
 */
export function SourceControlPanel() {
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

	// Sync preview state
	const [syncPreview, setSyncPreview] = useState<SyncPreviewResponse | null>(null);
	const [isSyncLoading, setIsSyncLoading] = useState(false);
	const [syncProgress, setSyncProgress] = useState<GitProgress | null>(null);
	const [conflictResolutions, setConflictResolutions] = useState<
		Record<string, "keep_local" | "keep_remote">
	>({});
	const [orphansConfirmed, setOrphansConfirmed] = useState(false);

	// Use ref to track refresh loading state synchronously (prevents React 18 double-call race condition)
	const isLoadingRef = useRef(false);

	const sidebarPanel = useEditorStore((state) => state.sidebarPanel);
	const appendTerminalOutput = useEditorStore(
		(state) => state.appendTerminalOutput,
	);
	const setDiffPreview = useEditorStore((state) => state.setDiffPreview);

	// Handler for clicking any sync item to show diff
	const handleShowDiff = async (
		path: string,
		displayName: string,
		entityType: string,
		localContent: string | null,
		remoteContent: string | null,
		isConflict: boolean,
		resolution?: "keep_local" | "keep_remote",
		onResolve?: (res: "keep_local" | "keep_remote") => void
	) => {
		// Determine if we need to fetch content
		const needsLocalFetch = localContent === null;
		const needsRemoteFetch = remoteContent === null;
		const needsFetch = needsLocalFetch || needsRemoteFetch;

		// Set preview immediately with available content and loading state
		setDiffPreview({
			path,
			displayName,
			entityType,
			localContent,
			remoteContent,
			isConflict,
			isLoading: needsFetch,
			resolution,
			onResolve,
		});

		// If missing content, fetch it (both regular items and conflicts use lazy loading)
		// Use functional updates to avoid race conditions when both fetches complete
		const fetchPromises: Promise<void>[] = [];

		if (needsLocalFetch) {
			fetchPromises.push(
				apiClient.POST("/api/github/sync/content", {
					body: { path, source: "local" },
				}).then((response) => {
					if (response.data?.content !== undefined) {
						setDiffPreview((prev) =>
							prev ? { ...prev, localContent: response.data?.content ?? null } : null
						);
					}
				}).catch((error) => {
					console.error("Failed to fetch local content:", error);
				})
			);
		}
		if (needsRemoteFetch) {
			fetchPromises.push(
				apiClient.POST("/api/github/sync/content", {
					body: { path, source: "remote" },
				}).then((response) => {
					if (response.data?.content !== undefined) {
						setDiffPreview((prev) =>
							prev ? { ...prev, remoteContent: response.data?.content ?? null } : null
						);
					}
				}).catch((error) => {
					console.error("Failed to fetch remote content:", error);
				})
			);
		}

		// Clear loading state when all fetches complete
		if (fetchPromises.length > 0) {
			await Promise.all(fetchPromises);
			setDiffPreview((prev) =>
				prev ? { ...prev, isLoading: false } : null
			);
		}
	};

	// Query hooks
	const { data: status, isLoading } = useGitStatus();
	const { data: commitsData, isLoading: isLoadingCommits } = useGitCommits(
		20,
		0,
	);

	// Sync hooks
	const syncPreviewMutation = useSyncPreview();
	const syncExecuteMutation = useSyncExecute();
	const queryClient = useQueryClient();

	// Update commits state when data loads
	useEffect(() => {
		if (commitsData) {
			setCommits(commitsData.commits || []);
			setTotalCommits(commitsData.total_commits);
			setHasMoreCommits(commitsData.has_more);
		}
	}, [commitsData]);

	// Refresh status by invalidating queries
	// Note: sync preview refresh is handled separately via handleFetchSyncPreview
	// because the new async pattern requires WebSocket subscription setup
	const handleRefreshWithPreview = useCallback(async () => {
		// Prevent duplicate fetches using ref (synchronous check)
		if (isLoadingRef.current) {
			return;
		}

		isLoadingRef.current = true;
		try {
			// Invalidate status query to refresh from server
			await queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});

			// If we have a sync preview loaded, clear it so user can re-fetch
			// with the new async pattern (which requires WebSocket setup)
			if (syncPreview && !syncPreview.is_empty) {
				// Clear preview - user can click Sync to re-fetch
				setSyncPreview(null);
				setConflictResolutions({});
				setOrphansConfirmed(false);
			}
		} catch (error) {
			console.error("Failed to refresh Git status:", error);
			toast.error("Failed to refresh Git status");
		} finally {
			isLoadingRef.current = false;
		}
	}, [queryClient, syncPreview]);

	// Set up event listeners for visibility changes and git status events
	// Note: useGitStatus() already fetches data on mount, so we don't call refresh here
	useEffect(() => {
		// Only set up listeners if source control panel is active
		if (sidebarPanel !== "sourceControl") {
			return;
		}

		// Set up event listeners for visibility and git status changes
		const handleVisibilityChange = () => {
			if (!document.hidden && sidebarPanel === "sourceControl") {
				handleRefreshWithPreview();
			}
		};

		const handleGitStatusChanged = () => {
			if (sidebarPanel === "sourceControl") {
				handleRefreshWithPreview();
			}
		};

		document.addEventListener("visibilitychange", handleVisibilityChange);
		window.addEventListener("git-status-changed", handleGitStatusChanged);

		return () => {
			document.removeEventListener(
				"visibilitychange",
				handleVisibilityChange,
			);
			window.removeEventListener(
				"git-status-changed",
				handleGitStatusChanged,
			);
		};
	}, [sidebarPanel, handleRefreshWithPreview]);

	// Fetch sync preview (shows what will be pulled/pushed)
	// Now uses async WebSocket pattern for progress updates
	const handleFetchSyncPreview = async () => {
		setIsSyncLoading(true);
		setSyncPreview(null);
		setConflictResolutions({});
		setOrphansConfirmed(false);
		setSyncProgress(null);

		try {
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "INFO",
						message: "Checking for changes to sync...",
						source: "git",
					},
				],
				variables: {},
				status: "running",
				error: undefined,
			});

			// Queue the preview job (returns immediately with job_id)
			const jobResponse = await syncPreviewMutation.mutateAsync();
			const jobId = jobResponse.job_id;

			if (!jobId) {
				throw new Error("Failed to queue sync preview job");
			}

			// Connect to WebSocket channel for progress updates
			await webSocketService.connectToGitSync(jobId);

			// Set up progress handler
			const unsubProgress = webSocketService.onGitSyncProgress(jobId, (progress: GitProgress) => {
				setSyncProgress(progress);
				// Map phase to user-friendly message
				const phaseMessages: Record<string, string> = {
					cloning: "Cloning repository...",
					scanning: `Scanning files (${progress.current}/${progress.total})...`,
					loading_local: "Loading local file state...",
					serializing: "Serializing virtual files...",
					comparing: `Comparing (${progress.current}/${progress.total})...`,
					analyzing_orphans: "Detecting orphaned workflows...",
					analyzing_refs: "Checking workflow references...",
				};
				const message = phaseMessages[progress.phase] || `${progress.phase}...`;

				appendTerminalOutput({
					loggerOutput: [
						{
							level: "INFO",
							message,
							source: "git",
						},
					],
					variables: {},
					status: "running",
					error: undefined,
				});
			});

			// Set up log handler for milestone messages
			const unsubLog = webSocketService.onGitSyncLog(jobId, (log) => {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: log.level === "error" ? "ERROR" : log.level === "warning" ? "WARNING" : "INFO",
							message: log.message,
							source: "git",
						},
					],
					variables: {},
					status: "running",
					error: undefined,
				});
			});

			// Wait for completion via promise
			const preview = await new Promise<SyncPreviewResponse>((resolve, reject) => {
				const unsubComplete = webSocketService.onGitSyncPreviewComplete(jobId, (complete: GitPreviewComplete) => {
					// Clean up all subscriptions
					unsubProgress();
					unsubLog();
					unsubComplete();

					if (complete.status === "success" && complete.preview) {
						resolve(complete.preview);
					} else {
						reject(new Error(complete.error || "Sync preview failed"));
					}
				});
			});

			setSyncPreview(preview);
			setSyncProgress(null);

			if (preview.is_empty) {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "SUCCESS",
							message: "Already up to date with GitHub",
							source: "git",
						},
					],
					variables: {},
					status: "success",
					error: undefined,
				});
				toast.success("Already up to date");
			} else {
				const pullCount = preview.to_pull?.length ?? 0;
				const pushCount = preview.to_push?.length ?? 0;
				const conflictCount = preview.conflicts?.length ?? 0;
				const orphanCount = preview.will_orphan?.length ?? 0;

				let message = "";
				if (pullCount > 0) message += `${pullCount} to pull`;
				if (pushCount > 0) message += `${message ? ", " : ""}${pushCount} to push`;
				if (conflictCount > 0) message += `${message ? ", " : ""}${conflictCount} conflict(s)`;
				if (orphanCount > 0) message += `${message ? ", " : ""}${orphanCount} will be orphaned`;

				appendTerminalOutput({
					loggerOutput: [
						{
							level: conflictCount > 0 ? "WARNING" : "INFO",
							message: `Sync preview: ${message}`,
							source: "git",
						},
					],
					variables: {},
					status: "running",
					error: undefined,
				});

				if (conflictCount > 0) {
					toast.warning(`${conflictCount} conflict(s) need resolution`);
				}
			}
		} catch (error) {
			console.error("Failed to get sync preview:", error);
			const errorMessage = error instanceof Error ? error.message : String(error);
			toast.error("Failed to check sync status");
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Sync preview error: ${errorMessage}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: errorMessage,
			});
		} finally {
			setIsSyncLoading(false);
			setSyncProgress(null);
		}
	};

	// Execute the sync with conflict resolutions
	const handleExecuteSync = async () => {
		if (!syncPreview) return;

		// Check that all conflicts are resolved
		const conflicts = syncPreview.conflicts ?? [];
		const unresolvedConflicts = conflicts.filter(
			(c) => !conflictResolutions[c.path]
		);
		if (unresolvedConflicts.length > 0) {
			toast.error("Please resolve all conflicts before syncing");
			return;
		}

		// Check that orphans are confirmed if any
		const willOrphan = syncPreview.will_orphan ?? [];
		if (willOrphan.length > 0 && !orphansConfirmed) {
			toast.error("Please confirm orphaned workflows before syncing");
			return;
		}

		setIsSyncLoading(true);
		setSyncProgress(null);

		try {
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "INFO",
						message: "Executing sync...",
						source: "git",
					},
				],
				variables: {},
				status: "running",
				error: undefined,
			});

			// 1. Queue the sync job - returns job_id
			const result = await syncExecuteMutation.mutateAsync({
				body: {
					conflict_resolutions: conflictResolutions,
					confirm_orphans: orphansConfirmed,
					confirm_unresolved_refs: true,
				},
			});

			if (!result.success || !result.job_id) {
				throw new Error(result.error || "Failed to queue sync");
			}

			const jobId = result.job_id;

			// 2. Connect to WebSocket channel with the job_id from response
			await webSocketService.connectToGitSync(jobId);

			// 3. Subscribe to log messages
			const unsubscribeLog = webSocketService.onGitSyncLog(jobId, (log) => {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: log.level.toUpperCase() as "INFO" | "SUCCESS" | "WARNING" | "ERROR",
							message: log.message,
							source: "git",
						},
					],
					variables: {},
					status: "running",
					error: undefined,
				});
			});

			// 4. Subscribe to progress messages
			const unsubscribeProgress = webSocketService.onGitSyncProgress(jobId, (progress) => {
				setSyncProgress(progress);
			});

			// 5. Subscribe to completion message
			const unsubscribeComplete = webSocketService.onGitSyncComplete(jobId, (complete) => {
				// Unsubscribe from further messages
				unsubscribeLog();
				unsubscribeProgress();
				unsubscribeComplete();

				if (complete.status === "success") {
					toast.success("Synced with GitHub");

					// Check if there were incoming changes that may include new entities
					const hadIncomingChanges = (syncPreview?.to_pull?.length ?? 0) > 0;
					if (hadIncomingChanges) {
						toast.info(
							<div className="flex flex-col gap-1">
								<span>New entities have restricted access by default.</span>
								<a
									href="/entity-management"
									className="text-primary underline hover:no-underline"
								>
									Go to Entity Management to assign access
								</a>
							</div>,
							{ duration: 8000 },
						);
					}

					// Clear sync preview state
					setSyncPreview(null);
					setConflictResolutions({});
					setOrphansConfirmed(false);

					// Invalidate queries to refresh data
					queryClient.invalidateQueries({ queryKey: ["get", "/api/github/status"] });
					queryClient.invalidateQueries({ queryKey: ["get", "/api/github/changes"] });
					queryClient.invalidateQueries({ queryKey: ["get", "/api/github/commits"] });
				} else {
					toast.error(complete.message || "Sync failed");
				}

				setSyncProgress(null);
				setIsSyncLoading(false);
			});

			// Job is queued and WebSocket is connected - results will stream in
			// Don't setIsSyncLoading(false) here - wait for WebSocket completion

		} catch (error) {
			console.error("Failed to queue sync:", error);
			const errorMessage = error instanceof Error ? error.message : String(error);
			toast.error("Failed to sync with GitHub");
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Sync error: ${errorMessage}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: errorMessage,
			});
			setSyncProgress(null);
			setIsSyncLoading(false);
		}
	};

	// Handle conflict resolution
	const handleResolveConflict = (path: string, resolution: "keep_local" | "keep_remote") => {
		setConflictResolutions((prev) => ({
			...prev,
			[path]: resolution,
		}));
	};

	// Handle bulk conflict resolution (all local or all remote)
	const handleResolveAllConflicts = (resolution: "keep_local" | "keep_remote") => {
		if (!syncPreview?.conflicts) return;
		const allResolutions: Record<string, "keep_local" | "keep_remote"> = {};
		for (const conflict of syncPreview.conflicts) {
			allResolutions[conflict.path] = resolution;
		}
		setConflictResolutions(allResolutions);
	};

	// Show loading state while fetching initial status
	if (isLoading || !status) {
		return (
			<div className="flex h-full flex-col p-4">
				<div className="flex items-center gap-2 mb-4">
					<GitBranch className="h-5 w-5" />
					<h3 className="text-sm font-semibold">Source Control</h3>
				</div>

				<div className="flex flex-col items-center justify-center flex-1 text-center">
					<Loader2 className="h-12 w-12 text-muted-foreground mb-4 animate-spin" />
					<p className="text-sm text-muted-foreground">
						Loading Git status...
					</p>
				</div>
			</div>
		);
	}

	if (!status?.initialized) {
		// Check if GitHub is configured but just needs first pull
		if (status?.configured) {
			return (
				<div className="flex h-full flex-col p-4">
					<div className="flex items-center gap-2 mb-4">
						<GitBranch className="h-5 w-5" />
						<h3 className="text-sm font-semibold">Source Control</h3>
					</div>

					<div className="flex flex-col items-center justify-center flex-1 text-center">
						<GitBranch className="h-12 w-12 text-muted-foreground mb-4" />
						<p className="text-sm text-muted-foreground mb-2">
							GitHub connected
						</p>
						<p className="text-xs text-muted-foreground mb-4">
							Pull to initialize your local repository
						</p>
						<Button
							onClick={handleFetchSyncPreview}
							disabled={isSyncLoading}
							className="gap-2"
						>
							{isSyncLoading ? (
								<>
									<Loader2 className="h-4 w-4 animate-spin" />
									Checking...
								</>
							) : (
								<>
									<ArrowDownToLine className="h-4 w-4" />
									Pull from GitHub
								</>
							)}
						</Button>
					</div>
				</div>
			);
		}

		// Not configured at all
		return (
			<div className="flex h-full flex-col p-4">
				<div className="flex items-center gap-2 mb-4">
					<GitBranch className="h-5 w-5" />
					<h3 className="text-sm font-semibold">Source Control</h3>
				</div>

				<div className="flex flex-col items-center justify-center flex-1 text-center">
					<GitBranch className="h-12 w-12 text-muted-foreground mb-4" />
					<p className="text-sm text-muted-foreground mb-2">
						Git not initialized
					</p>
					<p className="text-xs text-muted-foreground">
						Configure GitHub integration in Settings
					</p>
				</div>
			</div>
		);
	}

	return (
		<div className="flex h-full flex-col">
			{/* Header */}
			<div className="flex items-center justify-between p-4 border-b">
				<div className="flex items-center gap-2">
					<GitBranch className="h-5 w-5" />
					<div className="flex flex-col">
						<h3 className="text-sm font-semibold">
							Source Control
						</h3>
						{status.current_branch && (
							<span className="text-xs text-muted-foreground">
								{status.current_branch}
							</span>
						)}
					</div>
				</div>
				<button
					onClick={handleRefreshWithPreview}
					disabled={isSyncLoading}
					className="p-1.5 rounded hover:bg-muted/50 transition-colors disabled:opacity-50"
					title="Refresh status"
				>
					{isSyncLoading ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<RefreshCw className="h-4 w-4" />
					)}
				</button>
			</div>

			{/* Sync controls - show when configured */}
			{status.configured && (
				<div className="border-b">
					{(() => {
						// Determine button state
						const hasPreview = syncPreview && !syncPreview.is_empty;
						const conflictsLength = syncPreview?.conflicts?.length ?? 0;
						const willOrphanLength = syncPreview?.will_orphan?.length ?? 0;
						const hasUnresolvedConflicts = hasPreview &&
							conflictsLength > 0 &&
							Object.keys(conflictResolutions).length < conflictsLength;
						const hasUnconfirmedOrphans = hasPreview &&
							willOrphanLength > 0 && !orphansConfirmed;
						const canApply = hasPreview && !hasUnresolvedConflicts && !hasUnconfirmedOrphans;

						// Format progress display with user-friendly phase names
						const phaseLabels: Record<string, string> = {
							cloning: "Cloning repository",
							scanning: "Scanning files",
							loading_local: "Loading local state",
							serializing: "Serializing entities",
							comparing: "Comparing",
							analyzing_orphans: "Detecting orphans",
							analyzing_refs: "Checking references",
						};
						const progressText = syncProgress
							? syncProgress.total > 0
								? `${phaseLabels[syncProgress.phase] || syncProgress.phase} (${syncProgress.current}/${syncProgress.total})`
								: `${phaseLabels[syncProgress.phase] || syncProgress.phase}...`
							: null;

						return (
							<button
								onClick={hasPreview ? handleExecuteSync : handleFetchSyncPreview}
								disabled={isSyncLoading || isLoading || !!(hasPreview && !canApply)}
								className="w-full px-4 py-3 flex flex-col items-start gap-1 hover:bg-muted/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-left"
							>
								<div className="flex items-center justify-between w-full">
									<div className="flex items-center gap-2">
										{isSyncLoading ? (
											<Loader2 className="h-4 w-4 animate-spin" />
										) : hasPreview ? (
											<Check className="h-4 w-4" />
										) : (
											<RefreshCw className="h-4 w-4" />
										)}
										<span className="text-sm font-medium">
											{isSyncLoading
												? "Syncing..."
												: hasPreview
													? "Apply Changes"
													: "Sync with GitHub"}
										</span>
									</div>
									{/* Show counts from preview or status */}
									{hasPreview ? (
										<div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-muted text-xs">
											{(syncPreview.to_pull?.length ?? 0) > 0 && (
												<>
													<Download className="h-3 w-3" />
													<span>{syncPreview.to_pull?.length ?? 0}</span>
												</>
											)}
											{(syncPreview.to_push?.length ?? 0) > 0 && (
												<>
													<Upload className="h-3 w-3" />
													<span>{syncPreview.to_push?.length ?? 0}</span>
												</>
											)}
										</div>
									) : (status.commits_ahead > 0 || status.commits_behind > 0) && (
										<div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-muted text-xs">
											{status.commits_ahead > 0 && (
												<>
													<Upload className="h-3 w-3" />
													<span>{status.commits_ahead}</span>
												</>
											)}
											{status.commits_behind > 0 && (
												<>
													<Download className="h-3 w-3" />
													<span>{status.commits_behind}</span>
												</>
											)}
										</div>
									)}
								</div>
								{/* Progress indicator during sync */}
								{isSyncLoading && progressText ? (
									<span className="text-xs text-muted-foreground ml-6 truncate max-w-full" title={progressText}>
										{progressText}
									</span>
								) : hasPreview ? (
									hasUnresolvedConflicts ? (
										<span className="text-xs text-orange-500 ml-6">
											Resolve conflicts to continue
										</span>
									) : hasUnconfirmedOrphans ? (
										<span className="text-xs text-yellow-500 ml-6">
											Confirm orphaned workflows to continue
										</span>
									) : null
								) : status.last_synced && (
									<span className="text-xs text-muted-foreground ml-6">
										Last synced{" "}
										{formatDistanceToNow(
											new Date(status.last_synced),
											{ addSuffix: true },
										)}
									</span>
								)}
							</button>
						);
					})()}
				</div>
			)}

			{/* Collapsible sections container - all sections share space */}
			<div className="flex-1 flex flex-col min-h-0 overflow-hidden">
				{/* Sync sections when preview is available */}
				{syncPreview && !syncPreview.is_empty && (
					<>
						{/* Incoming changes (to pull) */}
						{(syncPreview.to_pull?.length ?? 0) > 0 && (
							<SyncActionList
								title="Incoming"
								icon={<Download className="h-4 w-4 text-blue-500 flex-shrink-0" />}
								actions={syncPreview.to_pull ?? []}
								onShowDiff={(path, displayName, entityType, local, remote) =>
									handleShowDiff(path, displayName, entityType, local, remote, false)
								}
							/>
						)}

						{/* Outgoing changes (to push) */}
						{(syncPreview.to_push?.length ?? 0) > 0 && (
							<SyncActionList
								title="Outgoing"
								icon={<Upload className="h-4 w-4 text-green-500 flex-shrink-0" />}
								actions={syncPreview.to_push ?? []}
								onShowDiff={(path, displayName, entityType, local, remote) =>
									handleShowDiff(path, displayName, entityType, local, remote, false)
								}
							/>
						)}

						{/* Conflicts */}
						{(syncPreview.conflicts?.length ?? 0) > 0 && (
							<ConflictList
								conflicts={syncPreview.conflicts ?? []}
								resolutions={conflictResolutions}
								onResolve={handleResolveConflict}
								onResolveAll={handleResolveAllConflicts}
								onShowDiff={handleShowDiff}
							/>
						)}

						{/* Orphaned workflows warning */}
						{(syncPreview.will_orphan?.length ?? 0) > 0 && (
							<OrphanWarning
								orphans={syncPreview.will_orphan ?? []}
								confirmed={orphansConfirmed}
								onConfirmChange={setOrphansConfirmed}
							/>
						)}
					</>
				)}

				{/* Commits section - always visible */}
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
// Helper Components for Sync Preview
// =============================================================================

/**
 * List of sync actions (files to pull or push) - Entity-centric display
 */
function SyncActionList({
	title,
	icon,
	actions,
	onShowDiff,
}: {
	title: string;
	icon: React.ReactNode;
	actions: SyncAction[];
	onShowDiff: (
		path: string,
		displayName: string,
		entityType: string,
		localContent: string | null,
		remoteContent: string | null
	) => void;
}) {
	const [expanded, setExpanded] = useState(true);
	const groupedEntities = groupSyncActions(actions);

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
				{icon}
				<span className="text-sm font-medium flex-1 truncate">{title}</span>
				<span className="text-xs text-muted-foreground bg-muted w-10 text-center py-0.5 rounded-full flex-shrink-0">
					{groupedEntities.length > 999 ? "999+" : groupedEntities.length}
				</span>
			</button>
			{expanded && (
				<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
					{groupedEntities.map((entity) => (
						<EntitySyncItem
							key={entity.action.path}
							action={entity.action}
							childFiles={entity.childFiles}
							onClick={() => onShowDiff(
								entity.action.path,
								entity.action.display_name || entity.action.path,
								entity.action.entity_type || "workflow",
								null,
								null
							)}
							onChildClick={(child) => onShowDiff(
								child.path,
								child.display_name || child.path,
								child.entity_type || "app_file",
								null,
								null
							)}
						/>
					))}
				</div>
			)}
		</div>
	);
}

/**
 * List of conflicts with resolution buttons - Entity-centric display
 */
function ConflictList({
	conflicts,
	resolutions,
	onResolve,
	onResolveAll,
	onShowDiff,
}: {
	conflicts: SyncConflictInfo[];
	resolutions: Record<string, "keep_local" | "keep_remote">;
	onResolve: (path: string, resolution: "keep_local" | "keep_remote") => void;
	onResolveAll: (resolution: "keep_local" | "keep_remote") => void;
	onShowDiff: (
		path: string,
		displayName: string,
		entityType: string,
		localContent: string | null,
		remoteContent: string | null,
		isConflict: boolean,
		resolution?: "keep_local" | "keep_remote",
		onResolve?: (res: "keep_local" | "keep_remote") => void
	) => void;
}) {
	const [expanded, setExpanded] = useState(true);
	const groupedConflicts = groupConflicts(conflicts);
	const resolvedCount = Object.keys(resolutions).length;

	return (
		<div className={cn("border-t flex flex-col min-h-0", expanded && "flex-1")}>
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
					<span className="text-sm font-medium flex-1 truncate">Conflicts</span>
					<span
						className={cn(
							"text-xs w-10 text-center py-0.5 rounded-full flex-shrink-0",
							resolvedCount === conflicts.length
								? "bg-green-500/20 text-green-700"
								: "bg-orange-500/20 text-orange-700"
						)}
					>
						{resolvedCount}/{conflicts.length}
					</span>
				</button>
				{/* Bulk resolution buttons */}
				{conflicts.length > 1 && (
					<div className="flex gap-1 ml-2">
						<button
							onClick={(e) => {
								e.stopPropagation();
								onResolveAll("keep_local");
							}}
							className="px-2 py-0.5 text-xs rounded bg-muted hover:bg-muted/80 transition-colors"
							title="Keep all local versions"
						>
							All Local
						</button>
						<button
							onClick={(e) => {
								e.stopPropagation();
								onResolveAll("keep_remote");
							}}
							className="px-2 py-0.5 text-xs rounded bg-muted hover:bg-muted/80 transition-colors"
							title="Accept all incoming versions"
						>
							All Remote
						</button>
					</div>
				)}
			</div>
			{expanded && (
				<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
					{groupedConflicts.map((group) => {
						const conflict = group.conflict;
						const resolution = resolutions[conflict.path];
						// Extract entity metadata from conflict (now has entity_type, display_name)
						const metadata: SyncAction = {
							path: conflict.path,
							action: "modify" as const,
							display_name: conflict.display_name || conflict.path.split("/").pop() || conflict.path,
							entity_type: conflict.entity_type || (
								conflict.path.endsWith(".form.json")
									? "form"
									: conflict.path.endsWith(".agent.json")
										? "agent"
										: conflict.path.startsWith("apps/")
											? "app"
											: "workflow"
							),
							parent_slug: conflict.parent_slug,
						};

						// Convert child conflicts to SyncAction format for EntitySyncItem
						const childFiles: SyncAction[] = group.childConflicts.map((child) => ({
							path: child.path,
							action: "modify" as const,
							display_name: child.display_name || child.path.split("/").pop() || child.path,
							entity_type: child.entity_type || "app_file",
							parent_slug: child.parent_slug,
						}));

						return (
							<EntitySyncItem
								key={conflict.path}
								action={metadata}
								childFiles={childFiles}
								isConflict
								resolution={resolution}
								onResolve={(res) => onResolve(conflict.path, res)}
								onClick={() => onShowDiff(
									conflict.path,
									metadata.display_name || conflict.path,
									metadata.entity_type || "workflow",
									conflict.local_content ?? null,
									conflict.remote_content ?? null,
									true,
									resolution,
									(res) => onResolve(conflict.path, res)
								)}
								onChildClick={(child) => {
									// Find the matching child conflict to get its content
									const childConflict = group.childConflicts.find((c) => c.path === child.path);
									onShowDiff(
										child.path,
										child.display_name || child.path,
										child.entity_type || "app_file",
										childConflict?.local_content ?? null,
										childConflict?.remote_content ?? null,
										true,
										resolutions[child.path],
										(res) => onResolve(child.path, res)
									);
								}}
							/>
						);
					})}
				</div>
			)}
		</div>
	);
}

/**
 * Warning about workflows that will be orphaned
 */
function OrphanWarning({
	orphans,
	confirmed,
	onConfirmChange,
}: {
	orphans: OrphanInfo[];
	confirmed: boolean;
	onConfirmChange: (confirmed: boolean) => void;
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
				<FileWarning className="h-4 w-4 text-yellow-500 flex-shrink-0" />
				<span className="text-sm font-medium flex-1 truncate">Orphans</span>
				<span className="text-xs bg-yellow-500/20 text-yellow-700 w-10 text-center py-0.5 rounded-full flex-shrink-0">
					{orphans.length > 999 ? "999+" : orphans.length}
				</span>
			</button>
			{expanded && (
				<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
					<p className="text-xs text-muted-foreground mb-2">
						These workflows will be orphaned. They may still be referenced by forms or apps.
					</p>
					<div className="space-y-1">
						{orphans.map((orphan) => (
							<div
								key={orphan.workflow_id}
								className="flex items-center gap-2 py-1"
							>
								<FileWarning className="h-3.5 w-3.5 text-yellow-500 flex-shrink-0" />
								<span className="text-xs truncate" title={`${orphan.workflow_name} (${orphan.function_name})`}>
									{orphan.workflow_name}
								</span>
							</div>
						))}
					</div>
					<div className="flex items-center gap-2 mt-2 pt-2 border-t">
						<Checkbox
							id="confirm-orphans"
							checked={confirmed}
							onCheckedChange={(checked) =>
								onConfirmChange(checked === true)
							}
						/>
						<label
							htmlFor="confirm-orphans"
							className="text-xs cursor-pointer"
						>
							I understand
						</label>
					</div>
				</div>
			)}
		</div>
	);
}

/**
 * Commits section showing commit history
 */
function CommitsSection({
	commits,
	totalCommits,
	hasMore,
	isLoading,
	onLoadMore,
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
	onLoadMore?: () => void;
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
						{/* Loading state on initial load */}
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

								{/* Load More button */}
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
				</div>
			)}
		</div>
	);
}
