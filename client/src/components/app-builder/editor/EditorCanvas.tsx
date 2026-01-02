/**
 * Editor Canvas for App Builder
 *
 * Central editing area for visually building apps.
 * Renders the page layout tree with drag-and-drop support.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import {
	draggable,
	dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import {
	attachClosestEdge,
	extractClosestEdge,
	type Edge,
} from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge";
import { cn } from "@/lib/utils";
import type {
	PageDefinition,
	LayoutContainer,
	AppComponent,
	ComponentType,
	LayoutType,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
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
	Trash2,
} from "lucide-react";

/**
 * Drag data for components being moved within the canvas.
 * Uses index signature to satisfy pragmatic-drag-and-drop's Record<string, unknown> requirement.
 */
export interface DragData {
	/** Type of drag operation */
	type: "component" | "layout" | "palette";
	/** Component/layout ID being dragged */
	id: string;
	/** Parent ID (for reordering) */
	parentId?: string;
	/** Index within parent */
	index?: number;
	/** Component type (for palette items) */
	componentType?: ComponentType | LayoutType;
	/** Index signature for compatibility with pragmatic-drag-and-drop */
	[key: string]: unknown;
}

/**
 * Type guard to check if data is DragData
 */
function isDragData(data: Record<string, unknown>): data is DragData {
	return (
		typeof data.type === "string" &&
		["component", "layout", "palette"].includes(data.type) &&
		typeof data.id === "string"
	);
}

/**
 * Type guard to check if data is from ComponentPalette
 */
function isPaletteDragData(data: Record<string, unknown>): boolean {
	return (
		data.type === "new-component" && typeof data.componentType === "string"
	);
}

/**
 * Safely extract DragData from source data
 * Also handles palette drag data by converting it to DragData format
 */
function extractDragData(data: Record<string, unknown>): DragData | null {
	// Handle palette items (type: "new-component")
	if (isPaletteDragData(data)) {
		return {
			type: "palette",
			id: `new-${Date.now()}`,
			componentType: data.componentType as ComponentType | LayoutType,
		};
	}

	if (isDragData(data)) {
		return data;
	}
	return null;
}

/**
 * Drop target information
 */
export interface DropTarget {
	/** Target component/layout ID */
	id: string;
	/** Drop position relative to target */
	position: "before" | "after" | "inside";
	/** Edge for the drop indicator */
	edge?: Edge;
}

interface EditorCanvasProps {
	/** The page to render */
	page: PageDefinition;
	/** Currently selected component ID */
	selectedId: string | null;
	/** Selection callback */
	onSelect: (id: string | null) => void;
	/** Drop callback when a component is moved/added */
	onDrop: (source: DragData, target: DropTarget) => void;
	/** Delete callback */
	onDelete: (id: string) => void;
}

/**
 * Icon component that renders the appropriate icon for a component type
 */
function ComponentIcon({
	type,
	className,
}: {
	type: ComponentType | LayoutType;
	className?: string;
}) {
	switch (type) {
		case "heading":
		case "text":
			return <Type className={className} />;
		case "html":
			return <Code className={className} />;
		case "card":
			return <Square className={className} />;
		case "divider":
			return <Minus className={className} />;
		case "spacer":
			return <Box className={className} />;
		case "button":
			return <MousePointerClick className={className} />;
		case "stat-card":
			return <BarChart3 className={className} />;
		case "image":
			return <Image className={className} />;
		case "badge":
			return <Tag className={className} />;
		case "progress":
			return <Loader2 className={className} />;
		case "data-table":
			return <Table2 className={className} />;
		case "tabs":
			return <Layers className={className} />;
		case "row":
			return <Rows3 className={className} />;
		case "column":
			return <Columns3 className={className} />;
		case "grid":
			return <LayoutGrid className={className} />;
		default:
			return <Box className={className} />;
	}
}

/**
 * Get display label for a component type
 */
