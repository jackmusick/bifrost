import { useState, useEffect } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
	Loader2,
	Github,
	CheckCircle2,
	AlertCircle,
	Plus,
	RefreshCw,
	ArrowDownToLine,
	ArrowUpFromLine,
	AlertTriangle,
} from "lucide-react";
import {
	useGitHubConfig,
	useGitHubRepositories,
	useConfigureGitHub,
	useCreateGitHubRepository,
	useDisconnectGitHub,
	useSyncPreview,
	useSyncExecute,
	validateGitHubToken,
	listGitHubBranches,
	type GitHubRepoInfo,
	type GitHubBranchInfo,
	type GitHubConfigResponse,
	type SyncPreviewResponse,
	type SyncAction,
} from "@/hooks/useGitHub";
import { webSocketService, type GitPreviewComplete } from "@/services/websocket";

export function GitHub() {
	const [config, setConfig] = useState<GitHubConfigResponse | null>(null);
	const [saving, setSaving] = useState(false);
	const [testingToken, setTestingToken] = useState(false);
	const [loadingBranches, setLoadingBranches] = useState(false);

	// Form state
	const [token, setToken] = useState("");
	const [tokenValid, setTokenValid] = useState<boolean | null>(null);
	const [repositories, setRepositories] = useState<GitHubRepoInfo[]>([]);
	const [branches, setBranches] = useState<GitHubBranchInfo[]>([]);
	const [selectedRepo, setSelectedRepo] = useState<string>("");
	const [selectedBranch, setSelectedBranch] = useState<string>("main");

	// Create repo state
	const [showCreateRepo, setShowCreateRepo] = useState(false);
	const [newRepoName, setNewRepoName] = useState("");
	const [newRepoDescription, setNewRepoDescription] = useState("");
	const [newRepoPrivate, setNewRepoPrivate] = useState(true);
	const [creatingRepo, setCreatingRepo] = useState(false);

	// Disconnect confirmation state
	const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

	// Sync preview dialog state
	const [showSyncPreview, setShowSyncPreview] = useState(false);
	const [syncPreviewData, setSyncPreviewData] =
		useState<SyncPreviewResponse | null>(null);
	const [loadingSyncPreview, setLoadingSyncPreview] = useState(false);
	const [executingSync, setExecutingSync] = useState(false);

	// Load current GitHub configuration
	const { data: configData, isLoading: configLoading } = useGitHubConfig();

	// Load repositories when token is saved but not configured
	const shouldLoadRepos = configData?.token_saved && !configData?.configured;
	const { data: reposData } = useGitHubRepositories(shouldLoadRepos ?? false);

	// Mutations
	const configureMutation = useConfigureGitHub();
	const createRepoMutation = useCreateGitHubRepository();
	const disconnectMutation = useDisconnectGitHub();
	const syncPreviewMutation = useSyncPreview();
	const syncExecuteMutation = useSyncExecute();

	// Track the saved token for use in configuration
	const [savedToken, setSavedToken] = useState<string | null>(null);

	// Update local state when config data loads
	useEffect(() => {
		if (configData) {
			setConfig(configData);

			// If token is saved but not configured, set token as valid
			if (configData.token_saved && !configData.configured) {
				setTokenValid(true);
			}
		}
	}, [configData]);

	// Load repositories when they're available from the saved token
	useEffect(() => {
		if (reposData?.repositories && config?.token_saved && !config?.configured) {
			setRepositories(reposData.repositories);
		}
	}, [reposData, config?.token_saved, config?.configured]);

	// Validate token and load repositories
	const handleTokenValidation = async () => {
		if (!token.trim()) {
			toast.error("Please enter a GitHub Personal Access Token");
			return;
		}

		setTestingToken(true);
		setTokenValid(null);
		setRepositories([]);
		setBranches([]);

		try {
			const response = await validateGitHubToken(token);
			setRepositories(response.repositories);
			setSavedToken(token); // Save token for later use in configure
			setTokenValid(true);

			// Auto-select detected repo if available
			if (response.detected_repo) {
				setSelectedRepo(response.detected_repo.full_name);
				setSelectedBranch(response.detected_repo.branch);

				// Load branches for detected repo
				try {
					const branchList = await listGitHubBranches(
						response.detected_repo.full_name,
					);
					setBranches(branchList);
				} catch (error) {
					console.error(
						"Failed to load branches for detected repo:",
						error,
					);
				}

				toast.success("Token validated successfully", {
					description: `Detected existing repository: ${response.detected_repo.full_name}`,
				});
			} else {
				toast.success("Token validated successfully", {
					description: `Found ${response.repositories.length} accessible repositories`,
				});
			}
		} catch {
			setTokenValid(false);
			toast.error("Invalid token", {
				description:
					"Please check your GitHub Personal Access Token and try again",
			});
		} finally {
			setTestingToken(false);
		}
	};

	// Load branches when repository is selected
	const handleRepoSelection = async (repoFullName: string) => {
		setSelectedRepo(repoFullName);
		setBranches([]);
		setSelectedBranch("main");

		if (!repoFullName) return;

		setLoadingBranches(true);
		try {
			const branchList = await listGitHubBranches(repoFullName);
			setBranches(branchList);

			// Auto-select main/master if available
			const defaultBranch =
				branchList.find((b) => b.name === "main") ||
				branchList.find((b) => b.name === "master");
			if (defaultBranch) {
				setSelectedBranch(defaultBranch.name);
			}
		} catch {
			toast.error("Failed to load branches");
		} finally {
			setLoadingBranches(false);
		}
	};

	// Create new repository
	const handleCreateRepository = async () => {
		if (!newRepoName.trim()) {
			toast.error("Please enter a repository name");
			return;
		}

		setCreatingRepo(true);
		try {
			const newRepo = await createRepoMutation.mutateAsync({
				body: {
					name: newRepoName,
					description: newRepoDescription || null,
					private: newRepoPrivate,
					organization: null,
				},
			});

			toast.success("Repository created", {
				description: `Created ${newRepo.full_name}`,
			});

			// Update repositories list - refetch will happen automatically from mutation
			// For now, we manually update the state for immediate feedback
			setRepositories([
				...repositories,
				newRepo as unknown as GitHubRepoInfo,
			]);
			setSelectedRepo(newRepo.full_name);

			// Load branches for new repo
			await handleRepoSelection(newRepo.full_name);

			// Close dialog and reset form
			setShowCreateRepo(false);
			setNewRepoName("");
			setNewRepoDescription("");
			setNewRepoPrivate(true);
		} catch (error) {
			toast.error("Failed to create repository", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setCreatingRepo(false);
		}
	};

	// Configure GitHub integration
	const handleConfigure = async () => {
		// Token must be saved to configure
		if (!config?.token_saved && !savedToken) {
			toast.error("Please validate your token first");
			return;
		}

		if (!selectedRepo) {
			toast.error("Please select a repository");
			return;
		}

		// Proceed directly to configuration
		await handleSaveConfig();
	};

	// Save configuration (always replaces workspace with remote)
	const handleSaveConfig = async () => {
		setSaving(true);

		try {
			const setupResponse = await configureMutation.mutateAsync({
				body: {
					repo_url: selectedRepo,
					branch: selectedBranch,
				},
			});

			// Configuration is now async - show job queued message
			toast.success("GitHub configuration started", {
				description: `Job ${setupResponse.job_id} queued. Watch for notifications for progress.`,
			});
		} catch (error) {
			toast.error("Failed to save configuration", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Disconnect GitHub integration
	const handleDisconnect = async () => {
		setSaving(true);
		setShowDisconnectConfirm(false);

		try {
			await disconnectMutation.mutateAsync({});

			// Reset all state
			setConfig({
				configured: false,
				token_saved: false,
				repo_url: null,
				branch: null,
				backup_path: null,
			});
			setToken("");
			setTokenValid(null);
			setRepositories([]);
			setBranches([]);
			setSelectedRepo("");
			setSelectedBranch("main");

			toast.success("GitHub integration disconnected", {
				description: "Your credentials have been removed",
			});
		} catch (error) {
			toast.error("Failed to disconnect GitHub", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Open sync preview dialog (uses WebSocket for progress updates)
	const handleOpenSyncPreview = async () => {
		setLoadingSyncPreview(true);
		setShowSyncPreview(true);
		setSyncPreviewData(null);

		try {
			// Queue the preview job (returns immediately with job_id)
			const jobResponse = await syncPreviewMutation.mutateAsync();
			const jobId = jobResponse.job_id;

			if (!jobId) {
				throw new Error("Failed to queue sync preview job");
			}

			// Connect to WebSocket channel for progress updates
			await webSocketService.connectToGitSync(jobId);

			// Wait for completion via promise
			const preview = await new Promise<SyncPreviewResponse>((resolve, reject) => {
				const unsubComplete = webSocketService.onGitSyncPreviewComplete(jobId, (complete: GitPreviewComplete) => {
					unsubComplete();

					if (complete.status === "success" && complete.preview) {
						resolve(complete.preview);
					} else {
						reject(new Error(complete.error || "Sync preview failed"));
					}
				});
			});

			setSyncPreviewData(preview);
		} catch (error) {
			toast.error("Failed to get sync preview", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
			setShowSyncPreview(false);
		} finally {
			setLoadingSyncPreview(false);
		}
	};

	// Execute sync with resolutions
	const handleExecuteSync = async (
		resolutions: Record<string, "keep_local" | "keep_remote">,
		confirmOrphans: boolean,
	) => {
		setExecutingSync(true);

		try {
			const result = await syncExecuteMutation.mutateAsync({
				body: {
					conflict_resolutions: resolutions,
					confirm_orphans: confirmOrphans,
					confirm_unresolved_refs: true,
				},
			});

			if (result.success) {
				toast.success("Sync completed successfully", {
					description: `Pulled ${result.pulled} files, pushed ${result.pushed} files`,
				});
				setShowSyncPreview(false);
				setSyncPreviewData(null);
			} else {
				toast.error("Sync failed", {
					description: result.error || "Unknown error",
				});
			}
		} catch (error) {
			toast.error("Failed to execute sync", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setExecutingSync(false);
		}
	};

	if (configLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<Card>
				<CardHeader>
					<div className="flex items-center gap-2">
						<Github className="h-5 w-5" />
						<CardTitle>GitHub Integration</CardTitle>
					</div>
					<CardDescription>
						Connect your workspace to a GitHub repository for
						version control and collaboration
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{/* Current Status */}
					{config?.configured ? (
						<div className="space-y-4">
							<div className="rounded-lg border bg-muted/50 p-4">
								<div className="flex items-center justify-between mb-2">
									<div className="flex items-center gap-2">
										<CheckCircle2 className="h-4 w-4 text-green-500" />
										<span className="text-sm font-medium">
											Currently Connected
										</span>
									</div>
									<div className="flex items-center gap-2">
										<Button
											variant="outline"
											size="sm"
											onClick={handleOpenSyncPreview}
											disabled={
												loadingSyncPreview ||
												executingSync
											}
										>
											{loadingSyncPreview ? (
												<>
													<Loader2 className="h-4 w-4 mr-2 animate-spin" />
													Loading...
												</>
											) : (
												<>
													<RefreshCw className="h-4 w-4 mr-2" />
													Sync
												</>
											)}
										</Button>
										<Button
											variant="destructive"
											size="sm"
											onClick={() =>
												setShowDisconnectConfirm(true)
											}
											disabled={saving}
										>
											{saving ? (
												<Loader2 className="h-4 w-4 animate-spin" />
											) : (
												"Disconnect"
											)}
										</Button>
									</div>
								</div>
								<div className="space-y-1 text-sm text-muted-foreground">
									<div>
										<strong>Repository:</strong>{" "}
										{config.repo_url}
									</div>
									<div>
										<strong>Branch:</strong> {config.branch}
									</div>
								</div>
							</div>
							<p className="text-sm text-muted-foreground">
								To change your configuration, disconnect first.
							</p>
						</div>
					) : (
						<>
							{/* GitHub Token */}
							<div className="space-y-2">
								<Label htmlFor="github-token">
									GitHub Personal Access Token
								</Label>
								<div className="flex gap-2">
									<Input
										id="github-token"
										type="password"
										autoComplete="off"
										placeholder={
											config?.token_saved
												? "Token saved - enter new token to change"
												: "ghp_xxxxxxxxxxxxxxxxxxxx"
										}
										value={token}
										onChange={(e) => {
											setToken(e.target.value);
											// Only invalidate if we actually had a validated token from manual validation
											// Don't clear if token was just saved (not manually validated)
											if (tokenValid === true) {
												setTokenValid(null);
											}
										}}
									/>
									<Button
										onClick={handleTokenValidation}
										disabled={testingToken || !token.trim()}
										variant={
											tokenValid === true
												? "default"
												: tokenValid === false
													? "destructive"
													: "secondary"
										}
										className="gap-2"
									>
										{testingToken ? (
											<>
												<Loader2 className="h-4 w-4 animate-spin" />
												Validating...
											</>
										) : tokenValid === true ? (
											<>
												<CheckCircle2 className="h-4 w-4" />
												Validated
											</>
										) : tokenValid === false ? (
											<>
												<AlertCircle className="h-4 w-4" />
												Invalid
											</>
										) : (
											"Validate"
										)}
									</Button>
								</div>
								<p className="text-xs text-muted-foreground">
									Create a token at{" "}
									<a
										href="https://github.com/settings/tokens/new"
										target="_blank"
										rel="noopener noreferrer"
										className="underline hover:text-foreground"
									>
										github.com/settings/tokens
									</a>{" "}
									with <code className="text-xs">repo</code>{" "}
									scope
								</p>
							</div>

							{/* Repository Selection - always show if token is valid or saved */}
							{(tokenValid || config?.token_saved) && (
								<div className="space-y-2">
									<div className="flex items-center justify-between">
										<Label htmlFor="repository">
											Repository
										</Label>
										<Button
											variant="ghost"
											size="sm"
											onClick={() =>
												setShowCreateRepo(true)
											}
										>
											<Plus className="h-4 w-4 mr-1" />
											Create New
										</Button>
									</div>
									<Select
										value={selectedRepo}
										onValueChange={handleRepoSelection}
									>
										<SelectTrigger id="repository">
											<SelectValue placeholder="Select a repository" />
										</SelectTrigger>
										<SelectContent>
											{repositories.map((repo) => (
												<SelectItem
													key={repo.full_name}
													value={repo.full_name}
												>
													<div className="flex items-center gap-2">
														<span>
															{repo.full_name}
														</span>
														{repo.private && (
															<span className="text-xs text-muted-foreground">
																(private)
															</span>
														)}
													</div>
												</SelectItem>
											))}
										</SelectContent>
									</Select>
								</div>
							)}

							{/* Branch Selection - always show if repo selected */}
							{(tokenValid || config?.token_saved) && (
								<div className="space-y-2">
									<Label htmlFor="branch">Branch</Label>
									<Select
										value={selectedBranch}
										onValueChange={setSelectedBranch}
										disabled={
											!selectedRepo || loadingBranches
										}
									>
										<SelectTrigger id="branch">
											{loadingBranches ? (
												<div className="flex items-center gap-2">
													<Loader2 className="h-4 w-4 animate-spin" />
													<span>
														Loading branches...
													</span>
												</div>
											) : (
												<SelectValue placeholder="Select a branch" />
											)}
										</SelectTrigger>
										<SelectContent>
											{branches.map((branch) => (
												<SelectItem
													key={branch.name}
													value={branch.name}
												>
													<div className="flex items-center gap-2">
														<span>
															{branch.name}
														</span>
														{branch.protected && (
															<span className="text-xs text-muted-foreground">
																(protected)
															</span>
														)}
													</div>
												</SelectItem>
											))}
										</SelectContent>
									</Select>
									{!selectedRepo && (
										<p className="text-xs text-muted-foreground">
											Select a repository first
										</p>
									)}
								</div>
							)}

							{/* Save Button */}
							<div className="flex justify-end">
								<Button
									onClick={handleConfigure}
									disabled={
										saving ||
										!selectedRepo ||
										(!config?.token_saved &&
											!token.trim()) ||
										(!config?.token_saved &&
											tokenValid !== true)
									}
								>
									{saving ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											Configuring...
										</>
									) : (
										<>
											<Github className="h-4 w-4 mr-2" />
											Configure GitHub
										</>
									)}
								</Button>
							</div>
						</>
					)}
				</CardContent>
			</Card>

			{/* Additional Information */}
			<Card>
				<CardHeader>
					<CardTitle className="text-base">How it works</CardTitle>
				</CardHeader>
				<CardContent className="space-y-2 text-sm text-muted-foreground">
					<p>
						Once configured, your workspace will be synced with the
						selected GitHub repository:
					</p>
					<ul className="list-disc list-inside space-y-1 ml-2">
						<li>
							Use the <strong>Source Control</strong> panel in the
							Code Editor to view changes
						</li>
						<li>
							Commit and push changes directly from the editor
						</li>
						<li>
							Pull updates from GitHub to keep your workspace in
							sync
						</li>
						<li>Resolve merge conflicts with inline tools</li>
					</ul>
				</CardContent>
			</Card>

			{/* Create Repository Modal */}
			<Dialog open={showCreateRepo} onOpenChange={setShowCreateRepo}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Create New Repository</DialogTitle>
						<DialogDescription>
							Create a new GitHub repository in your account
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-4">
						<div className="space-y-2">
							<Label htmlFor="new-repo-name">
								Repository Name
							</Label>
							<Input
								id="new-repo-name"
								placeholder="my-repository"
								value={newRepoName}
								onChange={(e) => setNewRepoName(e.target.value)}
							/>
						</div>

						<div className="space-y-2">
							<Label htmlFor="new-repo-desc">
								Description (Optional)
							</Label>
							<Input
								id="new-repo-desc"
								placeholder="A brief description"
								value={newRepoDescription}
								onChange={(e) =>
									setNewRepoDescription(e.target.value)
								}
							/>
						</div>

						<div className="flex items-center space-x-2">
							<input
								type="checkbox"
								id="new-repo-private"
								checked={newRepoPrivate}
								onChange={(e) =>
									setNewRepoPrivate(e.target.checked)
								}
								className="h-4 w-4"
							/>
							<Label
								htmlFor="new-repo-private"
								className="text-sm font-normal"
							>
								Private repository
							</Label>
						</div>
					</div>

					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setShowCreateRepo(false)}
						>
							Cancel
						</Button>
						<Button
							onClick={handleCreateRepository}
							disabled={!newRepoName.trim() || creatingRepo}
						>
							{creatingRepo ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Creating...
								</>
							) : (
								"Create Repository"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Disconnect Confirmation Dialog */}
			<Dialog
				open={showDisconnectConfirm}
				onOpenChange={setShowDisconnectConfirm}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Disconnect GitHub Integration</DialogTitle>
						<DialogDescription>
							Are you sure you want to disconnect GitHub
							integration? This will remove all stored credentials
							and you'll need to reconfigure to reconnect.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setShowDisconnectConfirm(false)}
							disabled={saving}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={handleDisconnect}
							disabled={saving}
						>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Disconnecting...
								</>
							) : (
								"Disconnect"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Sync Preview Dialog - key forces remount when preview changes to reset internal state */}
			<SyncPreviewDialog
				key={syncPreviewData ? "loaded" : "empty"}
				open={showSyncPreview}
				onClose={() => {
					setShowSyncPreview(false);
					setSyncPreviewData(null);
				}}
				onConfirm={handleExecuteSync}
				preview={syncPreviewData}
				loading={loadingSyncPreview}
				executing={executingSync}
			/>
		</div>
	);
}

// =============================================================================
// SyncPreviewDialog Component
// =============================================================================

interface SyncPreviewDialogProps {
	open: boolean;
	onClose: () => void;
	onConfirm: (
		resolutions: Record<string, "keep_local" | "keep_remote">,
		confirmOrphans: boolean,
	) => void;
	preview: SyncPreviewResponse | null;
	loading: boolean;
	executing: boolean;
}

function SyncPreviewDialog({
	open,
	onClose,
	onConfirm,
	preview,
	loading,
	executing,
}: SyncPreviewDialogProps) {
	// State is reset via key prop on parent component when preview data changes
	const [resolutions, setResolutions] = useState<
		Record<string, "keep_local" | "keep_remote">
	>({});
	const [orphansConfirmed, setOrphansConfirmed] = useState(false);

	// Helper to render action badge
	const renderActionBadge = (action: SyncAction["action"]) => {
		switch (action) {
			case "add":
				return (
					<Badge variant="default" className="text-xs px-1.5">
						A
					</Badge>
				);
			case "modify":
				return (
					<Badge variant="secondary" className="text-xs px-1.5">
						M
					</Badge>
				);
			case "delete":
				return (
					<Badge variant="destructive" className="text-xs px-1.5">
						D
					</Badge>
				);
		}
	};

	// Check if all conflicts are resolved and orphans confirmed (if needed)
	const conflicts = preview?.conflicts ?? [];
	const willOrphan = preview?.will_orphan ?? [];
	const canSync =
		preview &&
		!preview.is_empty &&
		conflicts.every((c) => resolutions[c.path]) &&
		(willOrphan.length === 0 || orphansConfirmed);

	// Check if sync is empty (nothing to do)
	const isEmpty = preview?.is_empty;

	return (
		<Dialog open={open} onOpenChange={onClose}>
			<DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<RefreshCw className="h-5 w-5" />
						Sync Preview
					</DialogTitle>
					<DialogDescription>
						Review the changes that will be synced with GitHub
					</DialogDescription>
				</DialogHeader>

				{loading ? (
					<div className="flex items-center justify-center py-12">
						<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
					</div>
				) : isEmpty ? (
					<div className="flex flex-col items-center justify-center py-12 text-center">
						<CheckCircle2 className="h-12 w-12 text-green-500 mb-4" />
						<p className="text-lg font-medium">
							Everything is in sync
						</p>
						<p className="text-sm text-muted-foreground">
							No changes to pull or push
						</p>
					</div>
				) : preview ? (
					<div className="flex-1 overflow-y-auto space-y-6 pr-2">
						{/* Files to Pull */}
						{(preview.to_pull?.length ?? 0) > 0 && (
							<div>
								<h3 className="flex items-center gap-2 font-medium mb-3">
									<ArrowDownToLine className="h-4 w-4 text-blue-500" />
									<span>Pull from GitHub</span>
									<Badge variant="outline" className="ml-2">
										{preview.to_pull?.length ?? 0}
									</Badge>
								</h3>
								<ul className="text-sm space-y-1.5 max-h-40 overflow-y-auto rounded-md border p-3 bg-muted/30">
									{(preview.to_pull ?? []).map((item) => (
										<li
											key={item.path}
											className="flex items-center gap-2"
										>
											{renderActionBadge(item.action)}
											<span className="font-mono text-xs truncate">
												{item.path}
											</span>
										</li>
									))}
								</ul>
							</div>
						)}

						{/* Files to Push */}
						{(preview.to_push?.length ?? 0) > 0 && (
							<div>
								<h3 className="flex items-center gap-2 font-medium mb-3">
									<ArrowUpFromLine className="h-4 w-4 text-green-500" />
									<span>Push to GitHub</span>
									<Badge variant="outline" className="ml-2">
										{preview.to_push?.length ?? 0}
									</Badge>
								</h3>
								<ul className="text-sm space-y-1.5 max-h-40 overflow-y-auto rounded-md border p-3 bg-muted/30">
									{(preview.to_push ?? []).map((item) => (
										<li
											key={item.path}
											className="flex items-center gap-2"
										>
											{renderActionBadge(item.action)}
											<span className="font-mono text-xs truncate">
												{item.path}
											</span>
										</li>
									))}
								</ul>
							</div>
						)}

						{/* Conflicts Section */}
						{conflicts.length > 0 && (
							<div>
								<h3 className="flex items-center gap-2 font-medium mb-3 text-yellow-600">
									<AlertCircle className="h-4 w-4" />
									<span>Conflicts</span>
									<Badge variant="warning" className="ml-2">
										{conflicts.length}
									</Badge>
								</h3>
								<p className="text-sm text-muted-foreground mb-3">
									These files have been modified both locally
									and remotely. Choose which version to keep:
								</p>
								<div className="space-y-4">
									{conflicts.map((conflict) => (
										<div
											key={conflict.path}
											className="rounded-md border p-4 bg-yellow-50/50 dark:bg-yellow-950/20"
										>
											<p className="font-mono text-sm mb-3">
												{conflict.path}
											</p>
											<RadioGroup
												value={
													resolutions[conflict.path]
												}
												onValueChange={(
													value:
														| "keep_local"
														| "keep_remote",
												) =>
													setResolutions((r) => ({
														...r,
														[conflict.path]: value,
													}))
												}
												className="gap-3"
											>
												<div className="flex items-center space-x-2">
													<RadioGroupItem
														value="keep_local"
														id={`${conflict.path}-local`}
													/>
													<Label
														htmlFor={`${conflict.path}-local`}
														className="cursor-pointer"
													>
														Keep mine (push to
														GitHub)
													</Label>
												</div>
												<div className="flex items-center space-x-2">
													<RadioGroupItem
														value="keep_remote"
														id={`${conflict.path}-remote`}
													/>
													<Label
														htmlFor={`${conflict.path}-remote`}
														className="cursor-pointer"
													>
														Keep theirs (pull from
														GitHub)
													</Label>
												</div>
											</RadioGroup>
										</div>
									))}
								</div>
							</div>
						)}

						{/* Orphaned Workflows Warning */}
						{willOrphan.length > 0 && (
							<div className="rounded-md border border-yellow-300 bg-yellow-50 dark:bg-yellow-950/30 p-4">
								<h3 className="flex items-center gap-2 font-medium mb-3 text-yellow-800 dark:text-yellow-200">
									<AlertTriangle className="h-4 w-4" />
									<span>Workflows Will Become Orphaned</span>
								</h3>
								<p className="text-sm text-yellow-700 dark:text-yellow-300 mb-3">
									The following workflows will no longer have
									backing files after this sync. They will
									continue to work but cannot be edited via
									files:
								</p>
								<ul className="text-sm space-y-2 mb-4">
									{willOrphan.map((orphan) => (
										<li
											key={orphan.workflow_id}
											className="rounded bg-white/50 dark:bg-black/20 p-2"
										>
											<div className="font-medium">
												{orphan.workflow_name}
											</div>
											<div className="text-xs text-muted-foreground">
												<span className="font-mono">
													{orphan.function_name}
												</span>
												{" in "}
												<span className="font-mono">
													{orphan.last_path}
												</span>
											</div>
											{(orphan.used_by?.length ?? 0) > 0 && (
												<div className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
													Used by:{" "}
													{(orphan.used_by ?? [])
														.map((ref) => ref.name)
														.join(", ")}
												</div>
											)}
										</li>
									))}
								</ul>
								<div className="flex items-start space-x-2">
									<Checkbox
										id="confirm-orphans"
										checked={orphansConfirmed}
										onCheckedChange={(checked) =>
											setOrphansConfirmed(checked === true)
										}
									/>
									<Label
										htmlFor="confirm-orphans"
										className="text-sm text-yellow-800 dark:text-yellow-200 cursor-pointer leading-tight"
									>
										I understand these workflows will be
										orphaned and can be managed later in
										Settings
									</Label>
								</div>
							</div>
						)}
					</div>
				) : null}

				<DialogFooter className="mt-4">
					<Button variant="outline" onClick={onClose}>
						Cancel
					</Button>
					{isEmpty ? (
						<Button onClick={onClose}>Close</Button>
					) : (
						<Button
							onClick={() =>
								onConfirm(resolutions, orphansConfirmed)
							}
							disabled={!canSync || executing}
						>
							{executing ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Syncing...
								</>
							) : (
								<>
									<RefreshCw className="h-4 w-4 mr-2" />
									Sync
								</>
							)}
						</Button>
					)}
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
