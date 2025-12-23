/**
 * Entity Selector Component
 * Combobox-based searchable dropdown for selecting integration entities
 * Falls back to text input if no entities are available
 */

import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import type { DataProviderOption } from "@/services/dataProviders";

interface EntitySelectorProps {
	entities: DataProviderOption[];
	value: string;
	onChange: (value: string, label: string) => void;
	disabled?: boolean;
	placeholder?: string;
	isLoading?: boolean;
}

export function EntitySelector({
	entities,
	value,
	onChange,
	disabled = false,
	placeholder = "Select entity...",
	isLoading = false,
}: EntitySelectorProps) {
	// Show loading skeleton
	if (isLoading) {
		return <Skeleton className="h-8 w-full" />;
	}

	// Fall back to text input if no entities available
	if (!entities || entities.length === 0) {
		return (
			<Input
				placeholder="entity-id"
				value={value}
				onChange={(e) => onChange(e.target.value, e.target.value)}
				disabled={disabled}
				className="h-8 text-sm"
			/>
		);
	}

	// Convert DataProviderOption to ComboboxOption
	const options: ComboboxOption[] = entities.map((entity) => ({
		value: entity.value,
		label: entity.label,
		description: entity.description,
	}));

	return (
		<Combobox
			options={options}
			value={value}
			onValueChange={(selectedValue) => {
				// Find the selected option to get the label
				const selectedOption = options.find(
					(opt) => opt.value === selectedValue,
				);
				const label = selectedOption ? selectedOption.label : selectedValue;
				onChange(selectedValue, label);
			}}
			placeholder={placeholder}
			searchPlaceholder="Search entities..."
			emptyText="No entities found."
			disabled={disabled}
			className="h-8 text-sm"
		/>
	);
}
