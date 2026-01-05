/**
 * Button Component for App Builder
 *
 * Action button supporting navigation, workflow triggers, and custom actions.
 */

import { useCallback, useMemo } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
	ButtonComponentProps,
	OnCompleteAction,
} from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Button } from "@/components/ui/button";
import { getIcon } from "@/lib/icons";

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
	// Support both 'label' and 'text' for button text
	const labelValue =
		props?.label ?? (props as Record<string, unknown>)?.text ?? "";
	const label = String(
		evaluateExpression(labelValue as string, context) ?? "",
	);

	// Check if this button's workflow is currently executing
	const isWorkflowLoading = useMemo(() => {
		// Support both old format (actionType at top level) and new format (onClick object)
		const onClick = (props as Record<string, unknown>)?.onClick as
			| { type?: string; workflowId?: string }
			| undefined;
		const actionType = props?.actionType || onClick?.type;
		const workflowId = props?.workflowId || onClick?.workflowId;

		// Only check for workflow and submit action types
		if (
			(actionType === "workflow" || actionType === "submit") &&
			workflowId &&
			context.activeWorkflows
		) {
			return context.activeWorkflows.has(workflowId);
		}
		return false;
	}, [props, context.activeWorkflows]);

	// Evaluate disabled state - can be boolean or expression string
	const isDisabled = (() => {
		if (props?.disabled === undefined || props?.disabled === null) {
			return false;
		}
		if (typeof props.disabled === "boolean") {
			return props.disabled;
		}
		// It's a string - evaluate as expression
		return Boolean(evaluateExpression(props.disabled, context));
	})();

	const handleClick = useCallback(() => {
		// Support both old format (actionType at top level) and new format (onClick object)
		const onClick = (props as Record<string, unknown>)?.onClick as
			| {
					type?: string;
					navigateTo?: string;
					workflowId?: string;
					actionParams?: Record<string, unknown>;
					onComplete?: OnCompleteAction[];
					onError?: OnCompleteAction[];
			  }
			| undefined;

		const actionType = props?.actionType || onClick?.type;
		const navigateTo = props?.navigateTo || onClick?.navigateTo;
		const workflowId = props?.workflowId || onClick?.workflowId;
		const actionParams = props?.actionParams || onClick?.actionParams;
		const onComplete = (props?.onComplete || onClick?.onComplete) as
			| OnCompleteAction[]
			| undefined;
		const onError = ((props as Record<string, unknown>)?.onError ||
			onClick?.onError) as OnCompleteAction[] | undefined;

		// Evaluate expressions in actionParams before passing to workflows
		const evaluatedParams: Record<string, unknown> = {};
		if (actionParams) {
			for (const [key, value] of Object.entries(actionParams)) {
				if (typeof value === "string" && value.includes("{{")) {
					evaluatedParams[key] = evaluateExpression(value, context);
				} else {
					evaluatedParams[key] = value;
				}
			}
		}

		switch (actionType) {
			case "navigate":
				if (navigateTo && context.navigate) {
					// Evaluate navigation path in case it contains expressions
					const path = String(
						evaluateExpression(navigateTo, context) ?? navigateTo,
					);
					context.navigate(path);
				}
				break;

			case "workflow":
				if (workflowId && context.triggerWorkflow) {
					context.triggerWorkflow(
						workflowId,
						evaluatedParams,
						onComplete,
						onError,
					);
				}
				break;

			case "submit":
				// Submit form - collects all field values and triggers workflow
				if (workflowId && context.submitForm) {
					context.submitForm(
						workflowId,
						evaluatedParams,
						onComplete,
						onError,
					);
				}
				break;

			case "custom":
				if (props?.customActionId && context.onCustomAction) {
					context.onCustomAction(
						props.customActionId,
						evaluatedParams,
					);
				}
				break;
		}
	}, [props, context]);

	// Render button with optional icon (or loading spinner)
	const renderIcon = () => {
		// Show loading spinner when workflow is executing
		if (isWorkflowLoading) {
			return <Loader2 className="h-4 w-4 mr-2 animate-spin" />;
		}
		if (!props?.icon) return null;
		const Icon = getIcon(props.icon);
		return <Icon className="h-4 w-4 mr-2" />;
	};

	return (
		<Button
			variant={props?.variant || "default"}
			size={props?.size || "default"}
			disabled={isDisabled || isWorkflowLoading}
			onClick={handleClick}
			className={cn(props?.className)}
		>
			{renderIcon()}
			{label}
		</Button>
	);
}

export default ButtonComponent;
