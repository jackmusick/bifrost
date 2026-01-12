/**
 * App Builder Helper Functions and Runtime Types
 *
 * This file contains:
 * 1. Runtime helper functions for working with app builder types
 * 2. Frontend-only types not defined in the backend API (e.g., ExpressionContext)
 * 3. Core union types (AppComponent, LayoutContainer) that exclude AppComponentNode
 *    for proper discriminated union behavior
 * 4. All literal types and type aliases for backward compatibility
 *
 * Import from this file for:
 * - Runtime functions: isLayoutContainer, isAppComponent, canHaveChildren, getElementChildren
 * - Constants: CONTAINER_TYPES
 * - Frontend-only types: ExpressionContext, ExpressionUser, WorkflowResult
 * - Core types: AppComponent, LayoutContainer, LayoutElement
 * - Literal types: ComponentType, LayoutType, etc.
 * - Navigation types: NavItem, NavigationConfig, ApplicationDefinition
 */

import type { components } from "./v1";

// =============================================================================
// Literal Types
// =============================================================================

/**
 * Available component types for the app builder
 */
export type ComponentType =
	| "heading"
	| "text"
	| "html"
	| "card"
	| "divider"
	| "spacer"
	| "button"
	| "stat-card"
	| "image"
	| "badge"
	| "progress"
	| "data-table"
	| "tabs"
	| "file-viewer"
	| "modal"
	| "text-input"
	| "number-input"
	| "select"
	| "checkbox"
	| "form-embed"
	| "form-group";

/**
 * Width options for components
 */
export type ComponentWidth = "auto" | "full" | "1/2" | "1/3" | "1/4" | "2/3" | "3/4";

/**
 * Button action types
 */
export type ButtonActionType = "navigate" | "workflow" | "custom" | "submit" | "open-modal";

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
 * Layout max-width options for constraining container width
 */
export type LayoutMaxWidth = "sm" | "md" | "lg" | "xl" | "2xl" | "full" | "none";

/**
 * Layout container types
 */
export type LayoutType = "row" | "column" | "grid";

/**
 * How container children fill available space
 */
export type LayoutDistribute = "natural" | "equal" | "fit";

/**
 * Overflow behavior for scrollable containers
 */
export type LayoutOverflow = "auto" | "scroll" | "hidden" | "visible";

/**
 * Sticky positioning options
 */
export type LayoutSticky = "top" | "bottom";

/**
 * File display mode for file-viewer component
 */
export type FileViewerDisplayMode = "inline" | "modal" | "download";

/**
 * Data source type
 */
export type DataSourceType = "api" | "static" | "computed" | "data-provider" | "workflow";

// =============================================================================
// Re-export types from v1.d.ts for convenience
// =============================================================================

export type RepeatFor = components["schemas"]["RepeatFor"];
export type OnCompleteAction = components["schemas"]["OnCompleteAction"];
export type TableColumn = components["schemas"]["TableColumn"];
export type TableAction = components["schemas"]["TableAction"];
export type TabItem = components["schemas"]["TabItem"];
export type SelectOption = components["schemas"]["SelectOption"];
export type PageDefinition = components["schemas"]["PageDefinition"];
export type DataSourceConfig = components["schemas"]["DataSourceConfig"];
export type PagePermission = components["schemas"]["PagePermission"];

// Props types
export type HeadingProps = components["schemas"]["HeadingProps"];
export type TextProps = components["schemas"]["TextProps"];
export type HtmlProps = components["schemas"]["HtmlProps"];
export type CardProps = components["schemas"]["CardProps"];
export type DividerProps = components["schemas"]["DividerProps"];
export type SpacerProps = components["schemas"]["SpacerProps"];
export type ButtonProps = components["schemas"]["ButtonProps"];
export type StatCardProps = components["schemas"]["StatCardProps"];
export type ImageProps = components["schemas"]["ImageProps"];
export type BadgeProps = components["schemas"]["BadgeProps"];
export type ProgressProps = components["schemas"]["ProgressProps"];
export type DataTableProps = components["schemas"]["DataTableProps"];
export type TabsProps = components["schemas"]["TabsProps"];
export type FileViewerProps = components["schemas"]["FileViewerProps"];
export type ModalProps = components["schemas"]["ModalProps"];
export type TextInputProps = components["schemas"]["TextInputProps"];
export type NumberInputProps = components["schemas"]["NumberInputProps"];
export type SelectProps = components["schemas"]["SelectProps"];
export type CheckboxProps = components["schemas"]["CheckboxProps"];
export type FormEmbedProps = components["schemas"]["FormEmbedProps"];
export type FormGroupProps = components["schemas"]["FormGroupProps"];

