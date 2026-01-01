/**
 * Spacer Component for App Builder
 *
 * Fixed spacing element for layout control.
 */

import { cn } from "@/lib/utils";
import type { SpacerComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

/**
 * Get spacing class or style
 */
function getSpacingStyle(size?: number | string): { className?: string; style?: React.CSSProperties } {
	if (size === undefined) {
		return { className: "h-4" }; // Default 16px
	}

	if (typeof size === "number") {
		// Map common pixel values to Tailwind spacing
		const sizeMap: Record<number, string> = {
			0: "h-0",
			1: "h-px",
			2: "h-0.5",
			4: "h-1",
			6: "h-1.5",
			8: "h-2",
			10: "h-2.5",
			12: "h-3",
			14: "h-3.5",
			16: "h-4",
			20: "h-5",
			24: "h-6",
			28: "h-7",
			32: "h-8",
			36: "h-9",
			40: "h-10",
			44: "h-11",
			48: "h-12",
			56: "h-14",
			64: "h-16",
			80: "h-20",
			96: "h-24",
		};

		if (sizeMap[size]) {
			return { className: sizeMap[size] };
		}

		// Use arbitrary value for non-standard sizes
		return { style: { height: `${size}px` } };
	}

	// String value - could be Tailwind class or CSS value
	if (size.startsWith("h-")) {
		return { className: size };
	}

	return { style: { height: size } };
}

/**
 * Spacer Component
 *
 * Renders a fixed-height spacer for layout control.
 *
 * @example
 * // Definition with pixel value
 * {
 *   id: "spacer-1",
 *   type: "spacer",
 *   props: {
 *     size: 24
 *   }
 * }
 *
 * @example
 * // Definition with Tailwind class
 * {
 *   id: "spacer-2",
 *   type: "spacer",
 *   props: {
 *     size: "h-8"
 *   }
 * }
 */
export function SpacerComponent({ component }: RegisteredComponentProps) {
	const { props } = component as SpacerComponentProps;
	const { className: spacingClass, style } = getSpacingStyle(props.size);

	return (
		<div
			className={cn("w-full", spacingClass, props.className)}
			style={style}
			aria-hidden="true"
		/>
	);
}

export default SpacerComponent;
