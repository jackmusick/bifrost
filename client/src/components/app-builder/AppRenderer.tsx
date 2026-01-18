/**
 * App Renderer for App Builder
 *
 * Top-level page renderer that takes an ApplicationDefinition and renders the layout.
 * Handles component registration and context initialization.
 */

import { useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
	ApplicationDefinition,
	PageDefinition,
	WorkflowResult,
	OnCompleteAction,
	ExpressionContext,
} from "@/types/app-builder";
import {
	AppContextProvider,
	useExpressionContext,
} from "@/contexts/AppContext";
import { LayoutRenderer } from "./LayoutRenderer";
import { registerBasicComponents } from "./components";
import { usePageData } from "@/hooks/usePageData";
import { useAuth } from "@/contexts/AuthContext";
import { evaluateExpression } from "@/lib/expression-parser";

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
	/** Enable preview/editor mode (click-to-select, no interactions) */
	isPreview?: boolean;
	/** Currently selected component ID (for preview mode) */
	selectedComponentId?: string | null;
	/** Callback when a component is selected (for preview mode) */
	onSelectComponent?: (componentId: string | null) => void;
}

/**
 * Internal component that renders a single page
 */
function PageRenderer({
	page,
	isPreview,
	selectedComponentId,
	onSelectComponent,
}: PageRendererProps) {
	const context = useExpressionContext();

	// In the unified model, pages have children directly instead of a layout wrapper.
	// We wrap children in a column layout for consistent rendering.
	const rootLayout = useMemo(
		() => ({
			id: `${page.id}-root`,
			type: "column" as const,
			gap: 16,
			children: page.children || [],
			// When fill_height is true, the root layout fills available space and enables
			// flex: grow so it constrains to parent height (enabling child scroll containers)
			class_name: page.fill_height ? "h-full" : undefined,
			flex: page.fill_height ? ("grow" as const) : undefined,
		}),
		[page.id, page.children, page.fill_height],
	);

	return (
		<div className={cn("app-builder-page", page.fill_height && "h-full")}>
			{/* Inject page-level CSS styles */}
			{page.styles && (
				<style
					dangerouslySetInnerHTML={{ __html: page.styles }}
					data-page-id={page.id}
				/>
			)}
			<LayoutRenderer
				layout={rootLayout}
				context={context}
				isPreview={isPreview}
				selectedComponentId={selectedComponentId}
				onSelectComponent={onSelectComponent}
			/>
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
	/** Enable preview/editor mode (click-to-select, no interactions) */
	isPreview?: boolean;
	/** Currently selected component ID (for preview mode) */
	selectedComponentId?: string | null;
	/** Callback when a component is selected (for preview mode) */
	onSelectComponent?: (componentId: string | null) => void;
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
	isPreview,
	selectedComponentId,
	onSelectComponent,
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

	// Load page data via launch workflow
	const {
		isLoading: isDataLoading,
		workflow: pageWorkflowResults,
		refresh: refreshPageData,
	} = usePageData({
		page,
		baseContext,
		executeWorkflow: dummyExecuteWorkflow,
	});

	// Combine workflow results - page results merged with externally provided
	// External results (from button clicks, etc.) take precedence
	const combinedWorkflowResults = useMemo(() => {
		const results = { ...pageWorkflowResults };
		// Add externally provided result under "default" key if present
		if (workflowResult) {
			results.default = workflowResult.result;
		}
		return results;
	}, [pageWorkflowResults, workflowResult]);

	// Refresh handler - re-executes launch workflow to refresh all data
	const handleRefreshTable = useMemo(() => {
		return (_dataSourceKey: string) => {
			// Re-execute the launch workflow to refresh data
			refreshPageData();
			// Also call external handler if provided
			if (onRefreshTable) {
				onRefreshTable(_dataSourceKey);
			}
		};
	}, [refreshPageData, onRefreshTable]);

	if (!page) {
		return (
			<div className="flex items-center justify-center p-8 text-muted-foreground">
				{pageId ? `Page "${pageId}" not found` : "No pages defined"}
			</div>
		);
	}

	// Get app-level styles if this is a full application
	const appStyles = isApplication ? (definition as ApplicationDefinition).styles : undefined;

	return (
		<AppContextProvider
			initialVariables={initialVariables}
			isDataLoading={isDataLoading}
			onTriggerWorkflow={onTriggerWorkflow}
			onRefreshTable={handleRefreshTable}
			workflowResults={combinedWorkflowResults}
			customNavigate={customNavigate}
			routeParams={routeParams}
			activeWorkflows={activeWorkflows}
		>
			{/* Inject app-level CSS styles */}
			{appStyles && (
				<style
					dangerouslySetInnerHTML={{ __html: appStyles }}
					data-app-id={isApplication ? (definition as ApplicationDefinition).id : undefined}
				/>
			)}
			{isDataLoading ? (
				<div className="flex items-center justify-center min-h-[400px]">
					<Loader2 className="h-8 w-8 animate-spin text-primary" />
				</div>
			) : (
				<PageRenderer
					page={page}
					isPreview={isPreview}
					selectedComponentId={selectedComponentId}
					onSelectComponent={onSelectComponent}
				/>
			)}
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
