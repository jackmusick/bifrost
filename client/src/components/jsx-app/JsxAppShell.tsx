/**
 * JSX App Shell
 *
 * The root component for rendering a JSX-based application.
 * Fetches all files for an app, builds the router configuration,
 * and renders the app with proper layout and provider wrapping.
 */

import React, { useEffect, useState, useMemo } from "react";
import {
	Routes,
	Route,
	Outlet,
	useOutletContext,
} from "react-router-dom";
import { authFetch } from "@/lib/api-client";
import { buildRoutes, type AppCodeFile, type AppCodeRouteObject } from "@/lib/app-code-router";
import { createComponent } from "@/lib/app-code-runtime";
import {
	resolveAppComponentsFromFiles,
	extractComponentNames,
	getUserComponentNames,
} from "@/lib/app-code-resolver";
import { PageLoader } from "@/components/PageLoader";
import { AppLoadingSkeleton } from "./AppLoadingSkeleton";
import { JsxErrorBoundary } from "./JsxErrorBoundary";
import { JsxPageRenderer } from "./JsxPageRenderer";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import { useAppCodeUpdates } from "@/hooks/useAppCodeUpdates";

/**
 * Response shape from the file listing endpoint (editor)
 */
interface AppFileListResponse {
	files: AppCodeFile[];
	total: number;
}

/**
 * Response shape from the render endpoint
 */
interface AppRenderResponse {
	files: Array<{ path: string; code: string }>;
	total: number;
}

interface JsxAppShellProps {
	/** Application ID */
	appId: string;
	/** Application slug for URL routing */
	appSlug: string;
	/** Whether this is preview mode (uses draft files) */
	isPreview?: boolean;
}

/**
 * Context passed to all pages via outlet context
 */
interface JsxAppContext {
	appId: string;
	/** Set of component names that exist as user files in components/ */
	userComponentNames: Set<string>;
	/** All pre-loaded files (for resolving components without API calls) */
	allFiles: AppCodeFile[];
}

/**
 * Hook to access app context from within pages
 */
export function useJsxAppContext(): JsxAppContext {
	return useOutletContext<JsxAppContext>();
}

/**
 * Fetch all compiled app files for rendering.
 *
 * Uses the /render endpoint which returns pre-compiled JS and
 * batch-compiles on demand if any files are missing compiled versions.
 */
async function fetchAppFiles(
	appId: string,
	mode: "draft" | "live",
): Promise<AppCodeFile[]> {
	const response = await authFetch(
		`/api/applications/${appId}/render?mode=${mode}`,
	);

	if (!response.ok) {
		const errorText = await response.text();
		throw new Error(`Failed to fetch app files: ${errorText}`);
	}

	const data: AppRenderResponse = await response.json();
	// Map render response to AppCodeFile shape.
	// code is already compiled JS — set as both source and compiled
	// so the runtime uses the compiled path.
	return data.files.map((f) => ({
		path: f.path,
		source: f.code,
		compiled: f.code,
	}));
}

/**
 * Find a special file by path
 */
