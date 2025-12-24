import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
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
	MoreVertical,
	Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import {
	useIntegration,
	useCreateMapping,
	useUpdateMapping,
	useDeleteMapping,
	useUpdateIntegration,
	useUpdateIntegrationConfig,
	type IntegrationMapping,
} from "@/services/integrations";
import { $api } from "@/lib/api-client";
import {
	useAuthorizeOAuthConnection,
	useRefreshOAuthToken,
	useDeleteOAuthConnection,
} from "@/hooks/useOAuth";
import { getStatusLabel, isExpired, expiresSoon } from "@/lib/client-types";
import { CreateOAuthConnectionDialog } from "@/components/oauth/CreateOAuthConnectionDialog";
import { CreateIntegrationDialog } from "@/components/integrations/CreateIntegrationDialog";
import { OrgConfigDialog } from "@/components/integrations/OrgConfigDialog";
import { ConfigOverridesTab } from "@/components/integrations/ConfigOverridesTab";
import { useIntegrationEntities } from "@/hooks/useIntegrationEntities";
import { useAutoMatch } from "@/hooks/useAutoMatch";
import { EntitySelector } from "@/components/integrations/EntitySelector";
import { AutoMatchControls } from "@/components/integrations/AutoMatchControls";
import { MatchSuggestionBadge } from "@/components/integrations/MatchSuggestionBadge";

