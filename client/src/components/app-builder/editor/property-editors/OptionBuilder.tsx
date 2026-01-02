/**
 * Option Builder Component
 *
 * Visual editor for Select component options.
 * Allows add/remove of value/label pairs.
 */

import { useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SelectOption } from "@/lib/app-builder-types";

export interface OptionBuilderProps {
	/** Current options */
	value: SelectOption[];
	/** Callback when options change */
	onChange: (value: SelectOption[]) => void;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Option Builder
 *
 * Provides a visual interface for configuring Select options.
 *
 * @example
 * <OptionBuilder
 *   value={props.options ?? []}
 *   onChange={(options) => onChange({ props: { ...props, options } })}
 * />
 */
export function OptionBuilder({
	value,
	onChange,
	className,
}: OptionBuilderProps) {
	const handleAddOption = useCallback(() => {
		onChange([...value, { value: "", label: "" }]);
	}, [value, onChange]);

	const handleRemoveOption = useCallback(
		(index: number) => {
			onChange(value.filter((_, i) => i !== index));
		},
		[value, onChange],
	);

	const handleUpdateOption = useCallback(
		(index: number, field: "value" | "label", newValue: string) => {
			onChange(
				value.map((opt, i) =>
					i === index ? { ...opt, [field]: newValue } : opt,
				),
			);
		},
		[value, onChange],
	);

	return (
		<div className={cn("space-y-2", className)}>
			{/* Header */}
			{value.length > 0 && (
				<div className="grid grid-cols-[1fr_1fr_40px] gap-2 text-xs font-medium text-muted-foreground px-1">
					<span>Value</span>
					<span>Label</span>
					<span></span>
				</div>
			)}

			{/* Options */}
			{value.length === 0 ? (
				<div className="text-sm text-muted-foreground italic py-3 text-center border border-dashed rounded-md">
					No options defined
				</div>
			) : (
				<div className="space-y-2">
					{value.map((option, index) => (
						<div
							key={index}
							className="grid grid-cols-[1fr_1fr_40px] gap-2"
						>
							<Input
								value={option.value}
								onChange={(e) =>
									handleUpdateOption(
										index,
										"value",
										e.target.value,
									)
								}
								placeholder="value"
								className="text-sm font-mono"
							/>
							<Input
								value={option.label}
								onChange={(e) =>
									handleUpdateOption(
										index,
										"label",
										e.target.value,
									)
								}
								placeholder="Display label"
								className="text-sm"
							/>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="h-10 w-10 text-muted-foreground hover:text-destructive"
								onClick={() => handleRemoveOption(index)}
							>
								<Trash2 className="h-4 w-4" />
							</Button>
						</div>
					))}
				</div>
			)}

			<Button
				type="button"
				variant="outline"
				size="sm"
				className="w-full"
				onClick={handleAddOption}
			>
				<Plus className="h-4 w-4 mr-2" />
				Add Option
			</Button>
		</div>
	);
}

export default OptionBuilder;
