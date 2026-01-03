/**
 * Badge Component for App Builder
 *
 * Displays a badge with configurable variant. Expression evaluation
 * is handled centrally by ComponentRegistry.
 */

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { BadgeComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

export function BadgeComponent({ component }: RegisteredComponentProps) {
	const { props } = component as BadgeComponentProps;

	// Props are pre-evaluated by ComponentRegistry
	const text = String(props?.text ?? "");

	return (
		<Badge
			variant={props?.variant || "default"}
			className={cn(props?.className)}
		>
			{text}
		</Badge>
	);
}
