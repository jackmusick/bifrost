/**
 * Badge Component for App Builder
 *
 * Displays a badge with configurable variant.
 */

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { BadgeComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";

export function BadgeComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as BadgeComponentProps;

	// Evaluate expressions
	const text = String(evaluateExpression(props?.text ?? "", context) ?? "");

	return (
		<Badge
			variant={props?.variant || "default"}
			className={cn(props?.className)}
		>
			{text}
		</Badge>
	);
}
