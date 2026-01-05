/**
 * Application Editor Page
 *
 * Editor for creating and modifying App Builder applications.
 * Uses the 3-table schema (applications -> pages -> components).
 *
 * Pages are loaded and assembled into an ApplicationDefinition for the EditorShell.
 * Changes are saved per-page via the layout replace API.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
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
	usePublishApplication,
	getAppPage,
} from "@/hooks/useApplications";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { AppRenderer, EditorShell } from "@/components/app-builder";
import type { ComponentSaveData } from "@/components/app-builder/editor/EditorShell";
import { useComponentSaveQueue } from "@/hooks/useComponentSaveQueue";
import { useAppBuilderEditorStore } from "@/stores/app-builder-editor.store";
import type {
	ApplicationDefinition as AppDefinitionType,
	PageDefinition as FrontendPageDefinition,
	LayoutContainer,
	AppComponent,
	DataSource,
} from "@/lib/app-builder-types";
import type { components } from "@/lib/v1";

type ApiLayoutContainer = components["schemas"]["LayoutContainer"];
type ApiComponentNode = components["schemas"]["AppComponentNode"];
type ApiDataSource = components["schemas"]["DataSourceConfig"];

/**
 * Convert API LayoutContainer (with null values) to frontend LayoutContainer (with undefined).
 * Recursively processes children.
 */
function convertApiLayout(apiLayout: ApiLayoutContainer): LayoutContainer {
	return {
		type: apiLayout.type,
		gap: apiLayout.gap ?? undefined,
		padding: apiLayout.padding ?? undefined,
		align: apiLayout.align ?? undefined,
		justify: apiLayout.justify ?? undefined,
		columns: apiLayout.columns ?? undefined,
		autoSize: apiLayout.autoSize ?? undefined,
		visible: apiLayout.visible ?? undefined,
		className: apiLayout.className ?? undefined,
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
					loadingWorkflows: component.loadingWorkflows ?? undefined,
				} as AppComponent;
			},
		),
	};
}

/**
 * Convert API DataSource (with null values) to frontend DataSource (with undefined).
 */
function convertApiDataSource(apiDs: ApiDataSource): DataSource {
	return {
		id: apiDs.id,
		type: apiDs.type,
		endpoint: apiDs.endpoint ?? undefined,
		data: apiDs.data ?? undefined,
		expression: apiDs.expression ?? undefined,
		dataProviderId: apiDs.dataProviderId ?? undefined,
		workflowId: apiDs.workflowId ?? undefined,
		inputParams: apiDs.inputParams ?? undefined,
		autoRefresh: apiDs.autoRefresh ?? undefined,
		refreshInterval: apiDs.refreshInterval ?? undefined,
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

	// Fetch pages list (summaries)
	const { data: pagesData, isLoading: isLoadingPages } = useAppPages(
		existingApp?.id,
		true, // draft
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
		}
	}, [existingApp, defaultOrgId]);

	// Load full page definitions when we have the pages list
	useEffect(() => {
		const loadPages = async () => {
			if (!existingApp?.id || !pagesData?.pages) return;

			setIsLoadingDefinition(true);
			try {
				// Fetch each page with its full layout
				const pagePromises = pagesData.pages.map((pageSummary) =>
					getAppPage(existingApp.id, pageSummary.page_id, true),
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
						dataSources: (page.dataSources ?? []).map(
							convertApiDataSource,
						),
						variables: page.variables ?? {},
						launchWorkflowId: page.launchWorkflowId ?? undefined,
						launchWorkflowParams:
							page.launchWorkflowParams ?? undefined,
						permission: page.permission
							? {
									allowedRoles:
										page.permission.allowedRoles ??
										undefined,
									accessExpression:
										page.permission.accessExpression ??
										undefined,
									redirectTo:
										page.permission.redirectTo ?? undefined,
								}
							: undefined,
					}));

				const appDefinition: AppDefinitionType = {
					id: existingApp.id,
					name: existingApp.name,
					description: existingApp.description || "",
					version: `${existingApp.draft_version}`,
					pages: convertedPages,
					navigation: undefined, // TODO: Load from app metadata if needed
					globalDataSources: undefined,
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

	// Handle definition changes from visual editor
	// Note: This is called for ALL definition changes (including those from granular saves)
	// The save queue handles actual persistence, this just updates local state
	const handleDefinitionChange = useCallback(
		(newDefinition: AppDefinitionType) => {
			setDefinition(newDefinition);
		},
		[],
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

	// Save changes - flushes pending queue operations
	// For new apps, still uses bulk layout save
	const handleSave = async () => {
		if (!definition) {
			toast.error("No definition to save");
			return;
		}

		try {
			if (isEditing && existingApp?.id) {
				// Flush any pending granular saves first
				await saveQueue.flushAll();

				// Clear dirty tracking
				editorStore.clearAllDirty();

				toast.success("Changes saved");
			} else {
				// Create new application
				const result = await createApplication.mutateAsync({
					body: {
						name,
						description: description || null,
						slug,
						access_level: "authenticated",
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
			}
		} catch (error) {
			console.error("[ApplicationEditor] Save error:", error);
			toast.error(
				error instanceof Error ? error.message : "Failed to save",
			);
		}
	};

	const handlePublish = async () => {
		if (!existingApp?.id || !definition) return;

		try {
			// Save first
			await handleSave();

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
							isEditing && (
								<Badge
									variant="outline"
									className="gap-1 text-green-600 border-green-600/30"
								>
									<Check className="h-3 w-3" />
									Saved
								</Badge>
							)}
						{existingApp?.has_unpublished_changes && (
							<Badge variant="outline">Draft</Badge>
						)}
						{existingApp?.is_published && (
							<Badge variant="default">
								v{existingApp.live_version}
							</Badge>
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
					<Button
						variant="outline"
						size="sm"
						onClick={handleSave}
						disabled={isSaving || !definition}
					>
						<Save className="mr-2 h-4 w-4" />
						{isSaving ? "Saving..." : "Save"}
					</Button>
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
				<div className="max-w-2xl mx-auto py-6">
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
									<Label>Organization</Label>
									<OrganizationSelect
										value={organizationId}
										onChange={(val) =>
											setOrganizationId(val ?? null)
										}
										showGlobal={true}
										disabled={isEditing}
									/>
								</div>
							)}
						</CardContent>
					</Card>
				</div>
			</TabsContent>

			{/* Preview Tab */}
			<TabsContent value="preview" className="flex-1 overflow-auto mt-0">
				{definition ? (
					<div className="border rounded-lg overflow-hidden h-full">
						<AppRenderer
							definition={definition}
							navigate={previewNavigate}
						/>
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
