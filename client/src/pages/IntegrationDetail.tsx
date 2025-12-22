import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
	Save,
	Loader2,
	Link as LinkIcon,
	Unlink,
	CheckCircle2,
	XCircle,
	Plus,
	AlertCircle,
	Clock,
	RotateCw,
	Settings,
	Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { toast } from "sonner";
import {
	useIntegration,
	useCreateMapping,
	useUpdateMapping,
	useDeleteMapping,
	type IntegrationMapping,
	type ConfigSchemaItem,
} from "@/services/integrations";
import { $api } from "@/lib/api-client";
import {
	useAuthorizeOAuthConnection,
	useRefreshOAuthToken,
} from "@/hooks/useOAuth";
import { getStatusLabel, isExpired, expiresSoon } from "@/lib/client-types";
import { CreateOAuthConnectionDialog } from "@/components/oauth/CreateOAuthConnectionDialog";
import { CreateIntegrationDialog } from "@/components/integrations/CreateIntegrationDialog";

interface MappingFormData {
	organization_id: string;
	entity_id: string;
	entity_name: string;
	oauth_token_id?: string;
	config: Record<string, unknown>;
}

interface OrgWithMapping {
	id: string;
	name: string;
	mapping?: IntegrationMapping;
	formData: MappingFormData;
	isDirty: boolean;
}

