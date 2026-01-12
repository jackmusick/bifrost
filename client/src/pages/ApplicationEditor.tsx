/**
 * Application Editor Page
 *
 * Editor for creating and modifying App Builder applications.
 * Uses the 3-table schema (applications -> pages -> components).
 *
 * Pages are loaded and assembled into an ApplicationDefinition for the EditorShell.
 * Changes are saved per-page via the layout replace API.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
	ArrowLeft,
	Save,
	Eye,
	Upload,
	AlertTriangle,
	Layout,
	Settings,
	Loader2,
	Check,
	Variable,
	PanelRightClose,
	Shield,
	Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
	useApplication,
	useAppPages,
	useCreateApplication,
	useUpdateApplication,
	usePublishApplication,
	getAppPage,
} from "@/hooks/useApplications";
import { useRoles } from "@/hooks/useRoles";
import { useWorkflows } from "@/hooks/useWorkflows";
import { useWorkflowExecution } from "@/hooks/useWorkflowExecution";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { AppRenderer, AppShell, EditorShell } from "@/components/app-builder";
import { VariablePreview } from "@/components/app-builder/editor/VariablePreview";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import type { ComponentSaveData } from "@/components/app-builder/editor/EditorShell";
import { useComponentSaveQueue } from "@/hooks/useComponentSaveQueue";
import { useAppBuilderEditorStore } from "@/stores/app-builder-editor.store";
import type {
	ApplicationDefinition as AppDefinitionType,
	PageDefinition as FrontendPageDefinition,
	LayoutContainer,
	AppComponent,
	WorkflowResult,
	ExpressionContext,
} from "@/lib/app-builder-types";
import type { components } from "@/lib/v1";

type ApiLayoutContainer = components["schemas"]["LayoutContainer"];
type ApiComponentNode = components["schemas"]["AppComponentNode"];

/**
 * Convert API LayoutContainer (with null values) to frontend LayoutContainer (with undefined).
 * Recursively processes children.
 */
function convertApiLayout(apiLayout: ApiLayoutContainer): LayoutContainer {
	return {
		id: apiLayout.id,
		type: apiLayout.type,
		gap: apiLayout.gap ?? undefined,
		padding: apiLayout.padding ?? undefined,
		align: apiLayout.align ?? undefined,
		justify: apiLayout.justify ?? undefined,
		columns: apiLayout.columns ?? undefined,
		visible: apiLayout.visible ?? undefined,
		className: apiLayout.class_name ?? undefined,
		children: (apiLayout.children ?? []).map(
			(child): LayoutContainer | AppComponent => {
				// Check if it's a layout container (has type: row/column/grid and children)
				if (
					"children" in child &&
					(child.type === "row" ||
						child.type === "column" ||
						child.type === "grid")
				) {
					return convertApiLayout(child as ApiLayoutContainer);
				}
				// It's a component node - cast through unknown to AppComponent
				const component = child as ApiComponentNode;
				return {
					id: component.id,
					type: component.type,
					props: component.props ?? {},
					visible: component.visible ?? undefined,
					width: component.width ?? undefined,
					loadingWorkflows: component.loading_workflows ?? undefined,
				} as AppComponent;
			},
		),
	};
}

// Default empty application template
const DEFAULT_APP_DEFINITION: AppDefinitionType = {
	id: "",
	name: "New Application",
	description: "",
	version: "1.0.0",
	pages: [
		{
			id: "home",
			title: "Home",
			path: "/",
			layout: {
				id: "layout_home_root",
				type: "column",
				gap: 16,
				padding: 24,
				children: [
					{
						id: "heading-1",
						type: "heading",
						props: {
							text: "Welcome to your new application",
							level: 1,
						},
					},
					{
						id: "text-1",
						type: "text",
						props: {
							text: "Start building by editing the application definition.",
						},
					},
				],
			},
		},
	],
};

