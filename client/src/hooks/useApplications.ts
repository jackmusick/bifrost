/**
 * React Query hooks for applications management
 *
 * Handles CRUD operations, draft/publish workflow, and page/component management
 * for App Builder applications using the 3-table schema.
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

// Re-export types from OpenAPI spec
// Note: These types will be updated after running npm run generate:types
export type ApplicationPublic = components["schemas"]["ApplicationPublic"];
export type ApplicationCreate = components["schemas"]["ApplicationCreate"];
export type ApplicationUpdate = components["schemas"]["ApplicationUpdate"];
export type ApplicationListResponse =
	components["schemas"]["ApplicationListResponse"];
export type ApplicationPublishRequest =
	components["schemas"]["ApplicationPublishRequest"];

// Page types - PageDefinition is the new typed API response
export type AppPageSummary = components["schemas"]["AppPageSummary"];
export type AppPageResponse = components["schemas"]["AppPageResponse"];
export type PageDefinition = components["schemas"]["PageDefinition"];
// Legacy type alias for backwards compatibility
export type AppPageWithComponents = PageDefinition;
export type AppPageCreate = components["schemas"]["AppPageCreate"];
export type AppPageUpdate = components["schemas"]["AppPageUpdate"];
export type AppPageListResponse = components["schemas"]["AppPageListResponse"];

export type AppComponentSummary = components["schemas"]["AppComponentSummary"];
export type AppComponentResponse =
	components["schemas"]["AppComponentResponse"];
export type AppComponentCreate = components["schemas"]["AppComponentCreate"];
export type AppComponentUpdate = components["schemas"]["AppComponentUpdate"];
export type AppComponentMove = components["schemas"]["AppComponentMove"];
export type AppComponentListResponse =
	components["schemas"]["AppComponentListResponse"];

export type ApplicationExport = components["schemas"]["ApplicationExport"];
export type ApplicationImport = components["schemas"]["ApplicationImport"];

/** Helper to extract error message from API error response */
function getErrorMessage(error: unknown, fallback: string): string {
	if (typeof error === "object" && error) {
		const errObj = error as Record<string, unknown>;
		// Check for message
		if ("message" in errObj && typeof errObj.message === "string") {
			return errObj.message;
		}
		// Check for FastAPI detail format
		if ("detail" in errObj) {
			const detail = errObj.detail;
			if (typeof detail === "string") {
				return detail;
			}
			// FastAPI validation errors come as array of objects
			if (Array.isArray(detail)) {
				return detail
					.map((d) => {
						if (typeof d === "object" && d && "msg" in d) {
							const loc =
								"loc" in d && Array.isArray(d.loc)
									? d.loc.join(".")
									: "";
							return loc ? `${loc}: ${d.msg}` : String(d.msg);
						}
						return JSON.stringify(d);
					})
					.join("; ");
			}
			return JSON.stringify(detail);
		}
	}
	return fallback;
}

// =============================================================================
// Application Hooks
// =============================================================================

/**
 * Hook to fetch all applications
 */
export function useApplications(scope?: string) {
	return $api.useQuery(
		"get",
		"/api/applications",
		scope ? { params: { query: { scope } } } : undefined,
	);
}

/**
 * Hook to fetch a single application by slug
 */
export function useApplication(slug: string | undefined, scope?: string) {
	return $api.useQuery(
		"get",
		"/api/applications/{slug}",
		{
			params: {
				path: { slug: slug ?? "" },
				query: scope ? { scope } : undefined,
			},
		},
		{ enabled: !!slug },
	);
}

/**
 * Hook to create a new application
 */
