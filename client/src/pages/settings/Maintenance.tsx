/**
 * Workspace Maintenance Settings
 *
 * Platform admin page for managing workspace maintenance operations.
 * Provides tools for reindexing, SDK reference scanning, and docs indexing.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
	AlertCircle,
	CheckCircle2,
	Loader2,
	RefreshCw,
	FileCode,
	AlertTriangle,
	Settings2,
	Link2,
	Database,
	Search,
	AppWindow,
} from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";
import {
	webSocketService,
	type ReindexMessage,
	type ReindexProgress,
	type ReindexCompleted,
	type ReindexFailed,
} from "@/services/websocket";
import type { components } from "@/lib/v1";

type FileMetadata = components["schemas"]["FileMetadata"];

interface ReindexJobResponse {
	status: "queued";
	job_id: string;
}

interface SDKIssue {
	file_path: string;
	line_number: number;
	issue_type: "config" | "integration";
	key: string;
}

interface SDKScanResponse {
	files_scanned: number;
	issues_found: number;
	issues: SDKIssue[];
	notification_created: boolean;
}

interface DocsIndexResponse {
	status: string;
	files_indexed: number;
	files_unchanged: number;
	files_deleted: number;
	duration_ms: number;
	message: string | null;
}

interface AppDependencyIssue {
	app_id: string;
	app_name: string;
	app_slug: string;
	file_path: string;
	dependency_type: string;
	dependency_id: string;
}

interface AppDependencyScanResponse {
	apps_scanned: number;
	files_scanned: number;
	dependencies_rebuilt: number;
	issues_found: number;
	issues: AppDependencyIssue[];
	notification_created: boolean;
}

// Reindex streaming state
interface ReindexState {
	jobId: string | null;
	phase: string;
	current: number;
	total: number;
	currentFile: string | null;
}

// Completed reindex result (from WebSocket)
interface ReindexResult {
	counts: ReindexCompleted["counts"];
	warnings: string[];
	errors: ReindexCompleted["errors"];
}

type ScanResultType = "none" | "reindex" | "sdk" | "docs" | "app-deps";

export function Maintenance() {
	// Scan states
	const [isReindexing, setIsReindexing] = useState(false);
	const [isSdkScanning, setIsSdkScanning] = useState(false);
	const [isDocsIndexing, setIsDocsIndexing] = useState(false);
	const [isAppDepScanning, setIsAppDepScanning] = useState(false);

	// Reindex streaming state
	const [reindexState, setReindexState] = useState<ReindexState>({
		jobId: null,
		phase: "",
		current: 0,
		total: 0,
		currentFile: null,
	});
	const unsubscribeRef = useRef<(() => void) | null>(null);

	// Results
	const [lastScanType, setLastScanType] = useState<ScanResultType>("none");
	const [reindexResult, setReindexResult] = useState<ReindexResult | null>(
		null,
	);
	const [sdkScanResult, setSdkScanResult] = useState<SDKScanResponse | null>(
		null,
	);
	const [docsIndexResult, setDocsIndexResult] =
		useState<DocsIndexResponse | null>(null);
	const [appDepScanResult, setAppDepScanResult] =
		useState<AppDependencyScanResponse | null>(null);

	const isAnyRunning = isReindexing || isSdkScanning || isDocsIndexing || isAppDepScanning;

	// Cleanup WebSocket subscription on unmount
	useEffect(() => {
		return () => {
			if (unsubscribeRef.current) {
				unsubscribeRef.current();
			}
		};
	}, []);

	// Editor store actions
	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const openEditor = useEditorStore((state) => state.openEditor);
	const revealLine = useEditorStore((state) => state.revealLine);

	const openFileInEditor = useCallback(
		async (filePath: string, lineNumber?: number) => {
			try {
				// Get file name and extension from path
				const fileName = filePath.split("/").pop() || filePath;
				const extension = fileName.includes(".")
					? fileName.split(".").pop() || ""
					: "";

				// Create minimal FileMetadata
				const fileMetadata: FileMetadata = {
					name: fileName,
					path: filePath,
					type: "file",
					size: 0,
					extension,
					modified: new Date().toISOString(),
					entity_type: null,
					entity_id: null,
				};

				// Fetch file content
				const response = await fileService.readFile(filePath);

				// Open in editor
				openFileInTab(
					fileMetadata,
					response.content,
					response.encoding as "utf-8" | "base64",
					response.etag,
				);

				// Queue line reveal if provided (will execute after editor loads)
				if (lineNumber) {
					revealLine(lineNumber);
				}

				openEditor();

				toast.success("Opened in editor");
			} catch (err) {
				toast.error("Failed to open file", {
					description:
						err instanceof Error ? err.message : "Unknown error",
				});
			}
		},
		[openFileInTab, openEditor, revealLine],
	);

	const handleReindexMessage = useCallback((message: ReindexMessage) => {
		switch (message.type) {
			case "progress": {
				const progress = message as ReindexProgress;
				setReindexState((prev) => ({
					...prev,
					phase: progress.phase,
					current: progress.current,
					total: progress.total,
					currentFile: progress.current_file ?? null,
				}));
				break;
			}
			case "completed": {
				const completed = message as ReindexCompleted;
				setReindexResult({
					counts: completed.counts,
					warnings: completed.warnings,
					errors: completed.errors,
				});
				setLastScanType("reindex");
				setIsReindexing(false);
				setReindexState({
					jobId: null,
					phase: "",
					current: 0,
					total: 0,
					currentFile: null,
				});

				// Cleanup subscription
				if (unsubscribeRef.current) {
					unsubscribeRef.current();
					unsubscribeRef.current = null;
				}

				const hasErrors = completed.errors.length > 0;
				const hasWarnings = completed.warnings.length > 0;

				if (hasErrors) {
					toast.warning("Reindex completed with errors", {
						description: `${completed.errors.length} unresolved reference${completed.errors.length !== 1 ? "s" : ""}`,
					});
				} else if (hasWarnings) {
					toast.success("Reindex complete", {
						description: `${completed.warnings.length} correction${completed.warnings.length !== 1 ? "s" : ""} made`,
					});
				} else {
					toast.success("Reindex complete", {
						description: `Indexed ${completed.counts.files_indexed} files`,
					});
				}
				break;
			}
			case "failed": {
				const failed = message as ReindexFailed;
				setIsReindexing(false);
				setReindexState({
					jobId: null,
					phase: "",
					current: 0,
					total: 0,
					currentFile: null,
				});

				// Cleanup subscription
				if (unsubscribeRef.current) {
					unsubscribeRef.current();
					unsubscribeRef.current = null;
				}

				toast.error("Reindex failed", {
					description: failed.error,
				});
				break;
			}
		}
	}, []);

	const handleReindex = async () => {
		setIsReindexing(true);
		setReindexResult(null);

		try {
			const response = await authFetch("/api/maintenance/reindex", {
				method: "POST",
				body: JSON.stringify({}),
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error("Reindex failed", {
					description: errorData.detail || "Unknown error",
				});
				setIsReindexing(false);
				return;
			}

			const data: ReindexJobResponse = await response.json();

			// Update state with job ID
			setReindexState({
				jobId: data.job_id,
				phase: "Queued",
				current: 0,
				total: 0,
				currentFile: null,
			});

			// Connect to WebSocket for progress updates
			await webSocketService.connectToReindex(data.job_id);

			// Subscribe to progress updates
			unsubscribeRef.current = webSocketService.onReindexProgress(
				data.job_id,
				handleReindexMessage,
			);

			toast.info("Reindex started", {
				description: "Processing workspace files...",
			});
		} catch (err) {
			toast.error("Reindex failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
			setIsReindexing(false);
		}
	};

	const handleSdkScan = async () => {
		setIsSdkScanning(true);

		try {
			const response = await authFetch("/api/maintenance/scan-sdk", {
				method: "POST",
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error("SDK scan failed", {
					description: errorData.detail || "Unknown error",
				});
				return;
			}

			const data: SDKScanResponse = await response.json();
			setSdkScanResult(data);
			setLastScanType("sdk");

			if (data.issues_found === 0) {
				toast.success("No SDK issues found", {
					description: `Scanned ${data.files_scanned} files`,
				});
			} else {
				toast.warning("SDK issues found", {
					description: `Found ${data.issues_found} missing references in ${data.files_scanned} files`,
				});
			}
		} catch (err) {
			toast.error("SDK scan failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
		} finally {
			setIsSdkScanning(false);
		}
	};

	const handleDocsIndex = async () => {
		setIsDocsIndexing(true);

		try {
			const response = await authFetch("/api/maintenance/index-docs", {
				method: "POST",
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error("Documentation indexing failed", {
					description: errorData.detail || "Unknown error",
				});
				return;
			}

			const data: DocsIndexResponse = await response.json();
			setDocsIndexResult(data);
			setLastScanType("docs");

			if (data.status === "complete") {
				toast.success("Documentation indexed successfully", {
					description: data.message,
				});
			} else if (data.status === "skipped") {
				toast.info("Documentation indexing skipped", {
					description: data.message,
				});
			} else {
				toast.error("Documentation indexing failed", {
					description: data.message || "Unknown error",
				});
			}
		} catch (err) {
			toast.error("Documentation indexing failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
		} finally {
			setIsDocsIndexing(false);
		}
	};

	const handleAppDepScan = async () => {
		setIsAppDepScanning(true);

		try {
			const response = await authFetch("/api/maintenance/scan-app-dependencies", {
				method: "POST",
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error("App dependency scan failed", {
					description: errorData.detail || "Unknown error",
				});
				return;
			}

			const data: AppDependencyScanResponse = await response.json();
			setAppDepScanResult(data);
			setLastScanType("app-deps");

			if (data.issues_found === 0) {
				toast.success("Dependencies rebuilt successfully", {
					description: `Scanned ${data.apps_scanned} apps, ${data.files_scanned} files, rebuilt ${data.dependencies_rebuilt} dependencies`,
				});
			} else {
				toast.warning("Dependencies rebuilt with issues", {
					description: `Rebuilt ${data.dependencies_rebuilt} dependencies, found ${data.issues_found} broken references`,
				});
			}
		} catch (err) {
			toast.error("App dependency scan failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
		} finally {
			setIsAppDepScanning(false);
		}
	};

	return (
		<div className="space-y-6">
			{/* Actions Card */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Settings2 className="h-5 w-5" />
						Maintenance Actions
					</CardTitle>
					<CardDescription>
						Run workspace maintenance operations
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{/* Workspace Indexing Section */}
					<div className="space-y-4">
						<h3 className="text-sm font-medium">
							Workspace Indexing
						</h3>
						<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
							<RefreshCw className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
							<div className="text-sm text-blue-800 dark:text-blue-200">
								<p className="text-blue-700 dark:text-blue-300">
									Re-scan all workspace files to refresh
									workflow, tool, and data provider metadata
									(names, descriptions, parameters,
									categories). Use this after migrations or if
									metadata appears out of sync.
								</p>
							</div>
						</div>
						<div className="flex flex-wrap items-center gap-4">
							<Button
								onClick={handleReindex}
								disabled={isAnyRunning}
							>
								{isReindexing ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<RefreshCw className="h-4 w-4 mr-2" />
								)}
								Reindex Workspace
							</Button>
						</div>

						{/* Progress indicator during reindex */}
						{isReindexing && reindexState.jobId && (
							<div className="space-y-2 rounded-lg border bg-muted/50 p-4">
								<div className="flex items-center justify-between text-sm">
									<span className="font-medium capitalize">
										{reindexState.phase.replace(
											/_/g,
											" ",
										) || "Starting..."}
									</span>
									{reindexState.total > 0 && (
										<span className="text-muted-foreground">
											{reindexState.current} /{" "}
											{reindexState.total}
										</span>
									)}
								</div>
								{reindexState.total > 0 && (
									<Progress
										value={
											(reindexState.current /
												reindexState.total) *
											100
										}
										className="h-2"
									/>
								)}
								{reindexState.currentFile && (
									<p className="text-xs text-muted-foreground truncate font-mono">
										{reindexState.currentFile}
									</p>
								)}
							</div>
						)}
					</div>

					{/* Divider */}
					<div className="border-t" />

					{/* SDK Reference Section */}
					<div className="space-y-4">
						<h3 className="text-sm font-medium">
							SDK Reference Scan
						</h3>
						<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
							<Link2 className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
							<div className="text-sm text-blue-800 dark:text-blue-200">
								<p className="text-blue-700 dark:text-blue-300">
									Scan Python files for{" "}
									<code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">
										config.get()
									</code>{" "}
									and{" "}
									<code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">
										integrations.get()
									</code>{" "}
									calls that reference missing configurations
									or integrations.
								</p>
							</div>
						</div>
						<Button
							onClick={handleSdkScan}
							disabled={isAnyRunning}
							variant="outline"
						>
							{isSdkScanning ? (
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							) : (
								<Search className="h-4 w-4 mr-2" />
							)}
							Scan SDK References
						</Button>
					</div>

					{/* Divider */}
					<div className="border-t" />

					{/* Documentation Indexing Section */}
					<div className="space-y-4">
						<h3 className="text-sm font-medium">
							Documentation Indexing
						</h3>
						<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
							<Database className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
							<div className="text-sm text-blue-800 dark:text-blue-200">
								<p className="text-blue-700 dark:text-blue-300">
									Index Bifrost platform documentation into
									the knowledge store for use by the Coding
									Assistant. Only changed files are
									re-indexed.
								</p>
							</div>
						</div>
						<Button
							onClick={handleDocsIndex}
							disabled={isAnyRunning}
							variant="outline"
						>
							{isDocsIndexing ? (
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							) : (
								<Database className="h-4 w-4 mr-2" />
							)}
							Index Documents
						</Button>
					</div>

					{/* Divider */}
					<div className="border-t" />

					{/* App Dependencies Section */}
					<div className="space-y-4">
						<h3 className="text-sm font-medium">
							Rebuild App Dependencies
						</h3>
						<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
							<AppWindow className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
							<div className="text-sm text-blue-800 dark:text-blue-200">
								<p className="text-blue-700 dark:text-blue-300">
									Rebuild the app dependency graph by parsing
									all app source files. Extracts{" "}
									<code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">
										useWorkflow()
									</code>,{" "}
									<code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">
										useForm()
									</code>, and{" "}
									<code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900 rounded">
										useDataProvider()
									</code>{" "}
									references and populates the dependency table
									used by Entity Management.
								</p>
							</div>
						</div>
						<Button
							onClick={handleAppDepScan}
							disabled={isAnyRunning}
							variant="outline"
						>
							{isAppDepScanning ? (
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							) : (
								<AppWindow className="h-4 w-4 mr-2" />
							)}
							Rebuild App Dependencies
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Results Card */}
			<Card>
				<CardHeader>
					<CardTitle>Scan Results</CardTitle>
					<CardDescription>
						Results from the most recent scan operation
					</CardDescription>
				</CardHeader>
				<CardContent>
					{lastScanType === "none" ? (
						<div className="flex items-center justify-center py-8 text-muted-foreground">
							<p>No scan results yet. Run a scan above.</p>
						</div>
					) : lastScanType === "reindex" && reindexResult ? (
						<ReindexResults
							result={reindexResult}
							onOpenFile={openFileInEditor}
						/>
					) : lastScanType === "sdk" && sdkScanResult ? (
						<SdkScanResults
							result={sdkScanResult}
							onOpenFile={openFileInEditor}
						/>
					) : lastScanType === "docs" && docsIndexResult ? (
						<DocsIndexResults result={docsIndexResult} />
					) : lastScanType === "app-deps" && appDepScanResult ? (
						<AppDepScanResults result={appDepScanResult} />
					) : null}
				</CardContent>
			</Card>
		</div>
	);
}

