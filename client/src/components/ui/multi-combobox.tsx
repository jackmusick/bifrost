import * as React from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";

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

export interface MultiComboboxOption {
	value: string;
	label: string;
	description?: string;
}

export interface MultiComboboxProps {
	options: MultiComboboxOption[];
	value: string[];
	onValueChange: (values: string[]) => void;
	placeholder?: string;
	searchPlaceholder?: string;
	emptyText?: string;
	disabled?: boolean;
	isLoading?: boolean;
	className?: string;
	maxDisplayedItems?: number;
}

export function MultiCombobox({
	options,
	value,
	onValueChange,
	placeholder = "Select options...",
	searchPlaceholder = "Search...",
	emptyText = "No option found.",
	disabled = false,
	isLoading = false,
	className,
	maxDisplayedItems,
}: MultiComboboxProps) {
	const [open, setOpen] = React.useState(false);

	const selectedOptions = options.filter((option) =>
		value.includes(option.value),
	);

	const displayedItems = maxDisplayedItems
		? selectedOptions.slice(0, maxDisplayedItems)
		: selectedOptions;
	const overflowCount = maxDisplayedItems
		? Math.max(0, selectedOptions.length - maxDisplayedItems)
		: 0;

	const handleToggle = (optionValue: string) => {
		if (value.includes(optionValue)) {
			onValueChange(value.filter((v) => v !== optionValue));
		} else {
			onValueChange([...value, optionValue]);
		}
	};

	const handleRemove = (
		optionValue: string,
		e: React.MouseEvent | React.KeyboardEvent,
	) => {
		e.stopPropagation();
		e.preventDefault();
		onValueChange(value.filter((v) => v !== optionValue));
	};

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>
				<Button
					variant="outline"
					role="combobox"
					aria-expanded={open}
					className={cn(
						"w-full justify-between h-auto min-h-10",
						className,
					)}
					disabled={disabled || isLoading}
				>
					{value.length > 0 ? (
						<div className="flex flex-wrap gap-1">
							{displayedItems.map((option) => (
								<Badge
									key={option.value}
									variant="secondary"
									className="mr-1"
								>
									{option.label}
									<span
										role="button"
										tabIndex={0}
										onClick={(e) =>
											handleRemove(option.value, e)
										}
										onKeyDown={(e) => {
											if (
												e.key === "Enter" ||
												e.key === " "
											) {
												handleRemove(option.value, e);
											}
										}}
										className="ml-1 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors cursor-pointer"
									>
										<X className="h-3 w-3" />
									</span>
								</Badge>
							))}
							{overflowCount > 0 && (
								<Badge variant="secondary">
									+{overflowCount} more
								</Badge>
							)}
						</div>
					) : (
						<span className="text-muted-foreground">
							{placeholder}
						</span>
					)}
					<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
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
							{options.map((option) => (
								<CommandItem
									key={option.value}
									value={option.value}
									keywords={[option.label]}
									onSelect={() => handleToggle(option.value)}
								>
									<Check
										className={cn(
											"mr-2 h-4 w-4",
											value.includes(option.value)
												? "opacity-100"
												: "opacity-0",
										)}
									/>
									<div className="flex flex-col flex-1">
										<span>{option.label}</span>
										{option.description && (
											<span className="text-xs text-muted-foreground">
												{option.description}
											</span>
										)}
									</div>
								</CommandItem>
							))}
						</CommandGroup>
					</CommandList>
				</Command>
			</PopoverContent>
		</Popover>
	);
}