function getComponentLabel(type: ComponentType | LayoutType): string {
	const labels: Record<ComponentType | LayoutType, string> = {
		heading: "Heading",
		text: "Text",
		html: "HTML/JSX",
		card: "Card",
		divider: "Divider",
		spacer: "Spacer",
		button: "Button",
		"stat-card": "Stat Card",
		image: "Image",
		badge: "Badge",
		progress: "Progress",
		"data-table": "Data Table",
		tabs: "Tabs",
		"file-viewer": "File Viewer",
		modal: "Modal",
		row: "Row",
		column: "Column",
		grid: "Grid",
		"text-input": "Text Input",
		"number-input": "Number Input",
		select: "Select",
		checkbox: "Checkbox",
		"form-embed": "Form Embed",
		"form-group": "Form Group",
	};
	return labels[type] || type;
}

/**
 * Get additional info text for a component
 */
function getComponentInfo(element: LayoutContainer | AppComponent): string {
	if (isLayoutContainer(element)) {
		const childCount = element.children.length;
		return `${childCount} ${childCount === 1 ? "child" : "children"}`;
	}

	const component = element as AppComponent;
	switch (component.type) {
		case "heading":
			return (
				(component.props as { text?: string }).text?.slice(0, 30) || ""
			);
		case "text":
			return (
				(component.props as { text?: string }).text?.slice(0, 30) || ""
			);
		case "button":
			return (component.props as { label?: string }).label || "";
		case "card":
			return (component.props as { title?: string }).title || "";
		case "stat-card":
			return (component.props as { title?: string }).title || "";
		default:
			return "";
	}
}

interface DropIndicatorProps {
	edge: Edge | null;
	isContainer?: boolean;
}

/**
 * Visual indicator for drop position
 * Shows a prominent blue line with a circle indicator at the insertion point
 */
function DropIndicator({ edge, isContainer }: DropIndicatorProps) {
	if (!edge) return null;

	if (isContainer) {
		return (
			<div className="absolute inset-0 border-2 border-dashed border-blue-500 bg-blue-500/10 rounded pointer-events-none z-10" />
		);
	}

	// Determine if this is a horizontal or vertical indicator
	const isHorizontal = edge === "top" || edge === "bottom";

	const edgeStyles: Record<Edge, string> = {
		top: "-top-0.5 left-0 right-0 h-1",
		bottom: "-bottom-0.5 left-0 right-0 h-1",
		left: "left-0 top-0 bottom-0 w-1",
		right: "right-0 top-0 bottom-0 w-1",
	};

	return (
		<>
			{/* Main indicator line */}
			<div
				className={cn(
					"absolute bg-blue-500 pointer-events-none z-20 rounded-full shadow-sm shadow-blue-500/50",
					edgeStyles[edge],
				)}
			/>
			{/* Circle indicator at the start of the line */}
			<div
				className={cn(
					"absolute w-3 h-3 bg-blue-500 rounded-full pointer-events-none z-20 shadow-sm shadow-blue-500/50",
					isHorizontal ? "-left-1.5" : "left-1/2 -translate-x-1/2",
					edge === "top" && "-top-1.5",
					edge === "bottom" && "-bottom-1.5",
					edge === "left" && "-top-1.5",
					edge === "right" && "-top-1.5",
				)}
			/>
		</>
	);
}

interface CanvasElementProps {
	element: LayoutContainer | AppComponent;
	elementId: string;
	parentId?: string;
	index: number;
	selectedId: string | null;
	onSelect: (id: string | null) => void;
	onDrop: (source: DragData, target: DropTarget) => void;
	onDelete: (id: string) => void;
	depth?: number;
}

/**
 * Renders a single element in the canvas (component or layout container)
 */
