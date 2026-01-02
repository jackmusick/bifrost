/**
 * Select Component for App Builder
 *
 * Dropdown select with static or data-driven options and field tracking.
 */

import { useCallback, useEffect, useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import type {
	SelectComponentProps,
	SelectOption,
} from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

/**
 * Select Component
 *
 * Renders a dropdown select with static or dynamic options.
 * Value is tracked in the expression context under {{ field.<fieldId> }}.
 *
 * @example
 * // Static options
 * {
 *   id: "status-select",
 *   type: "select",
 *   props: {
 *     fieldId: "status",
 *     label: "Status",
 *     options: [
 *       { value: "active", label: "Active" },
 *       { value: "inactive", label: "Inactive" },
 *       { value: "pending", label: "Pending" }
 *     ],
 *     defaultValue: "active"
 *   }
 * }
 *
 * @example
 * // Data-driven options
 * {
 *   id: "category-select",
 *   type: "select",
 *   props: {
 *     fieldId: "categoryId",
 *     label: "Category",
 *     optionsSource: "categories",
 *     valueField: "id",
 *     labelField: "name"
 *   }
 * }
 */
export function SelectComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as SelectComponentProps;

	// Evaluate default value if it's an expression
	const defaultValue = props.defaultValue
		? String(evaluateExpression(props.defaultValue, context) ?? "")
		: "";

	// Local state for the selected value
	const [value, setValue] = useState(defaultValue);

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
		: "Select an option";

	// Build options from static config or data source
	const options: SelectOption[] = useMemo(() => {
		// If static options are provided as an array, use them
		if (
			props.options &&
			Array.isArray(props.options) &&
			props.options.length > 0
		) {
			return props.options;
		}

		// If options is an expression string, evaluate it
		if (
			props.options &&
			typeof props.options === "string" &&
			props.options.includes("{{")
		) {
			const evaluated = evaluateExpression(props.options, context);
			if (Array.isArray(evaluated)) {
				const valueField = props.valueField || "value";
				const labelField = props.labelField || "label";
				return evaluated.map(
					(item: Record<string, unknown>): SelectOption => ({
						value: String(item[valueField] ?? ""),
						label: String(item[labelField] ?? item[valueField] ?? ""),
					}),
				);
			}
		}

		// If optionsSource is specified, get from context data
		if (props.optionsSource && context.data) {
			const sourceData = context.data[props.optionsSource];
			if (Array.isArray(sourceData)) {
				const valueField = props.valueField || "value";
				const labelField = props.labelField || "label";

				return sourceData.map((item) => ({
					value: String(item[valueField] ?? ""),
					label: String(item[labelField] ?? item[valueField] ?? ""),
				}));
			}
		}

		return [];
	}, [
		props.options,
		props.optionsSource,
		props.valueField,
		props.labelField,
		context.data,
		context,
	]);

	// Get setFieldValue from context (stable reference)
	const setFieldValue = context.setFieldValue;

	// Update field value in context when value changes
	useEffect(() => {
		if (setFieldValue) {
			setFieldValue(props.fieldId, value || null);
		}
	}, [props.fieldId, value, setFieldValue]);

	// Initialize field value on mount
	useEffect(() => {
		if (setFieldValue && defaultValue) {
			setFieldValue(props.fieldId, defaultValue);
		}
	}, [props.fieldId, defaultValue, setFieldValue]);

	const handleChange = useCallback((newValue: string) => {
		setValue(newValue);
	}, []);

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
			<Select
				value={value}
				onValueChange={handleChange}
				disabled={isDisabled}
				required={props.required}
			>
				<SelectTrigger id={inputId}>
					<SelectValue placeholder={placeholder} />
				</SelectTrigger>
				<SelectContent>
					{options.map((option) => (
						<SelectItem key={option.value} value={option.value}>
							{option.label}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		</div>
	);
}

export default SelectComponent;
