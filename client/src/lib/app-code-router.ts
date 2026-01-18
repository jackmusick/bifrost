/**
 * App Code Router Builder
 *
 * Converts file-based routing conventions to react-router route configuration.
 * Handles layouts, dynamic segments, and index routes.
 */

import type { RouteObject } from "react-router-dom";

/**
 * Code file from the API
 */
export interface AppCodeFile {
	id: string;
	app_version_id: string;
	path: string;
	source: string;
	compiled: string | null;
	created_at: string;
	updated_at: string;
}

/**
 * Parsed route segment
 */
interface RouteSegment {
	/** Original segment (e.g., "[id]") */
	original: string;
	/** Converted segment for react-router (e.g., ":id") */
	param: string;
	/** Whether this is a dynamic segment */
	isDynamic: boolean;
}

/**
 * Internal tree node for building nested routes
 */
interface RouteNode {
	/** Route path segment */
	segment: string;
	/** Full path from root */
	fullPath: string;
	/** Layout file for this route level */
	layout?: AppCodeFile;
	/** Index page for this route level */
	index?: AppCodeFile;
	/** Named pages at this level (non-index) */
	pages: Map<string, AppCodeFile>;
	/** Child route nodes */
	children: Map<string, RouteNode>;
}

/**
 * Route with associated file information
 *
 * This extends RouteObject with file metadata needed for rendering.
 * The actual component rendering happens in AppCodePageRenderer.
 */
export interface AppCodeRouteObject extends Omit<RouteObject, "children"> {
	/** The code file to render for this route */
	file?: AppCodeFile;
	/** Whether this is a layout route (has Outlet) */
	isLayout?: boolean;
	/** Child routes */
	children?: AppCodeRouteObject[];
}

/**
 * Parse a file path into route segments
 *
 * @param path - File path (e.g., "pages/clients/[id]/contacts")
 * @returns Array of route segments
 *
 * @example
 * parseSegments("pages/clients/[id]/contacts")
 * // Returns: ["clients", ":id", "contacts"]
 */
function parseSegments(path: string): RouteSegment[] {
	// Remove "pages/" prefix if present
	const routePath = path.startsWith("pages/") ? path.slice(6) : path;

	// Split into segments and filter empty
	const parts = routePath.split("/").filter(Boolean);

	return parts.map((part) => {
		// Check for dynamic segment: [param]
		const dynamicMatch = part.match(/^\[([a-zA-Z_][a-zA-Z0-9_]*)\]$/);

		if (dynamicMatch) {
			return {
				original: part,
				param: `:${dynamicMatch[1]}`,
				isDynamic: true,
			};
		}

		return {
			original: part,
			param: part,
			isDynamic: false,
		};
	});
}

/**
 * Convert segments to a route path
 *
 * @param segments - Array of route segments
 * @returns Route path string (e.g., "/clients/:id/contacts")
 */
function segmentsToPath(segments: RouteSegment[]): string {
	if (segments.length === 0) return "/";
	return "/" + segments.map((s) => s.param).join("/");
}

/**
 * Get the filename without directory
 *
 * @param path - File path
 * @returns Filename (last segment)
 */
function getFileName(path: string): string {
	const parts = path.split("/");
	return parts[parts.length - 1];
}

/**
 * Get the directory path without filename
 *
 * @param path - File path
 * @returns Directory path
 */
function getDirPath(path: string): string {
	const parts = path.split("/");
	parts.pop();
	return parts.join("/");
}

/**
 * Check if a file is a page file (in pages/ directory)
 */
function isPageFile(file: AppCodeFile): boolean {
	return file.path.startsWith("pages/") || file.path === "_layout";
}

/**
 * Build the route tree from files
 *
 * @param files - All code files for the app
 * @returns Root route node
 */
function buildRouteTree(files: AppCodeFile[]): RouteNode {
	const root: RouteNode = {
		segment: "",
		fullPath: "",
		pages: new Map(),
		children: new Map(),
	};

	// Filter to only page files
	const pageFiles = files.filter(isPageFile);

	for (const file of pageFiles) {
		const fileName = getFileName(file.path);

		// Handle root _layout
		if (file.path === "_layout") {
			root.layout = file;
			continue;
		}

		// Get directory path relative to pages/
		const dirPath = getDirPath(file.path);
		const relativeDirPath = dirPath.startsWith("pages/")
			? dirPath.slice(6)
			: dirPath === "pages"
				? ""
				: dirPath;

		// Find or create the node for this directory
		let currentNode = root;
		if (relativeDirPath) {
			const segments = parseSegments(relativeDirPath);

			for (let i = 0; i < segments.length; i++) {
				const segment = segments[i];
				const fullPath = segmentsToPath(segments.slice(0, i + 1));

				if (!currentNode.children.has(segment.param)) {
					currentNode.children.set(segment.param, {
						segment: segment.param,
						fullPath,
						pages: new Map(),
						children: new Map(),
					});
				}
				currentNode = currentNode.children.get(segment.param)!;
			}
		}

		// Place the file in the appropriate slot
		if (fileName === "_layout") {
			currentNode.layout = file;
		} else if (fileName === "index") {
			currentNode.index = file;
		} else {
			// Regular page file (e.g., "billing" -> /settings/billing)
			currentNode.pages.set(fileName, file);
		}
	}

	return root;
}