// Full component types (with id, type, props, and common fields)
export type HeadingComponentProps = components["schemas"]["HeadingComponent"];
export type TextComponentProps = components["schemas"]["TextComponent"];
export type HtmlComponentProps = components["schemas"]["HtmlComponent"];
export type CardComponentProps = components["schemas"]["CardComponent"];
export type DividerComponentProps = components["schemas"]["DividerComponent"];
export type SpacerComponentProps = components["schemas"]["SpacerComponent"];
export type ButtonComponentProps = components["schemas"]["ButtonComponent"];
export type StatCardComponentProps = components["schemas"]["StatCardComponent"];
export type ImageComponentProps = components["schemas"]["ImageComponent"];
export type BadgeComponentProps = components["schemas"]["BadgeComponent"];
export type ProgressComponentProps = components["schemas"]["ProgressComponent"];
export type DataTableComponentProps = components["schemas"]["DataTableComponent"];
export type TabsComponentProps = components["schemas"]["TabsComponent"];
export type FileViewerComponentProps = components["schemas"]["FileViewerComponent"];
export type ModalComponentProps = components["schemas"]["ModalComponent"];
export type TextInputComponentProps = components["schemas"]["TextInputComponent"];
export type NumberInputComponentProps = components["schemas"]["NumberInputComponent"];
export type SelectComponentProps = components["schemas"]["SelectComponent"];
export type CheckboxComponentProps = components["schemas"]["CheckboxComponent"];
export type FormEmbedComponentProps = components["schemas"]["FormEmbedComponent"];
export type FormGroupComponentProps = components["schemas"]["FormGroupComponent"];

// =============================================================================
// Navigation and Permission Types (frontend-only, not in API)
// =============================================================================

/**
 * Permission rule for app access control
 */
export interface PermissionRule {
	/** Role that has this permission (e.g., "admin", "user", "*" for all) */
	role: string;
	/** Permission level: view, edit, admin */
	level: "view" | "edit" | "admin";
}

/**
 * Permission configuration for an application
 */
export interface PermissionConfig {
	/** Whether the app is public (no auth required) */
	public?: boolean;
	/** Default permission level for authenticated users */
	defaultLevel?: "none" | "view" | "edit" | "admin";
	/** Role-based permission rules */
	rules?: PermissionRule[];
}

/**
 * Navigation item for sidebar/navbar
 */
export interface NavItem {
	/** Item identifier (usually page ID) */
	id: string;
	/** Display label */
	label: string;
	/** Icon name (lucide icon) */
	icon?: string;
	/** Navigation path */
	path?: string;
	/** Visibility expression */
	visible?: string;
	/** Order in navigation */
	order?: number;
	/** Whether this is a section header (group) */
	isSection?: boolean;
	/** Child items for section groups */
	children?: NavItem[];
}

/**
 * Navigation configuration for the application
 */
export interface NavigationConfig {
	/** Sidebar navigation items */
	sidebar?: NavItem[];
	/** Whether to show the sidebar */
	showSidebar?: boolean;
	/** Whether to show the header */
	showHeader?: boolean;
	/** Custom logo URL */
	logoUrl?: string;
	/** Brand color (hex) */
	brandColor?: string;
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
	/** Navigation configuration */
	navigation?: NavigationConfig;
	/** Permission configuration */
	permissions?: PermissionConfig;
	/** Global variables available to all pages */
	globalVariables?: Record<string, unknown>;
	/** App-level CSS styles (global for entire application) */
	styles?: string;
}

