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
import { Switch } from "@/components/ui/switch";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
	Loader2,
	Key,
	Plus,
	Copy,
	Trash2,
	Code,
	Download,
	ExternalLink,
	AlertCircle,
} from "lucide-react";
import {
	sdkService,
	type DeveloperContext,
	type DeveloperApiKey,
	type CreateApiKeyResponse,
} from "@/services/sdk";
import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

export function DeveloperSettings() {
	const [_context, setContext] = useState<DeveloperContext | null>(null);
	const [apiKeys, setApiKeys] = useState<DeveloperApiKey[]>([]);
	const [organizations, setOrganizations] = useState<Organization[]>([]);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);

	// Create key dialog state
	const [showCreateKey, setShowCreateKey] = useState(false);
	const [newKeyName, setNewKeyName] = useState("");
	const [newKeyExpiry, setNewKeyExpiry] = useState<string>("never");
	const [creatingKey, setCreatingKey] = useState(false);
	const [createdKey, setCreatedKey] = useState<CreateApiKeyResponse | null>(
		null,
	);

	// Revoke key dialog state
	const [keyToRevoke, setKeyToRevoke] = useState<DeveloperApiKey | null>(
		null,
	);
	const [revoking, setRevoking] = useState(false);

	// Form state
	const [selectedOrg, setSelectedOrg] = useState<string>("");
	const [trackExecutions, setTrackExecutions] = useState(true);

	// Load data
	useEffect(() => {
		async function loadData() {
			try {
				const [contextData, keysData, orgsResult] = await Promise.all([
					sdkService.getContext(),
					sdkService.listApiKeys(),
					apiClient.GET("/api/organizations"),
				]);
				const orgsData = orgsResult.data ?? [];

				setContext(contextData);
				setApiKeys(keysData);
				setOrganizations(orgsData);

				// Set form defaults
				setSelectedOrg(contextData.organization?.id || "");
				setTrackExecutions(contextData.track_executions);
			} catch (error) {
				console.error("Failed to load developer settings:", error);
				toast.error("Failed to load developer settings");
			} finally {
				setLoading(false);
			}
		}

		loadData();
	}, []);

	// Save context settings
	const handleSaveContext = async () => {
		setSaving(true);
		try {
			const updated = await sdkService.updateContext({
				default_org_id: selectedOrg || null,
				track_executions: trackExecutions,
			});
			setContext(updated);
			toast.success("Developer settings saved");
		} catch (error) {
			console.error("Failed to save settings:", error);
			toast.error("Failed to save settings");
		} finally {
			setSaving(false);
		}
	};

	// Create API key
	const handleCreateKey = async () => {
		if (!newKeyName.trim()) {
			toast.error("Please enter a key name");
			return;
		}

		setCreatingKey(true);
		try {
			const expiryDays =
				newKeyExpiry === "never"
					? null
					: newKeyExpiry === "30"
						? 30
						: newKeyExpiry === "90"
							? 90
							: newKeyExpiry === "365"
								? 365
								: null;

			const result = await sdkService.createApiKey({
				name: newKeyName,
				expires_in_days: expiryDays,
			});

			setCreatedKey(result);

			// Refresh keys list
			const keys = await sdkService.listApiKeys();
			setApiKeys(keys);
		} catch (error) {
			console.error("Failed to create API key:", error);
			toast.error("Failed to create API key");
		} finally {
			setCreatingKey(false);
		}
	};

	// Copy key to clipboard
	const handleCopyKey = async (key: string) => {
		await navigator.clipboard.writeText(key);
		toast.success("API key copied to clipboard");
	};

	// Revoke API key
	const handleRevokeKey = async () => {
		if (!keyToRevoke) return;

		setRevoking(true);
		try {
			await sdkService.revokeApiKey(keyToRevoke.id);
			setApiKeys((keys) => keys.filter((k) => k.id !== keyToRevoke.id));
			setKeyToRevoke(null);
			toast.success("API key revoked");
		} catch (error) {
			console.error("Failed to revoke API key:", error);
			toast.error("Failed to revoke API key");
		} finally {
			setRevoking(false);
		}
	};

	// Close create dialog and reset
	const handleCloseCreateDialog = () => {
		setShowCreateKey(false);
		setNewKeyName("");
		setNewKeyExpiry("never");
		setCreatedKey(null);
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			{/* SDK Setup Instructions */}
			<Card>
				<CardHeader>
					<div className="flex items-center gap-2">
						<Code className="h-5 w-5" />
						<CardTitle>
							Local Development with Bifrost SDK
						</CardTitle>
					</div>
					<CardDescription>
						Develop and test workflows locally using VS Code or your
						preferred IDE
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="rounded-lg border bg-muted/50 p-4 space-y-3">
						<p className="font-medium">Quick Start</p>
						<div className="space-y-2 text-sm">
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									1
								</span>
								<div>
									<p>Install the SDK:</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										pip install {window.location.origin}
										/api/sdk/download
									</code>
								</div>
							</div>
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									2
								</span>
								<div>
									<p>
										Create an API key below and set
										environment variables:
									</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										export BIFROST_DEV_URL="
										{window.location.origin}"
										<br />
										export BIFROST_DEV_KEY="your-api-key"
									</code>
								</div>
							</div>
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									3
								</span>
								<div>
									<p>Run your workflow:</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										bifrost run my_workflow.py
									</code>
								</div>
							</div>
						</div>
					</div>

					<div className="flex gap-2">
						<Button variant="outline" asChild>
							<a href={sdkService.getSdkDownloadUrl()} download>
								<Download className="h-4 w-4 mr-2" />
								Download SDK
							</a>
						</Button>
						<Button variant="outline" asChild>
							<a
								href="https://docs.bifrost.io/sdk"
								target="_blank"
								rel="noopener noreferrer"
							>
								<ExternalLink className="h-4 w-4 mr-2" />
								Documentation
							</a>
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* API Keys */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-2">
							<Key className="h-5 w-5" />
							<CardTitle>API Keys</CardTitle>
						</div>
						<Button onClick={() => setShowCreateKey(true)}>
							<Plus className="h-4 w-4 mr-2" />
							Create Key
						</Button>
					</div>
					<CardDescription>
						API keys authenticate your local SDK with Bifrost
					</CardDescription>
				</CardHeader>
				<CardContent>
					{apiKeys.length === 0 ? (
						<div className="text-center py-8 text-muted-foreground">
							<Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
							<p>No API keys yet</p>
							<p className="text-sm">
								Create an API key to start developing locally
							</p>
						</div>
					) : (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Name</TableHead>
									<TableHead>Key</TableHead>
									<TableHead>Created</TableHead>
									<TableHead>Last Used</TableHead>
									<TableHead>Expires</TableHead>
									<TableHead className="w-[50px]"></TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{apiKeys.map((key) => (
									<TableRow key={key.id}>
										<TableCell className="font-medium">
											{key.name}
										</TableCell>
										<TableCell>
											<code className="text-xs bg-muted px-2 py-1 rounded">
												{key.key_prefix}...
											</code>
										</TableCell>
										<TableCell className="text-muted-foreground">
											{new Date(
												key.created_at,
											).toLocaleDateString()}
										</TableCell>
										<TableCell className="text-muted-foreground">
											{key.last_used_at
												? new Date(
														key.last_used_at,
													).toLocaleDateString()
												: "Never"}
										</TableCell>
										<TableCell className="text-muted-foreground">
											{key.expires_at
												? new Date(
														key.expires_at,
													).toLocaleDateString()
												: "Never"}
										</TableCell>
										<TableCell>
											<Button
												variant="ghost"
												size="icon"
												onClick={() =>
													setKeyToRevoke(key)
												}
											>
												<Trash2 className="h-4 w-4 text-destructive" />
											</Button>
										</TableCell>
									</TableRow>
								))}
							</TableBody>
						</Table>
					)}
				</CardContent>
			</Card>

			{/* Developer Context Settings */}
			<Card>
				<CardHeader>
					<CardTitle>Developer Context</CardTitle>
					<CardDescription>
						Configure default settings for local SDK development
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="space-y-2">
						<Label htmlFor="default-org">
							Default Organization
						</Label>
						<Select
							value={selectedOrg}
							onValueChange={setSelectedOrg}
						>
							<SelectTrigger id="default-org">
								<SelectValue placeholder="Select organization" />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="">
									None (personal)
								</SelectItem>
								{organizations.map((org) => (
									<SelectItem key={org.id} value={org.id}>
										{org.name}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
						<p className="text-xs text-muted-foreground">
							Organization context for workflow executions run
							from the SDK
						</p>
					</div>

					<div className="flex items-center justify-between">
						<div className="space-y-0.5">
							<Label htmlFor="track-executions">
								Track Executions
							</Label>
							<p className="text-xs text-muted-foreground">
								Log SDK executions in the Executions panel
							</p>
						</div>
						<Switch
							id="track-executions"
							checked={trackExecutions}
							onCheckedChange={setTrackExecutions}
						/>
					</div>

					<div className="flex justify-end">
						<Button onClick={handleSaveContext} disabled={saving}>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : (
								"Save Settings"
							)}
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Create Key Dialog */}
			<Dialog open={showCreateKey} onOpenChange={handleCloseCreateDialog}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>
							{createdKey ? "API Key Created" : "Create API Key"}
						</DialogTitle>
						<DialogDescription>
							{createdKey
								? "Copy your API key now. You won't be able to see it again."
								: "Create a new API key for local development"}
						</DialogDescription>
					</DialogHeader>

					{createdKey ? (
						<div className="space-y-4">
							<div className="rounded-lg border bg-amber-50 dark:bg-amber-950/30 p-4">
								<div className="flex items-start gap-2">
									<AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0" />
									<div className="space-y-2">
										<p className="text-sm font-medium text-amber-800 dark:text-amber-200">
											Save this key securely
										</p>
										<p className="text-xs text-amber-700 dark:text-amber-300">
											This is the only time you'll see
											this API key. Store it securely.
										</p>
									</div>
								</div>
							</div>

							<div className="space-y-2">
								<Label>API Key</Label>
								<div className="flex gap-2">
									<Input
										value={createdKey.key}
										readOnly
										className="font-mono text-sm"
									/>
									<Button
										variant="outline"
										size="icon"
										onClick={() =>
											handleCopyKey(createdKey.key)
										}
									>
										<Copy className="h-4 w-4" />
									</Button>
								</div>
							</div>

							<div className="rounded-lg bg-muted p-3 space-y-2 text-sm">
								<p className="font-medium">
									Set in your environment:
								</p>
								<code className="block text-xs">
									export BIFROST_DEV_KEY="{createdKey.key}"
								</code>
							</div>
						</div>
					) : (
						<div className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="key-name">Key Name</Label>
								<Input
									id="key-name"
									placeholder="e.g., MacBook Pro, CI/CD"
									value={newKeyName}
									onChange={(e) =>
										setNewKeyName(e.target.value)
									}
								/>
								<p className="text-xs text-muted-foreground">
									A descriptive name to identify this key
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="key-expiry">Expiration</Label>
								<Select
									value={newKeyExpiry}
									onValueChange={setNewKeyExpiry}
								>
									<SelectTrigger id="key-expiry">
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="never">
											Never expires
										</SelectItem>
										<SelectItem value="30">
											30 days
										</SelectItem>
										<SelectItem value="90">
											90 days
										</SelectItem>
										<SelectItem value="365">
											1 year
										</SelectItem>
									</SelectContent>
								</Select>
							</div>
						</div>
					)}

					<DialogFooter>
						{createdKey ? (
							<Button onClick={handleCloseCreateDialog}>
								Done
							</Button>
						) : (
							<>
								<Button
									variant="outline"
									onClick={handleCloseCreateDialog}
									disabled={creatingKey}
								>
									Cancel
								</Button>
								<Button
									onClick={handleCreateKey}
									disabled={!newKeyName.trim() || creatingKey}
								>
									{creatingKey ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											Creating...
										</>
									) : (
										"Create Key"
									)}
								</Button>
							</>
						)}
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Revoke Key Confirmation */}
			<Dialog
				open={!!keyToRevoke}
				onOpenChange={(open) => !open && setKeyToRevoke(null)}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Revoke API Key</DialogTitle>
						<DialogDescription>
							Are you sure you want to revoke "{keyToRevoke?.name}
							"? This action cannot be undone and any applications
							using this key will stop working.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setKeyToRevoke(null)}
							disabled={revoking}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={handleRevokeKey}
							disabled={revoking}
						>
							{revoking ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Revoking...
								</>
							) : (
								"Revoke Key"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
