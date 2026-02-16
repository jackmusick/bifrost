/**
 * ESM Loader — loads npm packages from esm.sh CDN at runtime.
 *
 * Packages are loaded with React version pinning to minimize
 * compatibility issues with React-dependent packages.
 */
import React from "react";

const REACT_VERSION = React.version;
const ESM_SH = "https://esm.sh";

/** Module-level cache: loaded once per session */
const moduleCache = new Map<string, Record<string, unknown>>();

/**
 * Build esm.sh URL for a package, pinning React version.
 */
function buildUrl(name: string, version: string): string {
	return `${ESM_SH}/${name}@${version}?deps=react@${REACT_VERSION},react-dom@${REACT_VERSION}`;
}

/**
 * Load all dependencies from esm.sh in parallel.
 *
 * @param deps - Map of {packageName: version} from app.yaml
 * @returns Map of {packageName: moduleExports} for injection as $deps
 */
export async function loadDependencies(
	deps: Record<string, string>,
): Promise<Record<string, Record<string, unknown>>> {
	const result: Record<string, Record<string, unknown>> = {};
	const entries = Object.entries(deps);

	if (entries.length === 0) {
		return result;
	}

	await Promise.all(
		entries.map(async ([name, version]) => {
			const key = `${name}@${version}`;
			if (moduleCache.has(key)) {
				result[name] = moduleCache.get(key)!;
				return;
			}
			try {
				const mod = await import(/* @vite-ignore */ buildUrl(name, version));
				const exports = { ...mod };
				moduleCache.set(key, exports);
				result[name] = exports;
			} catch (err) {
				console.error(`Failed to load dependency ${name}@${version}:`, err);
				// Set empty object so $deps["pkg"] is defined but empty
				// — destructuring will give undefined for individual exports
				result[name] = {};
			}
		}),
	);

	return result;
}
