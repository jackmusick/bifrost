/**
 * App Code File Resolver
 *
 * Fetches and compiles code files from the API with caching.
 * Handles component resolution for custom app components.
 */

import React from "react";
import { createComponent } from "./app-code-runtime";
import { authFetch } from "./api-client";
import type { components } from "@/lib/v1";

type AppCodeFile = components["schemas"]["AppCodeFileResponse"];

/**
 * Cached component entry
 */
interface ComponentCache {
	component: React.ComponentType;
	compiledAt: number;
}

/**
 * Code file response from the API
 */
interface AppCodeFileResponse {
	id: string;
	app_version_id: string;
	path: string;
	source: string;
	compiled: string | null;
	created_at: string;
	updated_at: string;
}

/**
 * Cache for compiled components
 * Key format: `{appId}:{versionId}:{path}`
 */
const componentCache = new Map<string, ComponentCache>();

/**
 * Build cache key from app, version, and path
 */
function buildCacheKey(
	appId: string,
	versionId: string,
	path: string,
): string {
	return `${appId}:${versionId}:${path}`;
}

/**
 * Fetch a code file from the API
 *
 * @param appId - Application ID
 * @param versionId - Version ID (draft or published)
 * @param path - File path (e.g., "components/ClientCard")
 * @returns The file response or null if not found
 */
export async function resolveFile(
	appId: string,
	versionId: string,
	path: string,
): Promise<AppCodeFileResponse | null> {
	try {
		// URL-encode the path since it may contain slashes
		const encodedPath = encodeURIComponent(path);
		const response = await authFetch(
			`/api/applications/${appId}/versions/${versionId}/files/${encodedPath}`,
		);

		if (!response.ok) {
			if (response.status === 404) {
				return null;
			}
			throw new Error(`Failed to fetch file: ${response.statusText}`);
		}

		return response.json();
	} catch (error) {
		console.error(`Error fetching code file ${path}:`, error);
		return null;
	}
}

/**
 * Extract component names from source code
 *
 * Uses regex to find all PascalCase component references in JSX.
 * This is a simple heuristic - a full AST parser would be more accurate.
 *
 * @param source - Source code
 * @returns Array of unique component names
 *
 * @example
 * ```typescript
 * extractComponentNames('<Card><ClientCard name="test" /></Card>')
 * // Returns: ["Card", "ClientCard"]
 * ```
 */
export function extractComponentNames(source: string): string[] {
	// Match JSX opening tags with PascalCase names
	// e.g., <ComponentName, <Card>, <MyComponent123>
	const matches = source.matchAll(/<([A-Z][a-zA-Z0-9]*)/g);
	const names = new Set<string>();

	for (const match of matches) {
		names.add(match[1]);
	}

	return Array.from(names);
}

/**
 * Clear all cached components for an app
 *
 * Call this when files are updated to ensure fresh compilation.
 *
 * @param appId - Application ID to clear cache for
 */
export function clearAppCache(appId: string): void {
	for (const key of componentCache.keys()) {
		if (key.startsWith(`${appId}:`)) {
			componentCache.delete(key);
		}
	}
}

/**
 * Clear cache for a specific app version
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 */
export function clearVersionCache(appId: string, versionId: string): void {
	const prefix = `${appId}:${versionId}:`;
	for (const key of componentCache.keys()) {
		if (key.startsWith(prefix)) {
			componentCache.delete(key);
		}
	}
}

/**
 * Clear cache for a specific file
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 * @param path - File path
 */
export function clearFileCache(
	appId: string,
	versionId: string,
	path: string,
): void {
	const key = buildCacheKey(appId, versionId, path);
	componentCache.delete(key);
}

/**
 * Get cache statistics for debugging
 */
export function getCacheStats(): { size: number; keys: string[] } {
	return {
		size: componentCache.size,
		keys: Array.from(componentCache.keys()),
	};
}

/**
 * Extract user component names from an app's file list.
 *
 * This looks for files in the `components/` directory and extracts their names.
 * These are the ONLY components that should be fetched from the API.
 *
 * @param files - All files for an app version
 * @returns Set of component names that exist as user files
 *
 * @example
 * ```typescript
 * const files = [
 *   { path: "pages/index" },
 *   { path: "components/ClientCard" },
 *   { path: "components/DataGrid" },
 * ];
 * getUserComponentNames(files);
 * // Returns: Set { "ClientCard", "DataGrid" }
 * ```
 */
export function getUserComponentNames(files: AppCodeFile[]): Set<string> {
	const names = new Set<string>();

	for (const file of files) {
		if (file.path.startsWith("components/")) {
			// Extract component name from path (e.g., "components/ClientCard.tsx" -> "ClientCard")
			let name = file.path.slice("components/".length);
			// Strip .tsx extension if present
			if (name.endsWith(".tsx")) {
				name = name.slice(0, -4);
			}
			// Handle nested components (e.g., "components/cards/ClientCard" -> "cards/ClientCard")
			// For now, only support flat components directory
			if (!name.includes("/")) {
				names.add(name);
			}
		}
	}

	return names;
}

/**
 * Resolve components using known user files.
 *
 * This is the preferred method when you already have the app's file list.
 * It only fetches components that actually exist, avoiding 404 errors.
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 * @param componentNames - Names referenced in JSX
 * @param userComponentNames - Set of component names that exist as user files
 * @returns Map of component name to React component
 */
export async function resolveAppComponentsFromFiles(
	appId: string,
	versionId: string,
	componentNames: string[],
	userComponentNames: Set<string>,
): Promise<Record<string, React.ComponentType>> {
	const components: Record<string, React.ComponentType> = {};

	// Only resolve components that actually exist as user files
	const existingCustomNames = componentNames.filter((name) =>
		userComponentNames.has(name),
	);

	for (const name of existingCustomNames) {
		const cacheKey = buildCacheKey(appId, versionId, `components/${name}`);

		// Check cache first
		const cached = componentCache.get(cacheKey);
		if (cached) {
			components[name] = cached.component;
			continue;
		}

		// Fetch from API - try with .tsx extension first, then without
		let file = await resolveFile(appId, versionId, `components/${name}.tsx`);
		if (!file) {
			file = await resolveFile(appId, versionId, `components/${name}`);
		}
		if (!file) {
			// This shouldn't happen since we filtered to known files
			console.warn(`Component file not found (unexpected): ${name}`);
			continue;
		}

		// Use compiled version if available, otherwise compile on client
		const source = file.compiled || file.source;
		const useCompiled = !!file.compiled;

		const component = createComponent(source, {}, useCompiled);

		// Cache the compiled component
		componentCache.set(cacheKey, {
			component,
			compiledAt: Date.now(),
		});

		components[name] = component;
	}

	return components;
}