function ReindexResults({
	result,
	onOpenFile,
}: {
	result: ReindexResult;
	onOpenFile: (path: string, line?: number) => void;
}) {
	const hasErrors = result.errors.length > 0;
	const hasWarnings = result.warnings.length > 0;

	return (
		<div className="space-y-4">
			{/* Summary */}
			<div className="flex items-center gap-4 flex-wrap">
				{hasErrors ? (
					<div className="flex items-center gap-2 text-destructive">
						<AlertCircle className="h-5 w-5" />
						<span className="font-medium">
							{result.errors.length} unresolved reference
							{result.errors.length !== 1 ? "s" : ""}
						</span>
					</div>
				) : hasWarnings ? (
					<div className="flex items-center gap-2 text-amber-600">
						<AlertTriangle className="h-5 w-5" />
						<span className="font-medium">
							{result.warnings.length} correction
							{result.warnings.length !== 1 ? "s" : ""} made
						</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-green-600">
						<CheckCircle2 className="h-5 w-5" />
						<span className="font-medium">
							All references validated
						</span>
					</div>
				)}
			</div>

			{/* Stats grid */}
			<div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.files_indexed}
					</div>
					<div className="text-xs text-muted-foreground">
						Files Indexed
					</div>
				</div>
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.files_skipped}
					</div>
					<div className="text-xs text-muted-foreground">Skipped</div>
				</div>
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.workflows_active}
					</div>
					<div className="text-xs text-muted-foreground">
						Workflows
					</div>
				</div>
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.forms_active}
					</div>
					<div className="text-xs text-muted-foreground">Forms</div>
				</div>
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.agents_active}
					</div>
					<div className="text-xs text-muted-foreground">Agents</div>
				</div>
				<div className="rounded-lg border bg-muted/50 p-3 text-center">
					<div className="text-xl font-bold">
						{result.counts.files_deleted}
					</div>
					<div className="text-xs text-muted-foreground">Deleted</div>
				</div>
			</div>

			{/* Errors */}
			{hasErrors && (
				<div className="space-y-2">
					<h4 className="text-sm font-medium text-destructive flex items-center gap-2">
						<AlertCircle className="h-4 w-4" />
						Unresolved References (requires action)
					</h4>
					<div className="max-h-64 overflow-y-auto rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-3">
						{result.errors.map((error, idx) => (
							<div
								key={`${error.file_path}-${error.field}-${idx}`}
								className="space-y-1"
							>
								<div className="flex items-center gap-2 text-sm font-mono">
									<FileCode className="h-4 w-4 text-destructive flex-shrink-0" />
									<button
										type="button"
										onClick={() =>
											onOpenFile(error.file_path)
										}
										className="truncate text-left hover:text-primary hover:underline"
									>
										{error.file_path}
									</button>
								</div>
								<div className="ml-6 text-xs text-muted-foreground space-y-0.5">
									<p>
										<span className="font-medium">
											Field:
										</span>{" "}
										{error.field}
									</p>
									<p>
										<span className="font-medium">
											References:
										</span>{" "}
										<code className="bg-muted px-1 py-0.5 rounded">
											{error.referenced_id}
										</code>
									</p>
									<p className="text-destructive">
										{error.message}
									</p>
								</div>
							</div>
						))}
					</div>
				</div>
			)}

			{/* Warnings */}
			{hasWarnings && (
				<div className="space-y-2">
					<h4 className="text-sm font-medium text-amber-600 flex items-center gap-2">
						<AlertTriangle className="h-4 w-4" />
						Corrections Made
					</h4>
					<div className="max-h-48 overflow-y-auto rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/50 p-3">
						<ul className="space-y-1 text-sm">
							{result.warnings.map((warning, idx) => (
								<li
									key={idx}
									className="text-amber-800 dark:text-amber-200"
								>
									{warning}
								</li>
							))}
						</ul>
					</div>
				</div>
			)}
		</div>
	);
}

