import { useEffect, useRef, useState } from "react";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { draggable } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import {
	Rows3,
	Columns3,
	LayoutGrid,
	PanelTop,
	CreditCard,
	Heading1,
	Type,
	Code,
	ImageIcon,
	Minus,
	Space,
	MousePointerClick,
	Table,
	BarChart3,
	BadgeCheck,
	Percent,
	TextCursorInput,
	Hash,
	ChevronDown,
	CheckSquare,
	FileText,
	PanelBottomOpen,
	FormInput,
	LayoutList,
	LucideIcon,
} from "lucide-react";
import type { ComponentType, LayoutType } from "@/lib/app-builder-types";

/**
 * Component definition for the palette
 */
interface ComponentDefinition {
	type: ComponentType | LayoutType;
	label: string;
	description: string;
	icon: LucideIcon;
	color: string;
}

/**
 * Category definition for grouping components
 */
interface ComponentCategory {
	id: string;
	label: string;
	components: ComponentDefinition[];
	disabled?: boolean;
}

/**
 * Drag data attached to draggable palette items
 */
export interface PaletteDragData {
	type: "new-component";
	componentType: ComponentType | LayoutType;
}

// Component definitions organized by category
const COMPONENT_CATEGORIES: ComponentCategory[] = [
	{
		id: "layout",
		label: "Layout",
		components: [
			{
				type: "row",
				label: "Row",
				description:
					"Horizontal flex container for side-by-side content",
				icon: Rows3,
				color: "bg-violet-500",
			},
			{
				type: "column",
				label: "Column",
				description: "Vertical flex container for stacked content",
				icon: Columns3,
				color: "bg-violet-500",
			},
			{
				type: "grid",
				label: "Grid",
				description: "CSS grid layout for complex arrangements",
				icon: LayoutGrid,
				color: "bg-violet-500",
			},
			{
				type: "tabs",
				label: "Tabs",
				description: "Tabbed container for organizing content",
				icon: PanelTop,
				color: "bg-violet-500",
			},
			{
				type: "card",
				label: "Card",
				description: "Container with optional title and border",
				icon: CreditCard,
				color: "bg-violet-500",
			},
		],
	},
	{
		id: "content",
		label: "Content",
		components: [
			{
				type: "heading",
				label: "Heading",
				description:
					"Title text with configurable heading level (h1-h6)",
				icon: Heading1,
				color: "bg-blue-500",
			},
			{
				type: "text",
				label: "Text",
				description: "Paragraph text with optional label",
				icon: Type,
				color: "bg-blue-500",
			},
			{
				type: "html",
				label: "HTML/JSX",
				description: "Custom HTML or JSX template with context access",
				icon: Code,
				color: "bg-red-500",
			},
			{
				type: "image",
				label: "Image",
				description: "Display images with sizing and fit options",
				icon: ImageIcon,
				color: "bg-blue-500",
			},
			{
				type: "divider",
				label: "Divider",
				description: "Horizontal or vertical line separator",
				icon: Minus,
				color: "bg-blue-500",
			},
			{
				type: "spacer",
				label: "Spacer",
				description: "Empty space with configurable size",
				icon: Space,
				color: "bg-blue-500",
			},
		],
	},
	{
		id: "interactive",
		label: "Interactive",
		components: [
			{
				type: "button",
				label: "Button",
				description:
					"Clickable button with navigation or workflow actions",
				icon: MousePointerClick,
				color: "bg-green-500",
			},
			{
				type: "data-table",
				label: "Table",
				description:
					"Data table with sorting, pagination, and row actions",
				icon: Table,
				color: "bg-green-500",
			},
			{
				type: "stat-card",
				label: "Stat Card",
				description:
					"Display metric with value, trend, and optional icon",
				icon: BarChart3,
				color: "bg-green-500",
			},
			{
				type: "badge",
				label: "Badge",
				description: "Small label for status or category indicators",
				icon: BadgeCheck,
				color: "bg-green-500",
			},
			{
				type: "progress",
				label: "Progress",
				description: "Progress bar with percentage display",
				icon: Percent,
				color: "bg-green-500",
			},
			{
				type: "file-viewer",
				label: "File Viewer",
				description:
					"Display files inline, in modal, or as download link",
				icon: FileText,
				color: "bg-green-500",
			},
			{
				type: "modal",
				label: "Modal",
				description: "Dialog with custom content and footer actions",
				icon: PanelBottomOpen,
				color: "bg-green-500",
			},
		],
	},
	{
		id: "forms",
		label: "Forms",
		components: [
			{
				type: "text-input",
				label: "Text Input",
				description:
					"Text field with label, placeholder, and validation",
				icon: TextCursorInput,
				color: "bg-amber-500",
			},
			{
				type: "number-input",
				label: "Number Input",
				description: "Numeric input with min/max and step controls",
				icon: Hash,
				color: "bg-amber-500",
			},
			{
				type: "select",
				label: "Select",
				description: "Dropdown with static or data-driven options",
				icon: ChevronDown,
				color: "bg-amber-500",
			},
			{
				type: "checkbox",
				label: "Checkbox",
				description: "Boolean toggle with label and description",
				icon: CheckSquare,
				color: "bg-amber-500",
			},
			{
				type: "form-group",
				label: "Form Group",
				description: "Group multiple form fields with a shared label",
				icon: LayoutList,
				color: "bg-amber-500",
			},
			{
				type: "form-embed",
				label: "Form Embed",
				description: "Embed an existing form from the forms system",
				icon: FormInput,
				color: "bg-amber-500",
			},
		],
	},
];

