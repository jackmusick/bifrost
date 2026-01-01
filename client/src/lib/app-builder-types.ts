/**
 * App Builder Type Definitions
 *
 * Core types for the recursive layout system and component definitions.
 */

/**
 * Available component types for the app builder
 */
export type ComponentType =
	| "heading"
	| "text"
	| "card"
	| "divider"
	| "spacer"
	| "button";

/**
 * Width options for components
 */
export type ComponentWidth = "auto" | "full" | "1/2" | "1/3" | "1/4";

/**
 * Button action types
 */
export type ButtonActionType = "navigate" | "workflow" | "custom";

/**
 * Heading levels
 */
export type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;

/**
 * Layout alignment options
 */
export type LayoutAlign = "start" | "center" | "end" | "stretch";

/**
 * Layout justify options
 */
export type LayoutJustify = "start" | "center" | "end" | "between" | "around";

/**
 * Layout container types
 */
export type LayoutType = "row" | "column" | "grid";

/**
 * Data source configuration for dynamic data binding
 */
export interface DataSource {
	/** Unique identifier for the data source */
	id: string;
	/** Type of data source (api, static, computed) */
	type: "api" | "static" | "computed";
	/** API endpoint for api type */
	endpoint?: string;
	/** Static data for static type */
	data?: unknown;
	/** Expression for computed type */
	expression?: string;
	/** Whether to auto-refresh the data */
	autoRefresh?: boolean;
	/** Refresh interval in milliseconds */
	refreshInterval?: number;
}

/**
 * User information for expression context
 */
export interface ExpressionUser {
	id: string;
	name: string;
	email: string;
	role: string;
}

/**
 * Context for expression evaluation
 */
export interface ExpressionContext {
	/** Current user information */
	user?: ExpressionUser;
	/** Page-level variables */
	variables: Record<string, unknown>;
	/** Data from data sources */
	data?: Record<string, unknown>;
	/** Navigation function for button actions */
	navigate?: (path: string) => void;
	/** Workflow trigger function */
	triggerWorkflow?: (workflowId: string, params?: Record<string, unknown>) => void;
	/** Custom action handler */
	onCustomAction?: (actionId: string, params?: Record<string, unknown>) => void;
}

/**
 * Base props shared by all app components
 */
export interface BaseComponentProps {
	/** Unique component identifier */
	id: string;
	/** Component type */
	type: ComponentType;
	/** Optional width constraint */
	width?: ComponentWidth;
	/** Visibility expression (e.g., "{{ user.role == 'admin' }}") */
	visible?: string;
}

/**
 * Props for heading component
 */
export interface HeadingComponentProps extends BaseComponentProps {
	type: "heading";
	props: {
		/** Text content (supports expressions) */
		text: string;
		/** Heading level (1-6) */
		level?: HeadingLevel;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for text component
 */
export interface TextComponentProps extends BaseComponentProps {
	type: "text";
	props: {
		/** Text content (supports expressions) */
		text: string;
		/** Optional label above text */
		label?: string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for card component
 */
export interface CardComponentProps extends BaseComponentProps {
	type: "card";
	props: {
		/** Optional card title */
		title?: string;
		/** Optional card description */
		description?: string;
		/** Card content (can be a layout container or components) */
		children?: (LayoutContainer | AppComponent)[];
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for divider component
 */
export interface DividerComponentProps extends BaseComponentProps {
	type: "divider";
	props: {
		/** Divider orientation */
		orientation?: "horizontal" | "vertical";
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for spacer component
 */
export interface SpacerComponentProps extends BaseComponentProps {
	type: "spacer";
	props: {
		/** Size in pixels or Tailwind spacing units */
		size?: number | string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for button component
 */
export interface ButtonComponentProps extends BaseComponentProps {
	type: "button";
	props: {
		/** Button label (supports expressions) */
		label: string;
		/** Action type */
		actionType: ButtonActionType;
		/** Navigation path for navigate action */
		navigateTo?: string;
		/** Workflow ID for workflow action */
		workflowId?: string;
		/** Custom action ID */
		customActionId?: string;
		/** Parameters to pass to action */
		actionParams?: Record<string, unknown>;
		/** Button variant */
		variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
		/** Button size */
		size?: "default" | "sm" | "lg";
		/** Disabled state */
		disabled?: boolean;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Union type of all app components
 */
export type AppComponent =
	| HeadingComponentProps
	| TextComponentProps
	| CardComponentProps
	| DividerComponentProps
	| SpacerComponentProps
	| ButtonComponentProps;

/**
 * Layout container for organizing components
 */
export interface LayoutContainer {
	/** Layout type */
	type: LayoutType;
	/** Gap between children (in pixels or Tailwind units) */
	gap?: number;
	/** Padding (in pixels or Tailwind units) */
	padding?: number;
	/** Cross-axis alignment */
	align?: LayoutAlign;
	/** Main-axis justification */
	justify?: LayoutJustify;
	/** Grid column count (for grid type) */
	columns?: number;
	/** Visibility expression */
	visible?: string;
	/** Additional CSS classes */
	className?: string;
	/** Child elements */
	children: (LayoutContainer | AppComponent)[];
}

/**
 * Page definition for the app builder
 */
export interface PageDefinition {
	/** Page identifier */
	id: string;
	/** Page title */
	title: string;
	/** Page path/route */
	path: string;
	/** Page layout */
	layout: LayoutContainer;
	/** Page-level data sources */
	dataSources?: DataSource[];
	/** Initial page variables */
	variables?: Record<string, unknown>;
}

/**
 * Full application definition
 */
export interface ApplicationDefinition {
	/** Application identifier */
	id: string;
	/** Application name */
	name: string;
	/** Application description */
	description?: string;
	/** Application version */
	version: string;
	/** Pages in the application */
	pages: PageDefinition[];
	/** Global data sources available to all pages */
	globalDataSources?: DataSource[];
	/** Global variables available to all pages */
	globalVariables?: Record<string, unknown>;
}

/**
 * Type guard to check if an element is a LayoutContainer
 */
export function isLayoutContainer(
	element: LayoutContainer | AppComponent,
): element is LayoutContainer {
	return (
		element.type === "row" ||
		element.type === "column" ||
		element.type === "grid"
	);
}

/**
 * Type guard to check if an element is an AppComponent
 */
export function isAppComponent(
	element: LayoutContainer | AppComponent,
): element is AppComponent {
	return !isLayoutContainer(element);
}
