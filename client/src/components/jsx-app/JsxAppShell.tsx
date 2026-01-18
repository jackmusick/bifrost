/**
 * JSX App Shell
 *
 * The root component for rendering a JSX-based application.
 * Fetches all files for an app version, builds the router configuration,
 * and renders the app with proper layout and provider wrapping.
 */

import React, { useEffect, useState, useMemo } from "react";
import {
	createBrowserRouter,
	RouterProvider,
	Outlet,
	useOutletContext,
} from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { authFetch } from "@/lib/api-client";
import { buildRoutes, type JsxFile, type JsxRouteObject } from "@/lib/jsx-router";
import { createComponent } from "@/lib/jsx-runtime";
import {
	resolveAppComponents,
	extractComponentNames,
	isBuiltInComponent,
} from "@/lib/jsx-resolver";
import { PageLoader } from "@/components/PageLoader";
import { JsxErrorBoundary } from "./JsxErrorBoundary";
import { JsxPageRenderer } from "./JsxPageRenderer";

interface JsxAppShellProps {
	/** Application ID */
	appId: string;
	/** Version ID (draft or published) */
	versionId: string;
	/** Optional base path for the app (defaults to /) */
	basePath?: string;
}

/**
 * Context passed to all pages via outlet context
 */
interface JsxAppContext {
	appId: string;
	versionId: string;
}

/**
 * Hook to access app context from within pages
 */
export function useJsxAppContext(): JsxAppContext {
	return useOutletContext<JsxAppContext>();
}

/**
 * Fetch all JSX files for an app version
 */
async function fetchAppFiles(
	appId: string,
	versionId: string,
): Promise<JsxFile[]> {
	const response = await authFetch(
		`/api/apps/${appId}/versions/${versionId}/files`,
	);

	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(`Failed to fetch app files: ${errorText}`);
	}

	return response.json();
}

/**
 * Find a special file by path
 */
function findSpecialFile(
	files: JsxFile[],
	path: string,
): JsxFile | undefined {
	return files.find((f) => f.path === path);
}

/**
 * Layout wrapper component
 *
 * Renders a layout file and passes the outlet context to children.
 */
function LayoutWrapper({
	file,
	appId,
	versionId,
}: {
	file: JsxFile;
	appId: string;
	versionId: string;
}) {
	const [LayoutComponent, setLayoutComponent] =
		useState<React.ComponentType | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	const appContext = useMemo<JsxAppContext>(
		() => ({ appId, versionId }),
		[appId, versionId],
	);

	useEffect(() => {
		let cancelled = false;

		async function loadLayout() {
			setIsLoading(true);
			setError(null);

			try {
				const componentNames = extractComponentNames(file.source);
				const customNames = componentNames.filter(
					(name) => !isBuiltInComponent(name),
				);

				let customComponents: Record<string, React.ComponentType> = {};
				if (customNames.length > 0) {
					customComponents = await resolveAppComponents(
						appId,
						versionId,
						customNames,
					);
				}

				if (cancelled) return;

				const source = file.compiled || file.source;
				const useCompiled = !!file.compiled;
				const Component = createComponent(
					source,
					customComponents,
					useCompiled,
				);

				setLayoutComponent(() => Component);
			} catch (err) {
				if (cancelled) return;
				setError(
					err instanceof Error ? err.message : "Failed to load layout",
				);
			} finally {
				if (!cancelled) {
					setIsLoading(false);
				}
			}
		}

		loadLayout();

		return () => {
			cancelled = true;
		};
	}, [appId, versionId, file.id, file.source, file.compiled]);

	if (isLoading) {
		return <PageLoader message="Loading layout..." />;
	}

	if (error) {
		return (
			<div className="p-6 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg m-4">
				<h2 className="text-lg font-semibold text-red-700 dark:text-red-400">
					Layout Error
				</h2>
				<p className="text-red-600 dark:text-red-300 mt-1 text-sm">
					Failed to load {file.path}
				</p>
				<pre className="mt-3 p-3 bg-red-100 dark:bg-red-900/30 rounded text-sm text-red-800 dark:text-red-200 overflow-auto">
					{error}
				</pre>
			</div>
		);
	}

	if (!LayoutComponent) {
		// Fallback: just render children without layout
		return <Outlet context={appContext} />;
	}

	return (
		<JsxErrorBoundary filePath={file.path}>
			<LayoutComponent />
		</JsxErrorBoundary>
	);
}

/**
 * Providers wrapper component
 *
 * Wraps the entire app with _providers if it exists.
 */
function ProvidersWrapper({
	file,
	appId,
	versionId,
	children,
}: {
	file: JsxFile;
	appId: string;
	versionId: string;
	children: React.ReactNode;
}) {
	const [ProvidersComponent, setProvidersComponent] = useState<
		React.ComponentType<{ children: React.ReactNode }> | null
	>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	useEffect(() => {
		let cancelled = false;

		async function loadProviders() {
			setIsLoading(true);
			setError(null);

			try {
				const componentNames = extractComponentNames(file.source);
				const customNames = componentNames.filter(
					(name) => !isBuiltInComponent(name),
				);

				let customComponents: Record<string, React.ComponentType> = {};
				if (customNames.length > 0) {
					customComponents = await resolveAppComponents(
						appId,
						versionId,
						customNames,
					);
				}

				if (cancelled) return;

				const source = file.compiled || file.source;
				const useCompiled = !!file.compiled;
				const Component = createComponent(
					source,
					customComponents,
					useCompiled,
				);

				setProvidersComponent(
					() =>
						Component as React.ComponentType<{
							children: React.ReactNode;
						}>,
				);
			} catch (err) {
				if (cancelled) return;
				setError(
					err instanceof Error
						? err.message
						: "Failed to load providers",
				);
			} finally {
				if (!cancelled) {
					setIsLoading(false);
				}
			}
		}

		loadProviders();

		return () => {
			cancelled = true;
		};
	}, [appId, versionId, file.id, file.source, file.compiled]);

	if (isLoading) {
		return <PageLoader message="Loading app..." />;
	}

	if (error) {
		// Show error but still render children (providers are optional enhancement)
		console.error("Failed to load _providers:", error);
		return <>{children}</>;
	}

	if (!ProvidersComponent) {
		return <>{children}</>;
	}

	return (
		<JsxErrorBoundary filePath={file.path}>
			<ProvidersComponent>{children}</ProvidersComponent>
		</JsxErrorBoundary>
	);
}

