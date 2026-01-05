/**
 * Component Inserter
 *
 * Popover for selecting a component type to insert into the tree.
 * Shows categorized component options with descriptions.
 */

import { useState, useCallback, type ReactNode } from "react";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import {
	Box,
	Type,
	Code,
	Minus,
	Square,
	MousePointerClick,
	BarChart3,
	Image,
	Tag,
	Loader2,
	Table2,
	Layers,
	LayoutGrid,
	Rows3,
	Columns3,
	FileInput,
	Hash,
	ListFilter,
	CheckSquare,
	FileText,
	Group,
	PanelTop,
	File,
	Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ComponentType, LayoutType } from "@/lib/app-builder-types";
import { componentCategories } from "@/lib/app-builder-tree";

interface ComponentInserterProps {
	/** Whether the popover is open */
	open: boolean;
	/** Callback when open state changes */
	onOpenChange: (open: boolean) => void;
	/** Callback when a component type is selected */
	onSelect: (type: ComponentType | LayoutType) => void;
	/** Custom trigger element */
	trigger: ReactNode;
}

/**
 * Get the icon for a component type
 */
function getComponentIcon(type: ComponentType | LayoutType) {
	const iconClass = "h-4 w-4 text-muted-foreground";

	switch (type) {
		case "heading":
		case "text":
			return <Type className={iconClass} />;
		case "html":
			return <Code className={iconClass} />;
		case "card":
			return <Square className={iconClass} />;
		case "divider":
			return <Minus className={iconClass} />;
		case "spacer":
			return <Box className={iconClass} />;
		case "button":
			return <MousePointerClick className={iconClass} />;
		case "stat-card":
			return <BarChart3 className={iconClass} />;
		case "image":
			return <Image className={iconClass} />;
		case "badge":
			return <Tag className={iconClass} />;
		case "progress":
			return <Loader2 className={iconClass} />;
		case "data-table":
			return <Table2 className={iconClass} />;
		case "tabs":
			return <Layers className={iconClass} />;
		case "row":
			return <Rows3 className={iconClass} />;
		case "column":
			return <Columns3 className={iconClass} />;
		case "grid":
			return <LayoutGrid className={iconClass} />;
		case "text-input":
			return <FileInput className={iconClass} />;
		case "number-input":
			return <Hash className={iconClass} />;
		case "select":
			return <ListFilter className={iconClass} />;
		case "checkbox":
			return <CheckSquare className={iconClass} />;
		case "file-viewer":
			return <File className={iconClass} />;
		case "modal":
			return <PanelTop className={iconClass} />;
		case "form-embed":
			return <FileText className={iconClass} />;
		case "form-group":
			return <Group className={iconClass} />;
		default:
			return <Box className={iconClass} />;
	}
}

export function ComponentInserter({
	open,
	onOpenChange,
	onSelect,
	trigger,
}: ComponentInserterProps) {
	const [search, setSearch] = useState("");

	const handleSelect = useCallback(
		(type: ComponentType | LayoutType) => {
			onSelect(type);
			setSearch("");
		},
		[onSelect],
	);

	// Filter categories and items based on search
	const filteredCategories = componentCategories
		.map((category) => ({
			...category,
			items: category.items.filter(
				(item) =>
					item.label.toLowerCase().includes(search.toLowerCase()) ||
					item.description
						.toLowerCase()
						.includes(search.toLowerCase()),
			),
		}))
		.filter((category) => category.items.length > 0);

	return (
		<Popover open={open} onOpenChange={onOpenChange}>
			<PopoverTrigger asChild>{trigger}</PopoverTrigger>
			<PopoverContent
				className="w-72 p-0"
				align="start"
				side="right"
				sideOffset={4}
			>
				{/* Search input */}
				<div className="p-2 border-b">
					<div className="relative">
						<Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
						<Input
							placeholder="Search components..."
							value={search}
							onChange={(e) => setSearch(e.target.value)}
							className="pl-8 h-8"
							autoFocus
						/>
					</div>
				</div>

				{/* Component list */}
				<div className="h-[300px] overflow-y-auto">
					<div className="p-2 space-y-4">
						{filteredCategories.map((category) => (
							<div key={category.name}>
								<div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1">
									{category.name}
								</div>
								<div className="space-y-0.5">
									{category.items.map((item) => (
										<button
											key={item.type}
											onClick={() =>
												handleSelect(item.type)
											}
											className={cn(
												"w-full flex items-start gap-3 rounded-md px-2 py-1.5 text-left transition-colors",
												"hover:bg-muted focus:bg-muted focus:outline-none",
											)}
										>
											<div className="mt-0.5">
												{getComponentIcon(item.type)}
											</div>
											<div className="flex-1 min-w-0">
												<div className="text-sm font-medium">
													{item.label}
												</div>
												<div className="text-xs text-muted-foreground truncate">
													{item.description}
												</div>
											</div>
										</button>
									))}
								</div>
							</div>
						))}

						{filteredCategories.length === 0 && (
							<div className="text-center py-8 text-muted-foreground text-sm">
								No components match "{search}"
							</div>
						)}
					</div>
				</div>
			</PopoverContent>
		</Popover>
	);
}

export default ComponentInserter;
