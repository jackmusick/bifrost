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
	// Form input components
	| "text-input"
	| "number-input"
	| "select"
	| "checkbox"
	// Form integration components
	| "form-embed"
	| "form-group";

/**
 * Width options for components
 */
export type ComponentWidth =
	| "auto"
	| "full"
	| "1/2"
	| "1/3"
	| "1/4"
	| "2/3"
	| "3/4";

/**
 * Button action types
 */
export type ButtonActionType = "navigate" | "workflow" | "custom" | "submit";

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
	/** Type of data source */
	type: "api" | "static" | "computed" | "data-provider" | "workflow";
	/** API endpoint for api type */
	endpoint?: string;
	/** Static data for static type */
	data?: unknown;
	/** Expression for computed type */
	expression?: string;
	/** Data provider ID for data-provider type */
	dataProviderId?: string;
	/** Workflow ID for workflow type */
	workflowId?: string;
	/** Input parameters (supports expressions like {{ query.id }}) */
	inputParams?: Record<string, unknown>;
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
	/** Data from data sources */
	data?: Record<string, unknown>;
	/** Field values from form inputs (accessed via {{ field.* }}) */
	field?: Record<string, unknown>;
	/** Last workflow execution result (accessed via {{ workflow.result.* }}) */
	workflow?: WorkflowResult;
	/** Current row context for table row click handlers (accessed via {{ row.* }}) */
	row?: Record<string, unknown>;
	/** Route parameters from URL (accessed via {{ params.id }}) */
	params?: Record<string, string>;
	/** Whether any data source is currently loading */
	isDataLoading?: boolean;
	/** Navigation function for button actions */
	navigate?: (path: string) => void;
	/** Workflow trigger function - returns Promise with result for onComplete handling */
	triggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
		onComplete?: OnCompleteAction[],
	) => void;
	/** Submit form to workflow - collects all field values and triggers workflow */
	submitForm?: (
		workflowId: string,
		additionalParams?: Record<string, unknown>,
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
 * Props for HTML component
 * Supports both plain HTML (sanitized) and JSX templates with context access
 */
export interface HtmlComponentProps extends BaseComponentProps {
	type: "html";
	props: {
		/** HTML or JSX template content */
		content: string;
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
		/** Alias for size - supports legacy definitions */
		height?: number | string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Action to execute after workflow completes
 */
export interface OnCompleteAction {
	/** Type of action to perform */
	type: "navigate" | "set-variable" | "refresh-table";
	/** Path to navigate to (for navigate type) */
	navigateTo?: string;
	/** Variable name to set (for set-variable type) */
	variableName?: string;
	/** Variable value to set, supports {{ workflow.result.* }} expressions */
	variableValue?: string;
	/** Data source key to refresh (for refresh-table type) */
	dataSourceKey?: string;
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
		/** Action(s) to execute after workflow completes */
		onComplete?: OnCompleteAction[];
		/** Button variant */
		variant?:
			| "default"
			| "destructive"
			| "outline"
			| "secondary"
			| "ghost"
			| "link";
		/** Button size */
		size?: "default" | "sm" | "lg";
		/** Disabled state (boolean or expression like "{{ row.status == 'completed' }}") */
		disabled?: boolean | string;
		/** Icon name to display (from lucide-react) */
		icon?: string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for stat-card component
 */
export interface StatCardComponentProps extends BaseComponentProps {
	type: "stat-card";
	props: {
		/** Card title */
		title: string;
		/** Value (supports expressions) */
		value: string;
		/** Optional description */
		description?: string;
		/** Icon name */
		icon?: string;
		/** Trend indicator */
		trend?: {
			value: string;
			direction: "up" | "down" | "neutral";
		};
		/** Click action */
		onClick?: {
			type: "navigate" | "workflow";
			navigateTo?: string;
			workflowId?: string;
		};
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for image component
 */
export interface ImageComponentProps extends BaseComponentProps {
	type: "image";
	props: {
		/** Image source (URL or expression) */
		src: string;
		/** Alt text */
		alt?: string;
		/** Max width */
		maxWidth?: number | string;
		/** Max height */
		maxHeight?: number | string;
		/** Object fit mode */
		objectFit?: "contain" | "cover" | "fill" | "none";
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for badge component
 */
export interface BadgeComponentProps extends BaseComponentProps {
	type: "badge";
	props: {
		/** Badge text (supports expressions) */
		text: string;
		/** Badge variant */
		variant?: "default" | "secondary" | "destructive" | "outline";
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for progress component
 */
export interface ProgressComponentProps extends BaseComponentProps {
	type: "progress";
	props: {
		/** Progress value (0-100, supports expressions) */
		value: string | number;
		/** Show percentage label */
		showLabel?: boolean;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Table column definition
 */
export interface TableColumn {
	/** Key path into document data */
	key: string;
	/** Column header */
	header: string;
	/** Column type for formatting */
	type?: "text" | "number" | "date" | "badge";
	/** Width */
	width?: number | "auto";
	/** Sortable */
	sortable?: boolean;
	/** Badge color mapping for badge type */
	badgeColors?: Record<string, string>;
}

/**
 * Table action definition
 */
export interface TableAction {
	/** Action label */
	label: string;
	/** Icon name */
	icon?: string;
	/** Button variant */
	variant?: "default" | "destructive" | "outline" | "ghost";
	/** Action handler */
	onClick: {
		type: "navigate" | "workflow" | "delete" | "set-variable";
		navigateTo?: string;
		workflowId?: string;
		/** Parameters to pass to workflow (supports {{ row.* }} expressions) */
		actionParams?: Record<string, unknown>;
		variableName?: string;
		variableValue?: string;
	};
	/** Confirmation dialog */
	confirm?: {
		title: string;
		message: string;
		confirmLabel?: string;
		cancelLabel?: string;
	};
	/** Visibility expression */
	visible?: string;
	/** Disabled expression (e.g., "{{ row.status == 'completed' }}") */
	disabled?: string;
}

/**
 * Props for data-table component
 */
export interface DataTableComponentProps extends BaseComponentProps {
	type: "data-table";
	props: {
		/** Data source - table name or expression */
		dataSource: string;
		/** Column definitions */
		columns: TableColumn[];
		/** Enable row selection */
		selectable?: boolean;
		/** Enable search */
		searchable?: boolean;
		/** Enable pagination */
		paginated?: boolean;
		/** Page size */
		pageSize?: number;
		/** Row actions */
		rowActions?: TableAction[];
		/** Header actions (e.g., Add New button) */
		headerActions?: TableAction[];
		/** Row click handler */
		onRowClick?: {
			type: "navigate" | "select" | "set-variable";
			navigateTo?: string;
			variableName?: string;
		};
		/** Empty state message */
		emptyMessage?: string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Tab item definition
 */
export interface TabItem {
	/** Tab ID */
	id: string;
	/** Tab label */
	label: string;
	/** Tab icon */
	icon?: string;
	/** Tab content (layout) */
	content: LayoutContainer;
}

/**
 * Props for tabs component
 */
export interface TabsComponentProps extends BaseComponentProps {
	type: "tabs";
	props: {
		/** Tab items */
		items: TabItem[];
		/** Default active tab ID */
		defaultTab?: string;
		/** Orientation */
		orientation?: "horizontal" | "vertical";
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for text-input component
 */
export interface TextInputComponentProps extends BaseComponentProps {
	type: "text-input";
	props: {
		/** Field ID for value tracking (used in {{ field.* }} expressions) */
		fieldId: string;
		/** Input label */
		label?: string;
		/** Placeholder text */
		placeholder?: string;
		/** Default value (supports expressions) */
		defaultValue?: string;
		/** Required field */
		required?: boolean;
		/** Disabled state (boolean or expression) */
		disabled?: boolean | string;
		/** Input type (text, email, password, url, tel) */
		inputType?: "text" | "email" | "password" | "url" | "tel";
		/** Minimum length */
		minLength?: number;
		/** Maximum length */
		maxLength?: number;
		/** Regex pattern for validation */
		pattern?: string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for number-input component
 */
export interface NumberInputComponentProps extends BaseComponentProps {
	type: "number-input";
	props: {
		/** Field ID for value tracking */
		fieldId: string;
		/** Input label */
		label?: string;
		/** Placeholder text */
		placeholder?: string;
		/** Default value (supports expressions) */
		defaultValue?: number | string;
		/** Required field */
		required?: boolean;
		/** Disabled state (boolean or expression) */
		disabled?: boolean | string;
		/** Minimum value */
		min?: number;
		/** Maximum value */
		max?: number;
		/** Step increment */
		step?: number;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Select option definition
 */
export interface SelectOption {
	/** Option value */
	value: string;
	/** Option display label */
	label: string;
}

/**
 * Props for select component
 */
export interface SelectComponentProps extends BaseComponentProps {
	type: "select";
	props: {
		/** Field ID for value tracking */
		fieldId: string;
		/** Select label */
		label?: string;
		/** Placeholder text */
		placeholder?: string;
		/** Default value (supports expressions) */
		defaultValue?: string;
		/** Required field */
		required?: boolean;
		/** Disabled state (boolean or expression) */
		disabled?: boolean | string;
		/** Static options or expression string like "{{ data.options }}" */
		options?: SelectOption[] | string;
		/** Data source name for dynamic options */
		optionsSource?: string;
		/** Field in data source for option value */
		valueField?: string;
		/** Field in data source for option label */
		labelField?: string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for checkbox component
 */
export interface CheckboxComponentProps extends BaseComponentProps {
	type: "checkbox";
	props: {
		/** Field ID for value tracking */
		fieldId: string;
		/** Checkbox label */
		label: string;
		/** Description text below label */
		description?: string;
		/** Default checked state */
		defaultChecked?: boolean;
		/** Required field */
		required?: boolean;
		/** Disabled state (boolean or expression) */
		disabled?: boolean | string;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * File display mode for file-viewer component
 */
export type FileViewerDisplayMode = "inline" | "modal" | "download";

/**
 * Props for file-viewer component
 */
export interface FileViewerComponentProps extends BaseComponentProps {
	type: "file-viewer";
	props: {
		/** File URL or path (supports expressions) */
		src: string;
		/** File name for display and download */
		fileName?: string;
		/** MIME type of the file (auto-detected if not provided) */
		mimeType?: string;
		/** Display mode: inline (embed), modal (popup), or download (link) */
		displayMode?: FileViewerDisplayMode;
		/** Max width for inline display */
		maxWidth?: number | string;
		/** Max height for inline display */
		maxHeight?: number | string;
		/** Label for download button (when displayMode is 'download') */
		downloadLabel?: string;
		/** Whether to show download button alongside inline/modal view */
		showDownloadButton?: boolean;
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for modal component
 */
export interface ModalComponentProps extends BaseComponentProps {
	type: "modal";
	props: {
		/** Modal title */
		title: string;
		/** Modal description */
		description?: string;
		/** Trigger button label */
		triggerLabel: string;
		/** Trigger button variant */
		triggerVariant?:
			| "default"
			| "destructive"
			| "outline"
			| "secondary"
			| "ghost"
			| "link";
		/** Trigger button size */
		triggerSize?: "default" | "sm" | "lg";
		/** Modal size */
		size?: "sm" | "default" | "lg" | "xl" | "full";
		/** Content layout inside the modal */
		content: LayoutContainer;
		/** Footer actions (optional) */
		footerActions?: {
			label: string;
			variant?:
				| "default"
				| "destructive"
				| "outline"
				| "secondary"
				| "ghost";
			actionType: ButtonActionType;
			navigateTo?: string;
			workflowId?: string;
			actionParams?: Record<string, unknown>;
			onComplete?: OnCompleteAction[];
			/** Whether clicking this action should close the modal */
			closeOnClick?: boolean;
		}[];
		/** Show close button in header */
		showCloseButton?: boolean;
		/** Additional CSS classes for modal content */
		className?: string;
	};
}

/**
 * Props for form-embed component
 * Embeds an existing form from the forms system into an App Builder page
 */
export interface FormEmbedComponentProps extends BaseComponentProps {
	type: "form-embed";
	props: {
		/** Form ID to embed */
		formId: string;
		/** Whether to show the form title */
		showTitle?: boolean;
		/** Whether to show the form description */
		showDescription?: boolean;
		/** Whether to show form progress steps */
		showProgress?: boolean;
		/** Actions to execute after form submission */
		onSubmit?: OnCompleteAction[];
		/** Additional CSS classes */
		className?: string;
	};
}

/**
 * Props for form-group component
 * Groups multiple form input components together with a label
 */
export interface FormGroupComponentProps extends BaseComponentProps {
	type: "form-group";
	props: {
		/** Group label */
		label?: string;
		/** Group description */
		description?: string;
		/** Whether the group fields are required */
		required?: boolean;
		/** Layout direction for grouped fields */
		direction?: "row" | "column";
		/** Gap between fields */
		gap?: number;
		/** Child form field components */
		children: AppComponent[];
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
	| HtmlComponentProps
	| CardComponentProps
	| DividerComponentProps
	| SpacerComponentProps
	| ButtonComponentProps
	| StatCardComponentProps
	| ImageComponentProps
	| BadgeComponentProps
	| ProgressComponentProps
	| DataTableComponentProps
	| TabsComponentProps
	| FileViewerComponentProps
	| ModalComponentProps
	| TextInputComponentProps
	| NumberInputComponentProps
	| SelectComponentProps
	| CheckboxComponentProps
	| FormEmbedComponentProps
	| FormGroupComponentProps;

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
	/**
	 * When true, children keep their natural size instead of expanding to fill space.
	 * Useful for button rows where you want to use justify to position buttons.
	 * Default: false (children expand equally in row layouts)
	 */
	autoSize?: boolean;
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
	/** Workflow to execute on page mount (results available as {{ workflow.* }}) */
	launchWorkflowId?: string;
	/** Parameters to pass to the launch workflow */
	launchWorkflowParams?: Record<string, unknown>;
	/** Alternative nested format for launch workflow configuration */
	launchWorkflow?: {
		workflowId: string;
		params?: Record<string, unknown>;
	};
	/** Page-level permission configuration */
	permission?: PagePermission;
}

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
 * Page-level permission configuration
 */
export interface PagePermission {
	/** Roles that can access this page (* for all authenticated users) */
	allowedRoles?: string[];
	/** Permission expression for dynamic access control */
	accessExpression?: string;
	/** Redirect path if access denied */
	redirectTo?: string;
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
