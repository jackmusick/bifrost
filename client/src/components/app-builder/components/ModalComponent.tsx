/**
 * Modal Component for App Builder
 *
 * A dialog component that can contain form inputs or other content.
 * Supports custom footer actions with workflow integration.
 */

import { useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import type {
	ModalComponentProps,
	ExpressionContext,
} from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";
import { LayoutRenderer } from "../LayoutRenderer";

/**
 * Get modal size classes
 */
function getModalSizeClass(
	size?: ModalComponentProps["props"]["size"],
): string {
	switch (size) {
		case "sm":
			return "max-w-sm";
		case "lg":
			return "max-w-3xl";
		case "xl":
			return "max-w-5xl";
		case "full":
			return "max-w-[95vw] h-[90vh]";
		case "default":
		default:
			return "max-w-lg";
	}
}

export function ModalComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as ModalComponentProps;
	const [isOpen, setIsOpen] = useState(false);
	const [loadingAction, setLoadingAction] = useState<number | null>(null);

	// Evaluate expressions
	const title = String(
		evaluateExpression(props.title, context) ?? props.title,
	);
	const description = props.description
		? String(
				evaluateExpression(props.description, context) ??
					props.description,
			)
		: undefined;
	const triggerLabel = String(
		evaluateExpression(props.triggerLabel, context) ?? props.triggerLabel,
	);

	// Handle footer action click
	const handleActionClick = useCallback(
		async (
			action: NonNullable<
				ModalComponentProps["props"]["footerActions"]
			>[number],
			index: number,
		) => {
			setLoadingAction(index);

			try {
				switch (action.actionType) {
					case "navigate":
						if (action.navigateTo && context.navigate) {
							const path = action.navigateTo.includes("{{")
								? String(
										evaluateExpression(
											action.navigateTo,
											context,
										) ?? action.navigateTo,
									)
								: action.navigateTo;
							context.navigate(path);
						}
						break;

					case "workflow":
						if (action.workflowId && context.triggerWorkflow) {
							// Evaluate action params
							const params: Record<string, unknown> = {};
							if (action.actionParams) {
								for (const [key, value] of Object.entries(
									action.actionParams,
								)) {
									if (
										typeof value === "string" &&
										value.includes("{{")
									) {
										params[key] = evaluateExpression(
											value,
											context,
										);
									} else {
										params[key] = value;
									}
								}
							}
							context.triggerWorkflow(
								action.workflowId,
								params,
								action.onComplete,
							);
						}
						break;

					case "submit":
						if (action.workflowId && context.submitForm) {
							// Evaluate additional params
							const additionalParams: Record<string, unknown> =
								{};
							if (action.actionParams) {
								for (const [key, value] of Object.entries(
									action.actionParams,
								)) {
									if (
										typeof value === "string" &&
										value.includes("{{")
									) {
										additionalParams[key] =
											evaluateExpression(value, context);
									} else {
										additionalParams[key] = value;
									}
								}
							}
							context.submitForm(
								action.workflowId,
								additionalParams,
							);
						}
						break;
				}

				// Close modal if configured
				if (action.closeOnClick !== false) {
					setIsOpen(false);
				}
			} finally {
				setLoadingAction(null);
			}
		},
		[context],
	);

	// Create a modal-scoped context that can track form values inside the modal
	const modalContext: ExpressionContext = {
		...context,
		// The field values from the modal should be accessible
		field: context.field || {},
	};

	const sizeClass = getModalSizeClass(props.size);
	const showCloseButton = props.showCloseButton ?? true;

	return (
		<Dialog open={isOpen} onOpenChange={setIsOpen}>
			<DialogTrigger asChild>
				<Button
					variant={props.triggerVariant || "default"}
					size={props.triggerSize || "default"}
				>
					{triggerLabel}
				</Button>
			</DialogTrigger>
			<DialogContent
				className={cn(sizeClass, props.className)}
				// Hide the default close button if not wanted
				onInteractOutside={(e) => {
					// Prevent closing when clicking inside the modal content
					if (!showCloseButton) {
						e.preventDefault();
					}
				}}
			>
				<DialogHeader>
					<DialogTitle>{title}</DialogTitle>
					{description && (
						<DialogDescription>{description}</DialogDescription>
					)}
				</DialogHeader>

				{/* Modal Content - Render the layout */}
				<div className="py-4">
					<LayoutRenderer
						layout={props.content}
						context={modalContext}
					/>
				</div>

				{/* Footer Actions */}
				{props.footerActions && props.footerActions.length > 0 && (
					<DialogFooter>
						{props.footerActions.map((action, index) => {
							const isLoading = loadingAction === index;
							const label = action.label.includes("{{")
								? String(
										evaluateExpression(
											action.label,
											context,
										) ?? action.label,
									)
								: action.label;

							return (
								<Button
									key={index}
									variant={action.variant || "default"}
									onClick={() =>
										handleActionClick(action, index)
									}
									disabled={isLoading}
								>
									{isLoading && (
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									)}
									{label}
								</Button>
							);
						})}
					</DialogFooter>
				)}
			</DialogContent>
		</Dialog>
	);
}
