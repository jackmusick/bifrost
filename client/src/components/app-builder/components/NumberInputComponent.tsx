/**
 * Number Input Component for App Builder
 *
 * Numeric input field with label, min/max validation, and field tracking.
 */

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { NumberInputComponentProps } from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Number Input Component
 *
 * Renders a numeric input field with label, min/max bounds, and step.
 * Value is tracked in the expression context under {{ field.<fieldId> }}.
 *
 * @example
 * // Basic number input
 * {
 *   id: "quantity-input",
 *   type: "number-input",
 *   props: {
 *     fieldId: "quantity",
 *     label: "Quantity",
 *     min: 1,
 *     max: 100,
 *     defaultValue: 1
 *   }
 * }
 *
 * @example
 * // Price input with decimal step
 * {
 *   id: "price-input",
 *   type: "number-input",
 *   props: {
 *     fieldId: "price",
 *     label: "Price",
 *     min: 0,
 *     step: 0.01,
 *     placeholder: "0.00"
 *   }
 * }
 */
export function NumberInputComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as NumberInputComponentProps;

	// Evaluate default value if it's an expression
	const getDefaultValue = (): number | "" => {
		if (props.defaultValue === undefined || props.defaultValue === null) {
			return "";
		}
		if (typeof props.defaultValue === "number") {
			return props.defaultValue;
		}
		// It's a string - could be an expression
		const evaluated = evaluateExpression(props.defaultValue, context);
		if (evaluated === undefined || evaluated === null || evaluated === "") {
			return "";
		}
		const num = Number(evaluated);
		return isNaN(num) ? "" : num;
	};

	const defaultValue = getDefaultValue();

	// Local state for the input value
	const [value, setValue] = useState<number | "">(defaultValue);

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
	const label = props.label
		? String(evaluateExpression(props.label, context) ?? props.label)
		: undefined;

	// Evaluate placeholder if it contains expressions
	const placeholder = props.placeholder
		? String(
				evaluateExpression(props.placeholder, context) ??
					props.placeholder,
			)
		: undefined;

	// Get setFieldValue from context (stable reference)
	const setFieldValue = context.setFieldValue;

	// Update field value in context when value changes
	useEffect(() => {
		if (setFieldValue) {
			setFieldValue(props.fieldId, value === "" ? null : value);
		}
	}, [props.fieldId, value, setFieldValue]);

	// Initialize field value on mount
	useEffect(() => {
		if (setFieldValue && defaultValue !== "") {
			setFieldValue(props.fieldId, defaultValue);
		}
	}, [props.fieldId, defaultValue, setFieldValue]);

	const handleChange = useCallback(
		(e: React.ChangeEvent<HTMLInputElement>) => {
			const inputValue = e.target.value;
			if (inputValue === "") {
				setValue("");
			} else {
				const num = Number(inputValue);
				if (!isNaN(num)) {
					setValue(num);
				}
			}
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
				type="number"
				value={value}
				onChange={handleChange}
				placeholder={placeholder}
				disabled={isDisabled}
				required={props.required}
				min={props.min}
				max={props.max}
				step={props.step}
			/>
		</div>
	);
}

export default NumberInputComponent;
