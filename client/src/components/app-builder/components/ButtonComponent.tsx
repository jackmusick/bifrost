/**
 * Button Component for App Builder
 *
 * Action button supporting navigation, workflow triggers, and custom actions.
 */

import { useCallback } from "react";
import { cn } from "@/lib/utils";
import type { ButtonComponentProps } from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Button } from "@/components/ui/button";

/**
 * Button Component
 *
 * Renders an action button with various action types.
 *
 * @example
 * // Navigation button
 * {
 *   id: "go-home",
 *   type: "button",
 *   props: {
 *     label: "Go Home",
 *     actionType: "navigate",
 *     navigateTo: "/home"
 *   }
 * }
 *
 * @example
 * // Workflow trigger button
 * {
 *   id: "run-workflow",
 *   type: "button",
 *   props: {
 *     label: "Run Analysis",
 *     actionType: "workflow",
 *     workflowId: "analysis-workflow",
 *     actionParams: { mode: "full" }
 *   }
 * }
 *
 * @example
 * // Custom action button
 * {
 *   id: "custom-action",
 *   type: "button",
 *   props: {
 *     label: "Do Something",
 *     actionType: "custom",
 *     customActionId: "my-action"
 *   }
 * }
 */
export function ButtonComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as ButtonComponentProps;
	const label = String(evaluateExpression(props.label, context) ?? "");

	const handleClick = useCallback(() => {
		switch (props.actionType) {
			case "navigate":
				if (props.navigateTo && context.navigate) {
					// Evaluate navigation path in case it contains expressions
					const path = String(
						evaluateExpression(props.navigateTo, context) ?? props.navigateTo,
					);
					context.navigate(path);
				}
				break;

			case "workflow":
				if (props.workflowId && context.triggerWorkflow) {
					context.triggerWorkflow(props.workflowId, props.actionParams);
				}
				break;

			case "custom":
				if (props.customActionId && context.onCustomAction) {
					context.onCustomAction(props.customActionId, props.actionParams);
				}
				break;
		}
	}, [
		props.actionType,
		props.navigateTo,
		props.workflowId,
		props.customActionId,
		props.actionParams,
		context,
	]);

	return (
		<Button
			variant={props.variant || "default"}
			size={props.size || "default"}
			disabled={props.disabled}
			onClick={handleClick}
			className={cn(props.className)}
		>
			{label}
		</Button>
	);
}

export default ButtonComponent;
