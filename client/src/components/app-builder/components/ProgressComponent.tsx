/**
 * Progress Component for App Builder
 *
 * Displays a progress bar with optional label.
 * Expression evaluation is handled centrally by ComponentRegistry.
 */

import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import type { ProgressComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

export function ProgressComponent({ component }: RegisteredComponentProps) {
	const { props } = component as ProgressComponentProps;

	// Props are pre-evaluated by ComponentRegistry
	const rawValue = props?.value ?? 0;
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