export function IntegrationDetail() {
	const { id: integrationId } = useParams<{ id: string }>();
	const queryClient = useQueryClient();

	const [orgsWithMappings, setOrgsWithMappings] = useState<OrgWithMapping[]>(
		[],
	);
	const [oauthConfigDialogOpen, setOAuthConfigDialogOpen] = useState(false);
	const [editDialogOpen, setEditDialogOpen] = useState(false);

	// Fetch integration details (includes mappings and OAuth config)
	const {
		data: integration,
		isLoading: isLoadingIntegration,
		refetch: refetchIntegration,
	} = useIntegration(integrationId || "");

	// Fetch organizations
	const { data: orgsData, isLoading: isLoadingOrgs } = $api.useQuery(
		"get",
		"/api/organizations",
	);

	const createMutation = useCreateMapping();
	const updateMutation = useUpdateMapping();
	const deleteMutation = useDeleteMapping();
	const authorizeMutation = useAuthorizeOAuthConnection();
	const refreshMutation = useRefreshOAuthToken();

	const organizations = Array.isArray(orgsData) ? orgsData : [];
	const mappings = integration?.mappings || [];

	// OAuth config from integration (now returned directly from GET /api/integrations/{id})
	const oauthConfig = integration?.oauth_config;

	// OAuth status helpers using the oauth_config from integration
	const isOAuthConnected = oauthConfig?.status === "completed";
	const isOAuthExpired =
		oauthConfig?.expires_at && isExpired(oauthConfig.expires_at);
	const isOAuthExpiringSoon =
		oauthConfig?.expires_at &&
		!isOAuthExpired &&
		expiresSoon(oauthConfig.expires_at);
	const canUseAuthCodeFlow =
		oauthConfig && oauthConfig.oauth_flow_type !== "client_credentials";

	// Combine organizations with their mappings
	useEffect(() => {
		if (!isLoadingOrgs && !isLoadingIntegration) {
			const combined: OrgWithMapping[] = organizations.map(
				(org: { id: string; name: string }) => {
					const existingMapping = mappings.find(
						(m) => m.organization_id === org.id,
					);

					const defaultConfig: Record<string, unknown> = {};
					integration?.config_schema?.forEach((field) => {
						if (field.default !== null && field.default !== undefined) {
							defaultConfig[field.key] = field.default;
						}
					});

					return {
						id: org.id,
						name: org.name,
						mapping: existingMapping,
						formData: existingMapping
							? {
									organization_id: existingMapping.organization_id,
									entity_id: existingMapping.entity_id,
									entity_name: existingMapping.entity_name || "",
									oauth_token_id:
										existingMapping.oauth_token_id || undefined,
									config: existingMapping.config || defaultConfig,
								}
							: {
									organization_id: org.id,
									entity_id: "",
									entity_name: "",
									config: defaultConfig,
								},
						isDirty: false,
					};
				},
			);
			setOrgsWithMappings(combined);
		}
	}, [organizations, mappings, isLoadingOrgs, isLoadingIntegration, integration]);

	// Listen for OAuth success messages from popup window
	useEffect(() => {
		const handleMessage = (event: MessageEvent) => {
			// Verify origin for security
			if (event.origin !== window.location.origin) {
				return;
			}

			// Check if this is an OAuth success message
			if (event.data?.type === "oauth_success") {
				// Refresh integration (includes OAuth config)
				refetchIntegration();
				toast.success("OAuth connection established successfully");
			}
		};

		window.addEventListener("message", handleMessage);

		// Cleanup listener on unmount
		return () => {
			window.removeEventListener("message", handleMessage);
		};
	}, [refetchIntegration]);

	const updateOrgMapping = (
		orgId: string,
		updates: Partial<MappingFormData>,
	) => {
		setOrgsWithMappings((prev) =>
			prev.map((org) =>
				org.id === orgId
					? {
							...org,
							formData: { ...org.formData, ...updates },
							isDirty: true,
						}
					: org,
			),
		);
	};

	const updateConfigField = (
		orgId: string,
		key: string,
		value: unknown,
	) => {
		setOrgsWithMappings((prev) =>
			prev.map((org) =>
				org.id === orgId
					? {
							...org,
							formData: {
								...org.formData,
								config: { ...org.formData.config, [key]: value },
							},
							isDirty: true,
						}
					: org,
			),
		);
	};

	const handleSaveMapping = async (org: OrgWithMapping) => {
		if (!integrationId) return;

		try {
			if (org.mapping) {
				// Update existing mapping
				await updateMutation.mutateAsync({
					params: {
						path: {
							integration_id: integrationId,
							mapping_id: org.mapping.id,
						},
					},
					body: {
						entity_id: org.formData.entity_id,
						entity_name: org.formData.entity_name || undefined,
						oauth_token_id: org.formData.oauth_token_id || undefined,
						config:
							Object.keys(org.formData.config).length > 0
								? org.formData.config
								: undefined,
					},
				});
				toast.success(`Mapping updated for ${org.name}`);
			} else {
				// Create new mapping
				await createMutation.mutateAsync({
					params: { path: { integration_id: integrationId } },
					body: {
						organization_id: org.id,
						entity_id: org.formData.entity_id,
						entity_name: org.formData.entity_name || undefined,
						oauth_token_id: org.formData.oauth_token_id || undefined,
						config:
							Object.keys(org.formData.config).length > 0
								? org.formData.config
								: undefined,
					},
				});
				toast.success(`Mapping created for ${org.name}`);
			}

			// Invalidate and refetch
			queryClient.invalidateQueries({
				queryKey: ["integrations", integrationId, "mappings"],
			});

			// Mark as not dirty
			setOrgsWithMappings((prev) =>
				prev.map((o) => (o.id === org.id ? { ...o, isDirty: false } : o)),
			);
		} catch (error) {
			console.error("Failed to save mapping:", error);
			toast.error(`Failed to save mapping for ${org.name}`);
		}
	};

	const handleDeleteMapping = async (org: OrgWithMapping) => {
		if (!integrationId || !org.mapping) return;

		try {
			await deleteMutation.mutateAsync({
				params: {
					path: {
						integration_id: integrationId,
						mapping_id: org.mapping.id,
					},
				},
			});
			toast.success(`Mapping deleted for ${org.name}`);

			// Invalidate queries
			queryClient.invalidateQueries({
				queryKey: ["integrations", integrationId, "mappings"],
			});
		} catch (error) {
			console.error("Failed to delete mapping:", error);
			toast.error(`Failed to delete mapping for ${org.name}`);
		}
	};

	// Handle main integration OAuth connect
	const handleIntegrationOAuthConnect = async () => {
		if (!integration?.has_oauth_config) return;

		const connectionName = integration.name;
		const redirectUri = `${window.location.origin}/oauth/callback/${connectionName}`;

		authorizeMutation.mutate(
			{
				params: {
					path: { connection_name: connectionName },
					query: { redirect_uri: redirectUri },
				},
			},
			{
				onSuccess: (response) => {
					const width = 600;
					const height = 700;
					const left = window.screenX + (window.outerWidth - width) / 2;
					const top = window.screenY + (window.outerHeight - height) / 2;
					window.open(
						response.authorization_url,
						"oauth_popup",
						`width=${width},height=${height},left=${left},top=${top},scrollbars=yes`,
					);
				},
			},
		);
	};

	// Handle main integration OAuth refresh
	const handleIntegrationOAuthRefresh = async () => {
		if (!integration?.has_oauth_config) return;

		try {
			await refreshMutation.mutateAsync({
				params: { path: { connection_name: integration.name } },
			});
			refetchIntegration();
			toast.success("Token refreshed successfully");
		} catch {
			// Error is already handled by the mutation's onError
		}
	};

	const handleSaveAll = async () => {
		const dirtyMappings = orgsWithMappings.filter(
			(org) => org.isDirty && org.formData.entity_id,
		);

		if (dirtyMappings.length === 0) {
			toast.info("No changes to save");
			return;
		}

		let successCount = 0;
		let errorCount = 0;

		for (const org of dirtyMappings) {
			try {
				await handleSaveMapping(org);
				successCount++;
			} catch {
				errorCount++;
			}
		}

		if (errorCount === 0) {
			toast.success(`Saved ${successCount} mapping(s)`);
		} else {
			toast.warning(
				`Saved ${successCount} mapping(s), ${errorCount} failed`,
			);
		}
	};

	const renderConfigField = (
		org: OrgWithMapping,
		field: ConfigSchemaItem,
	) => {
		const value = org.formData.config[field.key];

		switch (field.type) {
			case "bool":
				return (
					<div className="flex items-center gap-2">
						<input
							type="checkbox"
							checked={Boolean(value)}
							onChange={(e) =>
								updateConfigField(org.id, field.key, e.target.checked)
							}
							className="rounded"
						/>
						<Label className="text-xs">{field.key}</Label>
					</div>
				);
			case "int":
				return (
					<Input
						type="number"
						placeholder={field.key}
						value={value as number}
						onChange={(e) =>
							updateConfigField(
								org.id,
								field.key,
								parseInt(e.target.value),
							)
						}
						className="h-8 text-sm"
					/>
				);
			case "secret":
			case "string":
			default:
				return (
					<Input
						type={field.type === "secret" ? "password" : "text"}
						placeholder={field.key}
						value={(value as string) || ""}
						onChange={(e) =>
							updateConfigField(org.id, field.key, e.target.value)
						}
						className="h-8 text-sm"
					/>
				);
		}
	};

	const isLoading = isLoadingIntegration || isLoadingOrgs;

	if (isLoading) {
		return (
			<div className="space-y-6">
				<Skeleton className="h-12 w-64" />
				<Skeleton className="h-64 w-full" />
			</div>
		);
	}

	if (!integration) {
		return (
			<div className="flex flex-col items-center justify-center py-12">
				<XCircle className="h-12 w-12 text-destructive" />
				<h3 className="mt-4 text-lg font-semibold">
					Integration not found
				</h3>
				<Link to="/integrations">
					<Button variant="outline" className="mt-4">
						Back to Integrations
					</Button>
				</Link>
			</div>
		);
	}

	const dirtyCount = orgsWithMappings.filter((org) => org.isDirty).length;

	return (
		<div className="space-y-6">
			{/* Header */}
			<div>
				<div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
					<Link
						to="/integrations"
						className="hover:text-foreground transition-colors"
					>
						Integrations
					</Link>
					<span>/</span>
					<span>{integration.name}</span>
				</div>
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-4xl font-extrabold tracking-tight">
							{integration.name}
						</h1>
						<p className="mt-2 text-muted-foreground">
							{(
								integration as typeof integration & {
									description?: string;
								}
							).description ||
								"Configure OAuth, data providers, and organization mappings"}
						</p>
					</div>
					<div className="flex items-center gap-2">
						<Button
							variant="outline"
							size="icon"
							onClick={() => setEditDialogOpen(true)}
							title="Edit integration"
						>
							<Pencil className="h-4 w-4" />
						</Button>
						<Button
							variant="outline"
							size="icon"
							onClick={handleSaveAll}
							disabled={dirtyCount === 0}
							title={`Save All${dirtyCount > 0 ? ` (${dirtyCount})` : ""}`}
						>
							<Save className="h-4 w-4" />
						</Button>
					</div>
				</div>
			</div>

			{/* Config Defaults & OAuth Status */}
			<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
				{/* Configuration Defaults */}
				<Card>
					<CardHeader className="pb-3">
						<CardTitle className="text-base">
							Configuration Defaults
						</CardTitle>
						<CardDescription>
							Default config values for new mappings
						</CardDescription>
					</CardHeader>
					<CardContent>
						{integration.config_schema &&
						integration.config_schema.length > 0 ? (
							<div className="space-y-2">
								{integration.config_schema.map((field) => (
									<div
										key={field.key}
										className="flex items-center justify-between text-sm"
									>
										<span className="text-muted-foreground">
											{field.key}
											{field.required && (
												<span className="text-destructive ml-1">
													*
												</span>
											)}
										</span>
										<span className="font-mono text-xs bg-muted px-2 py-0.5 rounded">
											{field.default !== null &&
											field.default !== undefined
												? String(field.default)
												: "—"}
										</span>
									</div>
								))}
							</div>
						) : (
							<div className="text-center py-4">
								<Settings className="h-8 w-8 text-muted-foreground mx-auto" />
								<p className="mt-2 text-sm text-muted-foreground">
									No configuration schema defined
								</p>
								<Button
									variant="outline"
									size="sm"
									className="mt-3"
									onClick={() => setEditDialogOpen(true)}
								>
									<Pencil className="h-3 w-3 mr-2" />
									Edit Integration
								</Button>
							</div>
						)}
					</CardContent>
				</Card>

				{/* Compact OAuth Status */}
				<Card className="hover:shadow-md transition-shadow">
					<CardHeader className="pb-3">
						<div className="flex items-center justify-between">
							<div>
								<CardTitle className="text-base">OAuth</CardTitle>
								<CardDescription>
									Connection status and authentication
								</CardDescription>
							</div>
							<div className="flex items-center gap-2">
								{oauthConfig && (
									<Badge variant="outline" className="text-xs">
										{oauthConfig.oauth_flow_type}
									</Badge>
								)}
								{isOAuthConnected ? (
									<CheckCircle2 className="h-4 w-4 text-green-600" />
								) : oauthConfig?.status === "failed" ? (
									<XCircle className="h-4 w-4 text-red-600" />
								) : integration.has_oauth_config ? (
									<AlertCircle className="h-4 w-4 text-yellow-600" />
								) : null}
							</div>
						</div>
					</CardHeader>
					<CardContent>
						{integration.has_oauth_config ? (
							<div className="space-y-3">
								{/* Expiration warnings */}
								{isOAuthExpired && (
									<div className="flex items-center gap-2 p-2 rounded bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 text-sm">
										<AlertCircle className="h-4 w-4" />
										Token expired - reconnect required
									</div>
								)}
								{isOAuthExpiringSoon && !isOAuthExpired && (
									<div className="flex items-center gap-2 p-2 rounded bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300 text-sm">
										<Clock className="h-4 w-4" />
										Token expires soon - consider refreshing
									</div>
								)}

								{/* Connection status */}
								<div className="flex items-center justify-between">
									<span className="text-sm text-muted-foreground">
										Status
									</span>
									<span className="text-sm font-medium">
										{isOAuthConnected
											? "Connected"
											: oauthConfig?.status === "failed"
												? "Failed"
												: oauthConfig
													? getStatusLabel(oauthConfig.status)
													: "Not Connected"}
									</span>
								</div>

								{oauthConfig?.expires_at && !isOAuthExpired && (
									<div className="flex items-center justify-between">
										<span className="text-sm text-muted-foreground">
											Expires
										</span>
										<span className="text-sm font-mono">
											{new Date(
												oauthConfig.expires_at,
											).toLocaleDateString()}
										</span>
									</div>
								)}

								{/* Action buttons */}
								<div className="flex items-center gap-2 pt-1">
									{canUseAuthCodeFlow && (
										<Button
											variant={
												isOAuthConnected
													? "outline"
													: "default"
											}
											size="sm"
											className="flex-1"
											onClick={handleIntegrationOAuthConnect}
											disabled={authorizeMutation.isPending}
										>
											{authorizeMutation.isPending ? (
												<>
													<Loader2 className="mr-2 h-3 w-3 animate-spin" />
													Connecting...
												</>
											) : isOAuthConnected ? (
												"Reconnect"
											) : (
												"Connect"
											)}
										</Button>
									)}
									{isOAuthConnected && oauthConfig?.expires_at && (
										<Button
											variant="outline"
											size="sm"
											onClick={handleIntegrationOAuthRefresh}
											disabled={refreshMutation.isPending}
										>
											{refreshMutation.isPending ? (
												<Loader2 className="h-3 w-3 animate-spin" />
											) : (
												<RotateCw className="h-3 w-3" />
											)}
										</Button>
									)}
								</div>
							</div>
						) : (
							<div className="text-center py-4">
								<LinkIcon className="h-8 w-8 text-muted-foreground mx-auto" />
								<p className="mt-2 text-sm text-muted-foreground">
									No OAuth configured
								</p>
								<Button
									variant="outline"
									size="sm"
									className="mt-3"
									onClick={() => setOAuthConfigDialogOpen(true)}
								>
									<Plus className="h-3 w-3 mr-2" />
									Configure
								</Button>
							</div>
						)}
					</CardContent>
				</Card>
			</div>

			{/* Mappings Table */}
			<Card>
				<CardHeader>
					<CardTitle>Organization Mappings</CardTitle>
					<CardDescription>
						Configure how each organization maps to external entities
					</CardDescription>
				</CardHeader>
				<CardContent>
					{!integration.list_entities_data_provider_id ? (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<Settings className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								No Data Provider Configured
							</h3>
							<p className="mt-2 text-sm text-muted-foreground max-w-md">
								Configure a data provider to populate the entity
								dropdown. Edit the integration to select one.
							</p>
							<Button
								variant="outline"
								className="mt-4"
								onClick={() => setEditDialogOpen(true)}
							>
								<Pencil className="h-4 w-4 mr-2" />
								Edit Integration
							</Button>
						</div>
					) : orgsWithMappings.length === 0 ? (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<LinkIcon className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								No organizations available
							</h3>
							<p className="mt-2 text-sm text-muted-foreground">
								Create organizations first to set up mappings
							</p>
						</div>
					) : (
						<div className="rounded-md border overflow-x-auto">
							<DataTable>
								<DataTableHeader>
									<DataTableRow>
										<DataTableHead className="w-48">
											Organization
										</DataTableHead>
										<DataTableHead className="w-64">
											External Entity
										</DataTableHead>
										{integration.config_schema?.map((field) => (
											<DataTableHead
												key={field.key}
												className="w-48"
											>
												{field.key}
												{field.required && (
													<span className="text-destructive ml-1">
														*
													</span>
												)}
											</DataTableHead>
										))}
										<DataTableHead className="w-24">
											Status
										</DataTableHead>
										<DataTableHead className="w-32 text-right">
											Actions
										</DataTableHead>
									</DataTableRow>
								</DataTableHeader>
								<DataTableBody>
									{orgsWithMappings.map((org) => (
										<DataTableRow key={org.id}>
											<DataTableCell className="font-medium">
												{org.name}
											</DataTableCell>
											<DataTableCell>
												<Input
													placeholder="entity-id"
													value={org.formData.entity_id}
													onChange={(e) =>
														updateOrgMapping(org.id, {
															entity_id:
																e.target.value,
															entity_name:
																e.target.value,
														})
													}
													className="h-8 text-sm"
												/>
											</DataTableCell>
											{integration.config_schema?.map(
												(field) => (
													<DataTableCell key={field.key}>
														{renderConfigField(
															org,
															field,
														)}
													</DataTableCell>
												),
											)}
											<DataTableCell>
												{org.mapping ? (
													<Badge
														variant="default"
														className="bg-green-600"
													>
														<CheckCircle2 className="h-3 w-3 mr-1" />
														Mapped
													</Badge>
												) : org.formData.entity_id ? (
													<Badge variant="secondary">
														<Plus className="h-3 w-3 mr-1" />
														New
													</Badge>
												) : (
													<Badge variant="outline">
														Not Mapped
													</Badge>
												)}
												{org.isDirty && (
													<Badge
														variant="secondary"
														className="ml-1"
													>
														*
													</Badge>
												)}
											</DataTableCell>
											<DataTableCell className="text-right">
												<div className="flex gap-1 justify-end">
													<Button
														size="sm"
														variant="ghost"
														onClick={() =>
															handleSaveMapping(org)
														}
														disabled={
															!org.isDirty ||
															!org.formData.entity_id
														}
														title="Save"
													>
														<Save className="h-4 w-4" />
													</Button>
													{org.mapping && (
														<Button
															size="sm"
															variant="ghost"
															onClick={() =>
																handleDeleteMapping(
																	org,
																)
															}
															disabled={
																deleteMutation.isPending
															}
															title="Delete mapping"
															className="text-red-600 hover:text-red-700"
														>
															<Unlink className="h-4 w-4" />
														</Button>
													)}
												</div>
											</DataTableCell>
										</DataTableRow>
									))}
								</DataTableBody>
							</DataTable>
						</div>
					)}
				</CardContent>
			</Card>

			{/* OAuth Configuration Dialog */}
			{integrationId && (
				<CreateOAuthConnectionDialog
					open={oauthConfigDialogOpen}
					onOpenChange={setOAuthConfigDialogOpen}
					integrationId={integrationId}
				/>
			)}

			{/* Edit Integration Dialog */}
			<CreateIntegrationDialog
				open={editDialogOpen}
				onOpenChange={setEditDialogOpen}
				editIntegrationId={integrationId}
				initialData={integration}
			/>
		</div>
	);
}
