/**
 * Layout Renderer for App Builder
 *
 * Recursive renderer for layout containers and components.
 * Handles row/column/grid layouts and delegates component rendering to the registry.
 */

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
 * Get Tailwind gap class from numeric value
 */
function getGapClass(gap?: number): string {
	if (gap === undefined) return "";
	// Map common pixel values to Tailwind spacing
	const gapMap: Record<number, string> = {
		0: "gap-0",
		1: "gap-px",
		2: "gap-0.5",
		4: "gap-1",
		6: "gap-1.5",
		8: "gap-2",
		10: "gap-2.5",
		12: "gap-3",
		14: "gap-3.5",
		16: "gap-4",
		20: "gap-5",
		24: "gap-6",
		28: "gap-7",
		32: "gap-8",
		36: "gap-9",
		40: "gap-10",
		48: "gap-12",
		56: "gap-14",
		64: "gap-16",
	};
	return gapMap[gap] || `gap-[${gap}px]`;
}

/**
 * Get Tailwind padding class from numeric value
 */
function getPaddingClass(padding?: number): string {
	if (padding === undefined) return "";
	// Map common pixel values to Tailwind spacing
	const paddingMap: Record<number, string> = {
		0: "p-0",
		1: "p-px",
		2: "p-0.5",
		4: "p-1",
		6: "p-1.5",
		8: "p-2",
		10: "p-2.5",
		12: "p-3",
		14: "p-3.5",
		16: "p-4",
		20: "p-5",
		24: "p-6",
		28: "p-7",
		32: "p-8",
		36: "p-9",
		40: "p-10",
		48: "p-12",
		56: "p-14",
		64: "p-16",
	};
	return paddingMap[padding] || `p-[${padding}px]`;
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
 * Render a layout container (row, column, or grid)
 */
function renderLayoutContainer(
	layout: LayoutContainer,
	context: ExpressionContext,
	className?: string,
): React.ReactElement | null {
	// Check visibility
	if (!evaluateVisibility(layout.visible, context)) {
		return null;
	}

	const baseClasses = cn(
		getGapClass(layout.gap),
		getPaddingClass(layout.padding),
		getAlignClasses(layout.align),
		getJustifyClasses(layout.justify),
		layout.className,
		className,
	);

	const children = layout.children.map((child, index) => (
		<LayoutRenderer
			key={isLayoutContainer(child) ? `layout-${index}` : child.id}
			layout={child}
			context={context}
		/>
	));

	switch (layout.type) {
		case "row":
			return (
				<div className={cn("flex flex-row flex-wrap", baseClasses)}>
					{children}
				</div>
			);

		case "column":
			return (
				<div className={cn("flex flex-col", baseClasses)}>
					{children}
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
				>
					{children}
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
}: LayoutRendererProps): React.ReactElement | null {
	if (isLayoutContainer(layout)) {
		return renderLayoutContainer(layout, context, className);
	}

	return renderComponent(layout, context, className);
}

export default LayoutRenderer;
