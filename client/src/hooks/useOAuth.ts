/**
 * React Query hooks for OAuth connections
 * Uses openapi-react-query pattern with $api for type-safe queries and mutations
 * All hooks automatically handle X-Organization-Id via api-client middleware
 */

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { $api, apiClient } from "@/lib/api-client";

/**
 * Get OAuth connection details
 * Organization context is handled automatically by the api client
 */
export function useOAuthConnection(connectionName: string) {
	return $api.useQuery(
		"get",
		"/api/oauth/connections/{connection_name}",
		{ params: { path: { connection_name: connectionName } } },
		{ enabled: !!connectionName },
	);
}

/**
 * Create OAuth connection
 * Organization context is handled automatically by the api client
 */
export function useCreateOAuthConnection() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/oauth/connections", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
			toast.success("OAuth connection configured successfully");
		},
		onError: (error) => {
			const message =
				typeof error === "object" && error !== null && "detail" in error
					? String(error.detail)
					: "Failed to create OAuth connection";
			toast.error(message);
		},
	});
}

/**
 * Update OAuth connection
 * Organization context is handled automatically by the api client
 */
export function useUpdateOAuthConnection() {
	const queryClient = useQueryClient();

	return $api.useMutation("put", "/api/oauth/connections/{connection_name}", {
		onSuccess: (_, variables) => {
			const connectionName = variables.params?.path?.connection_name;
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/oauth/connections/{connection_name}",
					{ params: { path: { connection_name: connectionName } } },
				],
			});
			toast.success(
				`Connection "${connectionName}" updated successfully`,
			);
		},
		onError: (error) => {
			const message =
				typeof error === "object" && error !== null && "detail" in error
					? String(error.detail)
					: "Failed to update OAuth connection";
			toast.error(message);
		},
	});
}

/**
 * Delete OAuth connection
 * Organization context is handled automatically by the api client
 */
export function useDeleteOAuthConnection() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/oauth/connections/{connection_name}",
		{
			onSuccess: (_, variables) => {
				const connectionName = variables.params?.path?.connection_name;
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/integrations"],
				});
				toast.success(
					`Connection "${connectionName}" deleted successfully`,
				);
			},
			onError: (error) => {
				const message =
					typeof error === "object" &&
					error !== null &&
					"detail" in error
						? String(error.detail)
						: "Failed to delete OAuth connection";
				toast.error(message);
			},
		},
	);
}

/**
 * Authorize OAuth connection (initiate OAuth flow)
 * Organization context is handled automatically by the api client
 */
export function useAuthorizeOAuthConnection() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/oauth/connections/{connection_name}/authorize",
		{
			onSuccess: (response, variables) => {
				const connectionName = variables.params?.path?.connection_name;
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/integrations"],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/oauth/connections/{connection_name}",
						{
							params: {
								path: { connection_name: connectionName },
							},
						},
					],
				});

				// Open authorization URL in new window
				if (response?.authorization_url) {
					window.open(
						response.authorization_url,
						"_blank",
						"width=600,height=700",
					);
				}

				toast.success(
					"Authorization started - complete it in the popup window",
				);
			},
			onError: (error) => {
				const message =
					typeof error === "object" &&
					error !== null &&
					"detail" in error
						? String(error.detail)
						: "Failed to start authorization";
				toast.error(message);
			},
		},
	);
}

/**
 * Cancel OAuth authorization (reset to not_connected status)
 * Organization context is handled automatically by the api client
 */
export function useCancelOAuthAuthorization() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/oauth/connections/{connection_name}/cancel",
		{
			onSuccess: (_, variables) => {
				const connectionName = variables.params?.path?.connection_name;
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/integrations"],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/oauth/connections/{connection_name}",
						{
							params: {
								path: { connection_name: connectionName },
							},
						},
					],
				});
				toast.success("Authorization canceled");
			},
			onError: (error) => {
				const message =
					typeof error === "object" &&
					error !== null &&
					"detail" in error
						? String(error.detail)
						: "Failed to cancel authorization";
				toast.error(message);
			},
		},
	);
}

/**
 * Manually refresh OAuth access token using refresh token
 * Organization context is handled automatically by the api client
 */
export function useRefreshOAuthToken() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/oauth/connections/{connection_name}/refresh",
		{
			onSuccess: (_, variables) => {
				const connectionName = variables.params?.path?.connection_name;
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/integrations"],
				});
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/oauth/connections/{connection_name}",
						{
							params: {
								path: { connection_name: connectionName },
							},
						},
					],
				});
				toast.success("OAuth token refreshed successfully");
			},
			onError: (error) => {
				const message =
					typeof error === "object" &&
					error !== null &&
					"detail" in error
						? String(error.detail)
						: "Failed to refresh OAuth token";
				toast.error(message);
			},
		},
	);
}

/**
 * Get OAuth credentials (for debugging/admin purposes)
 * Organization context is handled automatically by the api client
 */
export function useOAuthCredentials(connectionName: string) {
	return $api.useQuery(
		"get",
		"/api/oauth/credentials/{connection_name}",
		{ params: { path: { connection_name: connectionName } } },
		{
			enabled: !!connectionName,
			// Don't retry on error - credentials might not be available
			retry: false,
		},
	);
}

/**
 * Get OAuth refresh job status
 */
export function useOAuthRefreshJobStatus() {
	const query = $api.useQuery(
		"get",
		"/api/oauth/refresh_job_status",
		{},
		{ refetchInterval: 30000 }, // Refresh every 30 seconds
	);

	// Transform response to extract and enrich last_run data
	return {
		...query,
		data:
			query.data && "last_run" in query.data && query.data.last_run
				? {
						...query.data.last_run,
						updated_at:
							query.data.last_run.end_time ||
							query.data.last_run.start_time,
					}
				: null,
	};
}

/**
 * Manually trigger the OAuth token refresh job
 */
export function useTriggerOAuthRefreshJob() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/oauth/refresh_all", {
		onSuccess: (data) => {
			// Invalidate all OAuth queries to refresh the UI
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/oauth/refresh_job_status"],
			});
			toast.success(
				`Refresh job completed: ${data.refreshed_successfully} refreshed, ${data.refresh_failed} failed`,
			);
		},
		onError: () => {
			toast.error("Failed to trigger refresh job");
		},
	});
}

/**
 * Handle OAuth callback (exchange authorization code for tokens)
 * Called from the UI callback page after OAuth provider redirects
 * This is a standalone async function used outside React hooks
 */
export async function handleOAuthCallback(
	connectionName: string,
	code: string,
	state?: string | null,
) {
	const { data, error } = await apiClient.POST(
		"/api/oauth/callback/{connection_name}",
		{
			params: { path: { connection_name: connectionName } },
			body: {
				code,
				state: state ?? null,
			},
		},
	);
	if (error) {
		throw new Error(
			`Failed to handle OAuth callback: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
	return data;
}