/**
 * Base props shared by all app components
 * @deprecated Use individual component types directly
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
	/** Workflow IDs/names that trigger loading skeleton when executing */
	loadingWorkflows?: string[];
	/** Grid column span (for components inside grid layouts) */
	gridSpan?: number;
	/** Repeat this component for each item in an array */
	repeatFor?: RepeatFor;
	/** Additional CSS classes */
	className?: string;
	/** Inline CSS styles (camelCase properties) */
	style?: React.CSSProperties;
}

// =============================================================================
// Core Union Types
// =============================================================================

/**
 * Union type of all app components.
 * Excludes AppComponentNode which has `type: string` and breaks discriminated unions.
 */
export type AppComponent =
	| components["schemas"]["HeadingComponent"]
	| components["schemas"]["TextComponent"]
	| components["schemas"]["HtmlComponent"]
	| components["schemas"]["CardComponent"]
	| components["schemas"]["DividerComponent"]
	| components["schemas"]["SpacerComponent"]
	| components["schemas"]["ButtonComponent"]
	| components["schemas"]["StatCardComponent"]
	| components["schemas"]["ImageComponent"]
	| components["schemas"]["BadgeComponent"]
	| components["schemas"]["ProgressComponent"]
	| components["schemas"]["DataTableComponent"]
	| components["schemas"]["TabsComponent"]
	| components["schemas"]["FileViewerComponent"]
	| components["schemas"]["ModalComponent"]
	| components["schemas"]["TextInputComponent"]
	| components["schemas"]["NumberInputComponent"]
	| components["schemas"]["SelectComponent"]
	| components["schemas"]["CheckboxComponent"]
	| components["schemas"]["FormEmbedComponent"]
	| components["schemas"]["FormGroupComponent"];

/**
 * API-sourced Layout container from OpenAPI spec.
 * This type matches exactly what the API returns, including AppComponentNode.
 */
export type ApiLayoutContainer = components["schemas"]["LayoutContainer"];

/**
 * API-sourced children element type from OpenAPI spec.
 * This includes AppComponentNode which has a generic string type field.
 * Use this type when receiving data from the API and cast to LayoutElement.
 */
export type ApiLayoutElement =
	| components["schemas"]["LayoutContainer"]
	| components["schemas"]["HeadingComponent"]
	| components["schemas"]["TextComponent"]
	| components["schemas"]["HtmlComponent"]
	| components["schemas"]["CardComponent"]
	| components["schemas"]["DividerComponent"]
	| components["schemas"]["SpacerComponent"]
	| components["schemas"]["ButtonComponent"]
	| components["schemas"]["StatCardComponent"]
	| components["schemas"]["ImageComponent"]
	| components["schemas"]["BadgeComponent"]
	| components["schemas"]["ProgressComponent"]
	| components["schemas"]["DataTableComponent"]
	| components["schemas"]["TabsComponent"]
	| components["schemas"]["FileViewerComponent"]
	| components["schemas"]["ModalComponent"]
	| components["schemas"]["TextInputComponent"]
	| components["schemas"]["NumberInputComponent"]
	| components["schemas"]["SelectComponent"]
	| components["schemas"]["CheckboxComponent"]
	| components["schemas"]["FormEmbedComponent"]
	| components["schemas"]["FormGroupComponent"]
	| components["schemas"]["AppComponentNode"];

/**
 * Layout container for organizing components.
 *
 * Uses the strict discriminated union for children (no AppComponentNode).
 * When receiving API data, cast to this type.
 */
