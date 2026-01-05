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
import { useWorkflows } from "@/hooks/useWorkflows";
import { useWorkflowExecution } from "@/hooks/useWorkflowExecution";
import { AppRenderer, AppShell } from "@/components/app-builder";
import {
	WorkflowExecutionModal,
	type PendingWorkflow,
} from "@/components/app-builder/WorkflowExecutionModal";
import { WorkflowLoadingIndicator } from "@/components/app-builder/WorkflowLoadingIndicator";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import type {
	ApplicationDefinition,
	PageDefinition,
	WorkflowResult,
	OnCompleteAction,
	LayoutContainer,
	DataSource,
} from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

/**
 * Convert API PageDefinition to frontend PageDefinition type.
 * The API returns camelCase JSON that should match frontend types,
 * but we cast to ensure type safety.
 */
function convertApiPageToFrontend(apiPage: PageDefinitionAPI): PageDefinition {
	// API already returns camelCase - just cast with proper type coercion
	return {
		id: apiPage.id,
		title: apiPage.title,
		path: apiPage.path,
		layout: apiPage.layout as unknown as LayoutContainer,
		dataSources: (apiPage.dataSources ?? []) as unknown as DataSource[],
		variables: (apiPage.variables ?? {}) as Record<string, unknown>,
		launchWorkflowId: apiPage.launchWorkflowId ?? undefined,
		launchWorkflowParams: apiPage.launchWorkflowParams ?? undefined,
		permission: apiPage.permission
			? {
					allowedRoles: apiPage.permission.allowedRoles ?? undefined,
					accessExpression:
						apiPage.permission.accessExpression ?? undefined,
					redirectTo: apiPage.permission.redirectTo ?? undefined,
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
	const refreshDataSource = useAppBuilderStore(
		(state) => state.refreshDataSource,
	);

	// Workflow execution state
	const [pendingWorkflow, setPendingWorkflow] =
		useState<PendingWorkflow | null>(null);
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

	// Fetch workflows metadata for parameter lookup
	const { data: workflows } = useWorkflows();

	// Workflow execution with real-time WebSocket subscription
	const {
		executeWorkflow: executeWorkflowWithSubscription,
		activeExecutionIds,
		isExecuting,
		activeWorkflowNames,
	} = useWorkflowExecution({
		onExecutionComplete: (_executionId, result) => {
			setWorkflowResult(result);
			// Set last completed result for header status display
			setLastCompletedResult(result);
			// Note: Errors are now shown in the header indicator, not as toasts
		},
	});

	// Reset the runtime store when the application changes
	useEffect(() => {
		resetStore();
		return () => {
			resetStore();
		};
	}, [slugParam, resetStore]);

	// Fetch application metadata
	const {
		data: application,
		isLoading: isLoadingApp,
		error: appError,
	} = useApplication(slugParam);

	// Fetch pages list (draft for preview, live for published)
	// isDraft=true for preview mode, isDraft=false for live mode
	const {
		data: pagesResponse,
		isLoading: isLoadingPages,
		error: pagesError,
	} = useAppPages(application?.id, preview); // isDraft = preview

	// Track loaded page definitions
	const [loadedPages, setLoadedPages] = useState<PageDefinition[]>([]);
	const [isLoadingPageDefinitions, setIsLoadingPageDefinitions] =
		useState(false);
	const [pageLoadError, setPageLoadError] = useState<Error | null>(null);

	// Load full page definitions when page list is available
	useEffect(() => {
		if (!application?.id || !pagesResponse?.pages?.length) {
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
							preview, // isDraft = preview (draft for preview mode)
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
	}, [application?.id, pagesResponse?.pages, preview]);

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
			version: String(
				preview ? application.draft_version : application.live_version,
			),
			pages: loadedPages,
			navigation: undefined, // TODO: Load from application metadata if needed
			permissions: undefined, // TODO: Load from application metadata if needed
			globalDataSources: undefined,
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

		// Find matching page - try exact match first, then pattern match
		for (const page of appDefinition.pages) {
			const pagePathNormalized = page.path.startsWith("/")
				? page.path
				: `/${page.path}`;

			// Exact match
			if (pagePathNormalized === normalizedPath) {
				return { currentPage: page, routeParams: {} };
			}

			// Pattern match (for routes like /tickets/:id)
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

	// Find a workflow by ID or name
	const findWorkflow = useCallback(
		(workflowId: string): WorkflowMetadata | undefined => {
			if (!workflows) return undefined;
			// Try to find by ID first, then by name
			return workflows.find(
				(w) => w.id === workflowId || w.name === workflowId,
			);
		},
		[workflows],
	);

	// Execute workflow with parameters - now waits for actual completion via WebSocket
	const executeWorkflow = useCallback(
		async (
			workflowId: string,
			params: Record<string, unknown>,
		): Promise<WorkflowResult | undefined> => {
			const workflow = findWorkflow(workflowId);
			try {
				// Execute and wait for completion (hook handles WebSocket subscription)
				const result = await executeWorkflowWithSubscription(
					workflow?.id ?? workflowId,
					params,
				);
				return result;
			} catch (error) {
				const errorResult: WorkflowResult = {
					executionId: "",
					workflowId: workflow?.id ?? workflowId,
					workflowName: workflow?.name ?? workflowId,
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
		[executeWorkflowWithSubscription, findWorkflow],
	);

	// Check if workflow has required parameters that need user input
	const hasRequiredParams = useCallback(
		(
			workflow: WorkflowMetadata,
			providedParams: Record<string, unknown>,
		): boolean => {
			if (!workflow.parameters) return false;
			return workflow.parameters.some((param) => {
				const paramName = param.name ?? "";
				// Required param not provided
				if (param.required && !(paramName in providedParams)) {
					return true;
				}
				return false;
			});
		},
		[],
	);

	// Create a navigate function that handles relative paths within the app
	const appNavigate = useCallback(
		(path: string) => {
			// If the path is relative (doesn't start with /apps/), make it relative to current app
			if (!path.startsWith("/apps/") && !path.startsWith("http")) {
				const basePath = `/apps/${slugParam}`;
				// Normalize path to avoid double slashes
				const relativePath = path.startsWith("/")
					? path.slice(1)
					: path;
				navigate(`${basePath}/${relativePath}`);
			} else {
				navigate(path);
			}
		},
		[navigate, slugParam],
	);

	// Execute onComplete actions after workflow completes
	const executeOnCompleteActions = useCallback(
		(actions: OnCompleteAction[], result: WorkflowResult) => {
			// Build a context with the workflow result for expression evaluation
			const context = {
				variables: {} as Record<string, unknown>,
				workflow: result,
			};

			for (const action of actions) {
				switch (action.type) {
					case "navigate":
						if (action.navigateTo) {
							// Evaluate any expressions in the navigation path
							const path = action.navigateTo.includes("{{")
								? String(
										evaluateExpression(
											action.navigateTo,
											context,
										) ?? action.navigateTo,
									)
								: action.navigateTo;
							appNavigate(path);
						}
						break;

					case "set-variable":
						if (action.variableName) {
							const value = action.variableValue?.includes("{{")
								? evaluateExpression(
										action.variableValue,
										context,
									)
								: (action.variableValue ?? result.result);
							// Use the store's setVariable function directly (getState for callback context)
							useAppBuilderStore
								.getState()
								.setVariable(action.variableName, value);
						}
						break;

					case "refresh-table":
						if (action.dataSourceKey) {
							refreshDataSource(action.dataSourceKey);
						}
						break;
				}
			}
		},
		[appNavigate, refreshDataSource],
	);

	// Workflow trigger handler with onComplete and onError support
	const handleTriggerWorkflow = useCallback(
		async (
			workflowId: string,
			params?: Record<string, unknown>,
			onComplete?: OnCompleteAction[],
			onError?: OnCompleteAction[],
		) => {
			const workflow = findWorkflow(workflowId);
			const providedParams = params ?? {};

			const executeAndComplete = async (
				finalParams: Record<string, unknown>,
			) => {
				const result = await executeWorkflow(workflowId, finalParams);
				if (!result) return;

				// Execute onError actions if workflow failed
				if (
					result.status === "failed" &&
					onError &&
					onError.length > 0
				) {
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
			};

			if (!workflow) {
				// Workflow not found - execute anyway and let API handle the error
				toast.warning(
					`Workflow "${workflowId}" not found in metadata, attempting execution...`,
				);
				executeAndComplete(providedParams);
				return;
			}

			// Check if we need to show the modal for required parameters
			if (hasRequiredParams(workflow, providedParams)) {
				// Show modal to collect missing parameters
				setPendingWorkflow({
					workflow,
					providedParams,
					onExecute: async (finalParams) => {
						await executeAndComplete(finalParams);
						setPendingWorkflow(null);
					},
					onCancel: () => setPendingWorkflow(null),
				});
			} else {
				// Execute immediately with provided params
				executeAndComplete(providedParams);
			}
		},
		[
			findWorkflow,
			hasRequiredParams,
			executeWorkflow,
			executeOnCompleteActions,
		],
	);

	// Refresh table handler - delegates to the Zustand store
	const handleRefreshTable = useCallback(
		(dataSourceKey: string) => {
			refreshDataSource(dataSourceKey);
		},
		[refreshDataSource],
	);

	// Build a Set of active workflow IDs and names for button loading states
	// Include both ID and name so buttons can match either format
	const activeWorkflowsSet = useMemo(() => {
		const set = new Set<string>();
		activeWorkflowNames.forEach((name) => {
			set.add(name); // workflow name (e.g., "ticket_create")
			// Also add the workflow ID so buttons can match by either ID or name
			const workflow = workflows?.find((w) => w.name === name);
			if (workflow?.id) {
				set.add(workflow.id); // workflow UUID
			}
		});
		return set;
	}, [activeWorkflowNames, workflows]);

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

	// Render the application
	const appContent = (
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
				<WorkflowExecutionModal
					pending={pendingWorkflow}
					isExecuting={isExecuting}
				/>
			</div>
		);
	}

	// Use AppShell for full application experience
	return (
		<div className="min-h-screen bg-background" style={embedThemeStyles}>
			{/* Preview Banner */}
			{preview && (
				<div className="bg-amber-500 text-amber-950 px-4 py-2 text-center text-sm font-medium">
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
				slug={slugParam}
				currentPageId={currentPage?.id}
				showBackButton={!preview}
				activeWorkflowNames={activeWorkflowNames}
				lastCompletedResult={lastCompletedResult}
				onClearWorkflowResult={() => setLastCompletedResult(undefined)}
			>
				{appContent}
			</AppShell>

			{/* Workflow Parameters Modal */}
			<WorkflowExecutionModal
				pending={pendingWorkflow}
				isExecuting={isExecuting}
			/>
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
