/**
 * Workspace Maintenance Settings
 *
 * Platform admin page for managing workspace maintenance operations.
 * Provides tools for ID injection and SDK reference scanning.
 */

import { useState, useCallback } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	AlertCircle,
	CheckCircle2,
	Loader2,
	Play,
	Search,
	FileCode,
	AlertTriangle,
	Settings2,
	Link2,
	Database,
} from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";
import type { components } from "@/lib/v1";

type FileMetadata = components["schemas"]["FileMetadata"];

interface ReindexResponse {
	status: string;
	files_indexed: number;
	files_needing_ids: string[];
	ids_injected: number;
	message: string | null;
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

type ScanResultType = "none" | "ids" | "sdk" | "docs";

export function Maintenance() {
	// Scan states
	const [isIdScanning, setIsIdScanning] = useState(false);
	const [isIdInjecting, setIsIdInjecting] = useState(false);
	const [isSdkScanning, setIsSdkScanning] = useState(false);

	const [isDocsIndexing, setIsDocsIndexing] = useState(false);

	// Results
	const [lastScanType, setLastScanType] = useState<ScanResultType>("none");
	const [idScanResult, setIdScanResult] = useState<ReindexResponse | null>(
		null,
	);
	const [sdkScanResult, setSdkScanResult] = useState<SDKScanResponse | null>(
		null,
	);
	const [docsIndexResult, setDocsIndexResult] =
		useState<DocsIndexResponse | null>(null);

	const isAnyRunning =
		isIdScanning || isIdInjecting || isSdkScanning || isDocsIndexing;

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
					is_workflow: false,
					is_data_provider: false,
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

	const handleIdScan = async (injectIds: boolean) => {
		if (injectIds) {
			setIsIdInjecting(true);
		} else {
			setIsIdScanning(true);
		}

		try {
			const response = await authFetch("/api/maintenance/reindex", {
				method: "POST",
				body: JSON.stringify({ inject_ids: injectIds }),
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error(
					injectIds ? "ID injection failed" : "ID scan failed",
					{
						description: errorData.detail || "Unknown error",
					},
				);
				return;
			}

			const data: ReindexResponse = await response.json();
			setIdScanResult(data);
			setLastScanType("ids");

			toast.success(data.message || "Completed", {
				description: injectIds
					? `Injected IDs into ${data.ids_injected} files`
					: `Found ${data.files_needing_ids?.length || 0} files needing IDs`,
			});
		} catch (err) {
			toast.error(injectIds ? "ID injection failed" : "ID scan failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
		} finally {
			setIsIdScanning(false);
			setIsIdInjecting(false);
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
					{/* ID Injection Section */}
					<div className="space-y-4">
						<h3 className="text-sm font-medium">
							Decorator ID Injection
						</h3>
						<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
							<AlertCircle className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
							<div className="text-sm text-blue-800 dark:text-blue-200">
								<p className="text-blue-700 dark:text-blue-300">
									Workflow, tool, and data provider decorators
									need unique IDs for proper tracking. Scan to
									find decorators missing IDs, or inject to
									add them automatically.
								</p>
							</div>
						</div>
						<div className="flex flex-wrap gap-3">
							<Button
								onClick={() => handleIdScan(false)}
								disabled={isAnyRunning}
								variant="outline"
							>
								{isIdScanning ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Search className="h-4 w-4 mr-2" />
								)}
								Scan for Missing IDs
							</Button>
							<Button
								onClick={() => handleIdScan(true)}
								disabled={isAnyRunning}
							>
								{isIdInjecting ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Play className="h-4 w-4 mr-2" />
								)}
								Inject IDs
							</Button>
						</div>
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
					) : lastScanType === "ids" && idScanResult ? (
						<IdScanResults
							result={idScanResult}
							onOpenFile={openFileInEditor}
						/>
					) : lastScanType === "sdk" && sdkScanResult ? (
						<SdkScanResults
							result={sdkScanResult}
							onOpenFile={openFileInEditor}
						/>
					) : lastScanType === "docs" && docsIndexResult ? (
						<DocsIndexResults result={docsIndexResult} />
					) : null}
				</CardContent>
			</Card>
		</div>
	);
}

function IdScanResults({
	result,
	onOpenFile,
}: {
	result: ReindexResponse;
	onOpenFile: (path: string, line?: number) => void;
}) {
	const filesNeedingIds = result.files_needing_ids || [];
	const hasFilesNeedingIds = filesNeedingIds.length > 0;

	return (
		<div className="space-y-4">
			{/* Summary */}
			<div className="flex items-center gap-4">
				{hasFilesNeedingIds ? (
					<div className="flex items-center gap-2 text-amber-600">
						<AlertTriangle className="h-5 w-5" />
						<span className="font-medium">
							{filesNeedingIds.length} file
							{filesNeedingIds.length !== 1 ? "s" : ""} need
							indexing
						</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-green-600">
						<CheckCircle2 className="h-5 w-5" />
						<span className="font-medium">All files indexed</span>
					</div>
				)}
				<Badge variant="secondary">
					{result.files_indexed} file
					{result.files_indexed !== 1 ? "s" : ""} scanned
				</Badge>
				{result.ids_injected > 0 && (
					<Badge variant="default">
						{result.ids_injected} ID
						{result.ids_injected !== 1 ? "s" : ""} injected
					</Badge>
				)}
			</div>

			{/* Files needing IDs */}
			{hasFilesNeedingIds && (
				<div className="space-y-2">
					<h4 className="text-sm font-medium text-muted-foreground">
						Files needing ID injection:
					</h4>
					<div className="max-h-48 overflow-y-auto rounded-md border bg-muted/50 p-3">
						<ul className="space-y-1 text-sm font-mono">
							{filesNeedingIds.map((file) => (
								<li
									key={file}
									className="flex items-center gap-2"
								>
									<FileCode className="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<button
										type="button"
										onClick={() => onOpenFile(file)}
										className="truncate text-left hover:text-primary hover:underline"
									>
										{file}
									</button>
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
				<p className="text-sm text-muted-foreground">{result.message}</p>
			)}
		</div>
	);
}
