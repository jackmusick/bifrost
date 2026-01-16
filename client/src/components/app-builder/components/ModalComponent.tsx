/**
 * Modal Component for App Builder
 *
 * A dialog component that can contain form inputs or other content.
 * Supports custom footer actions with workflow integration.
 */

import { useState, useCallback, useMemo } from "react";
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
import type { components } from "@/lib/v1";
import type { ExpressionContext } from "@/types/app-builder";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";
import { LayoutRenderer } from "../LayoutRenderer";
import { useAppContext } from "@/contexts/AppContext";

type ModalComponent = components["schemas"]["ModalComponent"];

/**
 * Get modal size classes
 */
function getModalSizeClass(
	size?: ModalComponent["props"]["size"],
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
	const { props } = component as ModalComponent;
	const { isModalOpen } = useAppContext();

	// Determine if this modal has its own trigger button or is controlled externally
	const hasTrigger = props.trigger_label !== undefined;

	// Local state for modals with trigger buttons
	const [localIsOpen, setLocalIsOpen] = useState(false);

	// For externally controlled modals, sync with context
	const externalIsOpen = isModalOpen(component.id);

	// Use local state if has trigger, otherwise use external state
	const isOpen = hasTrigger ? localIsOpen : externalIsOpen;
	const setIsOpen = useMemo(
		() =>
			hasTrigger
				? setLocalIsOpen
				: (open: boolean) => {
						if (open) {
							context.openModal?.(component.id);
						} else {
							context.closeModal?.(component.id);
						}
					},
		[hasTrigger, context.openModal, context.closeModal, component.id],
	);

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
	const triggerLabel = props.trigger_label
		? String(
				evaluateExpression(props.trigger_label, context) ??
					props.trigger_label,
			)
		: undefined;

	// Handle footer action click
	const handleActionClick = useCallback(
		async (
			action: NonNullable<
				ModalComponent["props"]["footer_actions"]
			>[number],
			index: number,
		) => {
			setLoadingAction(index);

			try {
				switch (action.action_type) {
					case "navigate":
						if (action.navigate_to && context.navigate) {
							const path = action.navigate_to.includes("{{")
								? String(
										evaluateExpression(
											action.navigate_to,
											context,
										) ?? action.navigate_to,
									)
								: action.navigate_to;
							context.navigate(path);
						}
						break;

					case "workflow":
						if (action.workflow_id && context.triggerWorkflow) {
							// Evaluate action params
							const params: Record<string, unknown> = {};
							if (action.action_params) {
								for (const [key, value] of Object.entries(
									action.action_params,
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
								action.workflow_id,
								params,
								action.on_complete ?? undefined,
							);
						}
						break;

					case "submit":
						if (action.workflow_id && context.submitForm) {
							// Evaluate additional params
							const additionalParams: Record<string, unknown> =
								{};
							if (action.action_params) {
								for (const [key, value] of Object.entries(
									action.action_params,
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
								action.workflow_id,
								additionalParams,
								action.on_complete ?? undefined,
								action.on_error ?? undefined,
							);
						}
						break;
				}

				// Close modal if configured
				if (action.close_on_click !== false) {
					setIsOpen(false);
				}
			} finally {
				setLoadingAction(null);
			}
		},
		[context, setIsOpen],
	);

	// Create a modal-scoped context that can track form values inside the modal
	const modalContext: ExpressionContext = {
		...context,
		// The field values from the modal should be accessible
		field: context.field || {},
	};

	const sizeClass = getModalSizeClass(props.size);
	const showCloseButton = props.show_close_button ?? true;

	return (
		<Dialog open={isOpen} onOpenChange={setIsOpen}>
			{hasTrigger && triggerLabel && (
				<DialogTrigger asChild>
					<Button
						variant={props.trigger_variant || "default"}
						size={props.trigger_size || "default"}
					>
						{triggerLabel}
					</Button>
				</DialogTrigger>
			)}
			<DialogContent
				className={cn(sizeClass, props.class_name)}
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
				{props.footer_actions && props.footer_actions.length > 0 && (
					<DialogFooter>
						{props.footer_actions.map((action, index) => {
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