function findSpecialFile(
	files: AppCodeFile[],
	path: string,
): AppCodeFile | undefined {
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
	userComponentNames,
	allFiles,
}: {
	file: AppCodeFile;
	appId: string;
	userComponentNames: Set<string>;
	allFiles: AppCodeFile[];
}) {
	const [LayoutComponent, setLayoutComponent] =
		useState<React.ComponentType | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	const appContext = useMemo<JsxAppContext>(
		() => ({ appId, userComponentNames, allFiles }),
		[appId, userComponentNames, allFiles],
	);

	useEffect(() => {
		let cancelled = false;

		async function loadLayout() {
			setIsLoading(true);
			setError(null);

			try {
				const componentNames = extractComponentNames(file.source);

				let customComponents: Record<string, React.ComponentType> = {};
				if (componentNames.length > 0) {
					customComponents = await resolveAppComponentsFromFiles(
						appId,
						componentNames,
						userComponentNames,
						allFiles,
					);
				}

				if (cancelled) return;

				// Use compiled code when available, skip client-side compilation
				const Component = createComponent(
					file.compiled || file.source,
					customComponents,
					!!file.compiled,
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
	}, [appId, userComponentNames, allFiles, file.path, file.source]);

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
		<JsxErrorBoundary filePath={file.path} resetKey={file.source}>
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
	userComponentNames,
	allFiles,
	children,
}: {
	file: AppCodeFile;
	appId: string;
	userComponentNames: Set<string>;
	allFiles: AppCodeFile[];
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

				let customComponents: Record<string, React.ComponentType> = {};
				if (componentNames.length > 0) {
					customComponents = await resolveAppComponentsFromFiles(
						appId,
						componentNames,
						userComponentNames,
						allFiles,
					);
				}

				if (cancelled) return;

				// Use compiled code when available, skip client-side compilation
				const Component = createComponent(
					file.compiled || file.source,
					customComponents,
					!!file.compiled,
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
	}, [appId, userComponentNames, allFiles, file.path, file.source]);

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
		<JsxErrorBoundary filePath={file.path} resetKey={file.source}>
			<ProvidersComponent>{children}</ProvidersComponent>
		</JsxErrorBoundary>
	);
}

/**
 * Recursively render Route elements from route objects
 */
function renderRoutes(
	routes: AppCodeRouteObject[],
	appId: string,
	userComponentNames: Set<string>,
	allFiles: AppCodeFile[],
): React.ReactNode {
	return routes.map((route, index) => {
		// Handle index routes
		if (route.index && route.file) {
			return (
				<Route
					key={`index-${index}`}
					index
					element={
						<JsxPageRenderer
							appId={appId}
							file={route.file}
							userComponentNames={userComponentNames}
							allFiles={allFiles}
						/>
					}
				/>
			);
		}

		// Build element for this route
		const element = route.file
			? route.isLayout
				? (
						<LayoutWrapper
							file={route.file}
							appId={appId}
							userComponentNames={userComponentNames}
							allFiles={allFiles}
						/>
					)
				: (
						<JsxPageRenderer
							appId={appId}
							file={route.file}
							userComponentNames={userComponentNames}
							allFiles={allFiles}
						/>
					)
			: route.children && route.children.length > 0
				? <Outlet context={{ appId, userComponentNames, allFiles }} />
				: undefined;

		// Render with children if any
		if (route.children && route.children.length > 0) {
			return (
				<Route key={route.path || index} path={route.path} element={element}>
					{renderRoutes(route.children, appId, userComponentNames, allFiles)}
				</Route>
			);
		}

		return (
			<Route
				key={route.path || index}
				path={route.path}
				element={element}
			/>
		);
	});
}

/**
 * App content component that renders routes
 */
function AppContent({
	files,
	appId,
	userComponentNames,
}: {
	files: AppCodeFile[];
	appId: string;
	userComponentNames: Set<string>;
}) {
	// Build routes from files
	const jsxRoutes = useMemo(() => buildRoutes(files), [files]);

	if (jsxRoutes.length === 0) {
		return (
			<div className="flex items-center justify-center h-full min-h-[200px]">
				<div className="text-center">
					<h2 className="text-lg font-semibold text-muted-foreground">
						No pages found
					</h2>
					<p className="text-sm text-muted-foreground mt-1">
						Create a page file to get started
					</p>
				</div>
			</div>
		);
	}

	return (
		<Routes>
			{renderRoutes(jsxRoutes, appId, userComponentNames, files)}
		</Routes>
	);
}

/**
 * JSX App Shell
 *
 * The main entry point for rendering a JSX-based application.
 *
 * This component:
 * 1. Sets up app context for navigation path transformation
 * 2. Fetches all files for the app
 * 3. Builds the router configuration from page files
 * 4. Wraps with _providers if it exists
 * 5. Renders the app with proper layouts
 *
 * @example
 * ```tsx
 * <JsxAppShell
 *   appId="my-app-id"
 *   appSlug="my-app"
 *   isPreview={true}
 * />
 * ```
 */
export function JsxAppShell({
	appId,
	appSlug,
	isPreview = false,
}: JsxAppShellProps) {
	const [files, setFiles] = useState<AppCodeFile[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const setAppContext = useAppBuilderStore((state) => state.setAppContext);

	// Determine file mode based on preview flag
	const mode = isPreview ? "draft" : "live";

	// Real-time updates via WebSocket (only in preview mode)
	const { updateCounter } = useAppCodeUpdates({
		appId,
		enabled: isPreview,
	});

	// Set app context for navigation path transformation
	useEffect(() => {
		setAppContext(appSlug, isPreview);

		// Clear context on unmount
		return () => {
			setAppContext("", false);
		};
	}, [appSlug, isPreview, setAppContext]);

	useEffect(() => {
		let cancelled = false;

		async function loadApp() {
			setIsLoading(true);
			setError(null);

			try {
				const appFiles = await fetchAppFiles(appId, mode);

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
	}, [appId, mode, updateCounter]);

	// Compute user component names from files list (memoized)
	// Must be called before any conditional returns to satisfy React Hooks rules
	const userComponentNames = useMemo(
		() => (files ? getUserComponentNames(files) : new Set<string>()),
		[files],
	);

	if (isLoading) {
		return <AppLoadingSkeleton message="Loading application..." />;
	}

	if (error) {
		return (
			<div className="flex items-center justify-center h-full min-h-[200px] p-4">
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
			userComponentNames={userComponentNames}
		/>
	);

	// Wrap with providers if present
	if (providersFile) {
		return (
			<div className="h-full w-full overflow-hidden">
				<ProvidersWrapper
					file={providersFile}
					appId={appId}
					userComponentNames={userComponentNames}
					allFiles={files}
				>
					{appContent}
				</ProvidersWrapper>
			</div>
		);
	}

	return <div className="h-full w-full overflow-hidden">{appContent}</div>;
}
