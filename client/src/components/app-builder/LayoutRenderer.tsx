/**
 * Layout Renderer for App Builder
 *
 * Recursive renderer for layout containers and components.
 * Handles row/column/grid layouts and delegates component rendering to the registry.
 */

import type React from "react";
import { cn } from "@/lib/utils";
import type {
	LayoutContainer,
	AppComponent,
	ExpressionContext,
	ComponentWidth,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
import { evaluateVisibility } from "@/lib/expression-parser";
import { renderRegisteredComponent } from "./ComponentRegistry";

interface LayoutRendererProps {
	/** The layout container or component to render */
	layout: LayoutContainer | AppComponent;
	/** Expression context for evaluating expressions and visibility */
	context: ExpressionContext;
	/** Optional additional class names */
	className?: string;
	/** Parent key for generating unique keys for nested layouts */
	parentKey?: string;
}

/**
 * Get Tailwind classes for component width
 */
function getWidthClasses(width?: ComponentWidth): string {
	switch (width) {
		case "full":
			return "w-full";
		case "1/2":
			return "w-1/2";
		case "1/3":
			return "w-1/3";
		case "1/4":
			return "w-1/4";
		case "2/3":
			return "w-2/3";
		case "3/4":
			return "w-3/4";
		case "auto":
		default:
			return "w-auto";
	}
}

/**
 * Get Tailwind classes for layout alignment (cross-axis)
 */
function getAlignClasses(align?: string): string {
	switch (align) {
		case "start":
			return "items-start";
		case "center":
			return "items-center";
		case "end":
			return "items-end";
		case "stretch":
			return "items-stretch";
		default:
			return "";
	}
}

/**
 * Get Tailwind classes for layout justification (main-axis)
 */
function getJustifyClasses(justify?: string): string {
	switch (justify) {
		case "start":
			return "justify-start";
		case "center":
			return "justify-center";
		case "end":
			return "justify-end";
		case "between":
			return "justify-between";
		case "around":
			return "justify-around";
		default:
			return "";
	}
}

/**
 * Get inline style for gap (Tailwind JIT can't compile dynamic values)
 */
function getGapStyle(gap?: number): React.CSSProperties {
	if (gap === undefined || gap === 0) return {};
	return { gap: `${gap}px` };
}

/**
 * Get inline style for padding (Tailwind JIT can't compile dynamic values)
 */
function getPaddingStyle(padding?: number): React.CSSProperties {
	if (padding === undefined || padding === 0) return {};
	return { padding: `${padding}px` };
}

/**
 * Get combined layout styles
 */
function getLayoutStyles(layout: {
	gap?: number;
	padding?: number;
}): React.CSSProperties {
	return {
		...getGapStyle(layout.gap),
		...getPaddingStyle(layout.padding),
	};
}

/**
 * Get grid columns class
 */
function getGridColumnsClass(columns?: number): string {
	if (columns === undefined) return "grid-cols-1";
	const colMap: Record<number, string> = {
		1: "grid-cols-1",
		2: "grid-cols-2",
		3: "grid-cols-3",
		4: "grid-cols-4",
		5: "grid-cols-5",
		6: "grid-cols-6",
		12: "grid-cols-12",
	};
	return colMap[columns] || `grid-cols-[repeat(${columns},1fr)]`;
}

/**
 * Generate a stable unique key for a layout child
 * For components, use their id. For layout containers, generate a key from
 * the parent's key/type and child index to ensure uniqueness across the tree.
 */
function generateChildKey(
	child: LayoutContainer | AppComponent,
	index: number,
	parentKey: string,
): string {
	if (isLayoutContainer(child)) {
		// For layout containers, combine parent key with index and child type
		return `${parentKey}-${child.type}-${index}`;
	}
	// For components, use their unique id
	return child.id;
}

/**
 * Render a layout container (row, column, or grid)
 */
function renderLayoutContainer(
	layout: LayoutContainer,
	context: ExpressionContext,
	className?: string,
	parentKey = "root",
): React.ReactElement | null {
	// Check visibility
	if (!evaluateVisibility(layout.visible, context)) {
		return null;
	}

	const baseClasses = cn(
		getAlignClasses(layout.align),
		getJustifyClasses(layout.justify),
		layout.className,
		className,
	);

	const layoutStyles = getLayoutStyles(layout);

	// Generate a unique key for this container based on parent
	const containerKey = parentKey;

	// For rows, we want children to flex and share space equally by default
	// unless they have an explicit width set OR autoSize is enabled
	const renderChild = (
		child: LayoutContainer | AppComponent,
		index: number,
		parentType: "row" | "column" | "grid",
		autoSize?: boolean,
	) => {
		const key = generateChildKey(child, index, containerKey);

		// In row layouts, wrap children with flex-1 to distribute space evenly
		// unless the child has an explicit width OR autoSize is enabled on the parent
		if (parentType === "row" && !autoSize) {
			const hasExplicitWidth =
				!isLayoutContainer(child) &&
				child.width &&
				child.width !== "auto";
			return (
				<div
					key={key}
					className={hasExplicitWidth ? undefined : "flex-1 min-w-0"}
				>
					<LayoutRenderer layout={child} context={context} parentKey={key} />
				</div>
			);
		}

		return <LayoutRenderer key={key} layout={child} context={context} parentKey={key} />;
	};

	switch (layout.type) {
		case "row":
			return (
				<div
					className={cn("flex flex-row flex-wrap", baseClasses)}
					style={layoutStyles}
				>
					{layout.children.map((child, index) =>
						renderChild(child, index, "row", layout.autoSize),
					)}
				</div>
			);

		case "column":
			return (
				<div
					className={cn("flex flex-col", baseClasses)}
					style={layoutStyles}
				>
					{layout.children.map((child, index) =>
						renderChild(child, index, "column"),
					)}
				</div>
			);

		case "grid":
			return (
				<div
					className={cn(
						"grid",
						getGridColumnsClass(layout.columns),
						baseClasses,
					)}
					style={layoutStyles}
				>
					{layout.children.map((child, index) =>
						renderChild(child, index, "grid"),
					)}
				</div>
			);

		default:
			return null;
	}
}

/**
 * Render an app component with visibility check and width handling
 */
function renderComponent(
	component: AppComponent,
	context: ExpressionContext,
	className?: string,
): React.ReactElement | null {
	// Check visibility
	if (!evaluateVisibility(component.visible, context)) {
		return null;
	}

	const widthClass = getWidthClasses(component.width);
	const wrappedComponent = renderRegisteredComponent(component, context);

	// If the component has a width constraint, wrap it
	if (component.width && component.width !== "auto") {
		return (
			<div key={component.id} className={cn(widthClass, className)}>
				{wrappedComponent}
			</div>
		);
	}

	return wrappedComponent;
}

/**
 * Layout Renderer Component
 *
 * Recursively renders layout containers and their children.
 * Delegates component rendering to the ComponentRegistry.
 *
 * @example
 * <LayoutRenderer
 *   layout={{
 *     type: "column",
 *     gap: 16,
 *     children: [
 *       { id: "h1", type: "heading", props: { text: "Hello", level: 1 } },
 *       { id: "t1", type: "text", props: { text: "Welcome to the app" } },
 *     ],
 *   }}
 *   context={{ user: { name: "John" }, variables: {} }}
 * />
 */
export function LayoutRenderer({
	layout,
	context,
	className,
	parentKey = "root",
}: LayoutRendererProps): React.ReactElement | null {
	if (isLayoutContainer(layout)) {
		return renderLayoutContainer(layout, context, className, parentKey);
	}

	return renderComponent(layout, context, className);
}

export default LayoutRenderer;
