import { useState, useEffect, useRef, useCallback } from "react";
import {
	GitBranch,
	Check,
	Loader2,
	Download,
	Upload,
	RefreshCw,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
	useGitStatus,
	useRefreshGitStatus,
	useGitCommits,
	useCommitChanges,
	usePullFromGitHub,
	usePushToGitHub,
	useDiscardUnpushedCommits,
	useDiscardCommit,
	type FileChange,
} from "@/hooks/useGitHub";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";
import { ChangesList } from "./ChangesList";
import { CommitsList } from "./CommitsList";

/**
 * Source Control panel for Git/GitHub integration
 * Shows changed files, allows commit/push, pull from GitHub, and conflict resolution
 */
export function SourceControlPanel() {
	const [commitMessage, setCommitMessage] = useState("");
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

	// Use ref to track refresh loading state synchronously (prevents React 18 double-call race condition)
	const isLoadingRef = useRef(false);

	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const sidebarPanel = useEditorStore((state) => state.sidebarPanel);
	const appendTerminalOutput = useEditorStore(
		(state) => state.appendTerminalOutput,
	);

	// Query hooks
	const { data: status, isLoading } = useGitStatus();
	const { data: commitsData, isLoading: isLoadingCommits } = useGitCommits(
		20,
		0,
	);

	// Mutation hooks
	const refreshStatus = useRefreshGitStatus();
	const commitMutation = useCommitChanges();
	const pullMutation = usePullFromGitHub();
	const pushMutation = usePushToGitHub();
	const discardAllMutation = useDiscardUnpushedCommits();
	const discardCommitMutation = useDiscardCommit();

	// Update commits state when data loads
	useEffect(() => {
		if (commitsData) {
			setCommits(commitsData.commits || []);
			setTotalCommits(commitsData.total_commits);
			setHasMoreCommits(commitsData.has_more);
		}
	}, [commitsData]);

	const handleRefreshStatus = useCallback(async () => {
		// Prevent duplicate fetches using ref (synchronous check)
		// This prevents React 18 strict mode double-calls from making duplicate HTTP requests
		if (isLoadingRef.current) {
			return;
		}

		isLoadingRef.current = true;
		try {
			await refreshStatus.mutateAsync({});
		} catch (error) {
			console.error("Failed to refresh Git status:", error);
			toast.error("Failed to refresh Git status");
		} finally {
			isLoadingRef.current = false;
		}
	}, [refreshStatus]);

	// Load status when this tab becomes active, on visibility change, or when git status changes
	useEffect(() => {
		// Only refresh if source control panel is active
		if (sidebarPanel !== "sourceControl") {
			return;
		}

		// Initial load when panel becomes active
		handleRefreshStatus();

		// Set up event listeners for visibility and git status changes
		const handleVisibilityChange = () => {
			if (!document.hidden && sidebarPanel === "sourceControl") {
				handleRefreshStatus();
			}
		};

		const handleGitStatusChanged = () => {
			if (sidebarPanel === "sourceControl") {
				handleRefreshStatus();
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
	}, [sidebarPanel, handleRefreshStatus]);

	const handleCommit = async () => {
		if (!commitMessage.trim()) {
			toast.error("Please enter a commit message");
			return;
		}

		try {
			await commitMutation.mutateAsync({
				body: { message: commitMessage },
			});

			appendTerminalOutput({
				loggerOutput: [
					{
						level: "SUCCESS",
						message: `Git commit: "${commitMessage}"`,
						source: "git",
					},
				],
				variables: {},
				status: "success",
				error: undefined,
			});
			toast.success("Changes committed");
			setCommitMessage("");
			await handleRefreshStatus();
		} catch (error) {
			console.error("Failed to commit:", error);
			toast.error("Failed to commit", {
				description:
					error instanceof Error ? error.message : String(error),
			});
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Git commit error: ${error instanceof Error ? error.message : String(error)}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: error instanceof Error ? error.message : String(error),
			});
		}
	};

	const handleSync = async () => {
		try {
			// First pull changes from remote
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "INFO",
						message: "Pulling changes from GitHub...",
						source: "git",
					},
				],
				variables: {},
				status: "running",
				error: undefined,
			});

			await pullMutation.mutateAsync({});

			appendTerminalOutput({
				loggerOutput: [
					{
						level: "SUCCESS",
						message: "Successfully pulled changes from GitHub",
						source: "git",
					},
				],
				variables: {},
				status: "success",
				error: undefined,
			});

			// Then push local commits if any
			if (status && status.commits_ahead > 0) {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "INFO",
							message: "Pushing local commits to GitHub...",
							source: "git",
						},
					],
					variables: {},
					status: "running",
					error: undefined,
				});

				await pushMutation.mutateAsync({ body: {} });

				appendTerminalOutput({
					loggerOutput: [
						{
							level: "SUCCESS",
							message: "Successfully pushed commits to GitHub",
							source: "git",
						},
					],
					variables: {},
					status: "success",
					error: undefined,
				});
			}

			toast.success("Synced with GitHub");
			await handleRefreshStatus();
		} catch (error) {
			console.error("Failed to sync:", error);
			toast.error("Failed to sync with GitHub");
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Git sync error: ${error instanceof Error ? error.message : String(error)}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: error instanceof Error ? error.message : String(error),
			});
		}
	};

	const handleDiscardAll = async () => {
		try {
			const result = await discardAllMutation.mutateAsync({});
			if (result.success) {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "SUCCESS",
							message: `Discarded ${result.discarded_commits?.length || 0} unpushed commit(s)`,
							source: "git",
						},
					],
					variables: {},
					status: "success",
					error: undefined,
				});
				await handleRefreshStatus();
			} else {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "ERROR",
							message: `Failed to discard commits: ${result.error || "Unknown error"}`,
							source: "git",
						},
					],
					variables: {},
					status: "error",
					error: result.error || undefined,
				});
			}
		} catch (error) {
			console.error("Failed to discard commits:", error);
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Failed to discard commits: ${error instanceof Error ? error.message : String(error)}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: error instanceof Error ? error.message : String(error),
			});
		}
	};

	const handleDiscardCommit = async (commitSha: string) => {
		try {
			const result = await discardCommitMutation.mutateAsync({
				body: { commit_sha: commitSha },
			});
			if (result.success) {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "SUCCESS",
							message: `Discarded ${result.discarded_commits?.length || 0} commit(s)`,
							source: "git",
						},
					],
					variables: {},
					status: "success",
					error: undefined,
				});
				await handleRefreshStatus();
			} else {
				appendTerminalOutput({
					loggerOutput: [
						{
							level: "ERROR",
							message: `Failed to discard commit: ${result.error || "Unknown error"}`,
							source: "git",
						},
					],
					variables: {},
					status: "error",
					error: result.error || undefined,
				});
			}
		} catch (error) {
			console.error("Failed to discard commit:", error);
			appendTerminalOutput({
				loggerOutput: [
					{
						level: "ERROR",
						message: `Failed to discard commit: ${error instanceof Error ? error.message : String(error)}`,
						source: "git",
					},
				],
				variables: {},
				status: "error",
				error: error instanceof Error ? error.message : String(error),
			});
		}
	};

	const handleFileClick = async (file: FileChange) => {
		try {
			// Load file content from workspace
			const fileData = await fileService.readFile(file.path);

			// Construct FileMetadata from response
			const fileName = fileData.path.split("/").pop() || "";
			const fileMetadata = {
				path: fileData.path,
				name: fileName,
				size: fileData.size,
				type: "file" as const,
				extension: fileName.includes(".")
					? fileName.split(".").pop() || null
					: null,
				modified: fileData.modified,
				isReadOnly: false,
			};

			// Open in editor tab
			openFileInTab(
				fileMetadata,
				fileData.content,
				fileData.encoding as "utf-8" | "base64",
				fileData.etag,
			);
		} catch (error) {
			console.error("Failed to open file:", error);
			toast.error(`Failed to open ${file.path}`);
		}
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

	const hasChanges = (status.changed_files?.length || 0) > 0;

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
					onClick={handleRefreshStatus}
					disabled={refreshStatus.isPending}
					className="p-1.5 rounded hover:bg-muted/50 transition-colors disabled:opacity-50"
					title="Refresh status"
				>
					{refreshStatus.isPending ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<RefreshCw className="h-4 w-4" />
					)}
				</button>
			</div>

			{/* Sync controls - only show when configured and there's something to sync */}
			{status.configured &&
				(status.commits_ahead > 0 || status.commits_behind > 0) && (
					<div className="border-b">
						<button
							onClick={handleSync}
							disabled={pullMutation.isPending || pushMutation.isPending || isLoading}
							className="w-full px-4 py-3 flex flex-col items-start gap-1 hover:bg-muted/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-left"
						>
							<div className="flex items-center justify-between w-full">
								<div className="flex items-center gap-2">
									{pullMutation.isPending || pushMutation.isPending ? (
										<Loader2 className="h-4 w-4 animate-spin" />
									) : (
										<RefreshCw className="h-4 w-4" />
									)}
									<span className="text-sm font-medium">
										Sync with GitHub
									</span>
								</div>
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
							</div>
							{status.last_synced && (
								<span className="text-xs text-muted-foreground ml-6">
									Last synced{" "}
									{formatDistanceToNow(
										new Date(status.last_synced),
										{ addSuffix: true },
									)}
								</span>
							)}
						</button>
					</div>
				)}

			{/* Commit section */}
			{hasChanges && (
				<div className="px-4 py-3 border-b space-y-2">
					<Input
						id="commit-message"
						placeholder={`Message (#Enter to commit on "${status.current_branch || "main"}")`}
						value={commitMessage}
						onChange={(e) => setCommitMessage(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey) {
								e.preventDefault();
								handleCommit();
							}
						}}
						className="text-sm"
					/>
					<Button
						size="sm"
						className="w-full"
						onClick={handleCommit}
						disabled={
							!commitMessage.trim() || commitMutation.isPending || isLoading
						}
					>
						{commitMutation.isPending ? (
							<Loader2 className="h-4 w-4 mr-2 animate-spin" />
						) : (
							<Check className="h-4 w-4 mr-2" />
						)}
						Commit
					</Button>
				</div>
			)}

			{/* Split pane container: Changes and Commits */}
			<div className="flex-1 flex flex-col min-h-0">
				{/* Changes section - takes half the space */}
				<div className="flex-1 flex flex-col min-h-0 border-b">
					<ChangesList
						changes={status.changed_files || []}
						hasConflicts={false}
						onFileClick={handleFileClick}
						isLoading={false}
					/>
				</div>

				{/* Commits section - takes half the space */}
				<div className="flex-1 flex flex-col min-h-0">
					<CommitsList
						commits={commits}
						totalCommits={totalCommits}
						hasMore={hasMoreCommits}
						isLoading={isLoadingCommits || discardAllMutation.isPending || discardCommitMutation.isPending}
						onDiscardAll={handleDiscardAll}
						onDiscardCommit={handleDiscardCommit}
					/>
				</div>
			</div>
		</div>
	);
}
