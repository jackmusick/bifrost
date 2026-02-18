import { useState, useMemo, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Info, Copy, Check } from "lucide-react";
import {
	useCreateOAuthConnection,
	useUpdateOAuthConnection,
	useOAuthConnection,
} from "@/hooks/useOAuth";
import type { components } from "@/lib/v1";
type CreateOAuthConnectionRequest =
	components["schemas"]["CreateOAuthConnectionRequest"];
type UpdateOAuthConnectionRequest =
	components["schemas"]["UpdateOAuthConnectionRequest"];
type OAuthConnectionDetail = components["schemas"]["OAuthConnectionDetail"];
type OAuthFlowType = "authorization_code" | "client_credentials";
import { toast } from "sonner";

interface CreateOAuthConnectionDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	integrationId: string;
	editConnectionName?: string | undefined;
}

export function CreateOAuthConnectionDialog({
	open,
	onOpenChange,
	integrationId,
	editConnectionName,
}: CreateOAuthConnectionDialogProps) {
	const isEditMode = !!editConnectionName;
	const createMutation = useCreateOAuthConnection();
	const updateMutation = useUpdateOAuthConnection();
	const { data: existingConnection } = useOAuthConnection(
		editConnectionName || "",
	) as { data?: OAuthConnectionDetail | undefined };

	// Compute initial form data from existing connection (for edit mode)
	const initialFormData = useMemo((): CreateOAuthConnectionRequest => {
		if (isEditMode && existingConnection) {
			return {
				description: existingConnection.description || "",
				oauth_flow_type: existingConnection.oauth_flow_type,
				client_id: existingConnection.client_id,
				client_secret: "", // Don't populate for security
				authorization_url: existingConnection.authorization_url ?? null,
				token_url: existingConnection.token_url,
				scopes: existingConnection.scopes || "",
				integration_id: integrationId,
				audience: existingConnection.audience || "",
			};
		}
		return {
			description: "",
			oauth_flow_type: "authorization_code",
			client_id: "",
			client_secret: "",
			authorization_url: "",
			token_url: "",
			scopes: "",
			integration_id: integrationId,
			audience: "",
		};
	}, [isEditMode, existingConnection, integrationId]);

	const [copiedRedirect, setCopiedRedirect] = useState(false);
	const [formData, setFormData] =
		useState<CreateOAuthConnectionRequest>(initialFormData);

	// Reset form when dialog opens with new data - wrap in async to satisfy React Compiler
	useEffect(() => {
		// Schedule reset for next tick to avoid synchronous setState in effect
		const timeoutId = setTimeout(() => {
			if (open) {
				setFormData(initialFormData);
			}
		}, 0);
		return () => clearTimeout(timeoutId);
	}, [
		open,
		editConnectionName,
		initialFormData,
		isEditMode,
		existingConnection,
	]);

	const redirectUri = `${window.location.origin}/oauth/callback/${integrationId}`;

	const handleCopyRedirectUri = () => {
		navigator.clipboard.writeText(redirectUri);
		setCopiedRedirect(true);
		toast.success("Redirect URI copied to clipboard");
		setTimeout(() => setCopiedRedirect(false), 2000);
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		if (isEditMode) {
			// Update existing connection
			// Backend accepts scopes as string (comma/space separated) via Pydantic validator
			const updateData: UpdateOAuthConnectionRequest = {
				oauth_flow_type: formData.oauth_flow_type,
				client_id: formData.client_id,
				client_secret: formData.client_secret || null,
				authorization_url: formData.authorization_url || null,
				token_url: formData.token_url,
				scopes: formData.scopes as unknown as string[],
				audience: formData.audience || null,
			};

			await updateMutation.mutateAsync({
				params: { path: { connection_name: editConnectionName } },
				body: updateData,
			});
		} else {
			// Create new connection
			// For client_credentials, authorization_url can be empty/null
			// The API will accept it as optional for this flow
			await createMutation.mutateAsync({
				body: formData,
			});
		}

		// Reset form and close
		setFormData(initialFormData);
		onOpenChange(false);
	};

	const isStep2Valid = () => {
		const baseValid = formData.client_id && formData.token_url;

		if (formData.oauth_flow_type === "client_credentials") {
			// Client credentials requires client_secret
			return baseValid && !!formData.client_secret;
		} else {
			// Authorization code requires authorization_url, client_secret is optional (PKCE)
			return baseValid && !!formData.authorization_url;
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
				<form onSubmit={handleSubmit}>
					<DialogHeader>
						<DialogTitle>
							{isEditMode
								? `Edit OAuth Connection: ${editConnectionName}`
								: `Configure OAuth for Integration`}
						</DialogTitle>
						<DialogDescription>
							{isEditMode
								? "Update OAuth 2.0 connection details"
								: "Set up OAuth 2.0 credentials for this integration"}
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-4 mt-4">
						<Alert>
							<Info className="h-4 w-4" />
							<AlertDescription>
								<div className="space-y-2">
									<p className="font-semibold text-sm">
										Your Redirect URI:
									</p>
									<div className="flex items-center gap-2">
										<code className="flex-1 px-2 py-1 bg-muted rounded text-xs break-all">
											{redirectUri}
										</code>
										<Button
											type="button"
											variant="outline"
											size="sm"
											onClick={handleCopyRedirectUri}
										>
											{copiedRedirect ? (
												<Check className="h-4 w-4" />
											) : (
												<Copy className="h-4 w-4" />
											)}
										</Button>
									</div>
									<p className="text-xs text-muted-foreground">
										Copy this and add it to your OAuth app's
										allowed redirect URIs before continuing
									</p>
								</div>
							</AlertDescription>
						</Alert>
						<div className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="oauth_flow_type">
									OAuth Flow Type *
								</Label>
								<Select
									value={formData.oauth_flow_type}
									onValueChange={(value) =>
										setFormData({
											...formData,
											oauth_flow_type:
												value as OAuthFlowType,
										})
									}
								>
									<SelectTrigger>
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="authorization_code">
											Authorization Code (Interactive)
										</SelectItem>
										<SelectItem value="client_credentials">
											Client Credentials
											(Service-to-Service)
										</SelectItem>
									</SelectContent>
								</Select>
								<p className="text-xs text-muted-foreground">
									{formData.oauth_flow_type ===
									"authorization_code"
										? "Requires user authorization. Use for delegated permissions."
										: "No user authorization required. Use for application permissions."}
								</p>
							</div>

							<div className="grid grid-cols-2 gap-4">
								<div className="space-y-2">
									<Label htmlFor="client_id">
										Client ID *
									</Label>
									<Input
										id="client_id"
										value={formData.client_id}
										onChange={(e) =>
											setFormData({
												...formData,
												client_id: e.target.value,
											})
										}
										placeholder="abc123..."
										required
										className="font-mono"
									/>
								</div>

								<div className="space-y-2">
									<Label htmlFor="client_secret">
										Client Secret{" "}
										{formData.oauth_flow_type ===
											"client_credentials" && "*"}
									</Label>
									<Input
										id="client_secret"
										type="password"
										value={formData.client_secret || ""}
										onChange={(e) =>
											setFormData({
												...formData,
												client_secret: e.target.value,
											})
										}
										placeholder={
											isEditMode
												? "Leave empty to keep existing..."
												: formData.oauth_flow_type ===
													  "client_credentials"
													? "Required for client credentials flow..."
													: "Optional for PKCE flow..."
										}
										required={
											formData.oauth_flow_type ===
												"client_credentials" &&
											!isEditMode
										}
									/>
									<p className="text-xs text-muted-foreground">
										{isEditMode
											? "Leave empty to keep the existing secret, or enter a new one to update"
											: formData.oauth_flow_type ===
												  "client_credentials"
												? "Required: Client credentials flow requires a client secret"
												: "Optional: Leave empty for PKCE (Proof Key for Code Exchange) flow"}
									</p>
								</div>
							</div>

							{formData.oauth_flow_type ===
								"authorization_code" && (
								<div className="space-y-2">
									<Label htmlFor="authorization_url">
										Authorization URL *
									</Label>
									<Input
										id="authorization_url"
										value={formData.authorization_url || ""}
										onChange={(e) =>
											setFormData({
												...formData,
												authorization_url:
													e.target.value,
											})
										}
										placeholder="https://provider.com/oauth/authorize"
										pattern="https://.*"
										required
										className="font-mono text-xs"
									/>
								</div>
							)}

							<div className="space-y-2">
								<Label htmlFor="token_url">Token URL *</Label>
								<Input
									id="token_url"
									value={formData.token_url}
									onChange={(e) =>
										setFormData({
											...formData,
											token_url: e.target.value,
										})
									}
									placeholder="https://provider.com/oauth/token"
									pattern="https://.*"
									required
									className="font-mono text-xs"
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="audience">
									Audience
								</Label>
								<Input
									id="audience"
									value={formData.audience || ""}
									onChange={(e) =>
										setFormData({
											...formData,
											audience: e.target.value,
										})
									}
									placeholder="https://api.example.com"
									className="font-mono text-xs"
								/>
								<p className="text-xs text-muted-foreground">
									Target API identifier sent with token
									requests. Required by some providers
									(e.g., Pax8, Auth0).
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="scopes">
									Scopes (comma or space separated)
								</Label>
								<Textarea
									id="scopes"
									value={formData.scopes}
									onChange={(e) =>
										setFormData({
											...formData,
											scopes: e.target.value,
										})
									}
									placeholder="read,write or https://graph.microsoft.com/.default"
									rows={2}
									className="font-mono text-xs"
								/>
								<p className="text-xs text-muted-foreground">
									OAuth permissions to request. Leave empty
									for default scopes.
								</p>
							</div>
						</div>
					</div>

					<DialogFooter className="mt-6">
						<Button
							type="button"
							variant="outline"
							onClick={() => onOpenChange(false)}
							disabled={
								createMutation.isPending ||
								updateMutation.isPending
							}
						>
							Cancel
						</Button>
						<Button
							type="submit"
							disabled={
								!isStep2Valid() ||
								createMutation.isPending ||
								updateMutation.isPending
							}
						>
							{isEditMode
								? updateMutation.isPending
									? "Updating..."
									: "Update Connection"
								: createMutation.isPending
									? "Creating..."
									: "Create Connection"}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