export function ApplicationEditor() {
	const navigate = useNavigate();
	const { applicationId: slugParam } = useParams();
	const isEditing = !!slugParam;
	const { user, isPlatformAdmin } = useAuth();

	// Default organization_id
	const defaultOrgId = isPlatformAdmin
		? null
		: (user?.organizationId ?? null);

	// Fetch existing application metadata
	const { data: existingApp, isLoading: isLoadingApp } = useApplication(
		isEditing ? slugParam : undefined,
	);

	// Fetch pages list (summaries) - always use draft version for editor
	const { data: pagesData, isLoading: isLoadingPages } = useAppPages(
		existingApp?.id,
		existingApp?.draft_version_id,
	);

	// Mutations
	const createApplication = useCreateApplication();
	const publishApplication = usePublishApplication();

	// Form state
	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [slug, setSlug] = useState("");
	const [organizationId, setOrganizationId] = useState<string | null>(
		defaultOrgId,
	);
	const [accessLevel, setAccessLevel] = useState<"authenticated" | "role_based">("authenticated");
	const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);

	// Track original values for scope change warning
	const [originalOrganizationId, setOriginalOrganizationId] = useState<string | null>(null);

	// Fetch roles for role-based access
	const { data: rolesData } = useRoles();
	const updateApplication = useUpdateApplication();

	// Application definition state (built from pages)
	const [definition, setDefinition] = useState<AppDefinitionType | null>(
		null,
	);
	const [isLoadingDefinition, setIsLoadingDefinition] = useState(false);

	// Dialog state
	const [isPublishDialogOpen, setIsPublishDialogOpen] = useState(false);
	const [publishMessage, setPublishMessage] = useState("");

	// Visual editor state
	const [selectedComponentId, setSelectedComponentId] = useState<
		string | null
	>(null);

	// Active tab
	const [activeTab, setActiveTab] = useState("visual");

	// Currently active page ID for save operations
	const [currentPageId, setCurrentPageId] = useState<string | null>(null);

	// Preview tab state
	const [previewPageId, setPreviewPageId] = useState<string | null>(null);
	const [isVariablesPanelOpen, setIsVariablesPanelOpen] = useState(false);

	// Save badge state
	const [recentlySaved, setRecentlySaved] = useState(false);
	const recentlySavedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const prevIsSavingRef = useRef(false);

	// App runtime store for expression context
	const appStore = useAppBuilderStore();

	// Editor store for dirty tracking
	const editorStore = useAppBuilderEditorStore();

	// Component save queue - only active when we have an app and page
	const saveQueue = useComponentSaveQueue({
		appId: existingApp?.id || "",
		pageId: currentPageId || "",
		debounceMs: 500,
		maxRetries: 2,
		onSaveError: (_componentId, operation, error) => {
			console.error(
				`[ApplicationEditor] Component ${operation} failed:`,
				error,
			);
		},
	});

	// Track if we have unsaved changes - combine local state tracking with save queue
	const hasUnsavedChanges = useMemo(() => {
		return (
			saveQueue.hasPendingOperations || editorStore.hasUnsavedChanges()
		);
	}, [saveQueue.hasPendingOperations, editorStore]);

	// Build expression context from runtime store for Variables panel
	const previewContext = useMemo((): Partial<ExpressionContext> => {
		// Build workflow results from dataSources (which contain workflow execution results)
		const workflowResults: Record<string, WorkflowResult> = {};
		for (const [key, ds] of Object.entries(appStore.dataSources)) {
			if (ds.data !== undefined) {
				workflowResults[key] = {
					executionId: key,
					workflowId: key,
					workflowName: key,
					status: ds.error ? "failed" : "completed",
					result: ds.data,
					error: ds.error,
				};
			}
		}

		return {
			user: user
				? {
						id: user.id,
						name: user.name || "",
						email: user.email || "",
						role: user.roles?.[0] || "user",
					}
				: undefined,
			variables: appStore.variables,
			workflow: workflowResults,
			field: {},
		};
	}, [user, appStore.dataSources, appStore.variables]);

	// Current page for preview (tracks separately from editor)
	const currentPreviewPage = useMemo(() => {
		if (!definition) return undefined;
		const pageId = previewPageId || definition.pages[0]?.id;
		return definition.pages.find((p) => p.id === pageId);
	}, [definition, previewPageId]);

	// Workflow execution for preview mode data loading
	const { data: workflows } = useWorkflows();
	const { executeWorkflow: executeWorkflowWithSubscription } =
		useWorkflowExecution({});

	// Find a workflow by ID or name
	const findWorkflow = useCallback(
		(workflowId: string) => {
			if (!workflows) return undefined;
			return workflows.find(
				(w) => w.id === workflowId || w.name === workflowId,
			);
		},
		[workflows],
	);

	// Execute workflow handler for preview mode
	const executeWorkflow = useCallback(
		async (
			workflowId: string,
			params: Record<string, unknown>,
		): Promise<WorkflowResult | undefined> => {
			const workflow = findWorkflow(workflowId);
			try {
				const result = await executeWorkflowWithSubscription(
					workflow?.id ?? workflowId,
					params,
				);
				return result;
			} catch (error) {
				const errorResult: WorkflowResult = {
					executionId: "",
					workflowId: workflow?.id ?? workflowId,
					workflowName: workflow?.name ?? workflowId,
					status: "failed",
					error:
						error instanceof Error
							? error.message
							: "Unknown error",
				};
				toast.error(
					`Failed to execute workflow: ${error instanceof Error ? error.message : "Unknown error"}`,
				);
				return errorResult;
			}
		},
		[executeWorkflowWithSubscription, findWorkflow],
	);

	// Initialize current page when definition loads
	useEffect(() => {
		if (definition?.pages?.[0]?.id && !currentPageId) {
			setCurrentPageId(definition.pages[0].id);
		}
	}, [definition, currentPageId]);

	// Set editor context when app/page changes
	// Note: We intentionally exclude editorStore from deps since we only need the stable method references
	useEffect(() => {
		if (existingApp?.id && currentPageId) {
			editorStore.setContext(existingApp.id, currentPageId);
		}
		return () => {
			editorStore.clearContext();
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [existingApp?.id, currentPageId]);

	// Initialize state from existing app metadata
	useEffect(() => {
		if (existingApp) {
			setName(existingApp.name || "");
			setDescription(existingApp.description || "");
			setSlug(existingApp.slug || "");
			setOrganizationId(existingApp.organization_id ?? defaultOrgId);
			setOriginalOrganizationId(existingApp.organization_id ?? defaultOrgId);
			setAccessLevel(
				(existingApp.access_level as "authenticated" | "role_based") || "authenticated"
			);
			setSelectedRoleIds(existingApp.role_ids || []);
		}
	}, [existingApp, defaultOrgId]);

	// Load full page definitions when we have the pages list
	useEffect(() => {
		const loadPages = async () => {
			if (!existingApp?.id || !existingApp?.draft_version_id || !pagesData?.pages) return;

			setIsLoadingDefinition(true);
			try {
				// Fetch each page with its full layout (always use draft version for editor)
				// We've already guarded that draft_version_id is truthy at line 366
				const draftVersionId = existingApp.draft_version_id!;
				const pagePromises = pagesData.pages.map((pageSummary) =>
					getAppPage(existingApp.id, pageSummary.page_id, draftVersionId),
				);
				const loadedPages = await Promise.all(pagePromises);

				// Build the ApplicationDefinition
				// Convert API page format to frontend format, handling null -> undefined
				const convertedPages: FrontendPageDefinition[] =
					loadedPages.map((page) => ({
						id: page.id,
						title: page.title,
						path: page.path,
						layout: convertApiLayout(page.layout),
						variables: page.variables ?? {},
						launchWorkflowId: page.launch_workflow_id ?? undefined,
						launchWorkflowParams:
							page.launch_workflow_params ?? undefined,
						launchWorkflowDataSourceId:
							page.launch_workflow_data_source_id ?? undefined,
						permission: page.permission
							? {
									allowedRoles:
										page.permission.allowed_roles ??
										undefined,
									accessExpression:
										page.permission.access_expression ??
										undefined,
									redirectTo:
										page.permission.redirect_to ?? undefined,
								}
							: undefined,
					}));

				const appDefinition: AppDefinitionType = {
					id: existingApp.id,
					name: existingApp.name,
					description: existingApp.description || "",
					version: "draft",
					pages: convertedPages,
					navigation: undefined, // TODO: Load from app metadata if needed
					globalVariables: undefined,
				};

				setDefinition(appDefinition);
			} catch (error) {
				console.error(
					"[ApplicationEditor] Failed to load pages:",
					error,
				);
				toast.error("Failed to load application pages");
			} finally {
				setIsLoadingDefinition(false);
			}
		};

		loadPages();
	}, [existingApp, pagesData]);

	// For new applications, use the default template
	useEffect(() => {
		if (!isEditing && !definition) {
			setDefinition({
				...DEFAULT_APP_DEFINITION,
				name: name || "New Application",
			});
		}
	}, [isEditing, definition, name]);

	// Auto-generate slug from name
	useEffect(() => {
		if (!isEditing && name && !slug) {
			const generated = name
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-")
				.replace(/^-|-$/g, "");
			setSlug(generated);
		}
	}, [name, slug, isEditing]);

	// Track last saved page metadata to avoid duplicate saves
	const lastSavedPageMetadataRef = useRef<string>("");

	// Handle definition changes from visual editor
	// Note: This is called for ALL definition changes (including those from granular saves)
	// The save queue handles actual persistence for both components and page metadata
	const handleDefinitionChange = useCallback(
		(newDefinition: AppDefinitionType) => {
			setDefinition(newDefinition);

			// Check if page metadata changed and enqueue to save queue
			if (isEditing && currentPageId && existingApp?.id) {
				const currentPage = newDefinition.pages.find(
					(p) => p.id === currentPageId,
				);
				if (currentPage) {
					// Create a hash of the page metadata fields we care about
					const metadataKey = JSON.stringify({
						title: currentPage.title,
						path: currentPage.path,
						variables: currentPage.variables,
						launchWorkflowId: currentPage.launchWorkflowId,
						launchWorkflowParams: currentPage.launchWorkflowParams,
						launchWorkflowDataSourceId:
							currentPage.launchWorkflowDataSourceId,
						permission: currentPage.permission,
					});

					// Only save if metadata actually changed
					if (metadataKey !== lastSavedPageMetadataRef.current) {
						lastSavedPageMetadataRef.current = metadataKey;

						// Enqueue page update to save queue (debounced automatically)
						saveQueue.enqueuePageUpdate(currentPage.id, {
							title: currentPage.title,
							path: currentPage.path,
							variables: currentPage.variables,
							launch_workflow_id: currentPage.launchWorkflowId ?? null,
							launch_workflow_params:
								currentPage.launchWorkflowParams ?? null,
							launch_workflow_data_source_id:
								currentPage.launchWorkflowDataSourceId ?? null,
							permission: currentPage.permission as { [key: string]: unknown } | null | undefined,
						});
					}
				}
			}
		},
		[isEditing, currentPageId, existingApp?.id, saveQueue],
	);

	// Initialize the lastSavedPageMetadata when page loads
	useEffect(() => {
		if (definition && currentPageId) {
			const currentPage = definition.pages.find(
				(p) => p.id === currentPageId,
			);
			if (currentPage) {
				lastSavedPageMetadataRef.current = JSON.stringify({
					title: currentPage.title,
					path: currentPage.path,
					variables: currentPage.variables,
					launchWorkflowId: currentPage.launchWorkflowId,
					launchWorkflowParams: currentPage.launchWorkflowParams,
					launchWorkflowDataSourceId:
						currentPage.launchWorkflowDataSourceId,
					permission: currentPage.permission,
				});
			}
		}
	}, [definition, currentPageId]);

	// Watch for save completion to show "Saved" badge briefly
	useEffect(() => {
		const wasSaving = prevIsSavingRef.current;
		const nowSaving = saveQueue.isSaving;

		// Transition from saving → not saving = save completed
		if (wasSaving && !nowSaving && !hasUnsavedChanges) {
			setRecentlySaved(true);

			// Clear any existing timeout
			if (recentlySavedTimeoutRef.current) {
				clearTimeout(recentlySavedTimeoutRef.current);
			}

			// Hide "Saved" badge after 2 seconds
			recentlySavedTimeoutRef.current = setTimeout(() => {
				setRecentlySaved(false);
			}, 2000);
		}

		prevIsSavingRef.current = nowSaving;

		// Cleanup on unmount
		return () => {
			if (recentlySavedTimeoutRef.current) {
				clearTimeout(recentlySavedTimeoutRef.current);
			}
		};
	}, [saveQueue.isSaving, hasUnsavedChanges]);

	// Handle page reordering with immediate save to backend
	const handleReorderPages = useCallback(
		async (newPages: FrontendPageDefinition[]) => {
			if (!existingApp?.id) return;

			// Save each page's new order to backend
			try {
				await Promise.all(
					newPages.map((page, index) =>
						apiClient.PATCH(
							"/api/applications/{app_id}/pages/{page_id}",
							{
								params: {
									path: {
										app_id: existingApp.id,
										page_id: page.id,
									},
								},
								body: {
									page_order: index,
								},
							},
						),
					),
				);
			} catch (error) {
				console.error(
					"[ApplicationEditor] Failed to save page order:",
					error,
				);
				toast.error("Failed to save page order");
			}
		},
		[existingApp?.id],
	);

	// Granular save callbacks - these are called by EditorShell for real-time saves
	const handleComponentCreate = useCallback(
		(data: ComponentSaveData) => {
			if (!existingApp?.id || !currentPageId) {
				console.warn(
					"[ApplicationEditor] Cannot save component - no app/page context",
				);
				return;
			}
			saveQueue.enqueueCreate(data.componentId, {
				component_id: data.componentId,
				type: data.type,
				props: data.props,
				parent_id: data.parentId,
				component_order: data.order,
			});
		},
		[existingApp?.id, currentPageId, saveQueue],
	);

	const handleComponentUpdate = useCallback(
		(componentId: string, props: Record<string, unknown>) => {
			if (!existingApp?.id || !currentPageId) {
				console.warn(
					"[ApplicationEditor] Cannot update component - no app/page context",
				);
				return;
			}
			saveQueue.enqueueUpdate(componentId, { props });
		},
		[existingApp?.id, currentPageId, saveQueue],
	);

	const handleComponentDelete = useCallback(
		(componentId: string) => {
			if (!existingApp?.id || !currentPageId) {
				console.warn(
					"[ApplicationEditor] Cannot delete component - no app/page context",
				);
				return;
			}
			saveQueue.enqueueDelete(componentId);
		},
		[existingApp?.id, currentPageId, saveQueue],
	);

	const handleComponentMove = useCallback(
		(componentId: string, newParentId: string | null, newOrder: number) => {
			if (!existingApp?.id || !currentPageId) {
				console.warn(
					"[ApplicationEditor] Cannot move component - no app/page context",
				);
				return;
			}
			saveQueue.enqueueMove(componentId, {
				new_parent_id: newParentId,
				new_order: newOrder,
			});
		},
		[existingApp?.id, currentPageId, saveQueue],
	);

	// Create a new application (only used when !isEditing)
	const handleSave = async () => {
		if (!definition) {
			toast.error("No definition to save");
			return;
		}

		try {
			// Create new application
			const result = await createApplication.mutateAsync({
				body: {
					name,
					description: description || null,
					slug,
					access_level: accessLevel,
					role_ids: accessLevel === "role_based" ? selectedRoleIds : undefined,
				},
			});

			// Create the initial home page
			const homePage = definition.pages[0];
			if (homePage) {
				await apiClient.POST("/api/applications/{app_id}/pages", {
					params: {
						path: { app_id: result.id },
					},
					body: {
						page_id: homePage.id,
						title: homePage.title,
						path: homePage.path,
						page_order: 0,
						root_layout_type: homePage.layout.type,
						root_layout_config: {
							gap: homePage.layout.gap,
							padding: homePage.layout.padding,
						},
					},
				});

				// Set the layout
				await apiClient.PUT(
					"/api/applications/{app_id}/pages/{page_id}/layout",
					{
						params: {
							path: {
								app_id: result.id,
								page_id: homePage.id,
							},
						},
						body: homePage.layout as unknown as Record<
							string,
							unknown
						>,
					},
				);
			}

			toast.success("Application created");
			navigate(`/apps/${result.slug}/edit`);
		} catch (error) {
			console.error("[ApplicationEditor] Create error:", error);
			toast.error(
				error instanceof Error ? error.message : "Failed to create",
			);
		}
	};

	const handlePublish = async () => {
		if (!existingApp?.id || !definition) return;

		try {
			// Flush any pending auto-saves first
			await saveQueue.flushAll();

			// Clear dirty tracking
			editorStore.clearAllDirty();

			// Publish
			await publishApplication.mutateAsync({
				params: { path: { app_id: existingApp.id } },
				body: {
					message: publishMessage || null,
				},
			});
			toast.success("Application published");
			setIsPublishDialogOpen(false);
			setPublishMessage("");
		} catch (error) {
			toast.error(
				error instanceof Error
					? error.message
					: "Failed to publish application",
			);
		}
	};

	// Navigate handler for preview
	const previewNavigate = useCallback(
		(path: string) => {
			if (!path.startsWith("/apps/") && !path.startsWith("http")) {
				const basePath = `/apps/${slugParam}`;
				const relativePath = path.startsWith("/")
					? path.slice(1)
					: path;
				navigate(`${basePath}/${relativePath}`);
			} else {
				navigate(path);
			}
		},
		[navigate, slugParam],
	);

	// Loading state
	const isLoading =
		isEditing && (isLoadingApp || isLoadingPages || isLoadingDefinition);

	if (isLoading) {
		return (
			<div className="space-y-6">
				<div className="flex items-center gap-4">
					<Skeleton className="h-10 w-10" />
					<Skeleton className="h-8 w-64" />
				</div>
				<Skeleton className="h-[600px] w-full" />
			</div>
		);
	}

	const isSaving = createApplication.isPending;
	const isPublishing = publishApplication.isPending;
	const hasDraft =
		existingApp?.has_unpublished_changes || hasUnsavedChanges || !isEditing;

	return (
		<Tabs
			value={activeTab}
			onValueChange={setActiveTab}
			className="h-[calc(100vh-8rem)] flex flex-col"
		>
			{/* Combined Header with View Switcher */}
			<div className="flex items-center justify-between pb-4">
				{/* Left: Back button + App info */}
				<div className="flex items-center gap-4">
					<Button
						variant="ghost"
						size="icon"
						onClick={() => navigate("/apps")}
					>
						<ArrowLeft className="h-5 w-5" />
					</Button>
					<div className="flex items-center gap-3">
						<h1 className="text-xl font-semibold">
							{isEditing
								? existingApp?.name || "Edit Application"
								: "New Application"}
						</h1>
						{/* Real-time save status indicator */}
						{saveQueue.isSaving && (
							<Badge variant="outline" className="gap-1">
								<Loader2 className="h-3 w-3 animate-spin" />
								Saving...
							</Badge>
						)}
						{!saveQueue.isSaving && hasUnsavedChanges && (
							<Badge variant="outline">Unsaved</Badge>
						)}
						{!saveQueue.isSaving &&
							!hasUnsavedChanges &&
							recentlySaved &&
							isEditing && (
								<Badge
									variant="outline"
									className="gap-1 text-green-600 border-green-600/30"
								>
									<Check className="h-3 w-3" />
									Saved
								</Badge>
							)}
						{!recentlySaved &&
							existingApp?.has_unpublished_changes &&
							isEditing && (
								<Badge variant="outline">Draft</Badge>
							)}
					</div>
				</div>

				{/* Center: View Switcher Tabs */}
				<TabsList>
					<TabsTrigger value="visual">
						<Layout className="mr-2 h-4 w-4" />
						Visual Editor
					</TabsTrigger>
					<TabsTrigger value="settings">
						<Settings className="mr-2 h-4 w-4" />
						Settings
					</TabsTrigger>
					<TabsTrigger value="preview">
						<Eye className="mr-2 h-4 w-4" />
						Preview
					</TabsTrigger>
				</TabsList>

				{/* Right: Actions */}
				<div className="flex items-center gap-2">
					{!isEditing && (
						<Button
							size="sm"
							onClick={handleSave}
							disabled={isSaving || !definition || !name}
						>
							<Save className="mr-2 h-4 w-4" />
							{isSaving ? "Creating..." : "Create Application"}
						</Button>
					)}
					{isEditing && hasDraft && (
						<Button
							size="sm"
							onClick={() => setIsPublishDialogOpen(true)}
							disabled={isPublishing || !definition}
						>
							<Upload className="mr-2 h-4 w-4" />
							{isPublishing ? "Publishing..." : "Publish"}
						</Button>
					)}
				</div>
			</div>

			{/* Visual Editor Tab */}
			<TabsContent
				value="visual"
				className="flex-1 -mx-6 lg:-mx-8 -mb-6 lg:-mb-8 overflow-hidden mt-0"
			>
				{definition ? (
					<EditorShell
						definition={definition}
						onDefinitionChange={handleDefinitionChange}
						selectedComponentId={selectedComponentId}
						onSelectComponent={setSelectedComponentId}
						pageId={currentPageId || undefined}
						onPageIdChange={setCurrentPageId}
						onComponentCreate={
							isEditing ? handleComponentCreate : undefined
						}
						onComponentUpdate={
							isEditing ? handleComponentUpdate : undefined
						}
						onComponentDelete={
							isEditing ? handleComponentDelete : undefined
						}
						onComponentMove={
							isEditing ? handleComponentMove : undefined
						}
						onReorderPages={
							isEditing ? handleReorderPages : undefined
						}
						appAccessLevel={accessLevel}
						appRoleIds={selectedRoleIds}
					/>
				) : (
					<div className="flex h-full items-center justify-center">
						<Card className="max-w-md">
							<CardContent className="flex flex-col items-center justify-center py-12">
								<AlertTriangle className="h-12 w-12 text-muted-foreground" />
								<p className="mt-4 text-center text-muted-foreground">
									Loading application...
								</p>
							</CardContent>
						</Card>
					</div>
				)}
			</TabsContent>

			{/* Settings Tab */}
			<TabsContent value="settings" className="flex-1 overflow-auto mt-0">
				<div className="max-w-2xl mx-auto py-6 space-y-6">
					{/* Basic Settings Card */}
					<Card>
						<CardHeader>
							<CardTitle>Application Settings</CardTitle>
							<CardDescription>
								Configure the basic settings for your
								application.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="name">Name</Label>
								<Input
									id="name"
									value={name}
									onChange={(e) => setName(e.target.value)}
									placeholder="My Application"
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="description">Description</Label>
								<Textarea
									id="description"
									value={description}
									onChange={(e) =>
										setDescription(e.target.value)
									}
									placeholder="A brief description of your application..."
									rows={3}
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="slug">URL Slug</Label>
								<Input
									id="slug"
									value={slug}
									onChange={(e) => setSlug(e.target.value)}
									placeholder="my-application"
									disabled={isEditing}
								/>
								{!isEditing && (
									<p className="text-xs text-muted-foreground">
										Your app will be accessible at /apps/
										{slug || "..."}
									</p>
								)}
							</div>

							{isPlatformAdmin && (
								<div className="space-y-2">
									<Label>Organization Scope</Label>
									<OrganizationSelect
										value={organizationId}
										onChange={(val) =>
											setOrganizationId(val ?? null)
										}
										showGlobal={true}
									/>
									{isEditing && organizationId !== originalOrganizationId && (
										<Alert className="mt-2 bg-amber-50 border-amber-200 dark:bg-amber-950 dark:border-amber-800">
											<AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
											<AlertDescription className="text-amber-800 dark:text-amber-200">
												Changing application scope affects which organizations can access this app.
												Users from other organizations may lose access.
											</AlertDescription>
										</Alert>
									)}
								</div>
							)}
						</CardContent>
					</Card>

					{/* Access Control Card */}
					<Card>
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<Shield className="h-5 w-5" />
								Access Control
							</CardTitle>
							<CardDescription>
								Configure who can access this application.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="space-y-3">
								<Label>Access Level</Label>
								<RadioGroup
									value={accessLevel}
									onValueChange={(value) => setAccessLevel(value as "authenticated" | "role_based")}
									className="space-y-2"
								>
									<div className="flex items-center space-x-3 rounded-lg border p-4 hover:bg-accent/50 transition-colors">
										<RadioGroupItem value="authenticated" id="access-authenticated" />
										<div className="flex-1">
											<Label htmlFor="access-authenticated" className="cursor-pointer font-medium">
												<div className="flex items-center gap-2">
													<Users className="h-4 w-4" />
													All Authenticated Users
												</div>
											</Label>
											<p className="text-sm text-muted-foreground">
												Any logged-in user within the organization scope can access this app.
											</p>
										</div>
									</div>
									<div className="flex items-center space-x-3 rounded-lg border p-4 hover:bg-accent/50 transition-colors">
										<RadioGroupItem value="role_based" id="access-role-based" />
										<div className="flex-1">
											<Label htmlFor="access-role-based" className="cursor-pointer font-medium">
												<div className="flex items-center gap-2">
													<Shield className="h-4 w-4" />
													Specific Roles Only
												</div>
											</Label>
											<p className="text-sm text-muted-foreground">
												Only users with selected roles can access this app.
											</p>
										</div>
									</div>
								</RadioGroup>
							</div>

							{accessLevel === "role_based" && (
								<div className="space-y-3 pt-2">
									<Label>Allowed Roles</Label>
									{!rolesData?.length ? (
										<p className="text-sm text-muted-foreground">
											No roles available. Create roles in the Roles section first.
										</p>
									) : (
										<div className="space-y-2 max-h-64 overflow-y-auto">
											{rolesData.map((role) => {
												const isSelected = selectedRoleIds.includes(role.id);
												return (
													<label
														key={role.id}
														htmlFor={`role-${role.id}`}
														className={`flex items-start space-x-3 rounded-lg border p-3 hover:bg-accent/50 transition-colors cursor-pointer ${
															isSelected ? 'border-primary bg-primary/5' : ''
														}`}
													>
														<Checkbox
															id={`role-${role.id}`}
															checked={isSelected}
															onCheckedChange={(checked) => {
																setSelectedRoleIds(prev =>
																	checked
																		? [...prev, role.id]
																		: prev.filter(id => id !== role.id)
																);
															}}
														/>
														<div className="flex-1">
															<span className="cursor-pointer font-medium">
																{role.name}
															</span>
															{role.description && (
																<p className="text-sm text-muted-foreground">
																	{role.description}
																</p>
															)}
														</div>
													</label>
												);
											})}
										</div>
									)}
									{accessLevel === "role_based" && selectedRoleIds.length === 0 && (
										<Alert className="mt-2">
											<AlertTriangle className="h-4 w-4" />
											<AlertDescription>
												No roles selected. Select at least one role to allow access.
											</AlertDescription>
										</Alert>
									)}
								</div>
							)}

							{/* Save Settings Button (for editing existing apps) */}
							{isEditing && (
								<div className="pt-4 border-t">
									<Button
										onClick={async () => {
											if (!existingApp?.slug) return;
											try {
												await updateApplication.mutateAsync({
													params: { path: { slug: existingApp.slug } },
													body: {
														name: name || undefined,
														description: description || undefined,
														access_level: accessLevel,
														role_ids: accessLevel === "role_based" ? selectedRoleIds : [],
													},
												});
												// Update original org ID after successful save
												if (organizationId !== originalOrganizationId) {
													setOriginalOrganizationId(organizationId);
												}
											} catch {
												// Error toast is handled by the hook
											}
										}}
										disabled={updateApplication.isPending}
									>
										{updateApplication.isPending ? (
											<>
												<Loader2 className="mr-2 h-4 w-4 animate-spin" />
												Saving...
											</>
										) : (
											<>
												<Save className="mr-2 h-4 w-4" />
												Save Settings
											</>
										)}
									</Button>
								</div>
							)}
						</CardContent>
					</Card>
				</div>
			</TabsContent>

			{/* Preview Tab */}
			<TabsContent value="preview" className="flex-1 overflow-hidden mt-0">
				{definition ? (
					<div className="flex h-full">
						{/* Main Preview Area with AppShell */}
						<div className="flex-1 border rounded-lg overflow-hidden m-2">
							<AppShell
								app={definition}
								currentPageId={
									previewPageId || definition.pages[0]?.id
								}
								onNavigate={setPreviewPageId}
								showBackButton={false}
							>
								<AppRenderer
									definition={definition}
									pageId={
										previewPageId || definition.pages[0]?.id
									}
									navigate={previewNavigate}
									executeWorkflow={executeWorkflow}
								/>
							</AppShell>
						</div>

						{/* Variables Panel Toggle */}
						<div className="flex flex-col">
							<Button
								variant="ghost"
								size="icon"
								className="m-2"
								onClick={() =>
									setIsVariablesPanelOpen(!isVariablesPanelOpen)
								}
								title={
									isVariablesPanelOpen
										? "Hide Variables"
										: "Show Variables"
								}
							>
								{isVariablesPanelOpen ? (
									<PanelRightClose className="h-5 w-5" />
								) : (
									<Variable className="h-5 w-5" />
								)}
							</Button>
						</div>

						{/* Variables Panel */}
						{isVariablesPanelOpen && (
							<div className="w-80 border-l bg-background flex flex-col">
								<VariablePreview
									context={previewContext}
									page={currentPreviewPage}
									className="flex-1"
								/>
							</div>
						)}
					</div>
				) : (
					<Card>
						<CardContent className="flex flex-col items-center justify-center py-12">
							<AlertTriangle className="h-12 w-12 text-muted-foreground" />
							<p className="mt-4 text-muted-foreground">
								Loading application...
							</p>
						</CardContent>
					</Card>
				)}
			</TabsContent>

			{/* Publish Dialog */}
			<Dialog
				open={isPublishDialogOpen}
				onOpenChange={setIsPublishDialogOpen}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Publish Application</DialogTitle>
						<DialogDescription>
							This will make the current draft live. Users will
							see the new version immediately.
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-4">
						<div className="space-y-2">
							<Label htmlFor="publish-message">
								Publish Message (optional)
							</Label>
							<Textarea
								id="publish-message"
								value={publishMessage}
								onChange={(e) =>
									setPublishMessage(e.target.value)
								}
								placeholder="What changed in this version?"
								rows={3}
							/>
						</div>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setIsPublishDialogOpen(false)}
						>
							Cancel
						</Button>
						<Button onClick={handlePublish} disabled={isPublishing}>
							{isPublishing ? "Publishing..." : "Publish"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</Tabs>
	);
}
