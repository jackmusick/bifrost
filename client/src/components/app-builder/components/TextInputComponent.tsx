/**
 * Text Input Component for App Builder
 *
 * Text input field with label, placeholder, validation, and field tracking.
 * Expression evaluation is handled centrally by ComponentRegistry.
 */

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { TextInputComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Text Input Component
 *
 * Renders a text input field with label, placeholder, and validation.
 * Value is tracked in the expression context under {{ field.<fieldId> }}.
 *
 * @example
 * // Basic text input
 * {
 *   id: "name-input",
 *   type: "text-input",
 *   props: {
 *     fieldId: "userName",
 *     label: "Name",
 *     placeholder: "Enter your name",
 *     required: true
 *   }
 * }
 *
 * @example
 * // Email input with validation
 * {
 *   id: "email-input",
 *   type: "text-input",
 *   props: {
 *     fieldId: "userEmail",
 *     label: "Email Address",
 *     inputType: "email",
 *     required: true
 *   }
 * }
 */
export function TextInputComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as TextInputComponentProps;

	// Props are pre-evaluated by ComponentRegistry
	const defaultValue = props.defaultValue ? String(props.defaultValue) : "";

	// Local state for the input value
	const [value, setValue] = useState(defaultValue);

	// Props are pre-evaluated by ComponentRegistry (disabled is now boolean)
	const isDisabled = Boolean(props.disabled);
	const label = props.label ? String(props.label) : undefined;
	const placeholder = props.placeholder
		? String(props.placeholder)
		: undefined;

	// Get setFieldValue from context (stable reference)
	const setFieldValue = context.setFieldValue;

	// Update field value in context when value changes
	useEffect(() => {
		if (setFieldValue) {
			setFieldValue(props.fieldId, value);
		}
	}, [props.fieldId, value, setFieldValue]);

	// Initialize field value on mount
	useEffect(() => {
		if (setFieldValue && defaultValue) {
			setFieldValue(props.fieldId, defaultValue);
		}
	}, [props.fieldId, defaultValue, setFieldValue]);

	const handleChange = useCallback(
		(e: React.ChangeEvent<HTMLInputElement>) => {
			setValue(e.target.value);
		},
		[],
	);

	const inputId = `field-${component.id}`;

	return (
		<div className={cn("space-y-2", props.className)}>
			{label && (
				<Label htmlFor={inputId}>
					{label}
					{props.required && (
						<span className="text-destructive ml-1">*</span>
					)}
				</Label>
			)}
			<Input
				id={inputId}
				type={props.inputType || "text"}
				value={value}
				onChange={handleChange}
				placeholder={placeholder}
				disabled={isDisabled}
				required={props.required}
				minLength={props.minLength}
				maxLength={props.maxLength}
				pattern={props.pattern}
			/>
		</div>
	);
}

export default TextInputComponent;