// Format datetime with relative time for dates within 7 days
const formatDateTime = (dateStr?: string | null) => {
	if (!dateStr) return "Never";

	// Parse the date - backend sends UTC timestamps without 'Z' suffix
	// Add 'Z' to explicitly mark it as UTC, then JavaScript will convert to local time
	const utcDateStr = dateStr.endsWith("Z") ? dateStr : `${dateStr}Z`;
	const date = new Date(utcDateStr);
	const now = new Date();
	const diffMs = date.getTime() - now.getTime();
	const diffMins = Math.floor(Math.abs(diffMs) / 60000);
	const diffHours = Math.floor(Math.abs(diffMs) / 3600000);
	const diffDays = Math.floor(Math.abs(diffMs) / 86400000);

	// For dates within 7 days, show relative time
	if (diffDays < 7) {
		// Past dates (negative diffMs) - show "X ago"
		if (diffMs < 0) {
			if (diffMins < 60) {
				return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
			} else if (diffHours < 24) {
				return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
			} else {
				return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
			}
		}

		// Future dates (positive diffMs) - show "in X"
		if (diffMs > 0) {
			if (diffMins < 60) {
				return `in ${diffMins} minute${diffMins !== 1 ? "s" : ""}`;
			} else if (diffHours < 24) {
				return `in ${diffHours} hour${diffHours !== 1 ? "s" : ""}`;
			} else {
				return `in ${diffDays} day${diffDays !== 1 ? "s" : ""}`;
			}
		}

		// Exactly now
		return "just now";
	}

	// Absolute dates for far past/future (converts to user's local timezone)
	return date.toLocaleString(undefined, {
		month: "short",
		day: "numeric",
		year: "numeric",
		hour: "numeric",
		minute: "2-digit",
	});
};

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

	const [oauthConfigDialogOpen, setOAuthConfigDialogOpen] = useState(false);
	const [editDialogOpen, setEditDialogOpen] = useState(false);
	const [configDialogOpen, setConfigDialogOpen] = useState(false);
	const [defaultsDialogOpen, setDefaultsDialogOpen] = useState(false);
	const [defaultsFormValues, setDefaultsFormValues] = useState<
		Record<string, unknown>
	>({});
	const [selectedOrgForConfig, setSelectedOrgForConfig] = useState<
		OrgWithMapping | undefined
	>();
	const [deleteMappingConfirm, setDeleteMappingConfirm] =
		useState<OrgWithMapping | null>(null);
	const [isSavingAll, setIsSavingAll] = useState(false);
	const [editingOAuthConfig, setEditingOAuthConfig] = useState(false);
	const [deleteOAuthDialogOpen, setDeleteOAuthDialogOpen] = useState(false);

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
	const updateIntegrationMutation = useUpdateIntegration();
	const updateConfigMutation = useUpdateIntegrationConfig();
	const authorizeMutation = useAuthorizeOAuthConnection();
	const refreshMutation = useRefreshOAuthToken();
	const deleteOAuthMutation = useDeleteOAuthConnection();

	// Memoize to stabilize references for the useEffect that combines them
	const organizations = useMemo(
		() => (Array.isArray(orgsData) ? orgsData : []),
		[orgsData],
	);
	const mappings = useMemo(
		() => integration?.mappings || [],
		[integration?.mappings],
	);

	// Fetch entities from data provider
	const { data: entities = [], isLoading: isLoadingEntities } =
		useIntegrationEntities(integration?.list_entities_data_provider_id);

	// Auto-match hook
	const {
		suggestions: autoMatchSuggestions,
		matchStats,
		isMatching,
		runAutoMatch,
		acceptSuggestion,
		rejectSuggestion,
		acceptAll,
		clearSuggestions,
	} = useAutoMatch({
		organizations: organizations.map(
			(org: { id: string; name: string }) => ({
				id: org.id,
				name: org.name,
			}),
		),
		entities: entities.map((e) => ({ value: e.value, label: e.label })),
		existingMappings: mappings.map((m) => ({
			organization_id: m.organization_id,
			entity_id: m.entity_id,
		})),
	});

	// OAuth config from integration (now returned directly from GET /api/integrations/{id})
	const oauthConfig = integration?.oauth_config;

	// OAuth status helpers using the oauth_config from integration
	const isOAuthConnected = oauthConfig?.status === "completed";
	const isOAuthExpired =
		oauthConfig?.expires_at && isExpired(oauthConfig.expires_at);
	const isOAuthExpiringSoon =
		oauthConfig?.expires_at &&
		!isOAuthExpired &&
		expiresSoon(oauthConfig.expires_at, 15); // 15 minutes matches the refresh scheduler interval
	const canUseAuthCodeFlow =
		oauthConfig && oauthConfig.oauth_flow_type !== "client_credentials";

	// Track dirty state for each org (user edits)
	const [dirtyEdits, setDirtyEdits] = useState<
		Map<string, { formData: Partial<MappingFormData>; isDirty: boolean }>
	>(new Map());

	// Combine organizations with their mappings using useMemo (no effect needed)
	const orgsWithMappings = useMemo((): OrgWithMapping[] => {
		if (isLoadingOrgs || isLoadingIntegration) {
			return [];
		}
		return organizations.map((org: { id: string; name: string }) => {
			const existingMapping = mappings.find(
				(m) => m.organization_id === org.id,
			);

			// Check for dirty edits from user
			const dirtyEdit = dirtyEdits.get(org.id);

			const baseFormData: MappingFormData = existingMapping
				? {
						organization_id: existingMapping.organization_id,
						entity_id: existingMapping.entity_id,
						entity_name: existingMapping.entity_name || "",
						oauth_token_id:
							existingMapping.oauth_token_id || undefined,
						// Use actual mapping config only - don't fall back to defaults
						// OrgConfigDialog shows defaults separately via defaultConfig prop
						config: existingMapping.config || {},
					}
				: {
						organization_id: org.id,
						entity_id: "",
						entity_name: "",
						// New mappings start empty - defaults shown separately in dialog
						config: {},
					};

			return {
				id: org.id,
				name: org.name,
				mapping: existingMapping,
				formData: dirtyEdit
					? { ...baseFormData, ...dirtyEdit.formData }
					: baseFormData,
				isDirty: dirtyEdit?.isDirty ?? false,
			};
		});
	}, [
		organizations,
		mappings,
		isLoadingOrgs,
		isLoadingIntegration,
		integration,
		dirtyEdits,
	]);

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

	// Warn about unsaved changes when navigating away
	useEffect(() => {
		const dirtyCount = orgsWithMappings.filter((org) => org.isDirty).length;

		if (dirtyCount > 0) {
			const handleBeforeUnload = (e: BeforeUnloadEvent) => {
				e.preventDefault();
				// Modern browsers require returnValue to be set
				e.returnValue = "";
			};

			window.addEventListener("beforeunload", handleBeforeUnload);

			return () => {
				window.removeEventListener("beforeunload", handleBeforeUnload);
			};
		}

		// Return cleanup function for the case when dirtyCount is 0
		return () => {};
	}, [orgsWithMappings]);

	const updateOrgMapping = (
		orgId: string,
		updates: Partial<MappingFormData>,
	) => {
		setDirtyEdits((prev) => {
			const next = new Map(prev);
			const existing = next.get(orgId);
			next.set(orgId, {
				formData: { ...(existing?.formData || {}), ...updates },
				isDirty: true,
			});
			return next;
		});
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
						oauth_token_id:
							org.formData.oauth_token_id || undefined,
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
						oauth_token_id:
							org.formData.oauth_token_id || undefined,
						config:
							Object.keys(org.formData.config).length > 0
								? org.formData.config
								: undefined,
					},
				});
				toast.success(`Mapping created for ${org.name}`);
			}

			// Mark as not dirty (remove from dirty edits)
			setDirtyEdits((prev) => {
				const next = new Map(prev);
				next.delete(org.id);
				return next;
			});
			// Cache invalidation in useCreateMapping/useUpdateMapping handles refetch
		} catch (error) {
			console.error("Failed to save mapping:", error);
			toast.error(`Failed to save mapping for ${org.name}`);
		}
	};

	const handleDeleteMappingClick = (org: OrgWithMapping) => {
		setDeleteMappingConfirm(org);
	};

	const handleDeleteMappingConfirm = async () => {
		const org = deleteMappingConfirm;
		if (!integrationId || !org?.mapping) {
			setDeleteMappingConfirm(null);
			return;
		}

		setDeleteMappingConfirm(null);

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
			// Cache invalidation in useDeleteMapping handles refetch
		} catch (error) {
			console.error("Failed to delete mapping:", error);
			toast.error(`Failed to delete mapping for ${org.name}`);
		}
	};

	// Handle main integration OAuth connect
	const handleIntegrationOAuthConnect = async () => {
		if (!integration?.has_oauth_config || !integrationId) return;

		const redirectUri = `${window.location.origin}/oauth/callback/${integrationId}`;

		authorizeMutation.mutate(
			{
				params: {
					path: { connection_name: integrationId },
					query: { redirect_uri: redirectUri },
				},
			},
			{
				onSuccess: (response) => {
					const width = 600;
					const height = 700;
					const left =
						window.screenX + (window.outerWidth - width) / 2;
					const top =
						window.screenY + (window.outerHeight - height) / 2;
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
		if (!integration?.has_oauth_config || !integrationId) return;

		try {
			await refreshMutation.mutateAsync({
				params: { path: { connection_name: integrationId } },
			});
			refetchIntegration();
			toast.success("Token refreshed successfully");
		} catch {
			// Error is already handled by the mutation's onError
		}
	};

	// Handle OAuth config deletion
	const handleDeleteOAuthConfig = async () => {
		if (!integrationId) return;

		try {
			await deleteOAuthMutation.mutateAsync({
				params: { path: { connection_name: integrationId } },
			});
			setDeleteOAuthDialogOpen(false);
			// The mutation's onSuccess already handles cache invalidation and toast
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

		setIsSavingAll(true);
		try {
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
		} finally {
			setIsSavingAll(false);
		}
	};

	const handleOpenConfigDialog = (orgId: string) => {
		const org = orgsWithMappings.find((o) => o.id === orgId);
		if (org) {
			setSelectedOrgForConfig(org);
			setConfigDialogOpen(true);
		}
	};

	const handleSaveOrgConfig = async (config: Record<string, unknown>) => {
		if (!selectedOrgForConfig || !integrationId) return;

		// Only save if mapping exists (config is per-mapping)
		if (!selectedOrgForConfig.mapping) {
			toast.error("Save the mapping first before configuring");
			throw new Error("No mapping exists");
		}

		try {
			await updateMutation.mutateAsync({
				params: {
					path: {
						integration_id: integrationId,
						mapping_id: selectedOrgForConfig.mapping.id,
					},
				},
				body: {
					entity_id: selectedOrgForConfig.formData.entity_id,
					entity_name:
						selectedOrgForConfig.formData.entity_name || undefined,
					oauth_token_id:
						selectedOrgForConfig.formData.oauth_token_id ||
						undefined,
					config: Object.keys(config).length > 0 ? config : undefined,
				},
			});
			toast.success(
				`Configuration saved for ${selectedOrgForConfig.name}`,
			);
			// Cache invalidation in useUpdateMapping handles refetch
		} catch (error) {
			console.error("Failed to save config:", error);
			toast.error(
				`Failed to save configuration for ${selectedOrgForConfig.name}`,
			);
			throw error; // Re-throw so dialog knows save failed
		}
	};

	const hasNonDefaultConfig = (org: OrgWithMapping): boolean => {
		if (!org.mapping?.config || !integration?.config_schema) return false;

		// Use config_defaults from the integration
		const defaultConfig = integration.config_defaults ?? {};

		return integration.config_schema.some((field) => {
			const currentValue = org.mapping?.config?.[field.key];
			const defaultValue = defaultConfig[field.key];
			return currentValue !== defaultValue;
		});
	};

	// Configuration Defaults Dialog handlers
	const handleOpenDefaultsDialog = () => {
		if (!integration?.config_schema) return;
		// Initialize form with current default values from config_defaults
		const currentDefaults: Record<string, unknown> = {};
		integration.config_schema.forEach((field) => {
			currentDefaults[field.key] =
				integration.config_defaults?.[field.key] ?? "";
		});
		setDefaultsFormValues(currentDefaults);
		setDefaultsDialogOpen(true);
	};

	const handleSaveDefaults = async () => {
		if (!integrationId || !integration?.config_schema) return;

		// Validate form values before save
		const validationErrors: string[] = [];
		for (const field of integration.config_schema) {
			const value = defaultsFormValues[field.key];

			// Skip empty values (they're allowed)
			if (value === "" || value === null || value === undefined) {
				continue;
			}

			// Validate int fields
			if (field.type === "int") {
				const numValue =
					typeof value === "string" ? parseInt(value) : value;
				if (isNaN(numValue as number)) {
					validationErrors.push(
						`${field.key} must be a valid integer`,
					);
				}
			}

			// Validate JSON fields
			if (field.type === "json") {
				if (typeof value === "string") {
					try {
						JSON.parse(value);
					} catch {
						validationErrors.push(
							`${field.key} must be valid JSON`,
						);
					}
				}
			}
		}

		if (validationErrors.length > 0) {
			toast.error(validationErrors.join(", "));
			return;
		}

		try {
			// Build config object from form values
			const config: Record<string, unknown> = {};
			for (const [key, value] of Object.entries(defaultsFormValues)) {
				// Only include non-empty values
				if (value !== "" && value !== null && value !== undefined) {
					config[key] = value;
				}
			}

			await updateConfigMutation.mutateAsync({
				params: { path: { integration_id: integrationId } },
				body: { config },
			});

			toast.success("Configuration defaults updated");
			setDefaultsDialogOpen(false);
		} catch (error) {
			console.error("Failed to update defaults:", error);
			toast.error("Failed to update configuration defaults");
		}
	};

	const handleAcceptSuggestion = (orgId: string) => {
		const suggestion = acceptSuggestion(orgId);
		if (suggestion) {
			updateOrgMapping(orgId, {
				entity_id: suggestion.entityId,
				entity_name: suggestion.entityName,
			});
		}
	};

	const handleAcceptAllSuggestions = () => {
		const suggestions = acceptAll();
		suggestions.forEach((suggestion) => {
			updateOrgMapping(suggestion.organizationId, {
				entity_id: suggestion.entityId,
				entity_name: suggestion.entityName,
			});
		});
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
							disabled={dirtyCount === 0 || isSavingAll}
							title={`Save All${dirtyCount > 0 ? ` (${dirtyCount})` : ""}`}
						>
							{isSavingAll ? (
								<Loader2 className="h-4 w-4 animate-spin" />
							) : (
								<Save className="h-4 w-4" />
							)}
						</Button>
					</div>
				</div>
			</div>

			{/* Config Defaults & OAuth Status */}
			<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
				{/* Configuration Defaults */}
				<Card>
					<CardHeader className="pb-3">
						<div className="flex items-center justify-between">
							<div>
								<CardTitle className="text-base">
									Configuration Defaults
								</CardTitle>
								<CardDescription>
									Default config values for new mappings
								</CardDescription>
							</div>
							{integration.config_schema &&
								integration.config_schema.length > 0 && (
									<Button
										variant="outline"
										size="sm"
										onClick={handleOpenDefaultsDialog}
									>
										<Pencil className="h-3 w-3 mr-1" />
										Edit
									</Button>
								)}
						</div>
					</CardHeader>
					<CardContent>
						{/* Default Entity ID section */}
						<div className="mb-4">
							<div className="flex items-center justify-between text-sm">
								<div className="flex flex-col">
									<span className="text-muted-foreground">
										Default{" "}
										{integration.entity_id_name ||
											"Entity ID"}
									</span>
									<span className="text-xs text-muted-foreground/70">
										Used when org mapping is not set
									</span>
								</div>
								<div className="flex items-center gap-2">
									<span className="font-mono text-xs bg-muted px-2 py-0.5 rounded">
										{integration.default_entity_id || "—"}
									</span>
									<Button
										variant="ghost"
										size="sm"
										className="h-6 w-6 p-0"
										onClick={() => setEditDialogOpen(true)}
										title="Edit integration settings"
									>
										<Pencil className="h-3 w-3" />
									</Button>
								</div>
							</div>
						</div>

						{integration.config_schema &&
						integration.config_schema.length > 0 ? (
							<div className="space-y-2">
								{integration.config_schema.map((field) => {
									const defaultValue =
										integration.config_defaults?.[
											field.key
										];
									return (
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
												{defaultValue !== null &&
												defaultValue !== undefined
													? field.type === "secret"
														? "••••••••"
														: String(defaultValue)
													: "—"}
											</span>
										</div>
									);
								})}
							</div>
						) : null}
					</CardContent>
				</Card>

				{/* Compact OAuth Status */}
				<Card className="hover:shadow-md transition-shadow">
					<CardHeader className="pb-3">
						<div className="flex items-center justify-between">
							<div>
								<CardTitle className="text-base">
									OAuth
								</CardTitle>
								<CardDescription>
									Connection status and authentication
								</CardDescription>
							</div>
							<div className="flex items-center gap-2">
								{oauthConfig && (
									<Badge
										variant="outline"
										className="text-xs"
									>
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
								{integration.has_oauth_config && (
									<DropdownMenu>
										<DropdownMenuTrigger asChild>
											<Button
												variant="ghost"
												size="icon"
												className="h-8 w-8"
											>
												<MoreVertical className="h-4 w-4" />
											</Button>
										</DropdownMenuTrigger>
										<DropdownMenuContent align="end">
											<DropdownMenuItem
												onClick={() =>
													setEditingOAuthConfig(true)
												}
											>
												<Pencil className="h-4 w-4 mr-2" />
												Edit Configuration
											</DropdownMenuItem>
											<DropdownMenuItem
												onClick={() =>
													setDeleteOAuthDialogOpen(
														true,
													)
												}
												className="text-destructive focus:text-destructive"
											>
												<Trash2 className="h-4 w-4 mr-2" />
												Delete Configuration
											</DropdownMenuItem>
										</DropdownMenuContent>
									</DropdownMenu>
								)}
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

								{/* No refresh token warning */}
								{isOAuthConnected &&
									oauthConfig &&
									oauthConfig.has_refresh_token === false && (
										<div className="flex items-center gap-2 p-2 rounded bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300 text-sm">
											<AlertCircle className="h-4 w-4" />
											No refresh token - manual
											reconnection required when token
											expires
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
													? getStatusLabel(
															oauthConfig.status,
														)
													: "Not Connected"}
									</span>
								</div>

								{oauthConfig?.expires_at && !isOAuthExpired && (
									<div className="flex items-center justify-between">
										<span className="text-sm text-muted-foreground">
											Expires
										</span>
										<span className="text-sm font-mono">
											{formatDateTime(
												oauthConfig.expires_at,
											)}
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
											onClick={
												handleIntegrationOAuthConnect
											}
											disabled={
												authorizeMutation.isPending
											}
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
									{isOAuthConnected &&
										oauthConfig?.expires_at && (
											<Button
												variant="outline"
												size="sm"
												onClick={
													handleIntegrationOAuthRefresh
												}
												disabled={
													refreshMutation.isPending
												}
											>
												{refreshMutation.isPending ? (
													<>
														<Loader2 className="mr-2 h-3 w-3 animate-spin" />
														Refreshing...
													</>
												) : (
													<>
														<RotateCw className="mr-2 h-3 w-3" />
														Refresh Token
													</>
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
									onClick={() =>
										setOAuthConfigDialogOpen(true)
									}
								>
									<Plus className="h-3 w-3 mr-2" />
									Configure
								</Button>
							</div>
						)}
					</CardContent>
				</Card>
			</div>

			{/* Tabs for Mappings and Config Overrides */}
			<Tabs defaultValue="mappings" className="space-y-4">
				<TabsList>
					<TabsTrigger value="mappings">Mappings</TabsTrigger>
					<TabsTrigger value="config-overrides">
						Config Overrides
					</TabsTrigger>
				</TabsList>

				<TabsContent value="mappings">
					<Card>
						<CardHeader className="flex flex-row items-start justify-between space-y-0">
							<div>
								<CardTitle>Organization Mappings</CardTitle>
								<CardDescription>
									Configure how each organization maps to
									external entities
								</CardDescription>
							</div>
							{/* Auto-Match Controls in header */}
							{integration.list_entities_data_provider_id &&
								orgsWithMappings.length > 0 && (
									<AutoMatchControls
										onRunAutoMatch={runAutoMatch}
										onAcceptAll={handleAcceptAllSuggestions}
										onClear={clearSuggestions}
										matchStats={matchStats}
										hasSuggestions={
											autoMatchSuggestions.size > 0
										}
										isMatching={isMatching}
										disabled={isLoadingEntities}
									/>
								)}
						</CardHeader>
						<CardContent>
							{!integration.list_entities_data_provider_id ? (
								<div className="flex flex-col items-center justify-center py-12 text-center">
									<Settings className="h-12 w-12 text-muted-foreground" />
									<h3 className="mt-4 text-lg font-semibold">
										No Data Provider Configured
									</h3>
									<p className="mt-2 text-sm text-muted-foreground max-w-md">
										Configure a data provider to populate
										the entity dropdown. Edit the
										integration to select one.
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
										Create organizations first to set up
										mappings
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
												<DataTableHead className="w-24">
													Status
												</DataTableHead>
												<DataTableHead className="w-32 text-right">
													Actions
												</DataTableHead>
											</DataTableRow>
										</DataTableHeader>
										<DataTableBody>
											{orgsWithMappings.map((org) => {
												// Filter out entities already mapped to other orgs
												const usedEntityIds =
													orgsWithMappings
														.filter(
															(o) =>
																o.id !==
																	org.id &&
																o.formData
																	.entity_id,
														)
														.map(
															(o) =>
																o.formData
																	.entity_id,
														);
												const availableEntities =
													entities.filter(
														(e) =>
															e.value ===
																org.formData
																	.entity_id ||
															!usedEntityIds.includes(
																e.value,
															),
													);

												return (
													<DataTableRow key={org.id}>
														<DataTableCell className="font-medium">
															{org.name}
														</DataTableCell>
														<DataTableCell>
															{autoMatchSuggestions.has(
																org.id,
															) ? (
																<MatchSuggestionBadge
																	suggestion={
																		autoMatchSuggestions.get(
																			org.id,
																		)!
																	}
																	onAccept={() =>
																		handleAcceptSuggestion(
																			org.id,
																		)
																	}
																	onReject={() =>
																		rejectSuggestion(
																			org.id,
																		)
																	}
																/>
															) : (
																<EntitySelector
																	entities={
																		availableEntities
																	}
																	value={
																		org
																			.formData
																			.entity_id
																	}
																	onChange={(
																		value,
																		label,
																	) =>
																		updateOrgMapping(
																			org.id,
																			{
																				entity_id:
																					value,
																				entity_name:
																					label,
																			},
																		)
																	}
																	isLoading={
																		isLoadingEntities
																	}
																	placeholder="Select entity..."
																/>
															)}
														</DataTableCell>
														<DataTableCell>
															{org.mapping ? (
																<Badge
																	variant="default"
																	className="bg-green-600"
																>
																	<CheckCircle2 className="h-3 w-3 mr-1" />
																	Mapped
																</Badge>
															) : org.formData
																	.entity_id ? (
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
																		handleOpenConfigDialog(
																			org.id,
																		)
																	}
																	title="Configure"
																	className="relative"
																>
																	<Settings className="h-4 w-4" />
																	{hasNonDefaultConfig(
																		org,
																	) && (
																		<span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-blue-600" />
																	)}
																</Button>
																<Button
																	size="sm"
																	variant="ghost"
																	onClick={() =>
																		handleDeleteMappingClick(
																			org,
																		)
																	}
																	disabled={
																		!org.mapping ||
																		deleteMutation.isPending
																	}
																	title={
																		org.mapping
																			? "Unlink mapping"
																			: "No mapping to unlink"
																	}
																	className="text-red-600 hover:text-red-700 disabled:text-muted-foreground"
																>
																	<Unlink className="h-4 w-4" />
																</Button>
															</div>
														</DataTableCell>
													</DataTableRow>
												);
											})}
										</DataTableBody>
									</DataTable>
								</div>
							)}
						</CardContent>
					</Card>
				</TabsContent>

				<TabsContent value="config-overrides">
					<Card>
						<CardHeader>
							<CardTitle>Configuration Overrides</CardTitle>
							<CardDescription>
								Manage organization-specific configuration
								overrides
							</CardDescription>
						</CardHeader>
						<CardContent>
							<ConfigOverridesTab
								orgsWithMappings={orgsWithMappings}
								configSchema={integration?.config_schema || []}
								integrationId={integrationId || ""}
							/>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>

			{/* OAuth Configuration Dialog (Create) */}
			{integrationId && (
				<CreateOAuthConnectionDialog
					open={oauthConfigDialogOpen}
					onOpenChange={setOAuthConfigDialogOpen}
					integrationId={integrationId}
				/>
			)}

			{/* OAuth Configuration Dialog (Edit) */}
			{integrationId && (
				<CreateOAuthConnectionDialog
					open={editingOAuthConfig}
					onOpenChange={setEditingOAuthConfig}
					integrationId={integrationId}
					editConnectionName={integrationId}
				/>
			)}

			{/* Edit Integration Dialog */}
			<CreateIntegrationDialog
				open={editDialogOpen}
				onOpenChange={setEditDialogOpen}
				editIntegrationId={integrationId}
				initialData={integration}
			/>

			{/* Org Config Dialog */}
			{selectedOrgForConfig && (
				<OrgConfigDialog
					open={configDialogOpen}
					onOpenChange={setConfigDialogOpen}
					orgId={selectedOrgForConfig.id}
					orgName={selectedOrgForConfig.name}
					configSchema={integration?.config_schema || []}
					currentConfig={selectedOrgForConfig.formData.config}
					onSave={handleSaveOrgConfig}
				/>
			)}

			{/* Configuration Defaults Dialog */}
			<Dialog
				open={defaultsDialogOpen}
				onOpenChange={setDefaultsDialogOpen}
			>
				<DialogContent className="max-w-md">
					<form
						onSubmit={(e) => {
							e.preventDefault();
							handleSaveDefaults();
						}}
					>
						<DialogHeader>
							<DialogTitle>
								Edit Configuration Defaults
							</DialogTitle>
							<DialogDescription>
								Set default values for new organization mappings
							</DialogDescription>
						</DialogHeader>
						<div className="space-y-4 py-4">
							{integration?.config_schema?.map((field) => (
								<div key={field.key} className="space-y-2">
									<Label htmlFor={`default-${field.key}`}>
										{field.key}
										{field.required && (
											<span className="text-destructive ml-1">
												*
											</span>
										)}
										<span className="text-muted-foreground text-xs ml-2">
											({field.type})
										</span>
									</Label>
									{field.type === "bool" ? (
										<select
											id={`default-${field.key}`}
											value={String(
												defaultsFormValues[field.key] ??
													"",
											)}
											onChange={(e) =>
												setDefaultsFormValues(
													(prev) => ({
														...prev,
														[field.key]:
															e.target.value ===
															"true",
													}),
												)
											}
											className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors"
										>
											<option value="">
												— Not set —
											</option>
											<option value="true">True</option>
											<option value="false">False</option>
										</select>
									) : (
										<Input
											id={`default-${field.key}`}
											type={
												field.type === "secret"
													? "password"
													: "text"
											}
											placeholder={`Default ${field.key}`}
											value={String(
												defaultsFormValues[field.key] ??
													"",
											)}
											onChange={(e) =>
												setDefaultsFormValues(
													(prev) => ({
														...prev,
														[field.key]:
															field.type === "int"
																? parseInt(
																		e.target
																			.value,
																	) || ""
																: e.target
																		.value,
													}),
												)
											}
										/>
									)}
								</div>
							))}
						</div>
						<DialogFooter>
							<Button
								type="button"
								variant="outline"
								onClick={() => setDefaultsDialogOpen(false)}
								disabled={updateIntegrationMutation.isPending}
							>
								Cancel
							</Button>
							<Button
								type="submit"
								disabled={updateIntegrationMutation.isPending}
							>
								{updateIntegrationMutation.isPending ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Saving...
									</>
								) : (
									"Save Defaults"
								)}
							</Button>
						</DialogFooter>
					</form>
				</DialogContent>
			</Dialog>

			{/* Delete Mapping Confirmation Dialog */}
			<AlertDialog
				open={deleteMappingConfirm !== null}
				onOpenChange={(open) => !open && setDeleteMappingConfirm(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Mapping</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete the mapping for{" "}
							<span className="font-semibold">
								{deleteMappingConfirm?.name}
							</span>
							? This will remove the organization's integration
							configuration and cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDeleteMappingConfirm}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Delete OAuth Configuration Confirmation Dialog */}
			<AlertDialog
				open={deleteOAuthDialogOpen}
				onOpenChange={setDeleteOAuthDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Delete OAuth Configuration
						</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete the OAuth
							configuration for{" "}
							<span className="font-semibold">
								{integration?.name}
							</span>
							? This will remove the OAuth connection and any
							stored tokens. This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel
							disabled={deleteOAuthMutation.isPending}
						>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDeleteOAuthConfig}
							disabled={deleteOAuthMutation.isPending}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{deleteOAuthMutation.isPending ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Deleting...
								</>
							) : (
								"Delete"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
