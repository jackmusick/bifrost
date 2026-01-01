/**
 * App Renderer for App Builder
 *
 * Top-level page renderer that takes an ApplicationDefinition and renders the layout.
 * Handles component registration and context initialization.
 */

import { useEffect, useMemo } from "react";
import type {
	ApplicationDefinition,
	PageDefinition,
} from "@/lib/app-builder-types";
import {
	AppContextProvider,
	useExpressionContext,
} from "@/contexts/AppContext";
import { LayoutRenderer } from "./LayoutRenderer";
import { registerBasicComponents } from "./components";

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
	) => void;
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
}: AppRendererProps) {
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
	const initialVariables = useMemo((): Record<string, unknown> => {
		const vars: Record<string, unknown> = {};

		if (isApplication) {
			const app = definition as ApplicationDefinition;
			if (app.globalVariables) {
				Object.assign(vars, app.globalVariables);
			}
		}

		if (page?.variables) {
			Object.assign(vars, page.variables);
		}

		return vars;
	}, [definition, isApplication, page]);

	if (!page) {
		return (
			<div className="flex items-center justify-center p-8 text-muted-foreground">
				{pageId ? `Page "${pageId}" not found` : "No pages defined"}
			</div>
		);
	}

	return (
		<AppContextProvider
			initialVariables={initialVariables}
			onTriggerWorkflow={onTriggerWorkflow}
		>
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
