/**
 * Package management hooks using openapi-react-query pattern
 */

import { $api, apiClient } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/v1";

// Type aliases for cleaner code
export type InstalledPackage = components["schemas"]["InstalledPackage"];
export type PackageUpdate = components["schemas"]["PackageUpdate"];
export type InstallPackageRequest =
	components["schemas"]["InstallPackageRequest"];
export type InstalledPackagesResponse =
	components["schemas"]["InstalledPackagesResponse"];
export type PackageUpdatesResponse =
	components["schemas"]["PackageUpdatesResponse"];

/**
 * Hook to fetch list of all installed packages
 */
export function usePackages() {
	return $api.useQuery("get", "/api/packages", {});
}

/**
 * Hook to check for available package updates
 */
export function useCheckPackageUpdates() {
	return $api.useQuery("get", "/api/packages/updates", {});
}

/**
 * Hook to install a package
 * Returns mutation that accepts optional packageName and version
 */
export function useInstallPackage() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/packages/install", {
		onSuccess: () => {
			// Invalidate packages query to refresh list after installation
			queryClient.invalidateQueries({ queryKey: ["packages"] });
		},
	});
}

/**
 * Standalone function to list all installed packages
 * Use this for imperative calls outside of React components
 */
export async function listPackages(): Promise<InstalledPackagesResponse> {
	const { data, error } = await apiClient.GET("/api/packages");
	if (error) throw new Error(`Failed to list packages: ${error}`);
	return data!;
}

/**
 * Standalone function to check for available updates
 * Use this for imperative calls outside of React components
 */
export async function checkUpdates(): Promise<PackageUpdatesResponse> {
	const { data, error } = await apiClient.GET("/api/packages/updates");
	if (error) throw new Error(`Failed to check updates: ${error}`);
	return data!;
}

/**
 * Standalone function to install a package
 * Use this for imperative calls outside of React components
 *
 * Installation is queued via RabbitMQ and progress is streamed via WebSocket
 * to the package:{user_id} channel.
 *
 * @param packageName - Name of package to install (optional - if not provided, installs from requirements.txt)
 * @param version - Optional version to install (e.g., "2.31.0")
 */
export async function installPackage(
	packageName?: string,
	version?: string,
) {
	const body: InstallPackageRequest = packageName
		? { package: packageName, version: version ?? null }
		: ({} as InstallPackageRequest);

	const { data, error } = await apiClient.POST("/api/packages/install", {
		body,
	});

	if (error) throw new Error(`Failed to install package: ${error}`);
	return data;
}
