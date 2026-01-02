/**
 * Key-Value Editor Component
 *
 * Visual editor for key-value pairs with add/remove functionality.
 * Supports expression hints for values.
 */

import { useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface KeyValuePair {
	key: string;
	value: string;
}

export interface KeyValueEditorProps {
	/** Current key-value pairs as an object */
	value: Record<string, unknown>;
	/** Callback when pairs change */
	onChange: (value: Record<string, unknown>) => void;
	/** Placeholder for key input */
	keyPlaceholder?: string;
	/** Placeholder for value input */
	valuePlaceholder?: string;
	/** Hint text to show below the editor */
	hint?: string;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Key-Value Editor
 *
 * Provides a visual interface for editing key-value pairs instead of raw JSON.
 *
 * @example
 * <KeyValueEditor
 *   value={props.actionParams ?? {}}
 *   onChange={(params) => onChange({ props: { ...props, actionParams: params } })}
 *   hint="Use {{ row.fieldName }} for dynamic values"
 * />
 */
export function KeyValueEditor({
	value,
	onChange,
	keyPlaceholder = "Parameter name",
	valuePlaceholder = "Value or {{ expression }}",
	hint,
	className,
}: KeyValueEditorProps) {
	// Convert object to array of pairs for editing
	const pairs: KeyValuePair[] = Object.entries(value).map(([key, val]) => ({
		key,
		value: typeof val === "string" ? val : JSON.stringify(val),
	}));

	const handleAddPair = useCallback(() => {
		const newPairs = [...pairs, { key: "", value: "" }];
		const newValue: Record<string, unknown> = {};
		for (const pair of newPairs) {
			if (pair.key) {
				newValue[pair.key] = pair.value;
			}
		}
		// Add empty key temporarily to show the new row
		onChange({ ...newValue, "": "" });
	}, [pairs, onChange]);

	const handleRemovePair = useCallback(
		(index: number) => {
			const newPairs = pairs.filter((_, i) => i !== index);
			const newValue: Record<string, unknown> = {};
			for (const pair of newPairs) {
				if (pair.key) {
					newValue[pair.key] = pair.value;
				}
			}
			onChange(newValue);
		},
		[pairs, onChange],
	);

	const handleKeyChange = useCallback(
		(index: number, newKey: string) => {
			const newValue: Record<string, unknown> = {};
			pairs.forEach((pair, i) => {
				const key = i === index ? newKey : pair.key;
				if (key) {
					newValue[key] = pair.value;
				}
			});
			onChange(newValue);
		},
		[pairs, onChange],
	);

	const handleValueChange = useCallback(
		(index: number, newVal: string) => {
			const newValue: Record<string, unknown> = {};
			pairs.forEach((pair, i) => {
				if (pair.key) {
					newValue[pair.key] = i === index ? newVal : pair.value;
				}
			});
			// Handle the case where the key is empty (new row)
			if (!pairs[index].key && newVal) {
				// Keep the value so it's not lost when key is added
				newValue[""] = newVal;
			}
			onChange(newValue);
		},
		[pairs, onChange],
	);

	return (
		<div className={cn("space-y-2", className)}>
			{pairs.length === 0 ? (
				<div className="text-sm text-muted-foreground italic py-2">
					No parameters defined
				</div>
			) : (
				<div className="space-y-2">
					{pairs.map((pair, index) => (
						<div key={index} className="flex gap-2 items-start">
							<Input
								value={pair.key}
								onChange={(e) =>
									handleKeyChange(index, e.target.value)
								}
								placeholder={keyPlaceholder}
								className="flex-1 text-sm"
							/>
							<Input
								value={pair.value}
								onChange={(e) =>
									handleValueChange(index, e.target.value)
								}
								placeholder={valuePlaceholder}
								className="flex-1 text-sm font-mono"
							/>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="h-10 w-10 shrink-0 text-muted-foreground hover:text-destructive"
								onClick={() => handleRemovePair(index)}
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
				onClick={handleAddPair}
			>
				<Plus className="h-4 w-4 mr-2" />
				Add Parameter
			</Button>

			{hint && <p className="text-xs text-muted-foreground">{hint}</p>}
		</div>
	);
}

export default KeyValueEditor;
