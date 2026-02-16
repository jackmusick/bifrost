/**
 * npm Registry Search
 *
 * Searches the public npm registry for packages.
 * Used by the dependency management panel.
 */

export interface NpmPackageResult {
	name: string;
	version: string;
	description: string;
}

const NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search";

/**
 * Search the npm registry for packages.
 *
 * @param query - Search text
 * @param size - Max results (default 8)
 * @param signal - AbortSignal for cancellation
 * @returns Array of matching packages
 */
export async function searchNpmPackages(
	query: string,
	size: number = 8,
	signal?: AbortSignal,
): Promise<NpmPackageResult[]> {
	if (!query.trim()) return [];

	const url = `${NPM_SEARCH_URL}?text=${encodeURIComponent(query)}&size=${size}`;
	const response = await fetch(url, { signal });

	if (!response.ok) {
		throw new Error(`npm search failed: ${response.statusText}`);
	}

	const data = await response.json();
	return (data.objects || []).map(
		(obj: {
			package: { name: string; version: string; description?: string };
		}) => ({
			name: obj.package.name,
			version: obj.package.version,
			description: obj.package.description || "",
		}),
	);
}
