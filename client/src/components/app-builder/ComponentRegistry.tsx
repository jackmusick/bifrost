/**
 * Component Registry for App Builder
 *
 * Registry pattern for mapping component types to React components.
 * Allows dynamic component rendering based on type definitions.
 */

import type { ComponentType as ReactComponentType } from "react";
import type {
	ComponentType,
	AppComponent,
	ExpressionContext,
} from "@/lib/app-builder-types";

/**
 * Props passed to each registered component
 */
export interface RegisteredComponentProps {
	/** The component definition */
	component: AppComponent;
	/** Expression context for evaluating expressions */
	context: ExpressionContext;
}

/**
 * Type for registered React components
 */
type RegisteredComponent = ReactComponentType<RegisteredComponentProps>;

/**
 * Internal registry storage
 */
const componentRegistry = new Map<ComponentType, RegisteredComponent>();

/**
 * Register a component for a specific type
 *
 * @param type - The component type identifier
 * @param component - The React component to render for this type
 *
 * @example
 * registerComponent("heading", HeadingComponent);
 * registerComponent("button", ButtonComponent);
 */
export function registerComponent(
	type: ComponentType,
	component: RegisteredComponent,
): void {
	componentRegistry.set(type, component);
}

/**
 * Get a registered component by type
 *
 * @param type - The component type to look up
 * @returns The registered React component, or undefined if not found
 *
 * @example
 * const HeadingComponent = getComponent("heading");
 * if (HeadingComponent) {
 *   return <HeadingComponent component={def} context={ctx} />;
 * }
 */
export function getComponent(
	type: ComponentType,
): RegisteredComponent | undefined {
	return componentRegistry.get(type);
}

/**
 * Check if a component type is registered
 *
 * @param type - The component type to check
 * @returns True if the component type is registered
 */
export function hasComponent(type: ComponentType): boolean {
	return componentRegistry.has(type);
}

/**
 * Unregister a component type
 *
 * @param type - The component type to unregister
 * @returns True if the component was unregistered, false if it wasn't registered
 */
export function unregisterComponent(type: ComponentType): boolean {
	return componentRegistry.delete(type);
}

/**
 * Get all registered component types
 *
 * @returns Array of all registered component types
 */
export function getRegisteredTypes(): ComponentType[] {
	return Array.from(componentRegistry.keys());
}

/**
 * Clear all registered components
 * Useful for testing or hot module reloading
 */
export function clearRegistry(): void {
	componentRegistry.clear();
}

/**
 * Fallback component for unregistered types
 */
export function UnknownComponent({ component }: RegisteredComponentProps) {
	return (
		<div className="rounded border border-dashed border-yellow-500 bg-yellow-50 p-4 text-sm text-yellow-700 dark:border-yellow-400 dark:bg-yellow-900/20 dark:text-yellow-300">
			<span className="font-medium">Unknown component type:</span>{" "}
			<code className="rounded bg-yellow-100 px-1 dark:bg-yellow-800">
				{component.type}
			</code>
		</div>
	);
}

/**
 * Render a component from the registry
 *
 * @param component - The component definition
 * @param context - The expression context
 * @returns The rendered React element
 */
export function renderRegisteredComponent(
	component: AppComponent,
	context: ExpressionContext,
): React.ReactElement {
	const Component = getComponent(component.type) || UnknownComponent;
	return (
		<Component key={component.id} component={component} context={context} />
	);
}
