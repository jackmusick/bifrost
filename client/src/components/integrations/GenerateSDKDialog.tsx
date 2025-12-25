import { useState } from "react";
import { Loader2, Code, CheckCircle2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

type AuthType = "bearer" | "api_key" | "basic" | "oauth";

interface GenerateSDKResponse {
	success: boolean;
	module_name: string;
	module_path: string;
	class_name: string;
	endpoint_count: number;
	schema_count: number;
	usage_example: string;
}

interface GenerateSDKDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	integrationId: string;
	integrationName: string;
	hasOAuth: boolean;
}

export function GenerateSDKDialog({
	open,
	onOpenChange,
	integrationId,
	integrationName,
	hasOAuth,
}: GenerateSDKDialogProps) {
	const [specUrl, setSpecUrl] = useState("");
	const [authType, setAuthType] = useState<AuthType>("bearer");
	const [moduleName, setModuleName] = useState("");
	const [isGenerating, setIsGenerating] = useState(false);
	const [result, setResult] = useState<GenerateSDKResponse | null>(null);

	// Auth-specific fields
	const [baseUrl, setBaseUrl] = useState("");
	const [token, setToken] = useState("");
	const [headerName, setHeaderName] = useState("x-api-key");
	const [apiKey, setApiKey] = useState("");
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");

	const validateAuthFields = (): string | null => {
		if (!baseUrl.trim()) {
			return "Base URL is required";
		}

		switch (authType) {
			case "bearer":
				if (!token.trim()) return "Token is required";
				break;
			case "api_key":
				if (!headerName.trim()) return "Header name is required";
				if (!apiKey.trim()) return "API key is required";
				break;
			case "basic":
				if (!username.trim()) return "Username is required";
				if (!password.trim()) return "Password is required";
				break;
			case "oauth":
				// OAuth uses existing provider, no extra fields needed
				break;
		}
		return null;
	};

	const buildConfigPayload = (): Record<string, string> => {
		const config: Record<string, string> = {
			base_url: baseUrl.trim(),
		};

		switch (authType) {
			case "bearer":
				config.token = token.trim();
				break;
			case "api_key":
				config.header_name = headerName.trim();
				config.api_key = apiKey.trim();
				break;
			case "basic":
				config.username = username.trim();
				config.password = password.trim();
				break;
		}

		return config;
	};

	const handleGenerate = async () => {
		if (!specUrl.trim()) {
			toast.error("Please enter an OpenAPI spec URL");
			return;
		}

		const validationError = validateAuthFields();
		if (validationError) {
			toast.error(validationError);
			return;
		}

		setIsGenerating(true);
		try {
			// First, save the config to the integration
			if (authType !== "oauth") {
				const configResponse = await fetch(
					`/api/integrations/${integrationId}/config`,
					{
						method: "PUT",
						headers: {
							"Content-Type": "application/json",
						},
						body: JSON.stringify({
							config: buildConfigPayload(),
						}),
					},
				);

				if (!configResponse.ok) {
					const error = await configResponse.json();
					throw new Error(
						error.detail || "Failed to save configuration",
					);
				}
			}

			// Then generate the SDK
			const response = await fetch(
				`/api/integrations/${integrationId}/generate-sdk`,
				{
					method: "POST",
					headers: {
						"Content-Type": "application/json",
					},
					body: JSON.stringify({
						spec_url: specUrl.trim(),
						auth_type: authType,
						module_name: moduleName.trim() || undefined,
					}),
				},
			);

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || "Failed to generate SDK");
			}

			const data: GenerateSDKResponse = await response.json();
			setResult(data);
			toast.success("SDK generated successfully!");
		} catch (error) {
			console.error("SDK generation failed:", error);
			toast.error(
				error instanceof Error
					? error.message
					: "Failed to generate SDK",
			);
		} finally {
			setIsGenerating(false);
		}
	};

	const handleCopyUsage = () => {
		if (result?.usage_example) {
			navigator.clipboard.writeText(result.usage_example);
			toast.success("Usage example copied to clipboard");
		}
	};

	const handleClose = () => {
		// Reset state when closing
		setSpecUrl("");
		setAuthType("bearer");
		setModuleName("");
		setResult(null);
		setBaseUrl("");
		setToken("");
		setHeaderName("x-api-key");
		setApiKey("");
		setUsername("");
		setPassword("");
		onOpenChange(false);
	};

	const renderAuthFields = () => {
		return (
			<>
				{/* Base URL - always shown */}
				<div className="space-y-2">
					<Label htmlFor="base-url">
						Base URL <span className="text-destructive">*</span>
					</Label>
					<Input
						id="base-url"
						placeholder="https://api.example.com"
						value={baseUrl}
						onChange={(e) => setBaseUrl(e.target.value)}
					/>
				</div>

				{/* Bearer Token fields */}
				{authType === "bearer" && (
					<div className="space-y-2">
						<Label htmlFor="token">
							Token <span className="text-destructive">*</span>
						</Label>
						<Input
							id="token"
							type="password"
							placeholder="Enter your API token"
							value={token}
							onChange={(e) => setToken(e.target.value)}
						/>
					</div>
				)}

				{/* API Key fields */}
				{authType === "api_key" && (
					<>
						<div className="space-y-2">
							<Label htmlFor="header-name">
								Header Name{" "}
								<span className="text-destructive">*</span>
							</Label>
							<Input
								id="header-name"
								placeholder="x-api-key"
								value={headerName}
								onChange={(e) => setHeaderName(e.target.value)}
							/>
							<p className="text-xs text-muted-foreground">
								The HTTP header name for authentication (e.g.,
								x-api-key, X-Auth-Token)
							</p>
						</div>
						<div className="space-y-2">
							<Label htmlFor="api-key">
								API Key{" "}
								<span className="text-destructive">*</span>
							</Label>
							<Input
								id="api-key"
								type="password"
								placeholder="Enter your API key"
								value={apiKey}
								onChange={(e) => setApiKey(e.target.value)}
							/>
						</div>
					</>
				)}

				{/* Basic Auth fields */}
				{authType === "basic" && (
					<>
						<div className="space-y-2">
							<Label htmlFor="username">
								Username{" "}
								<span className="text-destructive">*</span>
							</Label>
							<Input
								id="username"
								placeholder="Enter username"
								value={username}
								onChange={(e) => setUsername(e.target.value)}
							/>
						</div>
						<div className="space-y-2">
							<Label htmlFor="password">
								Password{" "}
								<span className="text-destructive">*</span>
							</Label>
							<Input
								id="password"
								type="password"
								placeholder="Enter password"
								value={password}
								onChange={(e) => setPassword(e.target.value)}
							/>
						</div>
					</>
				)}

				{/* OAuth - no extra fields, just info */}
				{authType === "oauth" && (
					<div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-md">
						OAuth authentication will use the integration's
						configured OAuth provider. Make sure you've connected
						the OAuth flow before using the SDK.
					</div>
				)}
			</>
		);
	};

	const getConfigInfoMessage = () => {
		switch (authType) {
			case "bearer":
				return "Will save base_url and token to integration config";
			case "api_key":
				return "Will save base_url, header_name, and api_key to integration config";
			case "basic":
				return "Will save base_url, username, and password to integration config";
			case "oauth":
				return "Will use the existing OAuth connection for authentication";
		}
	};

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="max-w-lg">
				{result ? (
					// Success state
					<>
						<DialogHeader>
							<DialogTitle className="flex items-center gap-2">
								<CheckCircle2 className="h-5 w-5 text-green-600" />
								SDK Generated Successfully
							</DialogTitle>
							<DialogDescription>
								Your SDK is ready to use in workflows
							</DialogDescription>
						</DialogHeader>

						<div className="space-y-4 py-4">
							<div className="grid grid-cols-2 gap-4 text-sm">
								<div>
									<span className="text-muted-foreground">
										Module:
									</span>
									<p className="font-mono font-medium">
										{result.module_name}
									</p>
								</div>
								<div>
									<span className="text-muted-foreground">
										Path:
									</span>
									<p className="font-mono text-xs">
										{result.module_path}
									</p>
								</div>
								<div>
									<span className="text-muted-foreground">
										Endpoints:
									</span>
									<p className="font-medium">
										{result.endpoint_count}
									</p>
								</div>
								<div>
									<span className="text-muted-foreground">
										Schemas:
									</span>
									<p className="font-medium">
										{result.schema_count}
									</p>
								</div>
							</div>

							<div className="space-y-2">
								<Label>Usage Example</Label>
								<div className="relative">
									<pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
										<code>{result.usage_example}</code>
									</pre>
									<Button
										variant="ghost"
										size="icon"
										className="absolute top-2 right-2 h-6 w-6"
										onClick={handleCopyUsage}
									>
										<Copy className="h-3 w-3" />
									</Button>
								</div>
							</div>

							<div className="text-sm text-muted-foreground bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 p-3 rounded-md">
								<p>
									<strong>Configuration saved!</strong> The
									authentication settings have been saved to
									the integration config. The SDK will
									automatically use these credentials.
								</p>
							</div>
						</div>

						<DialogFooter>
							<Button onClick={handleClose}>Done</Button>
						</DialogFooter>
					</>
				) : (
					// Form state
					<>
						<DialogHeader>
							<DialogTitle className="flex items-center gap-2">
								<Code className="h-5 w-5" />
								Generate SDK for {integrationName}
							</DialogTitle>
							<DialogDescription>
								Generate a Python SDK from an OpenAPI
								specification. The SDK will automatically use
								this integration's configuration for
								authentication.
							</DialogDescription>
						</DialogHeader>

						<div className="space-y-4 py-4">
							<div className="space-y-2">
								<Label htmlFor="spec-url">
									OpenAPI Spec URL{" "}
									<span className="text-destructive">*</span>
								</Label>
								<Input
									id="spec-url"
									placeholder="https://api.example.com/openapi.json"
									value={specUrl}
									onChange={(e) => setSpecUrl(e.target.value)}
								/>
								<p className="text-xs text-muted-foreground">
									URL to an OpenAPI 3.0 specification (JSON or
									YAML)
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="auth-type">
									Authentication Type{" "}
									<span className="text-destructive">*</span>
								</Label>
								<Select
									value={authType}
									onValueChange={(v) =>
										setAuthType(v as AuthType)
									}
								>
									<SelectTrigger>
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="bearer">
											Bearer Token
										</SelectItem>
										<SelectItem value="api_key">
											API Key (custom header)
										</SelectItem>
										<SelectItem value="basic">
											Basic Auth
										</SelectItem>
										{hasOAuth && (
											<SelectItem value="oauth">
												OAuth (use configured provider)
											</SelectItem>
										)}
									</SelectContent>
								</Select>
							</div>

							{/* Dynamic auth fields based on selected type */}
							{renderAuthFields()}

							<div className="space-y-2">
								<Label htmlFor="module-name">
									Module Name{" "}
									<span className="text-muted-foreground">
										(optional)
									</span>
								</Label>
								<Input
									id="module-name"
									placeholder="example_api"
									value={moduleName}
									onChange={(e) =>
										setModuleName(e.target.value)
									}
									pattern="^[a-z][a-z0-9_]*$"
								/>
								<p className="text-xs text-muted-foreground">
									Lowercase with underscores. Defaults to the
									API title from the spec.
								</p>
							</div>

							{/* Info message about what will be saved */}
							<div className="text-sm text-muted-foreground bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 p-3 rounded-md flex items-start gap-2">
								<span className="mt-0.5">ℹ️</span>
								<span>{getConfigInfoMessage()}</span>
							</div>
						</div>

						<DialogFooter>
							<Button variant="outline" onClick={handleClose}>
								Cancel
							</Button>
							<Button
								onClick={handleGenerate}
								disabled={isGenerating || !specUrl.trim()}
							>
								{isGenerating ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Generating...
									</>
								) : (
									<>
										<Code className="h-4 w-4 mr-2" />
										Generate SDK
									</>
								)}
							</Button>
						</DialogFooter>
					</>
				)}
			</DialogContent>
		</Dialog>
	);
}