function CanvasElement({
	element,
	elementId,
	parentId,
	index,
	selectedId,
	onSelect,
	onDrop,
	onDelete,
	depth = 0,
}: CanvasElementProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [isDragging, setIsDragging] = useState(false);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [closestEdge, setClosestEdge] = useState<Edge | null>(null);
	const [isHovered, setIsHovered] = useState(false);

	const isContainer = isLayoutContainer(element);
	const isSelected = elementId === selectedId;

	const elementType = isContainer
		? (element as LayoutContainer).type
		: (element as AppComponent).type;
	const label = getComponentLabel(elementType);
	const info = getComponentInfo(element);

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		const dragData: DragData = {
			type: isContainer ? "layout" : "component",
			id: elementId,
			parentId,
			index,
		};

		return combine(
			draggable({
				element: el,
				getInitialData: () => dragData,
				onDragStart: () => setIsDragging(true),
				onDrop: () => setIsDragging(false),
			}),
			dropTargetForElements({
				element: el,
				getData: ({ input, element: targetEl }) => {
					const baseData = {
						id: elementId,
						isContainer,
					};
					// For containers, allow dropping inside
					// For components, only allow before/after
					const allowedEdges: Edge[] = isContainer
						? ["top", "bottom"]
						: ["top", "bottom"];
					return attachClosestEdge(baseData, {
						input,
						element: targetEl,
						allowedEdges,
					});
				},
				canDrop: ({ source }) => {
					// Prevent dropping on self
					if (source.data.id === elementId) return false;
					// Prevent dropping a parent into its own child
					// This would need more sophisticated checking in a real implementation
					return true;
				},
				onDragEnter: () => setIsDraggedOver(true),
				onDrag: ({ self }) => {
					const edge = extractClosestEdge(self.data);
					setClosestEdge(edge);
				},
				onDragLeave: () => {
					setIsDraggedOver(false);
					setClosestEdge(null);
				},
				onDrop: ({ source, self, location }) => {
					setIsDraggedOver(false);
					setClosestEdge(null);

					// Only handle the drop if we're the innermost (first) drop target
					// This prevents parent containers from also handling the drop
					const dropTargets = location.current.dropTargets;
					if (
						dropTargets.length > 0 &&
						dropTargets[0].element !== ref.current
					) {
						return;
					}

					const edge = extractClosestEdge(self.data);
					const sourceData = extractDragData(source.data);

					if (!sourceData) return;

					// Determine drop position
					let position: "before" | "after" | "inside" = "after";
					if (edge === "top" || edge === "left") {
						position = "before";
					} else if (edge === "bottom" || edge === "right") {
						position = "after";
					}

					onDrop(sourceData, {
						id: elementId,
						position,
						edge: edge ?? undefined,
					});
				},
			}),
		);
	}, [elementId, parentId, index, isContainer, onDrop]);

	const handleClick = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onSelect(elementId);
		},
		[elementId, onSelect],
	);

	const handleDelete = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onDelete(elementId);
		},
		[elementId, onDelete],
	);

	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "Delete" || e.key === "Backspace") {
				e.preventDefault();
				onDelete(elementId);
			}
		},
		[elementId, onDelete],
	);

	return (
		<div
			ref={ref}
			className={cn(
				"relative rounded-lg border-2 cursor-move",
				// Base transition for smooth state changes
				"transition-all duration-200 ease-out",
				// Dragging state - ghosted appearance
				isDragging &&
					"opacity-40 scale-[0.98] border-dashed border-gray-400 dark:border-gray-500",
				// Selected state
				!isDragging &&
					isSelected &&
					"border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-md",
				// Dragged over state (something hovering)
				!isDragging &&
					!isSelected &&
					isDraggedOver &&
					"border-blue-400 bg-blue-50/50 dark:bg-blue-950/20 shadow-sm",
				// Hover state
				!isDragging &&
					!isSelected &&
					!isDraggedOver &&
					isHovered &&
					"border-gray-300 dark:border-gray-600 bg-gray-50/50 dark:bg-gray-800/50",
				// Default state
				!isDragging &&
					!isSelected &&
					!isDraggedOver &&
					!isHovered &&
					"border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900",
				// Size constraints
				isContainer ? "min-h-[80px]" : "min-h-[48px]",
			)}
			onClick={handleClick}
			onKeyDown={handleKeyDown}
			onMouseEnter={() => setIsHovered(true)}
			onMouseLeave={() => setIsHovered(false)}
			tabIndex={0}
			role="button"
			aria-selected={isSelected}
			aria-label={`${label}${info ? `: ${info}` : ""}`}
		>
			{/* Drop indicator */}
			<DropIndicator edge={closestEdge} isContainer={false} />

			{/* Selection handles (visual only) */}
			{isSelected && (
				<>
					<div className="absolute -top-1 -left-1 w-2 h-2 bg-blue-500 rounded-sm" />
					<div className="absolute -top-1 -right-1 w-2 h-2 bg-blue-500 rounded-sm" />
					<div className="absolute -bottom-1 -left-1 w-2 h-2 bg-blue-500 rounded-sm" />
					<div className="absolute -bottom-1 -right-1 w-2 h-2 bg-blue-500 rounded-sm" />
				</>
			)}

			{/* Delete button on hover/select */}
			{(isHovered || isSelected) && (
				<button
					onClick={handleDelete}
					className="absolute -top-2 -right-2 p-1 bg-red-500 hover:bg-red-600 text-white rounded-full shadow-md z-20 transition-colors"
					aria-label="Delete component"
				>
					<Trash2 className="h-3 w-3" />
				</button>
			)}

			{/* Component header */}
			<div className="flex items-center gap-2 p-2 border-b border-gray-100 dark:border-gray-800">
				<ComponentIcon
					type={elementType}
					className="h-4 w-4 text-gray-500 dark:text-gray-400 flex-shrink-0"
				/>
				<span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
					{label}
				</span>
				{info && (
					<span className="text-xs text-gray-400 dark:text-gray-500 truncate flex-1">
						{info}
					</span>
				)}
				{isContainer && (
					<span className="text-xs text-gray-400 dark:text-gray-500 px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">
						{(element as LayoutContainer).type}
					</span>
				)}
			</div>

			{/* Container children or component placeholder */}
			{isContainer ? (
				<ContainerChildren
					container={element as LayoutContainer}
					containerId={elementId}
					selectedId={selectedId}
					onSelect={onSelect}
					onDrop={onDrop}
					onDelete={onDelete}
					depth={depth}
				/>
			) : (
				<div className="p-2 text-xs text-gray-400 dark:text-gray-500 italic">
					{elementType} component
				</div>
			)}
		</div>
	);
}