export function useCreateApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			toast.success("Application created", {
				description: `Application "${data.name}" has been created`,
			});
		},
		onError: (error) => {
			toast.error("Failed to create application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to update application metadata
 */
export function useUpdateApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("patch", "/api/applications/{slug}", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			toast.success("Application updated", {
				description: `Application "${data.name}" has been updated`,
			});
		},
		onError: (error) => {
			toast.error("Failed to update application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to delete an application
 */
export function useDeleteApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/applications/{slug}", {
		onSuccess: (_, variables) => {
			const slug = variables.params.path.slug;
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			toast.success("Application deleted", {
				description: `Application "${slug}" has been deleted`,
			});
		},
		onError: (error) => {
			toast.error("Failed to delete application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to publish an application (promote draft pages to live)
 */
export function usePublishApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/{app_id}/publish", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			// Invalidate page queries for this app
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{app_id}/pages"],
			});
			toast.success("Application published", {
				description: `Application is now live at version ${data.live_version}`,
			});
		},
		onError: (error) => {
			toast.error("Failed to publish application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

// =============================================================================
// Page Hooks
// =============================================================================

/**
 * Hook to fetch all pages for an application
 */
export function useAppPages(
	appId: string | undefined,
	isDraft = true,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/pages",
		{
			params: {
				path: { app_id: appId ?? "" },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId },
	);
}

/**
 * Hook to fetch a single page with its component tree
 */
export function useAppPage(
	appId: string | undefined,
	pageId: string | undefined,
	isDraft = true,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/pages/{page_id}",
		{
			params: {
				path: {
					app_id: appId ?? "",
					page_id: pageId ?? "",
				},
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId && !!pageId },
	);
}

/**
 * Hook to create a new page
 */
export function useCreateAppPage() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/{app_id}/pages", {
		onSuccess: (data, variables) => {
			const appId = variables.params.path.app_id;
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/applications/{app_id}/pages",
					{ params: { path: { app_id: appId } } },
				],
			});
			toast.success("Page created", {
				description: `Page "${data.title}" has been created`,
			});
		},
		onError: (error) => {
			toast.error("Failed to create page", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to update a page
 */
export function useUpdateAppPage() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"patch",
		"/api/applications/{app_id}/pages/{page_id}",
		{
			onSuccess: (data, variables) => {
				const appId = variables.params.path.app_id;
				const pageId = variables.params.path.page_id;
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/applications/{app_id}/pages"],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}",
						{
							params: {
								path: { app_id: appId, page_id: pageId },
							},
						},
					],
				});
				toast.success("Page updated", {
					description: `Page "${data.title}" has been updated`,
				});
			},
			onError: (error) => {
				toast.error("Failed to update page", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Hook to delete a page
 */
export function useDeleteAppPage() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/applications/{app_id}/pages/{page_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/applications/{app_id}/pages"],
				});
				toast.success("Page deleted");
			},
			onError: (error) => {
				toast.error("Failed to delete page", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

// =============================================================================
// Component Hooks
// =============================================================================

/**
 * Hook to fetch all components for a page (summary list)
 */
export function useAppComponents(
	appId: string | undefined,
	pageId: string | undefined,
	isDraft = true,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/pages/{page_id}/components",
		{
			params: {
				path: {
					app_id: appId ?? "",
					page_id: pageId ?? "",
				},
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId && !!pageId },
	);
}

/**
 * Hook to fetch a single component
 */
export function useAppComponent(
	appId: string | undefined,
	pageId: string | undefined,
	componentId: string | undefined,
	isDraft = true,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			params: {
				path: {
					app_id: appId ?? "",
					page_id: pageId ?? "",
					component_id: componentId ?? "",
				},
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId && !!pageId && !!componentId },
	);
}

/**
 * Hook to create a new component
 */
export function useCreateAppComponent() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/applications/{app_id}/pages/{page_id}/components",
		{
			onSuccess: () => {
				// Invalidate component list
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}/components",
					],
				});
				// Also invalidate the full page (which includes component tree)
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}",
					],
				});
			},
			onError: (error) => {
				toast.error("Failed to create component", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Hook to update a component
 */
export function useUpdateAppComponent() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"patch",
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}/components",
					],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
					],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}",
					],
				});
			},
			onError: (error) => {
				toast.error("Failed to update component", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Hook to delete a component
 */
export function useDeleteAppComponent() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}/components",
					],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}",
					],
				});
			},
			onError: (error) => {
				toast.error("Failed to delete component", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Hook to move a component to a new parent/position
 */
export function useMoveAppComponent() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}/move",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}/components",
					],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/applications/{app_id}/pages/{page_id}",
					],
				});
			},
			onError: (error) => {
				toast.error("Failed to move component", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

// =============================================================================
// Export/Import Hooks
// =============================================================================

/**
 * Hook to export an application to JSON
 */
export function useExportApplication(
	appId: string | undefined,
	isDraft = false,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/export",
		{
			params: {
				path: { app_id: appId ?? "" },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId },
	);
}

/**
 * Hook to import an application from JSON
 */
export function useImportApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/import", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			toast.success("Application imported", {
				description: `Application "${data.name}" has been imported`,
			});
		},
		onError: (error) => {
			toast.error("Failed to import application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

// =============================================================================
// Imperative API Functions (for use outside React components)
// =============================================================================

/**
 * List applications (imperative)
 */
export async function listApplications(
	scope?: string,
): Promise<ApplicationListResponse> {
	const { data, error } = await apiClient.GET("/api/applications", {
		params: {
			query: scope ? { scope } : undefined,
		},
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to list applications"));
	return data;
}

/**
 * Get an application by slug (imperative)
 */
export async function getApplication(
	slug: string,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.GET("/api/applications/{slug}", {
		params: {
			path: { slug },
			query: scope ? { scope } : undefined,
		},
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to get application"));
	return data;
}

/**
 * Create an application (imperative)
 */
export async function createApplication(
	appData: ApplicationCreate,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.POST("/api/applications", {
		params: {
			query: scope ? { scope } : undefined,
		},
		body: appData,
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to create application"));
	return data;
}

/**
 * Update an application (imperative)
 */
export async function updateApplication(
	slug: string,
	appData: ApplicationUpdate,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.PATCH("/api/applications/{slug}", {
		params: {
			path: { slug },
			query: scope ? { scope } : undefined,
		},
		body: appData,
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to update application"));
	return data;
}

/**
 * Delete an application (imperative)
 */
export async function deleteApplication(
	slug: string,
	scope?: string,
): Promise<void> {
	const { error } = await apiClient.DELETE("/api/applications/{slug}", {
		params: {
			path: { slug },
			query: scope ? { scope } : undefined,
		},
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to delete application"));
}

/**
 * Publish application (imperative)
 */
export async function publishApplication(
	appId: string,
	message?: string,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{app_id}/publish",
		{
			params: {
				path: { app_id: appId },
				query: scope ? { scope } : undefined,
			},
			body: message ? { message } : {},
		},
	);
	if (error)
		throw new Error(
			getErrorMessage(error, "Failed to publish application"),
		);
	return data;
}

/**
 * Export application (imperative)
 */
export async function exportApplication(
	appId: string,
	isDraft = false,
	scope?: string,
): Promise<ApplicationExport> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/export",
		{
			params: {
				path: { app_id: appId },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to export application"));
	return data;
}

/**
 * Import application (imperative)
 */
export async function importApplication(
	appData: ApplicationImport,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.POST("/api/applications/import", {
		params: {
			query: scope ? { scope } : undefined,
		},
		body: appData,
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to import application"));
	return data;
}

// =============================================================================
// Page Imperative Functions
// =============================================================================

/**
 * List pages for an application (imperative)
 */
export async function listAppPages(
	appId: string,
	isDraft = true,
	scope?: string,
): Promise<AppPageListResponse> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/pages",
		{
			params: {
				path: { app_id: appId },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to list pages"));
	return data;
}

/**
 * Get a page with its full layout tree (imperative)
 * Returns PageDefinition with nested LayoutContainer structure
 */
export async function getAppPage(
	appId: string,
	pageId: string,
	isDraft = true,
	scope?: string,
): Promise<PageDefinition> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/pages/{page_id}",
		{
			params: {
				path: { app_id: appId, page_id: pageId },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to get page"));
	return data;
}

/**
 * Create a page (imperative)
 */
export async function createAppPage(
	appId: string,
	pageData: AppPageCreate,
): Promise<AppPageResponse> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{app_id}/pages",
		{
			params: {
				path: { app_id: appId },
			},
			body: pageData,
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to create page"));
	return data;
}

/**
 * Update a page (imperative)
 */
export async function updateAppPage(
	appId: string,
	pageId: string,
	pageData: AppPageUpdate,
): Promise<AppPageResponse> {
	const { data, error } = await apiClient.PATCH(
		"/api/applications/{app_id}/pages/{page_id}",
		{
			params: {
				path: { app_id: appId, page_id: pageId },
			},
			body: pageData,
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to update page"));
	return data;
}

/**
 * Delete a page (imperative)
 */
export async function deleteAppPage(
	appId: string,
	pageId: string,
): Promise<void> {
	const { error } = await apiClient.DELETE(
		"/api/applications/{app_id}/pages/{page_id}",
		{
			params: {
				path: { app_id: appId, page_id: pageId },
			},
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to delete page"));
}

// =============================================================================
// Component Imperative Functions
// =============================================================================

/**
 * List components for a page (imperative)
 */
export async function listAppComponents(
	appId: string,
	pageId: string,
	isDraft = true,
	scope?: string,
): Promise<AppComponentListResponse> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/pages/{page_id}/components",
		{
			params: {
				path: { app_id: appId, page_id: pageId },
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to list components"));
	return data;
}

/**
 * Get a single component (imperative)
 */
export async function getAppComponent(
	appId: string,
	pageId: string,
	componentId: string,
	isDraft = true,
	scope?: string,
): Promise<AppComponentResponse> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			params: {
				path: {
					app_id: appId,
					page_id: pageId,
					component_id: componentId,
				},
				query: {
					is_draft: isDraft,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to get component"));
	return data;
}

/**
 * Create a component (imperative)
 */
export async function createAppComponent(
	appId: string,
	pageId: string,
	componentData: AppComponentCreate,
): Promise<AppComponentResponse> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{app_id}/pages/{page_id}/components",
		{
			params: {
				path: { app_id: appId, page_id: pageId },
			},
			body: componentData,
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to create component"));
	return data;
}

/**
 * Update a component (imperative)
 */
export async function updateAppComponent(
	appId: string,
	pageId: string,
	componentId: string,
	componentData: AppComponentUpdate,
): Promise<AppComponentResponse> {
	const { data, error } = await apiClient.PATCH(
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			params: {
				path: {
					app_id: appId,
					page_id: pageId,
					component_id: componentId,
				},
			},
			body: componentData,
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to update component"));
	return data;
}

/**
 * Delete a component (imperative)
 */
export async function deleteAppComponent(
	appId: string,
	pageId: string,
	componentId: string,
): Promise<void> {
	const { error } = await apiClient.DELETE(
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
		{
			params: {
				path: {
					app_id: appId,
					page_id: pageId,
					component_id: componentId,
				},
			},
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to delete component"));
}

/**
 * Move a component (imperative)
 */
export async function moveAppComponent(
	appId: string,
	pageId: string,
	componentId: string,
	moveData: AppComponentMove,
): Promise<AppComponentResponse> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{app_id}/pages/{page_id}/components/{component_id}/move",
		{
			params: {
				path: {
					app_id: appId,
					page_id: pageId,
					component_id: componentId,
				},
			},
			body: moveData,
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to move component"));
	return data;
}