/**
 * Props for the palette item component
 */
interface PaletteItemProps {
	component: ComponentDefinition;
	disabled?: boolean;
}

/**
 * Individual draggable component in the palette
 */
function PaletteItem({ component, disabled = false }: PaletteItemProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [isDragging, setIsDragging] = useState(false);
	const Icon = component.icon;

	useEffect(() => {
		const el = ref.current;
		if (!el || disabled) return;

		return draggable({
			element: el,
			getInitialData: () => ({
				type: "new-component",
				componentType: component.type,
			}),
			onDragStart: () => setIsDragging(true),
			onDrop: () => setIsDragging(false),
		});
	}, [component.type, disabled]);

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<div
					ref={ref}
					className={`
						flex items-center gap-3 rounded-lg border p-3 transition-all
						${disabled ? "opacity-50 cursor-not-allowed bg-muted" : "cursor-grab active:cursor-grabbing hover:border-primary hover:shadow-sm bg-card"}
						${isDragging ? "opacity-50 scale-95" : ""}
					`}
				>
					<div className={`${component.color} p-2 rounded`}>
						<Icon className="h-4 w-4 text-white" />
					</div>
					<span className="text-sm font-medium">
						{component.label}
					</span>
				</div>
			</TooltipTrigger>
			<TooltipContent side="right" className="max-w-[200px]">
				<p>{component.description}</p>
			</TooltipContent>
		</Tooltip>
	);
}

/**
 * Props for the ComponentPalette component
 */
export interface ComponentPaletteProps {
	/** Additional CSS classes */
	className?: string;
}

/**
 * Component palette for the App Builder visual editor.
 *
 * Displays draggable components organized by category that users can
 * drag onto the canvas to add to their application layout.
 */
export function ComponentPalette({ className = "" }: ComponentPaletteProps) {
	// Default all categories to expanded
	const defaultExpandedCategories = COMPONENT_CATEGORIES.filter(
		(cat) => !cat.disabled,
	).map((cat) => cat.id);

	return (
		<div className={`flex flex-col h-full ${className}`}>
			<div className="p-4 border-b">
				<h3 className="font-semibold text-sm">Components</h3>
				<p className="text-xs text-muted-foreground mt-1">
					Drag components to the canvas
				</p>
			</div>

			<div className="flex-1 overflow-y-auto p-2">
				<Accordion
					type="multiple"
					defaultValue={defaultExpandedCategories}
					className="w-full"
				>
					{COMPONENT_CATEGORIES.map((category) => (
						<AccordionItem key={category.id} value={category.id}>
							<AccordionTrigger className="text-sm px-2">
								<span className="flex items-center gap-2">
									{category.label}
									{category.disabled && (
										<span className="text-xs text-muted-foreground font-normal">
											(Coming soon)
										</span>
									)}
								</span>
							</AccordionTrigger>
							<AccordionContent className="px-2 pb-2">
								<div className="space-y-2">
									{category.components.map((component) => (
										<PaletteItem
											key={component.type}
											component={component}
											disabled={category.disabled}
										/>
									))}
								</div>
							</AccordionContent>
						</AccordionItem>
					))}
				</Accordion>
			</div>
		</div>
	);
}