interface ContainerChildrenProps {
	container: LayoutContainer;
	containerId: string;
	selectedId: string | null;
	onSelect: (id: string | null) => void;
	onDrop: (source: DragData, target: DropTarget) => void;
	onDelete: (id: string) => void;
	depth: number;
}

/**
 * Drop zone at the end of a container to allow adding more children
 */
function ContainerDropZone({
	containerId,
	onDrop,
	isEmpty,
}: {
	containerId: string;
	onDrop: (source: DragData, target: DropTarget) => void;
	isEmpty: boolean;
}) {
	const dropRef = useRef<HTMLDivElement>(null);
	const [isDraggedOver, setIsDraggedOver] = useState(false);

	useEffect(() => {
		const el = dropRef.current;
		if (!el) return;

		return dropTargetForElements({
			element: el,
			getData: () => ({
				id: containerId,
				isContainer: true,
				isEmpty,
				isDropZone: true,
			}),
			onDragEnter: () => setIsDraggedOver(true),
			onDragLeave: () => setIsDraggedOver(false),
			onDrop: ({ source, location }) => {
				setIsDraggedOver(false);

				// Only handle the drop if we're the innermost (first) drop target
				const dropTargets = location.current.dropTargets;
				if (
					dropTargets.length > 0 &&
					dropTargets[0].element !== dropRef.current
				) {
					return;
				}

				const sourceData = extractDragData(source.data);
				if (!sourceData) return;

				onDrop(sourceData, {
					id: containerId,
					position: "inside",
				});
			},
		});
	}, [containerId, isEmpty, onDrop]);

	return (
		<div
			ref={dropRef}
			className={cn(
				"flex items-center justify-center rounded border-2 border-dashed transition-colors",
				isEmpty ? "min-h-[60px] m-2" : "min-h-[40px] mx-2 mb-2",
				isDraggedOver
					? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
					: "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600",
			)}
		>
			<span className="text-xs text-gray-400 dark:text-gray-500">
				{isEmpty ? "Drop components here" : "+ Add here"}
			</span>
		</div>
	);
}

/**
 * Renders children of a layout container with empty state support
 */
