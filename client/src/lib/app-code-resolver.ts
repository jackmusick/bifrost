/**
 * App Code File Resolver
 *
 * Fetches and compiles code files from the API with caching.
 * Handles component resolution for custom app components.
 */

import React from "react";
import { createComponent } from "./app-code-runtime";
import { authFetch } from "./api-client";
import type { AppCodeFile } from "./app-code-router";

/**
 * Cached component entry
 */
interface ComponentCache {
	component: React.ComponentType;
	compiledAt: number;
}

/**
 * Code file response from the new API endpoint
 */
interface AppCodeFileResponse {
	path: string;
	source: string;
}

/**
 * Cache for compiled components
 * Key format: `{appId}:{path}`
 */
const componentCache = new Map<string, ComponentCache>();

/**
 * Build cache key from app and path
 */
function buildCacheKey(appId: string, path: string): string {
	return `${appId}:${path}`;
}

/**
 * Fetch a code file from the API
 *
 * @param appId - Application ID
 * @param path - File path (e.g., "components/ClientCard")
 * @returns The file response or null if not found
 */
export async function resolveFile(
	appId: string,
	path: string,
): Promise<AppCodeFileResponse | null> {
	try {
		// URL-encode the path since it may contain slashes
		const encodedPath = encodeURIComponent(path);
		const response = await authFetch(
			`/api/applications/${appId}/files/${encodedPath}?mode=draft`,
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
	const names = new Set<string>();

	// Match JSX opening tags: <ComponentName, <Card>, <MyComponent123>
	for (const match of source.matchAll(/<([A-Z][a-zA-Z0-9]*)/g)) {
		names.add(match[1]);
	}

	// Match compiled createElement calls: React.createElement(ComponentName, ...)
	for (const match of source.matchAll(
		/React\.createElement\(([A-Z][a-zA-Z0-9]*)/g,
	)) {
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
 * Clear cache for a specific file
 *
 * @param appId - Application ID
 * @param path - File path
 */
export function clearFileCache(appId: string, path: string): void {
	const key = buildCacheKey(appId, path);
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
 * @param files - All files for an app
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
 * @param componentNames - Names referenced in JSX
 * @param userComponentNames - Set of component names that exist as user files
 * @returns Map of component name to React component
 */
export async function resolveAppComponentsFromFiles(
	appId: string,
	componentNames: string[],
	userComponentNames: Set<string>,
	/** Pre-loaded files from /render — avoids per-component API calls */
	allFiles?: AppCodeFile[],
	/** Loaded external npm dependencies keyed by package name */
	externalDeps: Record<string, Record<string, unknown>> = {},
): Promise<Record<string, React.ComponentType>> {
	const components: Record<string, React.ComponentType> = {};

	// Only resolve components that actually exist as user files
	const existingCustomNames = componentNames.filter((name) =>
		userComponentNames.has(name),
	);

	for (const name of existingCustomNames) {
		const cacheKey = buildCacheKey(appId, `components/${name}`);

		// Check cache first
		const cached = componentCache.get(cacheKey);
		if (cached) {
			components[name] = cached.component;
			continue;
		}

		let source: string | null = null;
		let isPreCompiled = false;

		if (allFiles) {
			// Resolve from in-memory file list (no API call)
			const match = allFiles.find(
				(f) =>
					f.path === `components/${name}.tsx` ||
					f.path === `components/${name}.ts` ||
					f.path === `components/${name}`,
			);
			if (match) {
				source = match.compiled || match.source;
				isPreCompiled = !!match.compiled;
			}
		} else {
			// Fallback: fetch from API individually
			let file = await resolveFile(appId, `components/${name}.tsx`);
			if (!file) {
				file = await resolveFile(appId, `components/${name}`);
			}
			if (file) {
				source = (file as AppCodeFile).compiled || file.source;
				isPreCompiled = !!(file as AppCodeFile).compiled;
			}
		}

		if (!source) {
			console.warn(`Component file not found (unexpected): ${name}`);
			continue;
		}

		const component = createComponent(source, {}, isPreCompiled, externalDeps);

		// Cache the compiled component
		componentCache.set(cacheKey, {
			component,
			compiledAt: Date.now(),
		});

		components[name] = component;
	}

	return components;
}
