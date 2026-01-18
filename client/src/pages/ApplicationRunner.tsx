/**
 * Application Runner Page
 *
 * Renders and runs a published App Builder application.
 * Integrates with the Zustand store for runtime state management.
 *
 * Uses the page-based API:
 * 1. Fetches page list via useAppPages
 * 2. Fetches each page's full layout via getAppPage
 * 3. Assembles ApplicationDefinition for the renderer
 */

import { useMemo, useCallback, useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	useApplication,
	useAppPages,
	getAppPage,
	type PageDefinition as PageDefinitionAPI,
} from "@/hooks/useApplications";
import { useWorkflowExecution } from "@/hooks/useWorkflowExecution";
import { AppRenderer, AppShell } from "@/components/app-builder";
import { WorkflowLoadingIndicator } from "@/components/app-builder/WorkflowLoadingIndicator";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import { useAppLiveUpdates } from "@/hooks/useAppLiveUpdates";
import type {
	ApplicationDefinition,
	PageDefinition,
	WorkflowResult,
	OnCompleteAction,
	ExpressionContext,
} from "@/lib/app-builder-helpers";
import { evaluateExpression } from "@/lib/expression-parser";

/**
 * Convert API PageDefinition to frontend PageDefinition type.
 * The API returns snake_case JSON - pages now have children directly.
 */
function convertApiPageToFrontend(apiPage: PageDefinitionAPI): PageDefinition {
	// API returns snake_case - keep snake_case for frontend PageDefinition
	// Pages now have children directly (no nested layout)
	return {
		id: apiPage.id,
		title: apiPage.title,
		path: apiPage.path,
		children: apiPage.children ?? [],
		variables: (apiPage.variables ?? {}) as Record<string, unknown>,
		launch_workflow_id: apiPage.launch_workflow_id ?? undefined,
		launch_workflow_params: apiPage.launch_workflow_params ?? undefined,
		launch_workflow_data_source_id: apiPage.launch_workflow_data_source_id ?? undefined,
		fill_height: apiPage.fill_height ?? undefined,
		permission: apiPage.permission
			? {
					allowed_roles: apiPage.permission.allowed_roles ?? undefined,
					access_expression:
						apiPage.permission.access_expression ?? undefined,
					redirect_to: apiPage.permission.redirect_to ?? undefined,
				}
			: undefined,
	};
}

interface ApplicationRunnerProps {
	/** Whether to render in preview mode (uses draft instead of live) */
	preview?: boolean;
	/** Whether to render in embed mode (minimal chrome, no navigation) */
	embed?: boolean;
}