/**
 * Convert JsxRouteObject to react-router RouteObject
 *
 * This function creates the actual route elements by wrapping
 * pages with JsxPageRenderer and layouts with LayoutWrapper.
 */
function convertToRouteObjects(
	routes: JsxRouteObject[],
	appId: string,
	versionId: string,
): RouteObject[] {
	return routes.map((route): RouteObject => {
		// Handle index routes specially (they have a different type shape)
		if (route.index && route.file) {
			return {
				index: true,
				element: (
					<JsxPageRenderer
						appId={appId}
						versionId={versionId}
						file={route.file}
					/>
				),
			};
		}

		// Build non-index route
		const element = route.file
			? route.isLayout
				? (
						<LayoutWrapper
							file={route.file}
							appId={appId}
							versionId={versionId}
						/>
					)
				: (
						<JsxPageRenderer
							appId={appId}
							versionId={versionId}
							file={route.file}
						/>
					)
			: route.children && route.children.length > 0
				? <Outlet context={{ appId, versionId }} />
				: undefined;

		const children =
			route.children && route.children.length > 0
				? convertToRouteObjects(route.children, appId, versionId)
				: undefined;

		return {
			path: route.path,
			element,
			children,
		};
	});
}

/**
 * App content component that renders the router
 */
function AppContent({
	files,
	appId,
	versionId,
	basePath,
}: {
	files: JsxFile[];
	appId: string;
	versionId: string;
	basePath: string;
}) {
	// Build routes from files
	const jsxRoutes = useMemo(() => buildRoutes(files), [files]);

	// Convert to react-router format
	const routeObjects = useMemo(
		() => convertToRouteObjects(jsxRoutes, appId, versionId),
		[jsxRoutes, appId, versionId],
	);

	// Create router
	const router = useMemo(() => {
		if (routeObjects.length === 0) {
			// No routes - show empty state
			return createBrowserRouter(
				[
					{
						path: "*",
						element: (
							<div className="flex items-center justify-center min-h-screen">
								<div className="text-center">
									<h2 className="text-lg font-semibold text-muted-foreground">
										No pages found
									</h2>
									<p className="text-sm text-muted-foreground mt-1">
										Create a page file to get started
									</p>
								</div>
							</div>
						),
					},
				],
				{ basename: basePath },
			);
		}

		return createBrowserRouter(routeObjects, { basename: basePath });
	}, [routeObjects, basePath]);

	return <RouterProvider router={router} />;
}

/**
 * JSX App Shell
 *
 * The main entry point for rendering a JSX-based application.
 *
 * This component:
 * 1. Fetches all files for the app version
 * 2. Builds the router configuration from page files
 * 3. Wraps with _providers if it exists
 * 4. Renders the app with proper layouts
 *
 * @example
 * ```tsx
 * <JsxAppShell
 *   appId="my-app-id"
 *   versionId="draft"
 *   basePath="/apps/my-app"
 * />
 * ```
 */
export function JsxAppShell({
	appId,
	versionId,
	basePath = "/",
}: JsxAppShellProps) {
	const [files, setFiles] = useState<JsxFile[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	useEffect(() => {
		let cancelled = false;

		async function loadApp() {
			setIsLoading(true);
			setError(null);

			try {
				const appFiles = await fetchAppFiles(appId, versionId);

				if (cancelled) return;

				setFiles(appFiles);
			} catch (err) {
				if (cancelled) return;
				setError(
					err instanceof Error
						? err.message
						: "Failed to load application",
				);
			} finally {
				if (!cancelled) {
					setIsLoading(false);
				}
			}
		}

		loadApp();

		return () => {
			cancelled = true;
		};
	}, [appId, versionId]);

	if (isLoading) {
		return <PageLoader message="Loading application..." fullScreen />;
	}

	if (error) {
		return (
			<div className="flex items-center justify-center min-h-screen p-4">
				<div className="p-6 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg max-w-lg">
					<h2 className="text-lg font-semibold text-red-700 dark:text-red-400">
						Application Error
					</h2>
					<p className="text-red-600 dark:text-red-300 mt-1 text-sm">
						Failed to load the application
					</p>
					<pre className="mt-3 p-3 bg-red-100 dark:bg-red-900/30 rounded text-sm text-red-800 dark:text-red-200 overflow-auto">
						{error}
					</pre>
				</div>
			</div>
		);
	}

	if (!files) {
		return null;
	}

	// Check for _providers file
	const providersFile = findSpecialFile(files, "_providers");

	// Render the app content
	const appContent = (
		<AppContent
			files={files}
			appId={appId}
			versionId={versionId}
			basePath={basePath}
		/>
	);

	// Wrap with providers if present
	if (providersFile) {
		return (
			<ProvidersWrapper
				file={providersFile}
				appId={appId}
				versionId={versionId}
			>
				{appContent}
			</ProvidersWrapper>
		);
	}

	return appContent;
}
