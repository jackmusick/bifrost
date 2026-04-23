import * as React from "react";
import { Check, ChevronsUpDown, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import type { ComboboxOption } from "@/components/ui/combobox";

interface MultiComboboxProps {
	options: ComboboxOption[];
	value?: string[];
	onValueChange?: (value: string[]) => void;
	placeholder?: string;
	searchPlaceholder?: string;
	emptyText?: string;
	disabled?: boolean;
	isLoading?: boolean;
	className?: string;
	id?: string;
}

export function MultiCombobox({
	options,
	value = [],
	onValueChange,
	placeholder = "Select options...",
	searchPlaceholder = "Search...",
	emptyText = "No option found.",
	disabled = false,
	isLoading = false,
	className,
	id,
}: MultiComboboxProps) {
	const [open, setOpen] = React.useState(false);

	const selectedSet = React.useMemo(() => new Set(value), [value]);
	const selectedOptions = React.useMemo(
		() => value.map((v) => options.find((o) => o.value === v) ?? { value: v, label: v }),
		[options, value],
	);

	const toggle = (optionValue: string) => {
		if (selectedSet.has(optionValue)) {
			onValueChange?.(value.filter((v) => v !== optionValue));
		} else {
			onValueChange?.([...value, optionValue]);
		}
	};

	const removeValue = (optionValue: string, e: React.MouseEvent) => {
		e.stopPropagation();
		onValueChange?.(value.filter((v) => v !== optionValue));
	};

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>
				<Button
					id={id}
					variant="outline"
					role="combobox"
					aria-expanded={open}
					className={cn(
						"w-full justify-between font-normal h-auto min-h-10 py-2",
						className,
					)}
					disabled={disabled || isLoading}
				>
					{isLoading ? (
						<>
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							<span className="text-muted-foreground">
								Loading...
							</span>
						</>
					) : (
						<>
							<div className="flex flex-wrap gap-1 flex-1 min-w-0">
								{selectedOptions.length === 0 ? (
									<span className="text-muted-foreground">
										{placeholder}
									</span>
								) : (
									selectedOptions.map((option) => (
										<Badge
											key={option.value}
											variant="secondary"
											className="gap-1 pr-1"
										>
											<span className="truncate max-w-[200px]">
												{option.label}
											</span>
											<span
												role="button"
												tabIndex={-1}
												aria-label={`Remove ${option.label}`}
												className="inline-flex items-center justify-center rounded-sm hover:bg-muted-foreground/20 h-4 w-4 cursor-pointer"
												onClick={(e) =>
													removeValue(option.value, e)
												}
												onKeyDown={(e) => {
													if (
														e.key === "Enter" ||
														e.key === " "
													) {
														e.preventDefault();
														e.stopPropagation();
														onValueChange?.(
															value.filter(
																(v) =>
																	v !==
																	option.value,
															),
														);
													}
												}}
											>
												<X className="h-3 w-3" />
											</span>
										</Badge>
									))
								)}
							</div>
							<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
						</>
					)}
				</Button>
			</PopoverTrigger>
			<PopoverContent
				className="w-[var(--radix-popover-trigger-width)] p-0"
				align="start"
			>
				<Command>
					<CommandInput placeholder={searchPlaceholder} />
					<CommandList className="max-h-60 overflow-y-auto">
						<CommandEmpty>{emptyText}</CommandEmpty>
						<CommandGroup>
							{options.map((option) => {
								const isSelected = selectedSet.has(option.value);
								return (
									<CommandItem
										key={option.value}
										value={option.value}
										keywords={[option.label]}
										onSelect={() => toggle(option.value)}
									>
										<div className="flex flex-col flex-1">
											<span className="font-medium">
												{option.label}
											</span>
											{option.description && (
												<span className="text-xs text-muted-foreground">
													{option.description}
												</span>
											)}
										</div>
										<Check
											className={cn(
												"ml-auto h-4 w-4",
												isSelected
													? "opacity-100"
													: "opacity-0",
											)}
										/>
									</CommandItem>
								);
							})}
						</CommandGroup>
					</CommandList>
				</Command>
			</PopoverContent>
		</Popover>
	);
}
