/**
 * Divider Component for App Builder
 *
 * Horizontal or vertical divider for visual separation.
 */

import { cn } from "@/lib/utils";
import type { DividerComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

/**
 * Divider Component
 *
 * Renders a horizontal or vertical divider line.
 *
 * @example
 * // Definition
 * {
 *   id: "section-divider",
 *   type: "divider",
 *   props: {
 *     orientation: "horizontal"
 *   }
 * }
 */
export function DividerComponent({ component }: RegisteredComponentProps) {
	const { props } = component as DividerComponentProps;
	const orientation = props.orientation || "horizontal";

	if (orientation === "vertical") {
		return (
			<div
				className={cn(
					"mx-2 h-full w-px shrink-0 bg-border",
					props.className,
				)}
				role="separator"
				aria-orientation="vertical"
			/>
		);
	}

	return (
		<div
			className={cn(
				"my-4 h-px w-full shrink-0 bg-border",
				props.className,
			)}
			role="separator"
			aria-orientation="horizontal"
		/>
	);
}

export default DividerComponent;
