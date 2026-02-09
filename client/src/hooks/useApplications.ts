/**
 * React Query hooks for applications management
 *
 * Handles CRUD operations for App Builder applications.
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
export type ApplicationPublishRequest =
	components["schemas"]["ApplicationPublishRequest"];

// Export type for applications
export type ApplicationExport = ApplicationPublic;

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

	return $api.useMutation("patch", "/api/applications/{app_id}", {
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

	return $api.useMutation("delete", "/api/applications/{app_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			toast.success("Application deleted");
		},
		onError: (error) => {
			toast.error("Failed to delete application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/**
 * Hook to publish an application (promote draft to active)
 */
export function usePublishApplication() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/applications/{app_id}/publish", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/applications/{slug}"],
			});
			toast.success("Application published");
		},
		onError: (error) => {
			toast.error("Failed to publish application", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

// =============================================================================
// Export Hook
// =============================================================================

/**
 * Hook to export an application to JSON
 * @param appId - Application ID
 * @param versionId - Version ID (draft_version_id or active_version_id)
 * @param scope - Optional scope parameter
 */
export function useExportApplication(
	appId: string | undefined,
	versionId: string | undefined,
	scope?: string,
) {
	return $api.useQuery(
		"get",
		"/api/applications/{app_id}/export",
		{
			params: {
				path: { app_id: appId ?? "" },
				query: {
					version_id: versionId,
					...(scope ? { scope } : {}),
				},
			},
		},
		{ enabled: !!appId && !!versionId },
	);
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
	appId: string,
	appData: ApplicationUpdate,
): Promise<ApplicationPublic> {
	const { data, error } = await apiClient.PATCH(
		"/api/applications/{app_id}",
		{
			params: {
				path: { app_id: appId },
			},
			body: appData,
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to update application"));
	return data;
}

/**
 * Delete an application (imperative)
 */
export async function deleteApplication(appId: string): Promise<void> {
	const { error } = await apiClient.DELETE("/api/applications/{app_id}", {
		params: {
			path: { app_id: appId },
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
 * @param appId - Application ID
 * @param versionId - Version ID (draft_version_id or active_version_id)
 * @param scope - Optional scope parameter
 */
export async function exportApplication(
	appId: string,
	versionId: string,
	scope?: string,
): Promise<ApplicationExport> {
	const { data, error } = await apiClient.GET(
		"/api/applications/{app_id}/export",
		{
			params: {
				path: { app_id: appId },
				query: {
					version_id: versionId,
					...(scope ? { scope } : {}),
				},
			},
		},
	);
	if (error)
		throw new Error(getErrorMessage(error, "Failed to export application"));
	return data;
}
