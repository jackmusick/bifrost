/**
 * App Builder Types
 *
 * This file re-exports API types from the generated OpenAPI types and defines
 * frontend-only runtime types that don't exist in the backend.
 *
 * IMPORTANT: Do NOT define types here that exist in the backend. Use the
 * generated types from "@/lib/v1" instead.
 *
 * Frontend-only types (runtime constructs, not serialized):
 * - ExpressionUser: User info for {{ user.* }} expressions
 * - WorkflowResult: Workflow state for {{ workflow.* }} expressions
 * - ExpressionContext: Full context for expression evaluation
 */

import type { components } from "@/lib/v1";

// =============================================================================
// Re-exported API Types
// =============================================================================

// Core layout and page types
export type PageDefinition = components["schemas"]["PageDefinition"];
export type LayoutContainer = components["schemas"]["LayoutContainer"];
export type RepeatFor = components["schemas"]["RepeatFor"];
export type OnCompleteAction = components["schemas"]["OnCompleteAction"];

// Navigation types (use -Output for reading from API)
export type NavItem = components["schemas"]["NavItem-Output"];
export type NavigationConfig = components["schemas"]["NavigationConfig-Output"];

// Permission types
export type PermissionRule = components["schemas"]["PermissionRule"];
export type PermissionConfig = components["schemas"]["PermissionConfig"];

// Application type
export type ApplicationPublic = components["schemas"]["ApplicationPublic"];

// =============================================================================
// Frontend-Only Runtime Types
// =============================================================================

/**
 * User information available in expression context.
 *
 * This is a frontend-only runtime type - it's populated from the auth context
 * and used for evaluating {{ user.* }} expressions. It is NOT sent to/from the API.
 */
export interface ExpressionUser {
	id: string;
	name: string;
	email: string;
	role: string;
}

/**
 * Workflow execution result stored in context.
 *
 * This is a frontend-only runtime type - it tracks the state of workflow
 * executions for the current page. Used for {{ workflow.* }} expressions.
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
 * Context for expression evaluation (e.g., {{ user.name }}, {{ workflow.result }})
 *
 * This is a frontend-only runtime type that provides the namespace for
 * evaluating template expressions in the app builder. It is NOT serialized.
 */
export interface ExpressionContext {
	/** Current user information */
	user?: ExpressionUser;
	/** Page-level variables */
	variables: Record<string, unknown>;
	/** Field values from form inputs (accessed via {{ field.* }}) */
	field?: Record<string, unknown>;
	/** Workflow execution results keyed by dataSourceId */
	workflow?: Record<string, WorkflowResult>;
	/** Current row context for table row click handlers */
	row?: Record<string, unknown>;
	/** Route parameters from URL */
	params?: Record<string, string>;
	/** Whether any data source is currently loading */
	isDataLoading?: boolean;
	/** Navigation function for button actions */
	navigate?: (path: string) => void;
	/** Workflow trigger function */
	triggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
		onComplete?: OnCompleteAction[],
		onError?: OnCompleteAction[],
	) => void;
	/** Submit form to workflow */
	submitForm?: (
		workflowId: string,
		additionalParams?: Record<string, unknown>,
		onComplete?: OnCompleteAction[],
		onError?: OnCompleteAction[],
	) => void;
	/** Custom action handler */
	onCustomAction?: (actionId: string, params?: Record<string, unknown>) => void;
	/** Set field value function */
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
 * Full application definition for the frontend runtime.
 *
 * This combines ApplicationPublic with resolved pages for rendering.
 * The API returns ApplicationPublic; this type adds the resolved page data.
 */
export interface ApplicationDefinition {
	id: string;
	name: string;
	description?: string;
	version: string;
	pages: PageDefinition[];
	navigation?: NavigationConfig;
	permissions?: PermissionConfig;
	globalVariables?: Record<string, unknown>;
	styles?: string;
}
