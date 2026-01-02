/**
 * LLM Configuration Settings
 *
 * Configure the AI provider (OpenAI, Anthropic, or custom) for chat functionality.
 * Flow: Provider → Endpoint (if custom) → API Key → Test → Model (loaded dynamically)
 */

import { useState, useEffect, useRef } from "react";
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
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
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
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
	Loader2,
	Bot,
	CheckCircle2,
	AlertCircle,
	Trash2,
	Zap,
	Database,
	DollarSign,
	Plus,
	Pencil,
	X,
	Check,
	Code,
	ArrowRight,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { $api } from "@/lib/api-client";
import {
	listPricing,
	createPricing,
	updatePricing,
	deletePricing,
	type AIModelPricingListItem,
	type AIModelPricingCreate,
} from "@/services/ai-pricing";

type Provider = "openai" | "anthropic" | "custom";

// Model info with both ID and display name
interface ModelInfo {
	id: string;
	display_name: string;
}

// Default models for each provider (fallback if API doesn't return models)
const DEFAULT_MODELS: Record<Provider, string> = {
	openai: "gpt-4o",
	anthropic: "claude-sonnet-4-20250514",
	custom: "",
};

export function LLMConfig() {
	// Form state
	const [provider, setProvider] = useState<Provider>("openai");
	const [model, setModel] = useState(DEFAULT_MODELS.openai);
	const [apiKey, setApiKey] = useState("");
	const [endpoint, setEndpoint] = useState("");
	const [maxTokens, setMaxTokens] = useState(4096);
	const [temperature, setTemperature] = useState(0.7);
	const [defaultSystemPrompt, setDefaultSystemPrompt] = useState("");

	// Models state (loaded dynamically after test)
	const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
	const [modelsLoaded, setModelsLoaded] = useState(false);

	// UI state
	const [saving, setSaving] = useState(false);
	const [testing, setTesting] = useState(false);
	const [testResult, setTestResult] = useState<{
		success: boolean;
		message: string;
	} | null>(null);
	const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

	// Load current configuration
	const {
		data: config,
		isLoading: configLoading,
		refetch,
	} = $api.useQuery("get", "/api/admin/llm/config", undefined, {
		staleTime: 5 * 60 * 1000,
	});

	// Mutations
	const saveMutation = $api.useMutation("post", "/api/admin/llm/config");
	const deleteMutation = $api.useMutation("delete", "/api/admin/llm/config");
	const testMutation = $api.useMutation("post", "/api/admin/llm/test");
	const testSavedMutation = $api.useMutation(
		"post",
		"/api/admin/llm/test-saved",
	);

	// Update form when config loads
	useEffect(() => {
		if (config) {
			setProvider(config.provider);
			setModel(config.model);
			setMaxTokens(config.max_tokens);
			setTemperature(config.temperature);
			setDefaultSystemPrompt(config.default_system_prompt ?? "");
			if (config.endpoint) {
				setEndpoint(config.endpoint);
			}
		}
	}, [config]);

	// Track if we've already fetched models for this config
	const modelsFetchedRef = useRef(false);

	// Fetch available models when config has an API key set
	useEffect(() => {
		if (!config?.api_key_set || modelsFetchedRef.current) {
			return;
		}

		const fetchModels = async () => {
			modelsFetchedRef.current = true;
			try {
				const result = await testSavedMutation.mutateAsync({});
				if (
					result.success &&
					result.models &&
					result.models.length > 0
				) {
					// Cast to ModelInfo[] since API now returns objects
					const models = result.models as unknown as ModelInfo[];
					setAvailableModels(models);
				}
				setModelsLoaded(true);
			} catch {
				// Silently fail - user can still manually test
				setModelsLoaded(true);
			}
		};

		fetchModels();
	}, [config?.api_key_set, testSavedMutation]);

	// Handle provider change
	const handleProviderChange = (newProvider: Provider) => {
		setProvider(newProvider);
		setModel(DEFAULT_MODELS[newProvider]);
		setTestResult(null);
		setAvailableModels([]);
		setModelsLoaded(false);
		// Clear endpoint if not custom
		if (newProvider !== "custom") {
			setEndpoint("");
		}
	};

	// Test connection with current form values
	const handleTestConnection = async () => {
		if (!apiKey && !config?.api_key_set) {
			toast.error("Please enter an API key");
			return;
		}

		if (provider === "custom" && !endpoint) {
			toast.error("Please enter an endpoint URL for custom provider");
			return;
		}

		setTesting(true);
		setTestResult(null);

		try {
			let result;
			// If we have a new API key, test with that
			if (apiKey) {
				result = await testMutation.mutateAsync({
					body: {
						provider,
						model: model || DEFAULT_MODELS[provider],
						api_key: apiKey,
						endpoint: provider === "custom" ? endpoint : undefined,
					},
				});
			} else {
				// Test saved configuration
				result = await testSavedMutation.mutateAsync({});
			}

			setTestResult({ success: result.success, message: result.message });

			if (result.success) {
				toast.success("Connection successful", {
					description: result.message,
				});
				// Load models from response
				if (result.models && result.models.length > 0) {
					// Cast to ModelInfo[] since API now returns objects
					const models = result.models as unknown as ModelInfo[];
					setAvailableModels(models);
					// If current model is not in list, select first available
					const modelIds = models.map((m) => m.id);
					if (!modelIds.includes(model)) {
						setModel(models[0].id);
					}
				}
				setModelsLoaded(true);
			} else {
				toast.error("Connection failed", {
					description: result.message,
				});
				setModelsLoaded(false);
			}
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "Unknown error";
			setTestResult({ success: false, message });
			toast.error("Connection test failed", { description: message });
			setModelsLoaded(false);
		} finally {
			setTesting(false);
		}
	};

	// Save configuration
	const handleSave = async () => {
		if (!apiKey && !config?.api_key_set) {
			toast.error("Please enter an API key");
			return;
		}

		if (provider === "custom" && !endpoint) {
			toast.error("Please enter an endpoint URL for custom provider");
			return;
		}

		if (!model) {
			toast.error("Please select a model");
			return;
		}

		setSaving(true);
		try {
			await saveMutation.mutateAsync({
				body: {
					provider,
					model,
					api_key: apiKey || "unchanged", // Backend handles "unchanged" specially if key already set
					endpoint: provider === "custom" ? endpoint : undefined,
					max_tokens: maxTokens,
					temperature,
					default_system_prompt: defaultSystemPrompt || null,
				},
			});

			toast.success("Configuration saved", {
				description: `Using ${provider} with model ${model}`,
			});

			// Clear API key field (it's saved now)
			setApiKey("");
			setTestResult(null);

			// Refetch to get updated config
			refetch();
		} catch (error) {
			toast.error("Failed to save configuration", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Delete configuration
	const handleDelete = async () => {
		setSaving(true);
		setShowDeleteConfirm(false);

		try {
			await deleteMutation.mutateAsync({});

			// Reset form
			setProvider("openai");
			setModel(DEFAULT_MODELS.openai);
			setApiKey("");
			setEndpoint("");
			setMaxTokens(4096);
			setTemperature(0.7);
			setDefaultSystemPrompt("");
			setTestResult(null);
			setAvailableModels([]);
			setModelsLoaded(false);

			toast.success("Configuration deleted", {
				description: "AI chat is now disabled",
			});

			refetch();
		} catch (error) {
			toast.error("Failed to delete configuration", {
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

	// Check if we can show model selection
	const canSelectModel = modelsLoaded || config?.api_key_set;
	const hasModels = availableModels.length > 0;

	// Determine if we can save:
	// - If entering new API key: must be tested successfully
	// - If using existing config: must have modelsLoaded (via test) or unchanged config
	const isNewApiKey = apiKey.length > 0;
	const isVerified = testResult?.success === true;
	const hasValidConfig = config?.api_key_set && !isNewApiKey;
	const canSave =
		!saving &&
		model &&
		(provider !== "custom" || endpoint) &&
		(isVerified || hasValidConfig);

	return (
		<div className="space-y-6">
			<Card>
				<CardHeader>
					<div className="flex items-center gap-2">
						<Bot className="h-5 w-5" />
						<CardTitle>AI Provider Configuration</CardTitle>
					</div>
					<CardDescription>
						Configure the LLM provider for AI chat functionality.
						This enables the Chat feature across the platform.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{/* Status Banner */}
					{config?.is_configured ? (
						<div className="rounded-lg border bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900 p-4">
							<div className="flex items-center justify-between">
								<div className="flex items-center gap-2">
									<CheckCircle2 className="h-4 w-4 text-green-600" />
									<span className="text-sm font-medium text-green-800 dark:text-green-200">
										AI Chat Enabled
									</span>
								</div>
								<Button
									variant="ghost"
									size="sm"
									onClick={() => setShowDeleteConfirm(true)}
									className="text-destructive hover:text-destructive"
								>
									<Trash2 className="h-4 w-4 mr-1" />
									Remove
								</Button>
							</div>
							<p className="mt-1 text-sm text-green-700 dark:text-green-300">
								Using {config.provider} with model{" "}
								{config.model}
							</p>
						</div>
					) : (
						<div className="rounded-lg border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900 p-4">
							<div className="flex items-center gap-2">
								<AlertCircle className="h-4 w-4 text-amber-600" />
								<span className="text-sm font-medium text-amber-800 dark:text-amber-200">
									AI Chat Not Configured
								</span>
							</div>
							<p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
								Configure a provider below to enable AI chat
								functionality.
							</p>
						</div>
					)}

					{/* Provider Selection */}
					<div className="space-y-2">
						<Label htmlFor="provider">Provider</Label>
						<Select
							value={provider}
							onValueChange={handleProviderChange}
						>
							<SelectTrigger id="provider">
								<SelectValue placeholder="Select provider" />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="openai">OpenAI</SelectItem>
								<SelectItem value="anthropic">
									Anthropic
								</SelectItem>
								<SelectItem value="custom">
									Custom (OpenAI-compatible)
								</SelectItem>
							</SelectContent>
						</Select>
					</div>

					{/* Custom Endpoint (only for custom provider) */}
					{provider === "custom" && (
						<div className="space-y-2">
							<Label htmlFor="endpoint">API Endpoint</Label>
							<Input
								id="endpoint"
								placeholder="https://api.example.com/v1"
								value={endpoint}
								onChange={(e) => setEndpoint(e.target.value)}
							/>
							<p className="text-xs text-muted-foreground">
								Must be OpenAI-compatible API endpoint
							</p>
						</div>
					)}

					{/* API Key */}
					<div className="space-y-2">
						<Label htmlFor="api-key">API Key</Label>
						<div className="flex gap-2">
							<Input
								id="api-key"
								type="password"
								autoComplete="off"
								placeholder={
									config?.api_key_set
										? "API key saved - enter new key to change"
										: provider === "openai"
											? "sk-..."
											: provider === "anthropic"
												? "sk-ant-..."
												: "Enter API key"
								}
								value={apiKey}
								onChange={(e) => {
									setApiKey(e.target.value);
									setTestResult(null);
									// Reset models when key changes
									if (e.target.value !== "") {
										setModelsLoaded(false);
										setAvailableModels([]);
									}
								}}
							/>
							<Button
								variant="secondary"
								onClick={handleTestConnection}
								disabled={
									testing || (!apiKey && !config?.api_key_set)
								}
							>
								{testing ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Testing...
									</>
								) : testResult?.success ? (
									<>
										<CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />
										Verified
									</>
								) : testResult?.success === false ? (
									<>
										<AlertCircle className="h-4 w-4 mr-2 text-destructive" />
										Failed
									</>
								) : (
									<>
										<Zap className="h-4 w-4 mr-2" />
										Test
									</>
								)}
							</Button>
						</div>
						{provider === "openai" && (
							<p className="text-xs text-muted-foreground">
								Get your API key from{" "}
								<a
									href="https://platform.openai.com/api-keys"
									target="_blank"
									rel="noopener noreferrer"
									className="underline hover:text-foreground"
								>
									platform.openai.com
								</a>
							</p>
						)}
						{provider === "anthropic" && (
							<p className="text-xs text-muted-foreground">
								Get your API key from{" "}
								<a
									href="https://console.anthropic.com/settings/keys"
									target="_blank"
									rel="noopener noreferrer"
									className="underline hover:text-foreground"
								>
									console.anthropic.com
								</a>
							</p>
						)}
					</div>

					{/* Model Selection (only after successful test) */}
					<div className="space-y-2">
						<Label htmlFor="model">
							Model
							{!canSelectModel && (
								<span className="text-muted-foreground font-normal ml-2">
									(test API key first)
								</span>
							)}
						</Label>
						{canSelectModel ? (
							hasModels ? (
								<Select value={model} onValueChange={setModel}>
									<SelectTrigger id="model">
										<SelectValue placeholder="Select model">
											{/* Show display name in trigger if we have model info */}
											{availableModels.find(
												(m) => m.id === model,
											)?.display_name || model}
										</SelectValue>
									</SelectTrigger>
									<SelectContent>
										{availableModels.map((m) => (
											<SelectItem key={m.id} value={m.id}>
												<div className="flex flex-col">
													<span>
														{m.display_name}
													</span>
													<span className="text-xs text-muted-foreground">
														{m.id}
													</span>
												</div>
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							) : (
								<Input
									id="model"
									placeholder="Enter model identifier"
									value={model}
									onChange={(e) => setModel(e.target.value)}
								/>
							)
						) : (
							<Input
								id="model"
								placeholder="Test API key to load available models"
								disabled
								value=""
							/>
						)}
					</div>

					{/* Advanced Settings */}
					<div className="space-y-4 pt-4 border-t">
						<h4 className="text-sm font-medium">
							Advanced Settings
						</h4>

						{/* Max Tokens */}
						<div className="space-y-3">
							<div className="flex items-center justify-between">
								<Label htmlFor="max-tokens">Max Tokens</Label>
								<span className="text-sm text-muted-foreground">
									{maxTokens.toLocaleString()}
								</span>
							</div>
							<Slider
								id="max-tokens"
								min={256}
								max={32768}
								step={256}
								value={[maxTokens]}
								onValueChange={(values: number[]) =>
									setMaxTokens(values[0])
								}
							/>
							<p className="text-xs text-muted-foreground">
								Maximum tokens in the response (higher = longer
								responses)
							</p>
						</div>

						{/* Temperature */}
						<div className="space-y-3">
							<div className="flex items-center justify-between">
								<Label htmlFor="temperature">Temperature</Label>
								<span className="text-sm text-muted-foreground">
									{temperature.toFixed(1)}
								</span>
							</div>
							<Slider
								id="temperature"
								min={0}
								max={2}
								step={0.1}
								value={[temperature]}
								onValueChange={(values: number[]) =>
									setTemperature(values[0])
								}
							/>
							<p className="text-xs text-muted-foreground">
								Controls randomness (0 = deterministic, 2 =
								creative)
							</p>
						</div>

						{/* Default System Prompt */}
						<div className="space-y-2">
							<Label htmlFor="default-system-prompt">
								Default System Prompt
							</Label>
							<Textarea
								id="default-system-prompt"
								placeholder="You are a helpful AI assistant..."
								value={defaultSystemPrompt}
								onChange={(e) =>
									setDefaultSystemPrompt(e.target.value)
								}
								rows={4}
								className="font-mono text-sm resize-none"
							/>
							<p className="text-xs text-muted-foreground">
								System prompt used when chatting without a
								specific agent. Leave empty to use the built-in
								default.
							</p>
						</div>
					</div>

					{/* Save Button */}
					<div className="flex flex-col items-end gap-2 pt-4">
						{!canSave && isNewApiKey && !isVerified && (
							<p className="text-xs text-muted-foreground">
								Test your API key before saving
							</p>
						)}
						<Button onClick={handleSave} disabled={!canSave}>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : (
								"Save Configuration"
							)}
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Embedding Configuration Card */}
			<EmbeddingConfigCard llmProvider={config?.provider} />

			{/* Coding Mode Configuration Card */}
			<CodingConfigCard
				availableModels={availableModels}
				llmProvider={config?.provider}
			/>

			{/* Model Pricing Card */}
			<ModelPricingCard />

			{/* Info Card */}
			<Card>
				<CardHeader>
					<CardTitle className="text-base">About AI Chat</CardTitle>
				</CardHeader>
				<CardContent className="space-y-2 text-sm text-muted-foreground">
					<p>
						Once configured, AI chat will be available to users
						through the Chat page:
					</p>
					<ul className="list-disc list-inside space-y-1 ml-2">
						<li>
							Users can have conversations with the AI assistant
						</li>
						<li>
							Conversations are saved and can be continued later
						</li>
						<li>
							Agents can be configured to provide specialized
							assistance
						</li>
						<li>Token usage is tracked per conversation</li>
					</ul>
				</CardContent>
			</Card>

			{/* Delete Confirmation Dialog */}
			<Dialog
				open={showDeleteConfirm}
				onOpenChange={setShowDeleteConfirm}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Remove AI Configuration</DialogTitle>
						<DialogDescription>
							Are you sure you want to remove the AI provider
							configuration? This will disable AI chat
							functionality until reconfigured.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setShowDeleteConfirm(false)}
							disabled={saving}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={handleDelete}
							disabled={saving}
						>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Removing...
								</>
							) : (
								"Remove Configuration"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}

/**
 * Embedding Configuration Component
 *
 * Separate configuration for embeddings (used by Knowledge Store/RAG).
 * If using Anthropic as LLM provider, a dedicated OpenAI API key is required
 * since Anthropic doesn't provide embeddings.
 */
function EmbeddingConfigCard({ llmProvider }: { llmProvider?: string }) {
	const navigate = useNavigate();
	const [apiKey, setApiKey] = useState("");
	const [model, setModel] = useState("text-embedding-3-small");
	const [dimensions, setDimensions] = useState(1536);
	const [saving, setSaving] = useState(false);
	const [testing, setTesting] = useState(false);
	const [testResult, setTestResult] = useState<{
		success: boolean;
		message: string;
	} | null>(null);
	const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

	// Load current embedding configuration
	const {
		data: config,
		isLoading,
		refetch,
	} = $api.useQuery("get", "/api/admin/llm/embedding-config", undefined, {
		staleTime: 5 * 60 * 1000,
	});

	// Mutations
	const saveMutation = $api.useMutation(
		"post",
		"/api/admin/llm/embedding-config",
	);
	const deleteMutation = $api.useMutation(
		"delete",
		"/api/admin/llm/embedding-config",
	);
	const testMutation = $api.useMutation(
		"post",
		"/api/admin/llm/embedding-test",
	);

	// Determine if dedicated config is needed
	const needsDedicatedKey = llmProvider === "anthropic";

	// Test connection
	const handleTest = async () => {
		if (!apiKey && !config?.api_key_set) {
			toast.error("Please enter an API key");
			return;
		}

		setTesting(true);
		setTestResult(null);

		try {
			const result = await testMutation.mutateAsync({
				body: {
					api_key: apiKey || "use-saved",
					model,
					dimensions,
				},
			});

			setTestResult({ success: result.success, message: result.message });

			if (result.success) {
				toast.success("Embedding connection successful", {
					description: `Dimensions: ${result.dimensions}`,
				});
			} else {
				toast.error("Embedding test failed", {
					description: result.message,
				});
			}
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "Unknown error";
			setTestResult({ success: false, message });
			toast.error("Embedding test failed", { description: message });
		} finally {
			setTesting(false);
		}
	};

	// Save configuration
	const handleSave = async () => {
		if (!apiKey && !config?.api_key_set) {
			toast.error("Please enter an API key");
			return;
		}

		setSaving(true);
		try {
			await saveMutation.mutateAsync({
				body: {
					api_key: apiKey || "unchanged",
					model,
					dimensions,
				},
			});

			toast.success("Embedding configuration saved");
			setApiKey("");
			setTestResult(null);
			refetch();
		} catch (error) {
			toast.error("Failed to save embedding configuration", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Delete configuration
	const handleDelete = async () => {
		setSaving(true);
		setShowDeleteConfirm(false);

		try {
			await deleteMutation.mutateAsync({});
			setApiKey("");
			setModel("text-embedding-3-small");
			setDimensions(1536);
			setTestResult(null);
			toast.success("Embedding configuration removed");
			refetch();
		} catch (error) {
			toast.error("Failed to remove embedding configuration", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	if (isLoading) {
		return (
			<Card>
				<CardContent className="flex items-center justify-center py-8">
					<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
				</CardContent>
			</Card>
		);
	}

	const isVerified = testResult?.success === true;
	const hasValidConfig = config?.api_key_set && !apiKey;
	const canSave = !saving && (isVerified || hasValidConfig);

	return (
		<Card>
			<CardHeader>
				<div className="flex items-center gap-2">
					<Database className="h-5 w-5" />
					<CardTitle>Embedding Configuration</CardTitle>
				</div>
				<CardDescription>
					Configure OpenAI embeddings for the Knowledge Store (RAG).
					{needsDedicatedKey && (
						<span className="block mt-1 text-amber-600 dark:text-amber-400">
							Anthropic doesn't provide embeddings - a dedicated
							OpenAI key is required.
						</span>
					)}
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{/* Status Banner */}
				{config?.is_configured ? (
					<div className="rounded-lg border bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900 p-4">
						<div className="flex items-center justify-between">
							<div className="flex items-center gap-2">
								<CheckCircle2 className="h-4 w-4 text-green-600" />
								<span className="text-sm font-medium text-green-800 dark:text-green-200">
									Embeddings Configured
								</span>
							</div>
							<div className="flex items-center gap-2">
								<Button
									variant="outline"
									size="sm"
									onClick={() => navigate("/settings/maintenance")}
								>
									Index Docs
									<ArrowRight className="h-4 w-4 ml-1" />
								</Button>
								{!config.uses_llm_key && (
									<Button
										variant="ghost"
										size="sm"
										onClick={() => setShowDeleteConfirm(true)}
										className="text-destructive hover:text-destructive"
									>
										<Trash2 className="h-4 w-4 mr-1" />
										Remove
									</Button>
								)}
							</div>
						</div>
						<p className="mt-1 text-sm text-green-700 dark:text-green-300">
							{config.uses_llm_key
								? "Using LLM provider's OpenAI API key"
								: `Dedicated key configured (${config.model})`}
						</p>
					</div>
				) : (
					<div className="rounded-lg border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900 p-4">
						<div className="flex items-center gap-2">
							<AlertCircle className="h-4 w-4 text-amber-600" />
							<span className="text-sm font-medium text-amber-800 dark:text-amber-200">
								Embeddings Not Configured
							</span>
						</div>
						<p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
							Knowledge Store features require embedding
							configuration.
						</p>
					</div>
				)}

				{/* Only show form if dedicated config is needed or already set */}
				{(needsDedicatedKey || (config && !config.uses_llm_key)) && (
					<>
						{/* API Key */}
						<div className="space-y-2">
							<Label htmlFor="embedding-api-key">
								OpenAI API Key
							</Label>
							<div className="flex gap-2">
								<Input
									id="embedding-api-key"
									type="password"
									autoComplete="off"
									placeholder={
										config?.api_key_set
											? "API key saved - enter new key to change"
											: "sk-..."
									}
									value={apiKey}
									onChange={(e) => {
										setApiKey(e.target.value);
										setTestResult(null);
									}}
								/>
								<Button
									variant="secondary"
									onClick={handleTest}
									disabled={
										testing ||
										(!apiKey && !config?.api_key_set)
									}
								>
									{testing ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											Testing...
										</>
									) : testResult?.success ? (
										<>
											<CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />
											Verified
										</>
									) : testResult?.success === false ? (
										<>
											<AlertCircle className="h-4 w-4 mr-2 text-destructive" />
											Failed
										</>
									) : (
										<>
											<Zap className="h-4 w-4 mr-2" />
											Test
										</>
									)}
								</Button>
							</div>
						</div>

						{/* Model Selection */}
						<div className="space-y-2">
							<Label htmlFor="embedding-model">Model</Label>
							<Select value={model} onValueChange={setModel}>
								<SelectTrigger id="embedding-model">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="text-embedding-3-small">
										text-embedding-3-small (recommended)
									</SelectItem>
									<SelectItem value="text-embedding-3-large">
										text-embedding-3-large (higher quality)
									</SelectItem>
								</SelectContent>
							</Select>
						</div>

						{/* Dimensions */}
						<div className="space-y-2">
							<Label htmlFor="embedding-dimensions">
								Dimensions
							</Label>
							<Select
								value={dimensions.toString()}
								onValueChange={(v) =>
									setDimensions(parseInt(v))
								}
							>
								<SelectTrigger id="embedding-dimensions">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="512">512</SelectItem>
									<SelectItem value="1024">1024</SelectItem>
									<SelectItem value="1536">
										1536 (default)
									</SelectItem>
									{model === "text-embedding-3-large" && (
										<SelectItem value="3072">
											3072
										</SelectItem>
									)}
								</SelectContent>
							</Select>
							<p className="text-xs text-muted-foreground">
								Higher dimensions = better quality, more storage
							</p>
						</div>

						{/* Save Button */}
						<div className="flex justify-end pt-2">
							<Button onClick={handleSave} disabled={!canSave}>
								{saving ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Saving...
									</>
								) : (
									"Save Embedding Config"
								)}
							</Button>
						</div>
					</>
				)}

				{/* Info about fallback */}
				{config?.uses_llm_key && (
					<p className="text-sm text-muted-foreground">
						To use a separate API key for embeddings, configure one
						above. This is useful for usage tracking or if your main
						LLM key doesn't have embedding access.
					</p>
				)}

				{/* Delete Confirmation */}
				<Dialog
					open={showDeleteConfirm}
					onOpenChange={setShowDeleteConfirm}
				>
					<DialogContent>
						<DialogHeader>
							<DialogTitle>
								Remove Embedding Configuration
							</DialogTitle>
							<DialogDescription>
								Remove the dedicated embedding API key? If you
								have an OpenAI LLM configuration, embeddings
								will fall back to using that key.
							</DialogDescription>
						</DialogHeader>
						<DialogFooter>
							<Button
								variant="outline"
								onClick={() => setShowDeleteConfirm(false)}
								disabled={saving}
							>
								Cancel
							</Button>
							<Button
								variant="destructive"
								onClick={handleDelete}
								disabled={saving}
							>
								{saving ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Removing...
									</>
								) : (
									"Remove"
								)}
							</Button>
						</DialogFooter>
					</DialogContent>
				</Dialog>
			</CardContent>
		</Card>
	);
}

/**
 * Coding Mode Configuration Component
 *
 * Configure the AI model for the Bifrost coding assistant (Claude Agent SDK).
 * Falls back to main LLM config if using Anthropic, or allows dedicated config.
 */
function CodingConfigCard({
	availableModels,
	llmProvider,
}: {
	availableModels: ModelInfo[];
	llmProvider?: string;
}) {
	const [modelOverride, setModelOverride] = useState("");
	const [apiKeyOverride, setApiKeyOverride] = useState("");
	const [saving, setSaving] = useState(false);
	const [testing, setTesting] = useState(false);
	const [showOverrideForm, setShowOverrideForm] = useState(false);
	const [codingModels, setCodingModels] = useState<ModelInfo[]>([]);
	const [testResult, setTestResult] = useState<{
		success: boolean;
		message: string;
	} | null>(null);

	// Load current coding mode configuration
	const {
		data: config,
		isLoading,
		refetch,
	} = $api.useQuery("get", "/api/admin/llm/coding-config", undefined, {
		staleTime: 5 * 60 * 1000,
	});

	// Mutations
	const updateMutation = $api.useMutation(
		"put",
		"/api/admin/llm/coding-config",
	);
	const testSavedMutation = $api.useMutation(
		"post",
		"/api/admin/llm/test-saved",
	);

	// Use main LLM models if it's Anthropic, otherwise use coding-specific models
	const effectiveModels =
		llmProvider === "anthropic" && availableModels.length > 0
			? availableModels
			: codingModels;

	// Initialize form with existing overrides
	useEffect(() => {
		if (config) {
			setModelOverride(config.model_override || "");
			// Show form if there are existing overrides
			if (config.model_override || config.has_key_override) {
				setShowOverrideForm(true);
			}
		}
	}, [config]);

	// Test connection and load models
	const handleTestConnection = async () => {
		setTesting(true);
		setTestResult(null);

		try {
			const result = await testSavedMutation.mutateAsync({
				params: { query: { mode: "coding" } },
			});

			setTestResult({ success: result.success, message: result.message });

			if (result.success) {
				toast.success("Connection successful", {
					description: result.message,
				});
				// Load models from response
				if (result.models && result.models.length > 0) {
					const models = result.models as unknown as ModelInfo[];
					setCodingModels(models);
					// If no model selected yet, pick first
					if (!modelOverride && models.length > 0) {
						setModelOverride(models[0].id);
					}
				}
			} else {
				toast.error("Connection failed", {
					description: result.message,
				});
			}
		} catch (error) {
			const message =
				error instanceof Error ? error.message : "Unknown error";
			setTestResult({ success: false, message });
			toast.error("Connection test failed", { description: message });
		} finally {
			setTesting(false);
		}
	};

	// Save overrides
	const handleSave = async () => {
		setSaving(true);
		try {
			await updateMutation.mutateAsync({
				body: {
					model: modelOverride || null,
					api_key: apiKeyOverride || null,
					clear_overrides: false,
				},
			});

			toast.success("Coding mode configuration saved");
			setApiKeyOverride("");
			setTestResult(null);
			refetch();
		} catch (error) {
			toast.error("Failed to save coding mode configuration", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Clear all overrides
	const handleClearOverrides = async () => {
		setSaving(true);
		try {
			await updateMutation.mutateAsync({
				body: {
					clear_overrides: true,
				},
			});

			setModelOverride("");
			setApiKeyOverride("");
			setShowOverrideForm(false);
			setCodingModels([]);
			setTestResult(null);
			toast.success("Coding mode overrides cleared");
			refetch();
		} catch (error) {
			toast.error("Failed to clear overrides", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	if (isLoading) {
		return (
			<Card>
				<CardContent className="flex items-center justify-center py-8">
					<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
				</CardContent>
			</Card>
		);
	}

	const hasOverrides = config?.model_override || config?.has_key_override;
	const hasModels = effectiveModels.length > 0;
	const canSave = modelOverride || apiKeyOverride;

	return (
		<Card>
			<CardHeader>
				<div className="flex items-center gap-2">
					<Code className="h-5 w-5" />
					<CardTitle>Coding Mode</CardTitle>
					<Badge variant="outline" className="text-xs font-normal">
						Powered by Claude
					</Badge>
				</div>
				<CardDescription>
					Configure the AI model for the Bifrost coding assistant.
					{!config?.main_llm_is_anthropic &&
						!config?.has_key_override && (
							<span className="block mt-1 text-amber-600 dark:text-amber-400">
								Coding mode requires Anthropic. Add a dedicated
								API key below.
							</span>
						)}
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{/* Status Banner */}
				{config?.configured ? (
					<div className="rounded-lg border bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900 p-4">
						<div className="flex items-center justify-between">
							<div className="flex items-center gap-2">
								<CheckCircle2 className="h-4 w-4 text-green-600" />
								<span className="text-sm font-medium text-green-800 dark:text-green-200">
									Coding Mode Configured
								</span>
							</div>
							{hasOverrides && (
								<Button
									variant="ghost"
									size="sm"
									onClick={handleClearOverrides}
									disabled={saving}
									className="text-muted-foreground hover:text-foreground"
								>
									<X className="h-4 w-4 mr-1" />
									Clear Overrides
								</Button>
							)}
						</div>
						<div className="mt-2 space-y-1">
							<p className="text-sm text-green-700 dark:text-green-300">
								<span className="font-medium">Model:</span>{" "}
								{config.model}
							</p>
							<p className="text-sm text-green-700 dark:text-green-300">
								<span className="font-medium">Source:</span>{" "}
								{hasOverrides
									? "Custom override"
									: "Using main AI config"}
							</p>
						</div>
					</div>
				) : (
					<div className="rounded-lg border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900 p-4">
						<div className="flex items-center gap-2">
							<AlertCircle className="h-4 w-4 text-amber-600" />
							<span className="text-sm font-medium text-amber-800 dark:text-amber-200">
								Coding Mode Not Configured
							</span>
						</div>
						<p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
							{config?.main_llm_is_anthropic
								? "Configure an Anthropic model in main AI settings, or add a custom override below."
								: "Add an Anthropic API key to enable the coding assistant."}
						</p>
					</div>
				)}

				{/* Override Toggle */}
				{!showOverrideForm && config?.main_llm_is_anthropic && (
					<Button
						variant="outline"
						size="sm"
						onClick={() => setShowOverrideForm(true)}
					>
						<Pencil className="h-4 w-4 mr-2" />
						Override Settings
					</Button>
				)}

				{/* Override Form */}
				{(showOverrideForm || !config?.main_llm_is_anthropic) && (
					<div className="space-y-4 pt-2 border-t">
						<p className="text-sm text-muted-foreground">
							{config?.main_llm_is_anthropic
								? "Override the main AI config with custom settings for coding mode."
								: "Configure a dedicated Anthropic API key for coding mode."}
						</p>

						{/* API Key Override - show first if not using main Anthropic */}
						{!config?.main_llm_is_anthropic && (
							<div className="space-y-2">
								<Label htmlFor="coding-api-key">
									Anthropic API Key
								</Label>
								<div className="flex gap-2">
									<Input
										id="coding-api-key"
										type="password"
										autoComplete="off"
										placeholder={
											config?.has_key_override
												? "API key saved - enter new key to change"
												: "sk-ant-..."
										}
										value={apiKeyOverride}
										onChange={(e) => {
											setApiKeyOverride(e.target.value);
											setTestResult(null);
										}}
									/>
									<Button
										variant="secondary"
										onClick={handleTestConnection}
										disabled={
											testing ||
											(!apiKeyOverride &&
												!config?.has_key_override)
										}
									>
										{testing ? (
											<>
												<Loader2 className="h-4 w-4 mr-2 animate-spin" />
												Testing...
											</>
										) : testResult?.success ? (
											<>
												<CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />
												Verified
											</>
										) : testResult?.success === false ? (
											<>
												<AlertCircle className="h-4 w-4 mr-2 text-destructive" />
												Failed
											</>
										) : (
											<>
												<Zap className="h-4 w-4 mr-2" />
												Test
											</>
										)}
									</Button>
								</div>
								<p className="text-xs text-muted-foreground">
									Get your API key from{" "}
									<a
										href="https://console.anthropic.com/settings/keys"
										target="_blank"
										rel="noopener noreferrer"
										className="underline hover:text-foreground"
									>
										console.anthropic.com
									</a>
								</p>
							</div>
						)}

						{/* Model Override - dropdown when models available */}
						<div className="space-y-2">
							<Label htmlFor="coding-model">
								Model{" "}
								{config?.main_llm_is_anthropic
									? "Override"
									: ""}
								{!hasModels &&
									!config?.main_llm_is_anthropic && (
										<span className="text-muted-foreground font-normal ml-2">
											(test API key first)
										</span>
									)}
							</Label>
							{hasModels ? (
								<Select
									value={modelOverride || "__default__"}
									onValueChange={(v) =>
										setModelOverride(
											v === "__default__" ? "" : v,
										)
									}
								>
									<SelectTrigger id="coding-model">
										<SelectValue placeholder="Select model">
											{modelOverride
												? effectiveModels.find(
														(m) =>
															m.id ===
															modelOverride,
													)?.display_name ||
													modelOverride
												: "Use main AI config model"}
										</SelectValue>
									</SelectTrigger>
									<SelectContent>
										{config?.main_llm_is_anthropic && (
											<SelectItem value="__default__">
												<span className="text-muted-foreground">
													Use main AI config model
												</span>
											</SelectItem>
										)}
										{effectiveModels.map((m) => (
											<SelectItem key={m.id} value={m.id}>
												<div className="flex flex-col">
													<span>
														{m.display_name}
													</span>
													<span className="text-xs text-muted-foreground">
														{m.id}
													</span>
												</div>
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							) : config?.main_llm_is_anthropic ? (
								<Select
									value={modelOverride || "__default__"}
									onValueChange={(v) =>
										setModelOverride(
											v === "__default__" ? "" : v,
										)
									}
								>
									<SelectTrigger id="coding-model">
										<SelectValue placeholder="Use main AI config model">
											{modelOverride
												? availableModels.find(
														(m) =>
															m.id ===
															modelOverride,
													)?.display_name ||
													modelOverride
												: "Use main AI config model"}
										</SelectValue>
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="__default__">
											<span className="text-muted-foreground">
												Use main AI config model
											</span>
										</SelectItem>
										{availableModels.map((m) => (
											<SelectItem key={m.id} value={m.id}>
												<div className="flex flex-col">
													<span>
														{m.display_name}
													</span>
													<span className="text-xs text-muted-foreground">
														{m.id}
													</span>
												</div>
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							) : (
								<Input
									id="coding-model"
									placeholder="Test API key to load available models"
									disabled
									value=""
								/>
							)}
							{config?.main_llm_is_anthropic && (
								<p className="text-xs text-muted-foreground">
									Select a model to override, or keep default
									to use main config.
								</p>
							)}
						</div>

						{/* API Key Override for Anthropic main config - optional */}
						{config?.main_llm_is_anthropic && (
							<div className="space-y-2">
								<Label htmlFor="coding-api-key">
									API Key Override (Optional)
								</Label>
								<Input
									id="coding-api-key"
									type="password"
									autoComplete="off"
									placeholder={
										config?.has_key_override
											? "API key saved - enter new key to change"
											: "Leave empty to use main AI key"
									}
									value={apiKeyOverride}
									onChange={(e) =>
										setApiKeyOverride(e.target.value)
									}
								/>
								<p className="text-xs text-muted-foreground">
									Main LLM is Anthropic - no separate key
									needed unless you want to override.
								</p>
							</div>
						)}

						{/* Save Button */}
						<div className="flex justify-end gap-2">
							{showOverrideForm &&
								config?.main_llm_is_anthropic &&
								!hasOverrides && (
									<Button
										variant="outline"
										onClick={() => {
											setShowOverrideForm(false);
											setModelOverride("");
											setApiKeyOverride("");
										}}
									>
										Cancel
									</Button>
								)}
							<Button
								onClick={handleSave}
								disabled={!canSave || saving}
							>
								{saving ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Saving...
									</>
								) : (
									"Save"
								)}
							</Button>
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

/**
 * Model Pricing Configuration Component
 *
 * Manage AI model pricing for cost tracking.
 * Shows models that have been used with their pricing, and allows adding/editing.
 */
function ModelPricingCard() {
	const [pricingData, setPricingData] = useState<AIModelPricingListItem[]>(
		[],
	);
	const [modelsWithoutPricing, setModelsWithoutPricing] = useState<string[]>(
		[],
	);
	const [isLoading, setIsLoading] = useState(true);
	const [editingId, setEditingId] = useState<number | null>(null);
	const [editValues, setEditValues] = useState<{
		input: string;
		output: string;
	}>({ input: "", output: "" });
	const [saving, setSaving] = useState(false);
	const [showAddDialog, setShowAddDialog] = useState(false);
	const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
	const [deletingPricing, setDeletingPricing] =
		useState<AIModelPricingListItem | null>(null);
	const [newPricing, setNewPricing] = useState<AIModelPricingCreate>({
		provider: "openai",
		model: "",
		input_price_per_million: 0,
		output_price_per_million: 0,
	});

	// Load pricing data
	const loadPricing = async () => {
		try {
			setIsLoading(true);
			const data = await listPricing();
			setPricingData(data.pricing || []);
			setModelsWithoutPricing(data.models_without_pricing || []);
		} catch (error) {
			toast.error("Failed to load pricing data", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setIsLoading(false);
		}
	};

	useEffect(() => {
		loadPricing();
	}, []);

	// Format price for display
	const formatPrice = (price: number | string | null | undefined): string => {
		if (price === null || price === undefined) return "-";
		const numPrice = typeof price === "string" ? parseFloat(price) : price;
		if (isNaN(numPrice)) return "-";
		return `$${numPrice.toFixed(2)}`;
	};

	// Format date for display
	const formatDate = (dateStr: string | null | undefined): string => {
		if (!dateStr) return "-";
		return new Date(dateStr).toLocaleDateString();
	};

	// Start editing a row
	const startEdit = (item: AIModelPricingListItem) => {
		if (item.id === null) return;
		setEditingId(item.id);
		setEditValues({
			input: item.input_price_per_million?.toString() || "0",
			output: item.output_price_per_million?.toString() || "0",
		});
	};

	// Cancel editing
	const cancelEdit = () => {
		setEditingId(null);
		setEditValues({ input: "", output: "" });
	};

	// Save edited values
	const saveEdit = async () => {
		if (editingId === null) return;

		setSaving(true);
		try {
			await updatePricing(editingId, {
				input_price_per_million: parseFloat(editValues.input) || 0,
				output_price_per_million: parseFloat(editValues.output) || 0,
			});
			toast.success("Pricing updated");
			await loadPricing();
			cancelEdit();
		} catch (error) {
			toast.error("Failed to update pricing", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Add new pricing
	const handleAddPricing = async () => {
		if (!newPricing.model) {
			toast.error("Please enter a model name");
			return;
		}

		setSaving(true);
		try {
			await createPricing(newPricing);
			toast.success("Pricing added", {
				description: `Added pricing for ${newPricing.model}`,
			});
			await loadPricing();
			setShowAddDialog(false);
			setNewPricing({
				provider: "openai",
				model: "",
				input_price_per_million: 0,
				output_price_per_million: 0,
			});
		} catch (error) {
			toast.error("Failed to add pricing", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	// Show delete confirmation dialog
	const handleDeletePricing = (item: AIModelPricingListItem) => {
		setDeletingPricing(item);
		setShowDeleteConfirm(true);
	};

	// Confirm delete
	const confirmDeletePricing = async () => {
		if (!deletingPricing?.id) return;

		setSaving(true);
		try {
			await deletePricing(deletingPricing.id);
			toast.success("Pricing deleted", {
				description: `Removed pricing for ${deletingPricing.provider}/${deletingPricing.model}`,
			});
			await loadPricing();
			setShowDeleteConfirm(false);
			setDeletingPricing(null);
		} catch (error) {
			toast.error("Failed to delete pricing", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
		} finally {
			setSaving(false);
		}
	};

	if (isLoading) {
		return (
			<Card>
				<CardContent className="flex items-center justify-center py-8">
					<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
				</CardContent>
			</Card>
		);
	}

	const hasWarnings = modelsWithoutPricing.length > 0;

	// Parse "provider/model" strings into objects for display
	const unpricedModels = modelsWithoutPricing.map((pm) => {
		const [provider, ...modelParts] = pm.split("/");
		return { provider, model: modelParts.join("/") };
	});

	return (
		<Card>
			<CardHeader>
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2">
						<DollarSign className="h-5 w-5" />
						<CardTitle>Model Pricing</CardTitle>
						{hasWarnings && (
							<Badge variant="warning">
								{modelsWithoutPricing.length} unpriced
							</Badge>
						)}
					</div>
					<Button
						variant="outline"
						size="sm"
						onClick={() => setShowAddDialog(true)}
					>
						<Plus className="h-4 w-4 mr-1" />
						Add Model
					</Button>
				</div>
				<CardDescription>
					Configure pricing per million tokens for cost tracking.
					{hasWarnings && (
						<span className="block mt-1 text-amber-600 dark:text-amber-400">
							{modelsWithoutPricing.length} model(s) have been
							used but don't have pricing configured.
						</span>
					)}
				</CardDescription>
			</CardHeader>
			<CardContent>
				{pricingData.length === 0 &&
				modelsWithoutPricing.length === 0 ? (
					<div className="text-center py-8 text-muted-foreground">
						<DollarSign className="h-8 w-8 mx-auto mb-2 opacity-50" />
						<p>No model pricing configured yet.</p>
						<p className="text-sm mt-1">
							Add pricing to track AI usage costs.
						</p>
					</div>
				) : (
					<div className="rounded-md border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Provider</TableHead>
									<TableHead>Model</TableHead>
									<TableHead className="text-right">
										Input ($/1M)
									</TableHead>
									<TableHead className="text-right">
										Output ($/1M)
									</TableHead>
									<TableHead>Last Updated</TableHead>
									<TableHead className="w-[100px]"></TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{/* Models without pricing (need attention) */}
								{unpricedModels.map((item) => (
									<TableRow
										key={`unpriced-${item.provider}-${item.model}`}
										className="bg-amber-50/50 dark:bg-amber-950/10"
									>
										<TableCell className="font-medium capitalize">
											{item.provider}
										</TableCell>
										<TableCell>
											<div className="flex items-center gap-2">
												{item.model}
												<Badge variant="warning">
													No pricing
												</Badge>
											</div>
										</TableCell>
										<TableCell className="text-right text-muted-foreground">
											-
										</TableCell>
										<TableCell className="text-right text-muted-foreground">
											-
										</TableCell>
										<TableCell className="text-muted-foreground">
											-
										</TableCell>
										<TableCell>
											<div className="flex items-center justify-end">
												<Button
													variant="outline"
													size="sm"
													onClick={() => {
														setNewPricing({
															provider:
																item.provider,
															model: item.model,
															input_price_per_million: 0,
															output_price_per_million: 0,
														});
														setShowAddDialog(true);
													}}
												>
													<Plus className="h-4 w-4 mr-1" />
													Add
												</Button>
											</div>
										</TableCell>
									</TableRow>
								))}
								{/* Models with pricing configured */}
								{pricingData.map((item) => (
									<TableRow key={item.id}>
										<TableCell className="font-medium capitalize">
											{item.provider}
										</TableCell>
										<TableCell>
											<div className="flex items-center gap-2">
												{item.model}
												{item.is_used && (
													<Badge variant="secondary">
														In use
													</Badge>
												)}
											</div>
										</TableCell>
										<TableCell className="text-right">
											{editingId === item.id ? (
												<Input
													type="number"
													step="0.01"
													min="0"
													value={editValues.input}
													onChange={(e) =>
														setEditValues({
															...editValues,
															input: e.target
																.value,
														})
													}
													className="w-24 text-right"
												/>
											) : (
												formatPrice(
													item.input_price_per_million,
												)
											)}
										</TableCell>
										<TableCell className="text-right">
											{editingId === item.id ? (
												<Input
													type="number"
													step="0.01"
													min="0"
													value={editValues.output}
													onChange={(e) =>
														setEditValues({
															...editValues,
															output: e.target
																.value,
														})
													}
													className="w-24 text-right"
												/>
											) : (
												formatPrice(
													item.output_price_per_million,
												)
											)}
										</TableCell>
										<TableCell>
											{formatDate(item.updated_at)}
										</TableCell>
										<TableCell>
											<div className="flex items-center gap-1 justify-end">
												{editingId === item.id ? (
													<>
														<Button
															variant="ghost"
															size="sm"
															onClick={saveEdit}
															disabled={saving}
														>
															{saving ? (
																<Loader2 className="h-4 w-4 animate-spin" />
															) : (
																<Check className="h-4 w-4 text-green-600" />
															)}
														</Button>
														<Button
															variant="ghost"
															size="sm"
															onClick={cancelEdit}
															disabled={saving}
														>
															<X className="h-4 w-4" />
														</Button>
													</>
												) : (
													<>
														<Button
															variant="ghost"
															size="sm"
															onClick={() =>
																startEdit(item)
															}
														>
															<Pencil className="h-4 w-4" />
														</Button>
														<Button
															variant="ghost"
															size="sm"
															onClick={() =>
																handleDeletePricing(
																	item,
																)
															}
															className="text-destructive hover:text-destructive"
														>
															<Trash2 className="h-4 w-4" />
														</Button>
													</>
												)}
											</div>
										</TableCell>
									</TableRow>
								))}
							</TableBody>
						</Table>
					</div>
				)}
			</CardContent>

			{/* Add Pricing Dialog */}
			<Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Add Model Pricing</DialogTitle>
						<DialogDescription>
							Configure pricing for a new AI model.
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-4 py-4">
						<div className="space-y-2">
							<Label htmlFor="new-provider">Provider</Label>
							<Select
								value={newPricing.provider}
								onValueChange={(value) =>
									setNewPricing({
										...newPricing,
										provider: value,
									})
								}
							>
								<SelectTrigger id="new-provider">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="openai">
										OpenAI
									</SelectItem>
									<SelectItem value="anthropic">
										Anthropic
									</SelectItem>
									<SelectItem value="custom">
										Custom
									</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div className="space-y-2">
							<Label htmlFor="new-model">Model Name</Label>
							<Input
								id="new-model"
								placeholder="e.g., gpt-4o, claude-3-opus"
								value={newPricing.model}
								onChange={(e) =>
									setNewPricing({
										...newPricing,
										model: e.target.value,
									})
								}
							/>
						</div>
						<div className="grid grid-cols-2 gap-4">
							<div className="space-y-2">
								<Label htmlFor="new-input-price">
									Input Price ($/1M tokens)
								</Label>
								<Input
									id="new-input-price"
									type="number"
									step="0.01"
									min="0"
									placeholder="0.00"
									value={
										newPricing.input_price_per_million || ""
									}
									onChange={(e) =>
										setNewPricing({
											...newPricing,
											input_price_per_million:
												parseFloat(e.target.value) || 0,
										})
									}
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="new-output-price">
									Output Price ($/1M tokens)
								</Label>
								<Input
									id="new-output-price"
									type="number"
									step="0.01"
									min="0"
									placeholder="0.00"
									value={
										newPricing.output_price_per_million ||
										""
									}
									onChange={(e) =>
										setNewPricing({
											...newPricing,
											output_price_per_million:
												parseFloat(e.target.value) || 0,
										})
									}
								/>
							</div>
						</div>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setShowAddDialog(false)}
							disabled={saving}
						>
							Cancel
						</Button>
						<Button onClick={handleAddPricing} disabled={saving}>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Adding...
								</>
							) : (
								"Add Pricing"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Delete Confirmation Dialog */}
			<Dialog
				open={showDeleteConfirm}
				onOpenChange={setShowDeleteConfirm}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Delete Pricing Configuration</DialogTitle>
						<DialogDescription>
							Are you sure you want to delete pricing for{" "}
							<span className="font-medium">
								{deletingPricing?.provider}/
								{deletingPricing?.model}
							</span>
							? This action cannot be undone.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => {
								setShowDeleteConfirm(false);
								setDeletingPricing(null);
							}}
							disabled={saving}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={confirmDeletePricing}
							disabled={saving}
						>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Deleting...
								</>
							) : (
								"Delete"
							)}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</Card>
	);
}