function ContainerChildren({
	container,
	containerId,
	selectedId,
	onSelect,
	onDrop,
	onDelete,
	depth,
}: ContainerChildrenProps) {
	if (container.children.length === 0) {
		return (
			<ContainerDropZone
				containerId={containerId}
				onDrop={onDrop}
				isEmpty={true}
			/>
		);
	}

	// Map gap/padding values to Tailwind classes (matches LayoutRenderer)
	const getGapClass = (gap?: number): string => {
		if (gap === undefined) return "gap-2"; // Default editor gap
		const gapMap: Record<number, string> = {
			0: "gap-0",
			4: "gap-1",
			8: "gap-2",
			12: "gap-3",
			16: "gap-4",
			20: "gap-5",
			24: "gap-6",
			32: "gap-8",
			40: "gap-10",
			48: "gap-12",
		};
		return gapMap[gap] || `gap-[${gap}px]`;
	};

	const getPaddingClass = (padding?: number): string => {
		if (padding === undefined) return "p-2"; // Default editor padding
		const paddingMap: Record<number, string> = {
			0: "p-0",
			4: "p-1",
			8: "p-2",
			12: "p-3",
			16: "p-4",
			20: "p-5",
			24: "p-6",
			32: "p-8",
			40: "p-10",
			48: "p-12",
		};
		return paddingMap[padding] || `p-[${padding}px]`;
	};

	// Determine flex direction based on container type
	const containerStyles = cn(
		getPaddingClass(container.padding),
		"pb-0 flex",
		getGapClass(container.gap),
		container.type === "row" && "flex-row flex-wrap",
		container.type === "column" && "flex-col",
		container.type === "grid" && `grid grid-cols-${container.columns || 2}`,
	);

	return (
		<div className="flex flex-col">
			<div className={containerStyles}>
				{container.children.map((child, index) => {
					const childId = isLayoutContainer(child)
						? `${containerId}-layout-${index}`
						: (child as AppComponent).id;

					return (
						<CanvasElement
							key={childId}
							element={child}
							elementId={childId}
							parentId={containerId}
							index={index}
							selectedId={selectedId}
							onSelect={onSelect}
							onDrop={onDrop}
							onDelete={onDelete}
							depth={depth + 1}
						/>
					);
				})}
			</div>
			{/* Always show a drop zone at the end of the container to allow adding more children */}
			<ContainerDropZone
				containerId={containerId}
				onDrop={onDrop}
				isEmpty={false}
			/>
		</div>
	);
}

/**
 * Editor Canvas Component
 *
 * The main visual editing area for the App Builder.
 * Renders the page's layout tree with drag-and-drop support.
 *
 * @example
 * <EditorCanvas
 *   page={currentPage}
 *   selectedId={selectedComponentId}
 *   onSelect={setSelectedComponentId}
 *   onDrop={handleDrop}
 *   onDelete={handleDelete}
 * />
 */
export function EditorCanvas({
	page,
	selectedId,
	onSelect,
	onDrop,
	onDelete,
}: EditorCanvasProps) {
	const containerRef = useRef<HTMLDivElement>(null);

	// Handle click on empty canvas area to deselect
	const handleCanvasClick = useCallback(() => {
		onSelect(null);
	}, [onSelect]);

	// Handle keyboard shortcuts
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === "Escape") {
				onSelect(null);
			}
		};

		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [onSelect]);

	return (
		<div
			ref={containerRef}
			className="flex-1 p-6 overflow-auto bg-gray-100 dark:bg-gray-950"
			onClick={handleCanvasClick}
		>
			<div className="max-w-4xl mx-auto">
				{/* Page header */}
				<div className="mb-4 pb-4 border-b border-gray-200 dark:border-gray-800">
					<h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300">
						{page.title}
					</h2>
					<p className="text-sm text-gray-500 dark:text-gray-400">
						{page.path}
					</p>
				</div>

				{/* Layout tree */}
				<CanvasElement
					element={page.layout}
					elementId="root"
					index={0}
					selectedId={selectedId}
					onSelect={onSelect}
					onDrop={onDrop}
					onDelete={onDelete}
				/>
			</div>
		</div>
	);
}

export default EditorCanvas;
