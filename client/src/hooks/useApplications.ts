/**
 * React Query hooks for applications management
 *
 * Handles CRUD operations, draft/publish workflow, and version management
 * for App Builder applications.
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

// Re-export types from OpenAPI spec
export type ApplicationPublic = components["schemas"]["ApplicationPublic"];
export type ApplicationCreate = components["schemas"]["ApplicationCreate"];
export type ApplicationUpdate = components["schemas"]["ApplicationUpdate"];
export type ApplicationListResponse =
	components["schemas"]["ApplicationListResponse"];
export type ApplicationDraftSave =
	components["schemas"]["ApplicationDraftSave"];
export type ApplicationPublishRequest =
	components["schemas"]["ApplicationPublishRequest"];
export type ApplicationRollbackRequest =
	components["schemas"]["ApplicationRollbackRequest"];
export type ApplicationDefinition =
	components["schemas"]["ApplicationDefinition"];
export type VersionHistoryResponse =
	components["schemas"]["VersionHistoryResponse"];

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
 * Hook to fetch the live definition of an application
 */
export function useApplicationDefinition(
	slug: string | undefined,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{slug}/definition",
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
 * Hook to fetch the draft definition of an application
 */
export function useApplicationDraft(slug: string | undefined, scope?: string) {
	return $api.useQuery(
		"get",
		"/api/applications/{slug}/draft",
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
 * Hook to fetch version history of an application
 */
export function useApplicationVersions(
	slug: string | undefined,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{slug}/history",
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
 * Hook to save a draft definition
 */
export function useSaveApplicationDraft() {
	const queryClient = useQueryClient();

	return $api.useMutation("put", "/api/applications/{slug}/draft", {
		onSuccess: (_, variables) => {
			const slug = variables.params.path.slug;
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/draft"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			toast.success("Draft saved", {
				description: `Draft for "${slug}" has been saved`,
			});
		},
		onError: (error) => {
			toast.error("Failed to save draft", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to publish an application (promote draft to live)
 */
export function usePublishApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/{slug}/publish", {
		onSuccess: (data, variables) => {
			const slug = variables.params.path.slug;
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/definition"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/draft"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/history"],
			});
			toast.success("Application published", {
				description: `"${slug}" is now live at version ${data.live_version}`,
			});
		},
		onError: (error) => {
			toast.error("Failed to publish application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to rollback an application to a previous version
 */
export function useRollbackApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/{slug}/rollback", {
		onSuccess: (data, variables) => {
			const slug = variables.params.path.slug;
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/definition"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/draft"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}/history"],
			});
			toast.success("Application rolled back", {
				description: `"${slug}" has been rolled back to version ${data.live_version}`,
			});
		},
		onError: (error) => {
			toast.error("Failed to rollback application", {
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
 * Get live definition (imperative)
 */
export async function getApplicationDefinition(
	slug: string,
	scope?: string,
): Promise<ApplicationDefinition> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{slug}/definition",
		{
			params: {
				path: { slug },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error)
		throw new Error(
			getErrorMessage(error, "Failed to get application definition"),
		);
	return data;
}

/**
 * Get draft definition (imperative)
 */
export async function getApplicationDraft(
	slug: string,
	scope?: string,
): Promise<ApplicationDefinition> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{slug}/draft",
		{
			params: {
				path: { slug },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to get draft"));
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
 * Save draft definition (imperative)
 */
export async function saveApplicationDraft(
	slug: string,
	definition: Record<string, unknown>,
	scope?: string,
): Promise<ApplicationDefinition> {
	const { data, error } = await apiClient.PUT(
		"/api/applications/{slug}/draft",
		{
			params: {
				path: { slug },
				query: scope ? { scope } : undefined,
			},
			body: { definition },
		},
	);
	if (error) throw new Error(getErrorMessage(error, "Failed to save draft"));
	return data;
}

/**
 * Publish application (imperative)
 */
export async function publishApplication(
	slug: string,
	message?: string,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{slug}/publish",
		{
			params: {
				path: { slug },
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
 * Rollback application (imperative)
 */
export async function rollbackApplication(
	slug: string,
	version: number,
	scope?: string,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.POST(
		"/api/applications/{slug}/rollback",
		{
			params: {
				path: { slug },
				query: scope ? { scope } : undefined,
			},
			body: { version },
		},
	);
	if (error)
		throw new Error(
			getErrorMessage(error, "Failed to rollback application"),
		);
	return data;
}

/**
 * Get version history (imperative)
 */
export async function getVersionHistory(
	slug: string,
	scope?: string,
): Promise<VersionHistoryResponse> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{slug}/history",
		{
			params: {
				path: { slug },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error)
		throw new Error(
			getErrorMessage(error, "Failed to get version history"),
		);
	return data;
}
