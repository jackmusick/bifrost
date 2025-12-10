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
import { toast } from "sonner";
import { Loader2, Github, CheckCircle2, AlertCircle, Plus } from "lucide-react";
import {
	useGitHubConfig,
	useConfigureGitHub,
	useAnalyzeWorkspace,
	useCreateGitHubRepository,
	useDisconnectGitHub,
	validateGitHubToken,
	listGitHubBranches,
	type GitHubRepoInfo,
	type GitHubBranchInfo,
	type GitHubConfigResponse,
	type WorkspaceAnalysisResponse,
} from "@/hooks/useGitHub";

export function GitHub() {
	const [config, setConfig] = useState<GitHubConfigResponse | null>(null);
	const [saving, setSaving] = useState(false);
	const [testingToken, setTestingToken] = useState(false);
	const [analyzing, setAnalyzing] = useState(false);
	const [loadingBranches, setLoadingBranches] = useState(false);

	// Form state
	const [token, setToken] = useState("");
	const [tokenValid, setTokenValid] = useState<boolean | null>(null);
	const [repositories, setRepositories] = useState<GitHubRepoInfo[]>([]);
	const [branches, setBranches] = useState<GitHubBranchInfo[]>([]);
	const [selectedRepo, setSelectedRepo] = useState<string>("");
	const [selectedBranch, setSelectedBranch] = useState<string>("main");

	// Warning dialog state
	const [showConflictModal, setShowConflictModal] = useState(false);
	const [analysisResult, setAnalysisResult] =
		useState<WorkspaceAnalysisResponse | null>(null);

	// Create repo state
	const [showCreateRepo, setShowCreateRepo] = useState(false);
	const [newRepoName, setNewRepoName] = useState("");
	const [newRepoDescription, setNewRepoDescription] = useState("");
	const [newRepoPrivate, setNewRepoPrivate] = useState(true);
	const [creatingRepo, setCreatingRepo] = useState(false);

	// Disconnect confirmation state
	const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

	// Load current GitHub configuration
	const { data: configData, isLoading: configLoading } = useGitHubConfig();

	// Mutations
	const configureMutation = useConfigureGitHub();
	const analyzeMutation = useAnalyzeWorkspace();
	const createRepoMutation = useCreateGitHubRepository();
	const disconnectMutation = useDisconnectGitHub();

	// Track the saved token for use in configuration
	const [savedToken, setSavedToken] = useState<string | null>(null);

	// Update local state when config data loads
	useEffect(() => {
		if (configData) {
			setConfig(configData);

			// If token is saved, load repositories automatically
			if (configData.token_saved && !configData.configured) {
				setTokenValid(true);
				// Repositories will be loaded via validateToken if needed
			}
		}
	}, [configData]);

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
			setRepositories([...repositories, newRepo as unknown as GitHubRepoInfo]);
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

	// Analyze workspace before saving
	const handleAnalyzeAndConfigure = async () => {
		// Token must be saved to configure
		if (!config?.token_saved && !savedToken) {
			toast.error("Please validate your token first");
			return;
		}

		if (!selectedRepo) {
			toast.error("Please select a repository");
			return;
		}

		setAnalyzing(true);
		try {
			const analysis = await analyzeMutation.mutateAsync({
				body: {
					repo_url: selectedRepo,
					branch: selectedBranch,
					auth_token: savedToken || "",
				},
			});

			setAnalysisResult(analysis);

			if (analysis.requires_confirmation) {
				// Show warning dialog
				setShowConflictModal(true);
			} else {
				// No confirmation needed, proceed directly
				await handleSaveConfig();
			}
		} catch (error) {
			toast.error("Failed to analyze workspace", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setAnalyzing(false);
		}
	};

	// Save configuration (always replaces workspace with remote)
	const handleSaveConfig = async () => {
		setSaving(true);
		setShowConflictModal(false);

		try {
			const updated = await configureMutation.mutateAsync({
				body: {
					repo_url: selectedRepo,
					branch: selectedBranch,
					auth_token: savedToken || "",
				},
			});

			setConfig(updated);

			const successMessage = updated.backup_path
				? `Workspace replaced with repository content. Backup saved to: ${updated.backup_path}`
				: "GitHub integration configured successfully";

			toast.success("GitHub integration configured", {
				description: successMessage,
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
									onClick={handleAnalyzeAndConfigure}
									disabled={
										saving ||
										analyzing ||
										!selectedRepo ||
										(!config?.token_saved &&
											!token.trim()) ||
										(!config?.token_saved &&
											tokenValid !== true)
									}
								>
									{saving || analyzing ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											{analyzing
												? "Analyzing..."
												: "Configuring..."}
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

			{/* Warning Dialog - Workspace will be replaced */}
			<Dialog
				open={showConflictModal}
				onOpenChange={setShowConflictModal}
			>
				<DialogContent className="max-w-md">
					<DialogHeader>
						<DialogTitle className="flex items-center gap-2 text-amber-600">
							<AlertCircle className="h-5 w-5" />
							Replace Workspace Contents
						</DialogTitle>
						<DialogDescription className="space-y-3">
							<p>
								Your workspace contains{" "}
								<strong>
									{analysisResult?.file_count || 0} files
								</strong>
								. These will be replaced with the contents of
								the GitHub repository.
							</p>
							<div className="rounded-lg bg-muted p-3 space-y-2 text-sm">
								<p className="font-medium text-foreground">
									What will happen:
								</p>
								<ul className="list-disc list-inside space-y-1 ml-2">
									<li>
										A backup will be created automatically
									</li>
									<li>
										Your workspace files will be removed
									</li>
									<li>Repository contents will be cloned</li>
									<li>
										Requirements will be installed
										automatically
									</li>
								</ul>
							</div>
							<p className="text-xs">
								<strong>Tip:</strong> If you want to keep your
								current files in GitHub, push them to the
								repository first before configuring this
								integration.
							</p>
						</DialogDescription>
					</DialogHeader>

					<DialogFooter className="flex-col sm:flex-row gap-2">
						<Button
							variant="outline"
							onClick={() => setShowConflictModal(false)}
							disabled={saving}
							className="w-full sm:w-auto"
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={handleSaveConfig}
							disabled={saving}
							className="w-full sm:w-auto"
						>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Replacing...
								</>
							) : (
								<>
									<AlertCircle className="h-4 w-4 mr-2" />
									Replace Workspace
								</>
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

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
		</div>
	);
}
