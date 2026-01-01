/**
 * App Builder Module
 *
 * Recursive layout renderer and component system for building dynamic applications.
 */

// Core rendering
export { AppRenderer, StandalonePageRenderer } from "./AppRenderer";
export { LayoutRenderer } from "./LayoutRenderer";

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

// Basic components
export {
	HeadingComponent,
	TextComponent,
	CardComponent,
	DividerComponent,
	SpacerComponent,
	ButtonComponent,
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
	DataSource,
	ExpressionUser,
	ExpressionContext,
	BaseComponentProps,
	HeadingComponentProps,
	TextComponentProps,
	CardComponentProps,
	DividerComponentProps,
	SpacerComponentProps,
	ButtonComponentProps,
	AppComponent,
	LayoutContainer,
	PageDefinition,
	ApplicationDefinition,
} from "@/lib/app-builder-types";

export {
	isLayoutContainer,
	isAppComponent,
} from "@/lib/app-builder-types";

// Re-export expression utilities
export {
	evaluateExpression,
	evaluateVisibility,
	evaluateSingleExpression,
	hasExpressions,
	extractVariablePaths,
} from "@/lib/expression-parser";
