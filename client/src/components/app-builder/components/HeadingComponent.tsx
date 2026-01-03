/**
 * Heading Component for App Builder
 *
 * Renders h1-h6 headings. Expression evaluation is handled
 * centrally by ComponentRegistry.
 */

import { cn } from "@/lib/utils";
import type {
	HeadingComponentProps,
	HeadingLevel,
} from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

/**
 * Get Tailwind classes for heading level
 */
function getHeadingClasses(level: HeadingLevel): string {
	switch (level) {
		case 1:
			return "scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl";
		case 2:
			return "scroll-m-20 text-3xl font-semibold tracking-tight";
		case 3:
			return "scroll-m-20 text-2xl font-semibold tracking-tight";
		case 4:
			return "scroll-m-20 text-xl font-semibold tracking-tight";
		case 5:
			return "scroll-m-20 text-lg font-semibold tracking-tight";
		case 6:
			return "scroll-m-20 text-base font-semibold tracking-tight";
		default:
			return "scroll-m-20 text-xl font-semibold tracking-tight";
	}
}

/**
 * Heading Component
 *
 * Renders a heading element (h1-h6) with dynamic text content.
 *
 * @example
 * // Definition
 * {
 *   id: "welcome-heading",
 *   type: "heading",
 *   props: {
 *     text: "Welcome, {{ user.name }}!",
 *     level: 1
 *   }
 * }
 */
export function HeadingComponent({ component }: RegisteredComponentProps) {
	const { props } = component as HeadingComponentProps;
	const level = props?.level || 1;
	// Props are pre-evaluated by ComponentRegistry
	const text = String(props?.text ?? "");

	const classes = cn(getHeadingClasses(level), props?.className);

	// Render the appropriate heading element
	switch (level) {
		case 1:
			return <h1 className={classes}>{text}</h1>;
		case 2:
			return <h2 className={classes}>{text}</h2>;
		case 3:
			return <h3 className={classes}>{text}</h3>;
		case 4:
			return <h4 className={classes}>{text}</h4>;
		case 5:
			return <h5 className={classes}>{text}</h5>;
		case 6:
			return <h6 className={classes}>{text}</h6>;
		default:
			return <h1 className={classes}>{text}</h1>;
	}
}

export default HeadingComponent;
