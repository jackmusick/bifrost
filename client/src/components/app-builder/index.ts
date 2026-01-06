/**
 * App Builder Module
 *
 * Recursive layout renderer and component system for building dynamic applications.
 */

// Core rendering
export { AppRenderer, StandalonePageRenderer } from "./AppRenderer";
export { LayoutRenderer } from "./LayoutRenderer";
export { AppShell, AppShellMinimal } from "./AppShell";
export { WorkflowStatusIndicator } from "./WorkflowStatusIndicator";
export { AppUpdateIndicator } from "./AppUpdateIndicator";
export { NewVersionBanner } from "./NewVersionBanner";

// Editor
export {
	EditorShell,
	StructureTree,
	ComponentInserter,
	PropertyEditor,
	PageTree,
	type EditorShellProps,
	type StructureTreeProps,
	type PropertyEditorProps,
	type PageTreeProps,
} from "./editor";

// Component registry
export {
	registerComponent,
	getComponent,
	hasComponent,
	unregisterComponent,
	getRegisteredTypes,
	clearRegistry,
	renderRegisteredComponent,
	UnknownComponent,
	type RegisteredComponentProps,
} from "./ComponentRegistry";

// Components
export {
	// Basic
	HeadingComponent,
	TextComponent,
	CardComponent,
	DividerComponent,
	SpacerComponent,
	ButtonComponent,
	// Display
	StatCardComponent,
	ImageComponent,
	BadgeComponent,
	ProgressComponent,
	// Data
	DataTableComponent,
	TabsComponent,
	// Registration
	registerAllComponents,
	registerBasicComponents,
} from "./components";

// Re-export types from lib for convenience
export type {
	ComponentType,
	ComponentWidth,
	ButtonActionType,
	HeadingLevel,
	LayoutAlign,
	LayoutJustify,
	LayoutType,
	ExpressionUser,
	ExpressionContext,
	BaseComponentProps,
	HeadingComponentProps,
	TextComponentProps,
	CardComponentProps,
	DividerComponentProps,
	SpacerComponentProps,
	ButtonComponentProps,
	StatCardComponentProps,
	ImageComponentProps,
	BadgeComponentProps,
	ProgressComponentProps,
	DataTableComponentProps,
	TabsComponentProps,
	TableColumn,
	TableAction,
	TabItem,
	AppComponent,
	LayoutContainer,
	PageDefinition,
	ApplicationDefinition,
} from "@/lib/app-builder-types";

export { isLayoutContainer, isAppComponent } from "@/lib/app-builder-types";

// Re-export expression utilities
export {
	evaluateExpression,
	evaluateVisibility,
	evaluateSingleExpression,
	hasExpressions,
	extractVariablePaths,
} from "@/lib/expression-parser";
