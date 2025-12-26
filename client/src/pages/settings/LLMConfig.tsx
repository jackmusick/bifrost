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
import { toast } from "sonner";
import {
	Loader2,
	Bot,
	CheckCircle2,
	AlertCircle,
	Trash2,
	Zap,
	Database,
} from "lucide-react";
import { $api } from "@/lib/api-client";

type Provider = "openai" | "anthropic" | "custom";

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
	const [availableModels, setAvailableModels] = useState<string[]>([]);
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
				if (result.success && result.models && result.models.length > 0) {
					setAvailableModels(result.models);
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
					setAvailableModels(result.models);
					// If current model is not in list, select first available
					if (!result.models.includes(model)) {
						setModel(result.models[0]);
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
										<SelectValue placeholder="Select model" />
									</SelectTrigger>
									<SelectContent>
										{availableModels.map((m) => (
											<SelectItem key={m} value={m}>
												{m}
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
	const saveMutation = $api.useMutation("post", "/api/admin/llm/embedding-config");
	const deleteMutation = $api.useMutation("delete", "/api/admin/llm/embedding-config");
	const testMutation = $api.useMutation("post", "/api/admin/llm/embedding-test");

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
			const message = error instanceof Error ? error.message : "Unknown error";
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
				description: error instanceof Error ? error.message : "Unknown error",
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
				description: error instanceof Error ? error.message : "Unknown error",
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
							Anthropic doesn't provide embeddings - a dedicated OpenAI key is required.
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
							Knowledge Store features require embedding configuration.
						</p>
					</div>
				)}

				{/* Only show form if dedicated config is needed or already set */}
				{(needsDedicatedKey || (config && !config.uses_llm_key)) && (
					<>
						{/* API Key */}
						<div className="space-y-2">
							<Label htmlFor="embedding-api-key">OpenAI API Key</Label>
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
									disabled={testing || (!apiKey && !config?.api_key_set)}
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
							<Label htmlFor="embedding-dimensions">Dimensions</Label>
							<Select
								value={dimensions.toString()}
								onValueChange={(v) => setDimensions(parseInt(v))}
							>
								<SelectTrigger id="embedding-dimensions">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="512">512</SelectItem>
									<SelectItem value="1024">1024</SelectItem>
									<SelectItem value="1536">1536 (default)</SelectItem>
									{model === "text-embedding-3-large" && (
										<SelectItem value="3072">3072</SelectItem>
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
						To use a separate API key for embeddings, configure one above.
						This is useful for usage tracking or if your main LLM key doesn't have embedding access.
					</p>
				)}

				{/* Delete Confirmation */}
				<Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
					<DialogContent>
						<DialogHeader>
							<DialogTitle>Remove Embedding Configuration</DialogTitle>
							<DialogDescription>
								Remove the dedicated embedding API key? If you have an OpenAI
								LLM configuration, embeddings will fall back to using that key.
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