function SdkScanResults({
	result,
	onOpenFile,
}: {
	result: SDKScanResponse;
	onOpenFile: (path: string, line?: number) => void;
}) {
	const hasIssues = result.issues_found > 0;

	// Group issues by file
	const issuesByFile = result.issues.reduce(
		(acc, issue) => {
			if (!acc[issue.file_path]) {
				acc[issue.file_path] = [];
			}
			acc[issue.file_path].push(issue);
			return acc;
		},
		{} as Record<string, SDKIssue[]>,
	);

	return (
		<div className="space-y-4">
			{/* Summary */}
			<div className="flex items-center gap-4">
				{hasIssues ? (
					<div className="flex items-center gap-2 text-amber-600">
						<AlertTriangle className="h-5 w-5" />
						<span className="font-medium">
							{result.issues_found} missing reference
							{result.issues_found !== 1 ? "s" : ""}
						</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-green-600">
						<CheckCircle2 className="h-5 w-5" />
						<span className="font-medium">
							No missing references
						</span>
					</div>
				)}
				<Badge variant="secondary">
					{result.files_scanned} file
					{result.files_scanned !== 1 ? "s" : ""} scanned
				</Badge>
			</div>

			{/* Issues by file */}
			{hasIssues && (
				<div className="space-y-2">
					<h4 className="text-sm font-medium text-muted-foreground">
						Missing SDK references:
					</h4>
					<div className="max-h-64 overflow-y-auto rounded-md border bg-muted/50 p-3 space-y-3">
						{Object.entries(issuesByFile).map(
							([filePath, issues]) => (
								<div key={filePath} className="space-y-1">
									<div className="flex items-center gap-2 text-sm font-mono font-medium">
										<FileCode className="h-4 w-4 text-muted-foreground flex-shrink-0" />
										<button
											type="button"
											onClick={() =>
												onOpenFile(
													filePath,
													issues[0]?.line_number,
												)
											}
											className="truncate text-left hover:text-primary hover:underline"
										>
											{filePath}
										</button>
									</div>
									<ul className="ml-6 space-y-0.5">
										{issues.map((issue, idx) => (
											<li
												key={`${issue.key}-${idx}`}
												className="text-sm text-muted-foreground flex items-center gap-2"
											>
												<Badge
													variant="outline"
													className="text-xs px-1.5 py-0"
												>
													{issue.issue_type}
												</Badge>
												<code className="text-xs bg-muted px-1 py-0.5 rounded">
													{issue.key}
												</code>
												<button
													type="button"
													onClick={() =>
														onOpenFile(
															filePath,
															issue.line_number,
														)
													}
													className="text-xs hover:text-primary hover:underline"
												>
													line {issue.line_number}
												</button>
											</li>
										))}
									</ul>
								</div>
							),
						)}
					</div>
				</div>
			)}
		</div>
	);
}

