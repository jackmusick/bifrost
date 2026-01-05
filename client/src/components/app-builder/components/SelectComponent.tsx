/**
 * Select Component for App Builder
 *
 * Dropdown select with static or data-driven options and field tracking.
 * Expression evaluation is handled centrally by ComponentRegistry.
 */

import { useCallback, useEffect, useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import type {
	SelectComponentProps,
	SelectOption,
} from "@/lib/app-builder-types";
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

	// Props are pre-evaluated by ComponentRegistry
	const defaultValue = props.defaultValue ? String(props.defaultValue) : "";

	// Local state for the selected value
	const [value, setValue] = useState(defaultValue);

	// Props are pre-evaluated by ComponentRegistry (disabled is now boolean)
	const isDisabled = Boolean(props.disabled);
	const label = props.label ? String(props.label) : undefined;
	const placeholder = props.placeholder
		? String(props.placeholder)
		: "Select an option";

	// Build options from static config or data source
	// Note: options array is pre-evaluated by ComponentRegistry (evaluateDeep)
	const options: SelectOption[] = useMemo(() => {
		// If options were evaluated to an array, use them directly
		if (Array.isArray(props.options) && props.options.length > 0) {
			// Check if it's already SelectOption[] or raw data needing field mapping
			const firstOption = props.options[0];
			if (
				typeof firstOption === "object" &&
				firstOption !== null &&
				"value" in firstOption &&
				"label" in firstOption
			) {
				return props.options as SelectOption[];
			}
			// Raw data - apply field mapping
			const valueField = props.valueField || "value";
			const labelField = props.labelField || "label";
			return props.options.map((item): SelectOption => {
				const itemObj = item as unknown as Record<string, unknown>;
				return {
					value: String(itemObj[valueField] ?? ""),
					label: String(
						itemObj[labelField] ?? itemObj[valueField] ?? "",
					),
				};
			});
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
