/**
 * Checkbox Component for App Builder
 *
 * Boolean checkbox with label, description, and field tracking.
 */

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { CheckboxComponentProps } from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

/**
 * Checkbox Component
 *
 * Renders a checkbox with label and optional description.
 * Value is tracked in the expression context under {{ field.<fieldId> }}.
 *
 * @example
 * // Simple checkbox
 * {
 *   id: "terms-checkbox",
 *   type: "checkbox",
 *   props: {
 *     fieldId: "acceptTerms",
 *     label: "I accept the terms and conditions",
 *     required: true
 *   }
 * }
 *
 * @example
 * // Checkbox with description
 * {
 *   id: "subscribe-checkbox",
 *   type: "checkbox",
 *   props: {
 *     fieldId: "subscribe",
 *     label: "Subscribe to newsletter",
 *     description: "Receive weekly updates about new features",
 *     defaultChecked: true
 *   }
 * }
 */
export function CheckboxComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as CheckboxComponentProps;

	// Get default checked state
	const defaultChecked = props.defaultChecked ?? false;

	// Local state for the checked value
	const [checked, setChecked] = useState(defaultChecked);

	// Evaluate disabled state
	const isDisabled = (() => {
		if (props.disabled === undefined || props.disabled === null) {
			return false;
		}
		if (typeof props.disabled === "boolean") {
			return props.disabled;
		}
		return Boolean(evaluateExpression(props.disabled, context));
	})();

	// Evaluate label if it contains expressions
	const label = String(
		evaluateExpression(props.label, context) ?? props.label,
	);

	// Evaluate description if it contains expressions
	const description = props.description
		? String(
				evaluateExpression(props.description, context) ??
					props.description,
			)
		: undefined;

	// Get setFieldValue from context (stable reference)
	const setFieldValue = context.setFieldValue;

	// Update field value in context when value changes
	useEffect(() => {
		if (setFieldValue) {
			setFieldValue(props.fieldId, checked);
		}
	}, [props.fieldId, checked, setFieldValue]);

	// Initialize field value on mount
	useEffect(() => {
		if (setFieldValue) {
			setFieldValue(props.fieldId, defaultChecked);
		}
	}, [props.fieldId, defaultChecked, setFieldValue]);

	const handleChange = useCallback(
		(newChecked: boolean | "indeterminate") => {
			if (newChecked !== "indeterminate") {
				setChecked(newChecked);
			}
		},
		[],
	);

	const inputId = `field-${component.id}`;

	return (
		<div className={cn("flex items-start space-x-3", props.className)}>
			<Checkbox
				id={inputId}
				checked={checked}
				onCheckedChange={handleChange}
				disabled={isDisabled}
				required={props.required}
			/>
			<div className="grid gap-1.5 leading-none">
				<Label
					htmlFor={inputId}
					className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
				>
					{label}
					{props.required && (
						<span className="text-destructive ml-1">*</span>
					)}
				</Label>
				{description && (
					<p className="text-sm text-muted-foreground">
						{description}
					</p>
				)}
			</div>
		</div>
	);
}

export default CheckboxComponent;