export interface LayoutContainer {
	id: string;
	type: "row" | "column" | "grid";
	gap?: number | null;
	padding?: number | null;
	align?: ("start" | "center" | "end" | "stretch") | null;
	justify?: ("start" | "center" | "end" | "between" | "around") | null;
	columns?: number | null;
	distribute?: ("natural" | "equal" | "fit") | null;
	maxWidth?: ("sm" | "md" | "lg" | "xl" | "2xl" | "full" | "none") | null;
	maxHeight?: number | null;
	overflow?: ("auto" | "scroll" | "hidden" | "visible") | null;
	sticky?: ("top" | "bottom") | null;
	stickyOffset?: number | null;
	className?: string | null;
	style?: { [key: string]: unknown } | null;
	visible?: string | null;
	// Children use the strict discriminated union
	children: (LayoutContainer | AppComponent)[];
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
 * Workflow execution result stored in context
 */
export interface WorkflowResult {
	/** The execution ID */
	executionId: string;
	/** The workflow ID */
	workflowId?: string;
	/** The workflow name */
	workflowName?: string;
	/** Execution status */
	status: "pending" | "running" | "completed" | "failed";
	/** Result data from the workflow */
	result?: unknown;
	/** Error message if failed */
	error?: string;
}

/**
 * Context for expression evaluation
 */
export interface ExpressionContext {
	/** Current user information */
	user?: ExpressionUser;
	/** Page-level variables */
	variables: Record<string, unknown>;
	/** Field values from form inputs (accessed via {{ field.* }}) */
	field?: Record<string, unknown>;
	/**
	 * Workflow execution results keyed by dataSourceId.
	 * Access via {{ workflow.<dataSourceId>.result }}
	 */
	workflow?: Record<string, WorkflowResult>;
	/** Current row context for table row click handlers (accessed via {{ row.* }}) */
	row?: Record<string, unknown>;
	/** Route parameters from URL (accessed via {{ params.id }}) */
	params?: Record<string, string>;
	/** Whether any data source is currently loading */
	isDataLoading?: boolean;
	/** Navigation function for button actions */
	navigate?: (path: string) => void;
	/** Workflow trigger function - returns Promise with result for onComplete/onError handling */
	triggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
		onComplete?: components["schemas"]["OnCompleteAction"][],
		onError?: components["schemas"]["OnCompleteAction"][],
	) => void;
	/** Submit form to workflow - collects all field values and triggers workflow */
	submitForm?: (
		workflowId: string,
		additionalParams?: Record<string, unknown>,
		onComplete?: components["schemas"]["OnCompleteAction"][],
		onError?: components["schemas"]["OnCompleteAction"][],
	) => void;
	/** Custom action handler */
	onCustomAction?: (
		actionId: string,
		params?: Record<string, unknown>,
	) => void;
	/** Set field value function (used by input components) */
	setFieldValue?: (fieldId: string, value: unknown) => void;
	/** Refresh a data table by its data source key */
	refreshTable?: (dataSourceKey: string) => void;
	/** Set a page variable */
	setVariable?: (key: string, value: unknown) => void;
	/** Currently executing workflow IDs/names for loading states */
	activeWorkflows?: Set<string>;
	/** Open a modal by its component ID */
	openModal?: (modalId: string) => void;
	/** Close a modal by its component ID */
	closeModal?: (modalId: string) => void;
}

/**
 * Types that can contain children (layout containers + components with props.children)
 */
export const CONTAINER_TYPES = [
	"row",
	"column",
	"grid",
	"card",
	"modal",
] as const;

/**
 * Element type for the layout tree.
 * Strict discriminated union that allows type narrowing.
 */
export type LayoutElement = LayoutContainer | AppComponent;

/**
 * Type guard to check if an element is a LayoutContainer
 */
export function isLayoutContainer(
	element: LayoutElement,
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
export function isAppComponent(element: LayoutElement): element is AppComponent {
	return !isLayoutContainer(element);
}

/**
 * Check if an element type can have children
 */
export function canHaveChildren(element: LayoutElement): boolean {
	return CONTAINER_TYPES.includes(
		element.type as (typeof CONTAINER_TYPES)[number],
	);
}

/**
 * Get children from an element (handles both direct children and props.children)
 */
export function getElementChildren(element: LayoutElement): LayoutElement[] {
	// Layout containers have direct children
	if (isLayoutContainer(element)) {
		return (element.children || []) as LayoutElement[];
	}
	// Components may have children in props.children (e.g., Card)
	if ("props" in element) {
		const props = element.props as {
			children?: LayoutElement[];
			content?: LayoutContainer;
		};
		// Check for props.children first (cards)
		if (Array.isArray(props?.children)) {
			return props.children;
		}
		// Check for props.content (modals)
		if (props?.content) {
			// Modal content is a single LayoutContainer, return it as an array
			return [props.content];
		}
	}
	return [];
}
