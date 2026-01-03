/**
 * App Renderer for App Builder
 *
 * Top-level page renderer that takes an ApplicationDefinition and renders the layout.
 * Handles component registration and context initialization.
 */

import { useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";
import type {
	ApplicationDefinition,
	PageDefinition,
	WorkflowResult,
	OnCompleteAction,
} from "@/lib/app-builder-types";
import {
	AppContextProvider,
	useExpressionContext,
} from "@/contexts/AppContext";
import { LayoutRenderer } from "./LayoutRenderer";
import { registerBasicComponents } from "./components";
import { usePageData } from "@/hooks/usePageData";
import { useAuth } from "@/contexts/AuthContext";
import { evaluateExpression } from "@/lib/expression-parser";
import type { ExpressionContext } from "@/lib/app-builder-types";

// Track if components have been registered
let componentsRegistered = false;

/**
 * Ensure basic components are registered (idempotent)
 */
function ensureComponentsRegistered(): void {
	if (!componentsRegistered) {
		registerBasicComponents();
		componentsRegistered = true;
	}
}

interface PageRendererProps {
	/** The page definition to render */
	page: PageDefinition;
}

/**
 * Internal component that renders a single page
 */
function PageRenderer({ page }: PageRendererProps) {
	const context = useExpressionContext();

	return (
		<div className="app-builder-page">
			<LayoutRenderer layout={page.layout} context={context} />
		</div>
	);
}

interface AppRendererProps {
	/** The application or page definition to render */
	definition: ApplicationDefinition | PageDefinition;
	/** Page ID to render (for multi-page applications) */
	pageId?: string;
	/** Custom workflow trigger handler */
	onTriggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
		onComplete?: OnCompleteAction[],
	) => void;
	/** Execute a workflow and return result (for data loading) */
	executeWorkflow?: (
		workflowId: string,
		params: Record<string, unknown>,
	) => Promise<WorkflowResult | undefined>;
	/** Handler for refreshing a data table */
	onRefreshTable?: (dataSourceKey: string) => void;
	/** Current workflow result for context injection */
	workflowResult?: WorkflowResult;
	/** Custom navigate function (for relative path handling) */
	navigate?: (path: string) => void;
	/** Route parameters from URL (e.g., { id: "123" } for /tickets/:id) */
	routeParams?: Record<string, string>;
	/** Currently executing workflow IDs/names for loading states */
	activeWorkflows?: Set<string>;
}

/**
 * App Renderer Component
 *
 * Top-level renderer for App Builder applications.
 * Initializes the component registry and provides context.
 *
 * @example
 * // Render a full application
 * <AppRenderer
 *   definition={myAppDefinition}
 *   pageId="home"
 *   onTriggerWorkflow={(id, params) => runWorkflow(id, params)}
 * />
 *
 * @example
 * // Render a single page
 * <AppRenderer
 *   definition={myPageDefinition}
 *   onTriggerWorkflow={(id, params) => runWorkflow(id, params)}
 * />
 */