export function ApplicationRunner({
	preview = false,
	embed = false,
}: ApplicationRunnerProps) {
	const { applicationId: slugParam, "*": pagePath } = useParams();
	const [searchParams] = useSearchParams();
	const navigate = useNavigate();
	const resetStore = useAppBuilderStore((state) => state.reset);
	const setAppContext = useAppBuilderStore((state) => state.setAppContext);
	const getBasePath = useAppBuilderStore((state) => state.getBasePath);
	const refreshDataSource = useAppBuilderStore(
		(state) => state.refreshDataSource,
	);

	// Workflow execution state
	const [workflowResult, setWorkflowResult] = useState<
		WorkflowResult | undefined
	>(undefined);
	// Track last completed result for header status display
	const [lastCompletedResult, setLastCompletedResult] = useState<
		WorkflowResult | undefined
	>(undefined);

	// Extract embed theme customization from URL params
	const embedTheme = useMemo(() => {
		if (!embed) return null;
		const primaryColor = searchParams.get("primaryColor");
		const backgroundColor = searchParams.get("backgroundColor");
		const textColor = searchParams.get("textColor");
		const logoUrl = searchParams.get("logo");

		if (!primaryColor && !backgroundColor && !textColor && !logoUrl) {
			return null;
		}

		return {
			primaryColor,
			backgroundColor,
			textColor,
			logoUrl,
		};
	}, [embed, searchParams]);

	// Workflow execution with real-time WebSocket subscription
	const {
		executeWorkflow: executeWorkflowWithSubscription,
		activeExecutionIds,
		activeWorkflowNames,
	} = useWorkflowExecution({
		onExecutionComplete: (_executionId, result) => {
			setWorkflowResult(result);
			// Set last completed result for header status display
			setLastCompletedResult(result);
			// Note: Errors are now shown in the header indicator, not as toasts
		},
	});

	// Reset the runtime store and set app context when the application changes
	useEffect(() => {
		resetStore();
		if (slugParam) {
			setAppContext(slugParam, preview);
		}
		return () => {
			resetStore();
		};
	}, [slugParam, preview, resetStore, setAppContext]);

	// Fetch application metadata
	const {
		data: application,
		isLoading: isLoadingApp,
		error: appError,
	} = useApplication(slugParam);

	// Fetch pages list - use draft_version_id for preview, active_version_id for live
	const versionId = preview
		? application?.draft_version_id
		: application?.active_version_id;
	const {
		data: pagesResponse,
		isLoading: isLoadingPages,
		error: pagesError,
	} = useAppPages(application?.id, versionId);

	// Live updates for real-time sync
	const { lastUpdate, newVersionAvailable, refreshApp, updateCounter } =
		useAppLiveUpdates({
			appId: application?.id,
			mode: preview ? "draft" : "live",
			currentVersionId: versionId ?? undefined,
			enabled: !!application?.id,
		});

	// Track loaded page definitions
	const [loadedPages, setLoadedPages] = useState<PageDefinition[]>([]);
	const [isLoadingPageDefinitions, setIsLoadingPageDefinitions] =
		useState(false);
	const [pageLoadError, setPageLoadError] = useState<Error | null>(null);

	// Load full page definitions when page list is available or when live update occurs
	useEffect(() => {
		if (!application?.id || !versionId || !pagesResponse?.pages?.length) {
			setLoadedPages([]);
			return;
		}

		const loadPageDefinitions = async () => {
			setIsLoadingPageDefinitions(true);
			setPageLoadError(null);

			try {
				const pages = await Promise.all(
					pagesResponse.pages.map(async (pageSummary) => {
						const pageData = await getAppPage(
							application.id,
							pageSummary.page_id,
							versionId, // Use version ID from above
						);
						// Convert API PageDefinition to frontend PageDefinition
						return convertApiPageToFrontend(pageData);
					}),
				);
				setLoadedPages(pages);
			} catch (err) {
				console.error("Failed to load page definitions:", err);
				setPageLoadError(
					err instanceof Error
						? err
						: new Error("Failed to load pages"),
				);
			} finally {
				setIsLoadingPageDefinitions(false);
			}
		};

		loadPageDefinitions();
		// Include updateCounter to reload when live updates arrive
	}, [application?.id, versionId, pagesResponse?.pages, updateCounter]);

	// Combine loading states
	const isLoadingDef = isLoadingPages || isLoadingPageDefinitions;
	const defError = pagesError || pageLoadError;

	// Build ApplicationDefinition from loaded pages
	const appDefinition = useMemo((): ApplicationDefinition | null => {
		if (!application || loadedPages.length === 0) return null;

		return {
			id: application.id,
			name: application.name,
			description: application.description ?? undefined,
			version: preview ? "preview" : "live",
			pages: loadedPages,
			navigation: application.navigation as
				| ApplicationDefinition["navigation"]
				| undefined,
			permissions: undefined, // TODO: Load from application metadata if needed
			globalVariables: undefined,
		};
	}, [application, loadedPages, preview]);

	// Match a URL path against a route pattern (e.g., /tickets/:id matches /tickets/123)
	const matchRoutePath = useCallback(
		(
			pattern: string,
			urlPath: string,
		): { match: boolean; params: Record<string, string> } => {
			const patternParts = pattern.split("/").filter(Boolean);
			const urlParts = urlPath.split("/").filter(Boolean);

			// If different number of parts, no match
			if (patternParts.length !== urlParts.length) {
				return { match: false, params: {} };
			}

			const params: Record<string, string> = {};

			for (let i = 0; i < patternParts.length; i++) {
				const patternPart = patternParts[i];
				const urlPart = urlParts[i];

				// Dynamic segment (e.g., :id)
				if (patternPart.startsWith(":")) {
					const paramName = patternPart.slice(1);
					params[paramName] = urlPart;
				} else if (patternPart !== urlPart) {
					// Static segment must match exactly
					return { match: false, params: {} };
				}
			}

			return { match: true, params };
		},
		[],
	);

	// Determine current page and extract route params
	const { currentPage, routeParams } = useMemo(() => {
		if (!appDefinition?.pages?.length) {
			return { currentPage: null, routeParams: {} };
		}

		// Normalize the page path
		const normalizedPath = pagePath
			? `/${pagePath}`.replace(/\/+/g, "/")
			: "/";

		// First pass: try exact matches on ALL pages
		// This ensures /clients/new matches before /clients/:id
		for (const page of appDefinition.pages) {
			const pagePathNormalized = page.path.startsWith("/")
				? page.path
				: `/${page.path}`;

			if (pagePathNormalized === normalizedPath) {
				return { currentPage: page, routeParams: {} };
			}
		}

		// Second pass: try pattern matches (for routes like /tickets/:id)
		for (const page of appDefinition.pages) {
			const pagePathNormalized = page.path.startsWith("/")
				? page.path
				: `/${page.path}`;

			if (pagePathNormalized.includes(":")) {
				const { match, params } = matchRoutePath(
					pagePathNormalized,
					normalizedPath,
				);
				if (match) {
					return { currentPage: page, routeParams: params };
				}
			}
		}

		// Default to first page if no match
		return { currentPage: appDefinition.pages[0], routeParams: {} };
	}, [appDefinition, pagePath, matchRoutePath]);

	// Execute workflow with parameters - waits for completion via WebSocket
	const executeWorkflow = useCallback(
		async (
			workflowId: string,
			params: Record<string, unknown>,
		): Promise<WorkflowResult | undefined> => {
			try {
				// Execute and wait for completion (hook handles WebSocket subscription)
				const result = await executeWorkflowWithSubscription(
					workflowId,
					params,
				);
				return result;
			} catch (error) {
				const errorResult: WorkflowResult = {
					executionId: "",
					workflowId: workflowId,
					workflowName: workflowId,
					status: "failed",
					error:
						error instanceof Error
							? error.message
							: "Unknown error",
				};
				setWorkflowResult(errorResult);
				toast.error(
					`Failed to execute workflow: ${error instanceof Error ? error.message : "Unknown error"}`,
				);
				return errorResult;
			}
		},
		[executeWorkflowWithSubscription],
	);

	// Create a navigate function that handles relative paths within the app
	// Uses store's getBasePath() to correctly handle preview mode
	const appNavigate = useCallback(
		(path: string) => {
			// If the path is relative (doesn't start with /apps/), make it relative to current app
			if (!path.startsWith("/apps/") && !path.startsWith("http")) {
				const basePath = getBasePath();
				// Normalize path to avoid double slashes
				const relativePath = path.startsWith("/")
					? path.slice(1)
					: path;
				navigate(`${basePath}/${relativePath}`);
			} else {
				navigate(path);
			}
		},
		[navigate, getBasePath],
	);

	// Execute onComplete actions after workflow completes
	const executeOnCompleteActions = useCallback(
		(actions: OnCompleteAction[], result: WorkflowResult) => {
			// Build a minimal context with the workflow result for expression evaluation
			// Use "current" key so expressions like {{ workflow.current.result.id }} work
			const context = {
				variables: {} as Record<string, unknown>,
				workflow: {
					current: result,
				},
			} as ExpressionContext;

			for (const action of actions) {
				switch (action.type) {
					case "navigate":
						if (action.navigate_to) {
							// Evaluate any expressions in the navigation path
							const path = action.navigate_to.includes("{{")
								? String(
										evaluateExpression(
											action.navigate_to,
											context,
										) ?? action.navigate_to,
									)
								: action.navigate_to;
							appNavigate(path);
						}
						break;

					case "set-variable":
						if (action.variable_name) {
							const value = action.variable_value?.includes("{{")
								? evaluateExpression(
										action.variable_value,
										context,
									)
								: (action.variable_value ?? result.result);
							// Use the store's setVariable function directly (getState for callback context)
							useAppBuilderStore
								.getState()
								.setVariable(action.variable_name, value);
						}
						break;

					case "refresh-table":
						if (action.data_source_key) {
							refreshDataSource(action.data_source_key);
						}
						break;
				}
			}
		},
		[appNavigate, refreshDataSource],
	);

	// Workflow trigger handler with onComplete and onError support
	// Executes workflow directly - server validates parameters
	const handleTriggerWorkflow = useCallback(
		async (
			workflowId: string,
			params?: Record<string, unknown>,
			onComplete?: OnCompleteAction[],
			onError?: OnCompleteAction[],
		) => {
			const providedParams = params ?? {};

			const result = await executeWorkflow(workflowId, providedParams);
			if (!result) return;

			// Execute onError actions if workflow failed
			if (result.status === "failed" && onError && onError.length > 0) {
				executeOnCompleteActions(onError, result);
			}
			// Execute onComplete actions if workflow succeeded
			else if (
				result.status === "completed" &&
				onComplete &&
				onComplete.length > 0
			) {
				executeOnCompleteActions(onComplete, result);
			}
		},
		[executeWorkflow, executeOnCompleteActions],
	);

	// Refresh table handler - delegates to the Zustand store
	const handleRefreshTable = useCallback(
		(dataSourceKey: string) => {
			refreshDataSource(dataSourceKey);
		},
		[refreshDataSource],
	);

	// Build a Set of active workflow names for button loading states
	// activeWorkflowNames is Map<executionId, workflowName>, we want just the names
	const activeWorkflowsSet = useMemo(
		() => new Set(activeWorkflowNames.values()),
		[activeWorkflowNames],
	);

	// Build inline styles for embed theme customization
	const embedThemeStyles = useMemo(() => {
		if (!embedTheme) return undefined;
		const styles: Record<string, string> = {};
		if (embedTheme.primaryColor) {
			styles["--primary"] = embedTheme.primaryColor;
		}
		if (embedTheme.backgroundColor) {
			styles["--background"] = embedTheme.backgroundColor;
		}
		if (embedTheme.textColor) {
			styles["--foreground"] = embedTheme.textColor;
		}
		return styles as React.CSSProperties;
	}, [embedTheme]);

	// Get page transition configuration (defaults to 'fade')
	const pageTransition = appDefinition?.navigation?.page_transition;

	// Get transition animation props based on configuration
	const getTransitionProps = useCallback((transition: string | undefined | null) => {
		const type = transition || "fade";
		switch (type) {
			case "none":
				return {};
			case "blur":
				return {
					initial: { opacity: 0, filter: "blur(8px)" },
					animate: { opacity: 1, filter: "blur(0px)" },
					exit: { opacity: 0, filter: "blur(8px)" },
					transition: { duration: 0.3 },
				};
			case "slide":
				return {
					initial: { opacity: 0, x: 20 },
					animate: { opacity: 1, x: 0 },
					exit: { opacity: 0, x: -20 },
					transition: { duration: 0.2 },
				};
			case "fade":
			default:
				return {
					initial: { opacity: 0 },
					animate: { opacity: 1 },
					exit: { opacity: 0 },
					transition: { duration: 0.2 },
				};
		}
	}, []);

	// Loading state
	if (isLoadingApp || isLoadingDef) {
		return (
			<div className="min-h-screen flex items-center justify-center">
				<div className="flex flex-col items-center gap-4">
					<Loader2 className="h-8 w-8 animate-spin text-primary" />
					<p className="text-muted-foreground">
						Loading application...
					</p>
				</div>
			</div>
		);
	}

	// Error states
	if (appError || defError) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-destructive">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Application Error</CardTitle>
						</div>
						<CardDescription>
							{appError instanceof Error
								? appError.message
								: defError instanceof Error
									? defError.message
									: "Failed to load application"}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back to Applications
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// No application found
	if (!application) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Application Not Found</CardTitle>
						</div>
						<CardDescription>
							The requested application does not exist or you
							don't have access to it.
						</CardDescription>
					</CardHeader>
					<CardContent>
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back to Applications
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// No published version (and not in preview mode)
	if (!preview && !application.is_published) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Not Published</CardTitle>
						</div>
						<CardDescription>
							This application has not been published yet. Please
							publish the application before accessing it.
						</CardDescription>
					</CardHeader>
					<CardContent className="flex gap-2">
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back
						</Button>
						<Button
							onClick={() => navigate(`/apps/${slugParam}/edit`)}
						>
							Open Editor
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// No definition available
	if (!appDefinition) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>No Content</CardTitle>
						</div>
						<CardDescription>
							{preview
								? "No draft version is available for this application."
								: "This application has no published content."}
						</CardDescription>
					</CardHeader>
					<CardContent className="flex gap-2">
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back
						</Button>
						<Button
							onClick={() => navigate(`/apps/${slugParam}/edit`)}
						>
							Open Editor
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// Render the application with page transitions
	const transitionProps = getTransitionProps(pageTransition);
	const appContent = (
		<AnimatePresence mode="wait">
			<motion.div
				key={currentPage?.id || "default"}
				{...transitionProps}
				className="h-full"
			>
				<AppRenderer
					definition={currentPage || appDefinition}
					pageId={currentPage?.id}
					onTriggerWorkflow={handleTriggerWorkflow}
					executeWorkflow={executeWorkflow}
					onRefreshTable={handleRefreshTable}
					workflowResult={workflowResult}
					navigate={appNavigate}
					routeParams={routeParams}
					activeWorkflows={activeWorkflowsSet}
				/>
			</motion.div>
		</AnimatePresence>
	);

	// In embed mode, use minimal shell
	if (embed) {
		return (
			<div
				className="min-h-screen bg-background"
				style={embedThemeStyles}
			>
				<div className="p-4">{appContent}</div>
				<WorkflowLoadingIndicator
					activeCount={activeExecutionIds.length}
					workflowNames={activeWorkflowNames}
				/>
			</div>
		);
	}

	// Use AppShell for full application experience
	return (
		<div className="h-screen flex flex-col bg-background" style={embedThemeStyles}>
			{/* Preview Banner */}
			{preview && (
				<div className="sticky top-0 z-50 bg-amber-500 text-amber-950 px-4 py-2 text-center text-sm font-medium flex-shrink-0">
					Preview Mode - This is the draft version
					<Button
						variant="link"
						size="sm"
						className="ml-2 text-amber-950 underline"
						onClick={() => navigate(`/apps/${slugParam}/edit`)}
					>
						Back to Editor
					</Button>
				</div>
			)}

			{/* AppShell with sidebar and header */}
			<AppShell
				app={appDefinition}
				currentPageId={currentPage?.id}
				showBackButton={!preview}
				activeWorkflowNames={activeWorkflowNames}
				lastCompletedResult={lastCompletedResult}
				onClearWorkflowResult={() => setLastCompletedResult(undefined)}
				lastUpdate={lastUpdate}
				newVersionAvailable={newVersionAvailable}
				onRefresh={refreshApp}
				isPreview={preview}
			>
				{appContent}
			</AppShell>
		</div>
	);
}

/**
 * Preview wrapper component
 */
export function ApplicationPreview() {
	return <ApplicationRunner preview />;
}

/**
 * Embed wrapper component for iframe embedding
 * Minimal chrome, no navigation bars
 */
export function ApplicationEmbed() {
	return <ApplicationRunner embed />;
}