function DocsIndexResults({ result }: { result: DocsIndexResponse }) {
	const isSuccess = result.status === "complete";
	const isSkipped = result.status === "skipped";

	const formatDuration = (ms: number) => {
		if (ms < 1000) return `${ms}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	};

	return (
		<div className="space-y-4">
			{/* Summary */}
			<div className="flex items-center gap-4 flex-wrap">
				{isSuccess ? (
					<div className="flex items-center gap-2 text-green-600">
						<CheckCircle2 className="h-5 w-5" />
						<span className="font-medium">Indexing complete</span>
					</div>
				) : isSkipped ? (
					<div className="flex items-center gap-2 text-amber-600">
						<AlertCircle className="h-5 w-5" />
						<span className="font-medium">Indexing skipped</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-destructive">
						<AlertTriangle className="h-5 w-5" />
						<span className="font-medium">Indexing failed</span>
					</div>
				)}
			</div>

			{/* Stats */}
			{isSuccess && (
				<div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
					<div className="rounded-lg border bg-muted/50 p-3 text-center">
						<div className="text-2xl font-bold">
							{result.files_indexed}
						</div>
						<div className="text-xs text-muted-foreground">
							Indexed
						</div>
					</div>
					<div className="rounded-lg border bg-muted/50 p-3 text-center">
						<div className="text-2xl font-bold">
							{result.files_unchanged}
						</div>
						<div className="text-xs text-muted-foreground">
							Unchanged
						</div>
					</div>
					<div className="rounded-lg border bg-muted/50 p-3 text-center">
						<div className="text-2xl font-bold">
							{result.files_deleted}
						</div>
						<div className="text-xs text-muted-foreground">
							Deleted
						</div>
					</div>
					<div className="rounded-lg border bg-muted/50 p-3 text-center">
						<div className="text-2xl font-bold">
							{formatDuration(result.duration_ms)}
						</div>
						<div className="text-xs text-muted-foreground">
							Duration
						</div>
					</div>
				</div>
			)}

			{/* Message */}
			{result.message && (
				<p className="text-sm text-muted-foreground">
					{result.message}
				</p>
			)}
		</div>
	);
}

function AppDepScanResults({ result }: { result: AppDependencyScanResponse }) {
	const hasIssues = result.issues_found > 0;

	// Group issues by app
	const issuesByApp = result.issues.reduce(
		(acc, issue) => {
			const key = issue.app_slug;
			if (!acc[key]) {
				acc[key] = {
					app_name: issue.app_name,
					app_slug: issue.app_slug,
					issues: [],
				};
			}
			acc[key].issues.push(issue);
			return acc;
		},
		{} as Record<
			string,
			{
				app_name: string;
				app_slug: string;
				issues: AppDependencyIssue[];
			}
		>,
	);

	return (
		<div className="space-y-4">
			{/* Summary */}
			<div className="flex items-center gap-4 flex-wrap">
				{hasIssues ? (
					<div className="flex items-center gap-2 text-amber-600">
						<AlertTriangle className="h-5 w-5" />
						<span className="font-medium">
							{result.issues_found} broken reference
							{result.issues_found !== 1 ? "s" : ""}
						</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-green-600">
						<CheckCircle2 className="h-5 w-5" />
						<span className="font-medium">
							All dependencies valid
						</span>
					</div>
				)}
				<Badge variant="secondary">
					{result.apps_scanned} app
					{result.apps_scanned !== 1 ? "s" : ""} scanned
				</Badge>
				<Badge variant="outline">
					{result.files_scanned} file
					{result.files_scanned !== 1 ? "s" : ""}
				</Badge>
				<Badge variant="outline">
					{result.dependencies_rebuilt} dependenc
					{result.dependencies_rebuilt !== 1 ? "ies" : "y"} rebuilt
				</Badge>
			</div>

			{/* Issues by app */}
			{hasIssues && (
				<div className="space-y-2">
					<h4 className="text-sm font-medium text-muted-foreground">
						Missing workflow references:
					</h4>
					<div className="max-h-64 overflow-y-auto rounded-md border bg-muted/50 p-3 space-y-3">
						{Object.entries(issuesByApp).map(
							([appSlug, { app_name, issues }]) => (
								<div key={appSlug} className="space-y-1">
									<div className="flex items-center gap-2 text-sm font-medium">
										<AppWindow className="h-4 w-4 text-muted-foreground flex-shrink-0" />
										<span>{app_name}</span>
										<Badge
											variant="outline"
											className="text-xs px-1.5 py-0"
										>
											{appSlug}
										</Badge>
									</div>
									<ul className="ml-6 space-y-1">
										{issues.map((issue, idx) => (
											<li
												key={`${issue.dependency_id}-${idx}`}
												className="text-sm text-muted-foreground"
											>
												<span className="font-mono text-xs">
													{issue.file_path}
												</span>
												<span className="mx-1">→</span>
												<code className="bg-destructive/10 text-destructive px-1 py-0.5 rounded text-xs">
													{issue.dependency_type}:{" "}
													{issue.dependency_id}
												</code>
											</li>
										))}
									</ul>
								</div>
							),
						)}
					</div>
				</div>
			)}
		</div>
	);
}
