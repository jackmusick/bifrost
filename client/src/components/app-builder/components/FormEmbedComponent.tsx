/**
 * Form Embed Component for App Builder
 *
 * Embeds an existing form from the forms system into an App Builder page.
 * Form submission, execution progress, and results all happen inline
 * without navigating away from the parent page.
 */

import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import type {
	FormEmbedComponentProps,
	OnCompleteAction,
} from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { useForm } from "@/hooks/useForms";
import { FormRenderer } from "@/components/forms/FormRenderer";
import { ExecutionInlineDisplay } from "./ExecutionInlineDisplay";
import { Loader2, AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useAppContext } from "@/contexts/AppContext";

/**
 * State machine phases for the FormEmbed component
 */
type EmbedPhase =
	| { type: "form" }
	| { type: "executing"; executionId: string }
	| { type: "complete"; executionId: string; result?: unknown };

/**
 * Form Embed Component
 *
 * Renders an existing form from the forms system within an App Builder page.
 * Form submission, execution progress, and results are all displayed inline
 * within the embed container - the parent page never navigates away.
 *
 * @example
 * // Embed a form
 * {
 *   id: "survey-form",
 *   type: "form-embed",
 *   props: {
 *     formId: "abc-123",
 *     showTitle: true,
 *     showDescription: true
 *   }
 * }
 *
 * @example
 * // Embed with post-submission navigation
 * {
 *   id: "contact-form",
 *   type: "form-embed",
 *   props: {
 *     formId: "contact-form-id",
 *     showTitle: false,
 *     onSubmit: [
 *       { type: "navigate", navigateTo: "/thank-you" }
 *     ]
 *   }
 * }
 */
export function FormEmbedComponent({ component }: RegisteredComponentProps) {
	const { props } = component as FormEmbedComponentProps;
	const { context, setVariable, setWorkflowResult } = useAppContext();

	// State machine for form → executing → complete phases
	const [phase, setPhase] = useState<EmbedPhase>({ type: "form" });

	// Fetch the form by ID
	const { data: form, isLoading, error } = useForm(props.formId);

	// Handle when FormRenderer starts execution
	const handleExecutionStart = useCallback((executionId: string) => {
		setPhase({ type: "executing", executionId });
	}, []);

	// Execute onComplete/onSubmit actions
	const executeOnCompleteActions = useCallback(
		(actions: OnCompleteAction[], result?: unknown) => {
			for (const action of actions) {
				switch (action.type) {
					case "navigate":
						if (action.navigateTo && context.navigate) {
							context.navigate(action.navigateTo);
						}
						break;
					case "set-variable":
						if (action.variableName !== undefined) {
							// If value is an expression referencing result, resolve it
							let value: unknown = action.variableValue;
							if (
								typeof value === "string" &&
								value.includes("{{ workflow.result")
							) {
								// Simple result injection
								value = result;
							}
							setVariable(
								action.variableName,
								value as string | undefined,
							);
						}
						break;
					case "refresh-table":
						if (action.dataSourceKey && context.refreshTable) {
							context.refreshTable(action.dataSourceKey);
						}
						break;
					default:
						console.warn(
							`Unknown onSubmit action type: ${(action as OnCompleteAction).type}`,
						);
				}
			}
		},
		[context, setVariable],
	);

	// Handle when execution completes
	const handleExecutionComplete = useCallback(
		(result?: unknown) => {
			const executionId =
				phase.type === "executing" ? phase.executionId : "";
			setPhase({ type: "complete", executionId, result });

			// Inject result into expression context
			if (result !== undefined) {
				setWorkflowResult({
					executionId,
					status: "completed",
					result,
				});
			}

			// Execute onSubmit actions
			if (props.onSubmit && props.onSubmit.length > 0) {
				executeOnCompleteActions(props.onSubmit, result);
			}
		},
		[phase, props.onSubmit, setWorkflowResult, executeOnCompleteActions],
	);

	// Handle "Submit Another" - reset to form phase
	const handleBack = useCallback(() => {
		setPhase({ type: "form" });
	}, []);

	// Loading state
	if (isLoading) {
		return (
			<div
				className={cn(
					"flex items-center justify-center py-8",
					props.className,
				)}
			>
				<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	// Error state
	if (error || !form) {
		const errorMessage =
			error instanceof Error ? error.message : "Form not found";
		return (
			<Card className={cn("border-destructive/50", props.className)}>
				<CardContent className="flex items-center gap-2 py-6 text-destructive">
					<AlertTriangle className="h-5 w-5" />
					<span>Failed to load form: {errorMessage}</span>
				</CardContent>
			</Card>
		);
	}

	// Render based on current phase
	return (
		<div className={cn("space-y-4", props.className)}>
			{/* Optional title and description from props */}
			{(props.showTitle || props.showDescription) && (
				<div className="space-y-1">
					{props.showTitle && form.name && (
						<h3 className="text-lg font-semibold">{form.name}</h3>
					)}
					{props.showDescription && form.description && (
						<p className="text-sm text-muted-foreground">
							{form.description}
						</p>
					)}
				</div>
			)}

			{/* Phase-specific content */}
			{phase.type === "form" && (
				<FormRenderer
					form={form}
					onExecutionStart={handleExecutionStart}
					preventNavigation={true}
				/>
			)}

			{(phase.type === "executing" || phase.type === "complete") && (
				<ExecutionInlineDisplay
					executionId={phase.executionId}
					onComplete={handleExecutionComplete}
					onBack={handleBack}
				/>
			)}
		</div>
	);
}

export default FormEmbedComponent;