export function AppRenderer({
	definition,
	pageId,
	onTriggerWorkflow,
	executeWorkflow,
	onRefreshTable,
	workflowResult,
	navigate: customNavigate,
	routeParams = {},
	activeWorkflows,
}: AppRendererProps) {
	const { user: authUser } = useAuth();

	// Ensure components are registered on mount
	useEffect(() => {
		ensureComponentsRegistered();
	}, []);

	// Determine if this is a full application or single page
	const isApplication = "pages" in definition;

	// Get the page to render
	const page = useMemo((): PageDefinition | null => {
		if (!isApplication) {
			return definition as PageDefinition;
		}

		const app = definition as ApplicationDefinition;
		if (pageId) {
			return app.pages.find((p) => p.id === pageId) || null;
		}

		// Default to first page
		return app.pages[0] || null;
	}, [definition, isApplication, pageId]);

	// Build initial variables from app and page
	// Page variables can contain expressions like {{ params.ticketId }} that need evaluation
	const initialVariables = useMemo((): Record<string, unknown> => {
		const vars: Record<string, unknown> = {};

		if (isApplication) {
			const app = definition as ApplicationDefinition;
			if (app.globalVariables) {
				Object.assign(vars, app.globalVariables);
			}
		}

		if (page?.variables) {
			// Create a minimal context for evaluating variable expressions
			// Variables can reference params (route params) and user
			const evalContext: Partial<ExpressionContext> = {
				params: routeParams,
				user: authUser
					? {
							id: authUser.id,
							name: authUser.name,
							email: authUser.email,
							role: authUser.roles[0] || "user",
						}
					: undefined,
				variables: vars, // Already-evaluated variables for chained refs
			};

			// Evaluate each variable value if it contains expressions
			for (const [key, value] of Object.entries(page.variables)) {
				if (typeof value === "string" && value.includes("{{")) {
					vars[key] = evaluateExpression(
						value,
						evalContext as ExpressionContext,
					);
				} else {
					vars[key] = value;
				}
			}
		}

		return vars;
	}, [definition, isApplication, page, routeParams, authUser]);

	// Build base context for page data loading
	const baseContext = useMemo(
		() => ({
			user: authUser
				? {
						id: authUser.id,
						name: authUser.name,
						email: authUser.email,
						role: authUser.roles[0] || "user",
					}
				: undefined,
			variables: initialVariables,
			params: routeParams,
		}),
		[authUser, initialVariables, routeParams],
	);

	// Dummy executeWorkflow if not provided
	const dummyExecuteWorkflow = useMemo(() => {
		if (executeWorkflow) return executeWorkflow;
		return async (
			_workflowId: string,
			_params: Record<string, unknown>,
		) => {
			console.warn("No executeWorkflow handler provided to AppRenderer");
			return undefined;
		};
	}, [executeWorkflow]);

	// Load page data (launch workflow and data sources)
	const {
		data: pageData,
		isLoading: isDataLoading,
		isLaunchWorkflowLoading,
		launchWorkflowResult,
		refreshDataSource,
	} = usePageData({
		page,
		baseContext,
		executeWorkflow: dummyExecuteWorkflow,
	});

	// Combine workflow results - prefer launch workflow result, then externally provided
	const combinedWorkflowResult = launchWorkflowResult ?? workflowResult;

	// Enhanced refresh handler that checks page data sources first
	const handleRefreshTable = useMemo(() => {
		return (dataSourceKey: string) => {
			// Try to refresh from page data sources first
			if (page?.dataSources?.some((ds) => ds.id === dataSourceKey)) {
				refreshDataSource(dataSourceKey);
			}
			// Also call external handler if provided
			if (onRefreshTable) {
				onRefreshTable(dataSourceKey);
			}
		};
	}, [page, refreshDataSource, onRefreshTable]);

	if (!page) {
		return (
			<div className="flex items-center justify-center p-8 text-muted-foreground">
				{pageId ? `Page "${pageId}" not found` : "No pages defined"}
			</div>
		);
	}

	// Show loading state while launch workflow is executing
	if (isLaunchWorkflowLoading) {
		return (
			<div className="flex items-center justify-center p-8">
				<div className="flex flex-col items-center gap-3">
					<Loader2 className="h-6 w-6 animate-spin text-primary" />
					<p className="text-sm text-muted-foreground">
						Initializing page...
					</p>
				</div>
			</div>
		);
	}

	return (
		<AppContextProvider
			initialVariables={initialVariables}
			initialData={pageData}
			isDataLoading={isDataLoading}
			onTriggerWorkflow={onTriggerWorkflow}
			onRefreshTable={handleRefreshTable}
			workflowResult={combinedWorkflowResult}
			customNavigate={customNavigate}
			routeParams={routeParams}
			activeWorkflows={activeWorkflows}
		>
			{isDataLoading && (
				<div className="absolute top-2 right-2 flex items-center gap-2 text-xs text-muted-foreground bg-background/80 px-2 py-1 rounded">
					<Loader2 className="h-3 w-3 animate-spin" />
					Loading data...
				</div>
			)}
			<PageRenderer page={page} />
		</AppContextProvider>
	);
}

/**
 * Standalone page renderer that uses existing context
 *
 * Use this when you want to render a page within an existing AppContextProvider.
 *
 * @example
 * <AppContextProvider>
 *   <StandalonePageRenderer page={myPage} />
 * </AppContextProvider>
 */
export function StandalonePageRenderer({ page }: PageRendererProps) {
	// Ensure components are registered
	useEffect(() => {
		ensureComponentsRegistered();
	}, []);

	return <PageRenderer page={page} />;
}

export default AppRenderer;
