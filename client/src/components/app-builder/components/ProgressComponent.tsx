/**
 * Progress Component for App Builder
 *
 * Displays a progress bar with optional label.
 */

import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import type { ProgressComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";

export function ProgressComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as ProgressComponentProps;

	// Evaluate expressions
	const rawValue = evaluateExpression(String(props?.value ?? 0), context);
	const value =
		typeof rawValue === "number"
			? rawValue
			: parseFloat(String(rawValue)) || 0;

	// Clamp value between 0 and 100
	const clampedValue = Math.max(0, Math.min(100, value));

	return (
		<div className={cn("w-full", props?.className)}>
			<Progress value={clampedValue} className="h-2" />
			{props?.showLabel && (
				<p className="mt-1 text-right text-sm text-muted-foreground">
					{Math.round(clampedValue)}%
				</p>
			)}
		</div>
	);
}