/**
 * Convert a route node to a RouteObject
 *
 * @param node - Route node to convert
 * @param isRoot - Whether this is the root node
 * @returns AppCodeRouteObject or null if empty
 */
function nodeToRoute(node: RouteNode, isRoot: boolean = false): AppCodeRouteObject | null {
	const children: AppCodeRouteObject[] = [];

	// Add index route if present
	if (node.index) {
		children.push({
			index: true,
			file: node.index,
		});
	}

	// Add named page routes
	for (const [name, file] of node.pages) {
		// Convert [param] in name to :param
		const routePath = name.match(/^\[([a-zA-Z_][a-zA-Z0-9_]*)\]$/)
			? `:${name.slice(1, -1)}`
			: name;

		children.push({
			path: routePath,
			file,
		});
	}

	// Recursively add child routes
	for (const [, childNode] of node.children) {
		const childRoute = nodeToRoute(childNode, false);
		if (childRoute) {
			children.push(childRoute);
		}
	}

	// If no layout and no children, return null (empty node)
	if (!node.layout && children.length === 0) {
		return null;
	}

	// Build the route object
	if (node.layout) {
		// Layout route: wraps children with Outlet
		return {
			path: isRoot ? "/" : node.segment,
			file: node.layout,
			isLayout: true,
			children: children.length > 0 ? children : undefined,
		};
	}

	// No layout: if multiple children, create a pathless wrapper
	if (children.length > 1 || (children.length === 1 && !isRoot)) {
		return {
			path: isRoot ? "/" : node.segment,
			children,
		};
	}

	// Single child at root level: just return it
	if (children.length === 1 && isRoot) {
		const child = children[0];
		if (child.index) {
			// Index route at root becomes path: "/"
			return {
				path: "/",
				file: child.file,
			};
		}
		return {
			...child,
			path: child.path ? `/${child.path}` : "/",
		};
	}

	return null;
}

/**
 * Build react-router route configuration from code files
 *
 * Converts file-based routing conventions to RouteObject[]:
 * - `_layout` files become parent routes with Outlet
 * - `index` files become index routes
 * - `[param]` segments become `:param` dynamic routes
 * - Nested directories become nested routes
 *
 * @param files - All code files for the app version
 * @returns Array of route objects for react-router
 *
 * @example
 * ```typescript
 * const files = [
 *   { path: "_layout", ... },
 *   { path: "pages/index", ... },
 *   { path: "pages/clients/_layout", ... },
 *   { path: "pages/clients/index", ... },
 *   { path: "pages/clients/[id]/index", ... },
 * ];
 *
 * const routes = buildRoutes(files);
 * // Returns RouteObject[] ready for createBrowserRouter
 * ```
 */
export function buildRoutes(files: AppCodeFile[]): AppCodeRouteObject[] {
	if (files.length === 0) {
		return [];
	}

	const tree = buildRouteTree(files);
	const rootRoute = nodeToRoute(tree, true);

	if (!rootRoute) {
		return [];
	}

	// Return as array for react-router
	return [rootRoute];
}

/**
 * Get the route path for a file
 *
 * Useful for navigation and breadcrumbs.
 *
 * @param filePath - File path (e.g., "pages/clients/[id]/contacts")
 * @returns Route path (e.g., "/clients/:id/contacts")
 *
 * @example
 * getRoutePath("pages/clients/[id]/contacts") // "/clients/:id/contacts"
 * getRoutePath("pages/index") // "/"
 * getRoutePath("pages/settings/billing") // "/settings/billing"
 */
export function getRoutePath(filePath: string): string {
	// Handle root files
	if (filePath === "_layout" || filePath === "_providers") {
		return "/";
	}

	// Remove pages/ prefix
	if (!filePath.startsWith("pages/")) {
		return "/";
	}

	const relativePath = filePath.slice(6); // Remove "pages/"
	const fileName = getFileName(relativePath);

	// Handle index files
	if (fileName === "index") {
		const dirPath = getDirPath(relativePath);
		if (!dirPath) return "/";
		const segments = parseSegments(dirPath);
		return segmentsToPath(segments);
	}

	// Handle layout files (they represent their parent path)
	if (fileName === "_layout") {
		const dirPath = getDirPath(relativePath);
		if (!dirPath) return "/";
		const segments = parseSegments(dirPath);
		return segmentsToPath(segments);
	}

	// Regular page file
	const segments = parseSegments(relativePath);
	return segmentsToPath(segments);
}

/**
 * Check if a file path is a layout file
 */
export function isLayoutFile(filePath: string): boolean {
	return getFileName(filePath) === "_layout";
}

/**
 * Check if a file path is an index file
 */
export function isIndexFile(filePath: string): boolean {
	return getFileName(filePath) === "index";
}

/**
 * Check if a path segment is dynamic
 */
export function isDynamicSegment(segment: string): boolean {
	return /^\[([a-zA-Z_][a-zA-Z0-9_]*)\]$/.test(segment);
}

/**
 * Extract parameter name from dynamic segment
 *
 * @param segment - Dynamic segment (e.g., "[id]")
 * @returns Parameter name (e.g., "id") or null if not dynamic
 */
export function extractParamName(segment: string): string | null {
	const match = segment.match(/^\[([a-zA-Z_][a-zA-Z0-9_]*)\]$/);
	return match ? match[1] : null;
}
