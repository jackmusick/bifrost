/**
 * Workspace Maintenance Settings
 *
 * Platform admin page for managing workspace maintenance operations.
 * Shows files needing ID injection and allows running reindex.
 */

import { useState, useEffect, useCallback } from "react";
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
	RefreshCw,
	FileCode,
	AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";

interface MaintenanceStatus {
	files_needing_ids: string[];
	total_files: number;
	last_reindex: string | null;
}

interface ReindexResponse {
	status: string;
	files_indexed: number;
	files_needing_ids: string[];
	ids_injected: number;
	message: string | null;
}

export function Maintenance() {
	const [status, setStatus] = useState<MaintenanceStatus | null>(null);
	const [statusLoading, setStatusLoading] = useState(true);
	const [isRunning, setIsRunning] = useState(false);

	const fetchStatus = useCallback(async () => {
		setStatusLoading(true);
		try {
			const response = await authFetch("/api/maintenance/status");
			if (response.ok) {
				const data = await response.json();
				setStatus(data);
			} else {
				toast.error("Failed to load maintenance status");
			}
		} catch (err) {
			toast.error("Failed to load maintenance status", {
				description:
					err instanceof Error ? err.message : "Unknown error",
			});
		} finally {
			setStatusLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchStatus();
	}, [fetchStatus]);

	const handleReindex = async (injectIds: boolean) => {
		setIsRunning(true);
		try {
			const response = await authFetch("/api/maintenance/reindex", {
				method: "POST",
				body: JSON.stringify({ inject_ids: injectIds }),
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				toast.error("Reindex failed", {
					description: errorData.detail || "Unknown error",
				});
				return;
			}

			const data: ReindexResponse = await response.json();
			toast.success(data.message || "Reindex completed", {
				description: injectIds
					? `Injected IDs into ${data.ids_injected} files`
					: `Found ${data.files_needing_ids?.length || 0} files needing IDs`,
			});
			// Refresh status after reindex
			fetchStatus();
		} catch (err) {
			toast.error("Reindex failed", {
				description:
					err instanceof Error
						? err.message
						: "Unknown error occurred",
			});
		} finally {
			setIsRunning(false);
		}
	};

	const filesNeedingIds = status?.files_needing_ids || [];
	const totalFiles = status?.total_files || 0;
	const hasFilesNeedingIds = filesNeedingIds.length > 0;

	return (
		<div className="space-y-6">
			{/* Status Card */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle className="flex items-center gap-2">
								Workspace Status
								{statusLoading && (
									<Loader2 className="h-4 w-4 animate-spin" />
								)}
							</CardTitle>
							<CardDescription>
								Current state of workflow file indexing
							</CardDescription>
						</div>
						<Button
							variant="outline"
							size="sm"
							onClick={() => fetchStatus()}
							disabled={statusLoading}
						>
							<RefreshCw
								className={`h-4 w-4 mr-2 ${statusLoading ? "animate-spin" : ""}`}
							/>
							Refresh
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					{statusLoading ? (
						<div className="flex items-center justify-center py-8">
							<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
						</div>
					) : (
						<div className="space-y-4">
							{/* Summary */}
							<div className="flex items-center gap-4">
								{hasFilesNeedingIds ? (
									<div className="flex items-center gap-2 text-amber-600">
										<AlertTriangle className="h-5 w-5" />
										<span className="font-medium">
											{filesNeedingIds.length} file
											{filesNeedingIds.length !== 1
												? "s"
												: ""}{" "}
											need indexing
										</span>
									</div>
								) : (
									<div className="flex items-center gap-2 text-green-600">
										<CheckCircle2 className="h-5 w-5" />
										<span className="font-medium">
											All files indexed
										</span>
									</div>
								)}
								<Badge variant="secondary">
									{totalFiles} total file
									{totalFiles !== 1 ? "s" : ""}
								</Badge>
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
													<span className="truncate">
														{file}
													</span>
												</li>
											))}
										</ul>
									</div>
								</div>
							)}
						</div>
					)}
				</CardContent>
			</Card>

			{/* Actions Card */}
			<Card>
				<CardHeader>
					<CardTitle>Maintenance Actions</CardTitle>
					<CardDescription>
						Run workspace maintenance operations
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					{/* Info about ID injection */}
					<div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
						<AlertCircle className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
						<div className="text-sm text-blue-800 dark:text-blue-200">
							<p className="font-medium mb-1">
								About ID Injection
							</p>
							<p className="text-blue-700 dark:text-blue-300">
								Workflow, tool, and data provider decorators
								need unique IDs for proper tracking. Running
								"Inject IDs" will add UUIDs to any decorators
								that are missing them. This is a safe,
								non-destructive operation that preserves your
								code formatting.
							</p>
						</div>
					</div>

					{/* Action buttons */}
					<div className="flex flex-wrap gap-3">
						<Button
							onClick={() => handleReindex(false)}
							disabled={isRunning || statusLoading}
							variant="outline"
						>
							{isRunning ? (
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							) : (
								<RefreshCw className="h-4 w-4 mr-2" />
							)}
							Scan Only
						</Button>

						<Button
							onClick={() => handleReindex(true)}
							disabled={isRunning || statusLoading}
						>
							{isRunning ? (
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							) : (
								<Play className="h-4 w-4 mr-2" />
							)}
							Inject IDs
						</Button>
					</div>

					{/* Button descriptions */}
					<div className="text-xs text-muted-foreground space-y-1">
						<p>
							<strong>Scan Only:</strong> Check which files need
							IDs without making changes
						</p>
						<p>
							<strong>Inject IDs:</strong> Add missing IDs to
							decorators and update the workspace
						</p>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}
