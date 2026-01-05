/**
 * Structure Tree Component
 *
 * Tree view for the App Builder editor that shows the component hierarchy.
 * Supports selection, drag-and-drop reordering, and component insertion.
 */

import { useState, useCallback, useRef, useEffect } from "react";
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
import {
	ChevronRight,
	ChevronDown,
	Plus,
	Trash2,
	Copy,
	GripVertical,
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
	ContextMenu,
	ContextMenuContent,
	ContextMenuItem,
	ContextMenuSeparator,
	ContextMenuSub,
	ContextMenuSubContent,
	ContextMenuSubTrigger,
	ContextMenuTrigger,
} from "@/components/ui/context-menu";
import type {
	PageDefinition,
	LayoutContainer,
	AppComponent,
	ComponentType,
	LayoutType,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
import {
	getComponentLabel,
	getComponentInfo,
	getChildId,
	componentCategories,
} from "@/lib/app-builder-tree";
import { ComponentInserter } from "./ComponentInserter";

// ============================================================================
// Types
// ============================================================================

export interface StructureTreeProps {
	/** All pages in the app */
	pages: PageDefinition[];
	/** Currently selected page ID */
	selectedPageId: string;
	/** Currently selected component ID */
	selectedComponentId: string | null;
	/** Callback when a page is selected */
	onSelectPage: (pageId: string) => void;
	/** Callback when a component is selected */
	onSelectComponent: (componentId: string | null) => void;
	/** Callback when a component should be added */
	onAddComponent: (
		parentId: string,
		type: ComponentType | LayoutType,
		position: "inside" | "before" | "after",
	) => void;
	/** Callback when a component should be moved */
	onMoveComponent: (
		sourceId: string,
		targetId: string,
		position: "before" | "after" | "inside",
	) => void;
	/** Callback when a component should be deleted */
	onDeleteComponent: (componentId: string) => void;
	/** Callback when a component should be duplicated */
	onDuplicateComponent: (componentId: string) => void;
	/** Additional CSS classes */
	className?: string;
}

interface TreeItemDragData {
	type: "tree-item";
	id: string;
	isContainer: boolean;
	[key: string]: unknown;
}

// ============================================================================
// Icons
// ============================================================================

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
	const iconClass = cn("h-4 w-4", className);

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

// ============================================================================
// Tree Item Component
// ============================================================================

interface TreeItemProps {
	element: LayoutContainer | AppComponent;
	elementId: string;
	parentId: string;
	index: number;
	depth: number;
	selectedId: string | null;
	expandedIds: Set<string>;
	onSelect: (id: string) => void;
	onToggleExpand: (id: string) => void;
	onAddComponent: (
		parentId: string,
		type: ComponentType | LayoutType,
		position: "inside" | "before" | "after",
	) => void;
	onMoveComponent: (
		sourceId: string,
		targetId: string,
		position: "before" | "after" | "inside",
	) => void;
	onDelete: (id: string) => void;
	onDuplicate: (id: string) => void;
}

function TreeItem({
	element,
	elementId,
	parentId: _parentId,
	index: _index,
	depth,
	selectedId,
	expandedIds,
	onSelect,
	onToggleExpand,
	onAddComponent,
	onMoveComponent,
	onDelete,
	onDuplicate,
}: TreeItemProps) {
	// parentId and index are passed for future use (e.g., move up/down buttons)
	void _parentId;
	void _index;
	const ref = useRef<HTMLDivElement>(null);
	const [isDragging, setIsDragging] = useState(false);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [closestEdge, setClosestEdge] = useState<Edge | null>(null);
	const [inserterOpen, setInserterOpen] = useState<
		"before" | "after" | "inside" | null
	>(null);

	const isContainer = isLayoutContainer(element);
	const isSelected = elementId === selectedId;
	const isExpanded = expandedIds.has(elementId);
	const elementType = isContainer
		? (element as LayoutContainer).type
		: (element as AppComponent).type;
	const label = getComponentLabel(elementType);
	const info = getComponentInfo(element);

	// Set up drag and drop
	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		const dragData: TreeItemDragData = {
			type: "tree-item",
			id: elementId,
			isContainer,
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
					return attachClosestEdge(
						{ id: elementId, isContainer },
						{
							input,
							element: targetEl,
							allowedEdges: ["top", "bottom"],
						},
					);
				},
				canDrop: ({ source }) => {
					const data = source.data as TreeItemDragData;
					// Can't drop on self
					if (data.id === elementId) return false;
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
				onDrop: ({ source, self }) => {
					setIsDraggedOver(false);
					setClosestEdge(null);

					const sourceData = source.data as TreeItemDragData;
					const edge = extractClosestEdge(self.data);

					let position: "before" | "after" | "inside" = "after";
					if (edge === "top") {
						position = "before";
					} else if (edge === "bottom") {
						position =
							isContainer && isExpanded ? "inside" : "after";
					}

					onMoveComponent(sourceData.id, elementId, position);
				},
			}),
		);
	}, [elementId, isContainer, isExpanded, onMoveComponent]);

	const handleClick = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onSelect(elementId);
		},
		[elementId, onSelect],
	);

	const handleExpandClick = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onToggleExpand(elementId);
		},
		[elementId, onToggleExpand],
	);

	const handleAddClick = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			setInserterOpen(isContainer ? "inside" : "after");
		},
		[isContainer],
	);

	const handleInsert = useCallback(
		(type: ComponentType | LayoutType) => {
			if (inserterOpen) {
				onAddComponent(elementId, type, inserterOpen);
				setInserterOpen(null);
				// Expand container if we added inside
				if (inserterOpen === "inside" && !isExpanded) {
					onToggleExpand(elementId);
				}
			}
		},
		[elementId, inserterOpen, isExpanded, onAddComponent, onToggleExpand],
	);

	return (
		<div className="select-none">
			<ContextMenu>
				<ContextMenuTrigger asChild>
					<div
						ref={ref}
						className={cn(
							"group relative flex items-center gap-1 px-2 py-1 cursor-pointer transition-colors",
							isSelected
								? "bg-primary text-primary-foreground"
								: "hover:bg-muted",
							isDragging && "opacity-50",
							isDraggedOver &&
								closestEdge === "top" &&
								"border-t-2 border-primary",
							isDraggedOver &&
								closestEdge === "bottom" &&
								"border-b-2 border-primary",
						)}
						style={{ paddingLeft: `${depth * 12 + 8}px` }}
						onClick={handleClick}
					>
						{/* Drag handle */}
						<GripVertical className="h-3 w-3 opacity-0 group-hover:opacity-50 cursor-grab flex-shrink-0" />

						{/* Expand/collapse for containers */}
						{isContainer ? (
							<button
								onClick={handleExpandClick}
								className="flex-shrink-0 p-0.5 hover:bg-black/10 dark:hover:bg-white/10"
							>
								{isExpanded ? (
									<ChevronDown className="h-3 w-3" />
								) : (
									<ChevronRight className="h-3 w-3" />
								)}
							</button>
						) : (
							<div className="w-4" /> // Spacer for alignment
						)}

						{/* Icon */}
						<ComponentIcon
							type={elementType}
							className={cn(
								"flex-shrink-0",
								isSelected
									? "text-primary-foreground"
									: "text-muted-foreground",
							)}
						/>

						{/* Label */}
						<span className="text-sm truncate flex-1">{label}</span>

						{/* Info text */}
						{info && (
							<span
								className={cn(
									"text-xs truncate max-w-24",
									isSelected
										? "text-primary-foreground/70"
										: "text-muted-foreground",
								)}
							>
								{info}
							</span>
						)}

						{/* Add button */}
						<ComponentInserter
							open={inserterOpen !== null}
							onOpenChange={(open) =>
								setInserterOpen(
									open
										? isContainer
											? "inside"
											: "after"
										: null,
								)
							}
							onSelect={handleInsert}
							trigger={
								<Button
									variant="ghost"
									size="icon"
									className={cn(
										"h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity",
										isSelected &&
											"text-primary-foreground hover:bg-primary-foreground/20",
									)}
									onClick={handleAddClick}
								>
									<Plus className="h-3 w-3" />
								</Button>
							}
						/>
					</div>
				</ContextMenuTrigger>

				<ContextMenuContent>
					<ContextMenuSub>
						<ContextMenuSubTrigger>
							<Plus className="mr-2 h-4 w-4" />
							Add component...
						</ContextMenuSubTrigger>
						<ContextMenuSubContent className="w-48">
							{componentCategories.map((category) => (
								<ContextMenuSub key={category.name}>
									<ContextMenuSubTrigger>
										{category.name}
									</ContextMenuSubTrigger>
									<ContextMenuSubContent>
										{category.items.map((item) => (
											<ContextMenuItem
												key={item.type}
												onClick={() =>
													onAddComponent(
														elementId,
														item.type,
														isContainer
															? "inside"
															: "after",
													)
												}
											>
												{item.label}
											</ContextMenuItem>
										))}
									</ContextMenuSubContent>
								</ContextMenuSub>
							))}
						</ContextMenuSubContent>
					</ContextMenuSub>

					<ContextMenuSeparator />

					<ContextMenuItem onClick={() => onDuplicate(elementId)}>
						<Copy className="mr-2 h-4 w-4" />
						Duplicate
					</ContextMenuItem>

					<ContextMenuSeparator />

					{isContainer && (
						<>
							<ContextMenuSub>
								<ContextMenuSubTrigger>
									<LayoutGrid className="mr-2 h-4 w-4" />
									Wrap in...
								</ContextMenuSubTrigger>
								<ContextMenuSubContent>
									<ContextMenuItem
										onClick={() =>
											onAddComponent(
												elementId,
												"row",
												"before",
											)
										}
									>
										Row
									</ContextMenuItem>
									<ContextMenuItem
										onClick={() =>
											onAddComponent(
												elementId,
												"column",
												"before",
											)
										}
									>
										Column
									</ContextMenuItem>
									<ContextMenuItem
										onClick={() =>
											onAddComponent(
												elementId,
												"grid",
												"before",
											)
										}
									>
										Grid
									</ContextMenuItem>
								</ContextMenuSubContent>
							</ContextMenuSub>
							<ContextMenuSeparator />
						</>
					)}

					<ContextMenuItem
						onClick={() => onDelete(elementId)}
						className="text-destructive focus:text-destructive"
					>
						<Trash2 className="mr-2 h-4 w-4" />
						Delete
					</ContextMenuItem>
				</ContextMenuContent>
			</ContextMenu>

			{/* Render children if expanded */}
			{isContainer && isExpanded && (
				<div>
					{(element as LayoutContainer).children.map((child, i) => {
						const childId = getChildId(child, elementId, i);
						return (
							<TreeItem
								key={childId}
								element={child}
								elementId={childId}
								parentId={elementId}
								index={i}
								depth={depth + 1}
								selectedId={selectedId}
								expandedIds={expandedIds}
								onSelect={onSelect}
								onToggleExpand={onToggleExpand}
								onAddComponent={onAddComponent}
								onMoveComponent={onMoveComponent}
								onDelete={onDelete}
								onDuplicate={onDuplicate}
							/>
						);
					})}

					{/* Empty container message */}
					{(element as LayoutContainer).children.length === 0 && (
						<div
							className="text-xs text-muted-foreground italic py-2"
							style={{
								paddingLeft: `${(depth + 1) * 16 + 24}px`,
							}}
						>
							Empty - click + to add
						</div>
					)}
				</div>
			)}
		</div>
	);
}

// ============================================================================
// Main StructureTree Component
// ============================================================================

export function StructureTree({
	pages,
	selectedPageId,
	selectedComponentId,
	onSelectPage: _onSelectPage,
	onSelectComponent,
	onAddComponent,
	onMoveComponent,
	onDeleteComponent,
	onDuplicateComponent,
	className,
}: StructureTreeProps) {
	// onSelectPage is reserved for future page-switching in the tree
	void _onSelectPage;
	// Track which nodes are expanded
	const [expandedIds, setExpandedIds] = useState<Set<string>>(
		new Set(["root"]),
	);

	const currentPage = pages.find((p) => p.id === selectedPageId);

	const handleToggleExpand = useCallback((id: string) => {
		setExpandedIds((prev) => {
			const next = new Set(prev);
			if (next.has(id)) {
				next.delete(id);
			} else {
				next.add(id);
			}
			return next;
		});
	}, []);

	const handleSelect = useCallback(
		(id: string) => {
			onSelectComponent(id);
		},
		[onSelectComponent],
	);

	if (!currentPage) {
		return (
			<div
				className={cn(
					"p-4 text-center text-muted-foreground",
					className,
				)}
			>
				No page selected
			</div>
		);
	}

	return (
		<div className={cn("overflow-auto", className)}>
			{/* Page header */}
			<div
				className={cn(
					"flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors border-b",
					selectedComponentId === "root"
						? "bg-primary text-primary-foreground"
						: "hover:bg-muted",
				)}
				onClick={() => onSelectComponent("root")}
			>
				<FileText className="h-4 w-4 shrink-0" />
				<span className="text-sm font-medium truncate">
					{currentPage.title}
				</span>
				<span
					className={cn(
						"text-xs ml-auto truncate",
						selectedComponentId === "root"
							? "text-primary-foreground/70"
							: "text-muted-foreground",
					)}
				>
					{currentPage.path}
				</span>
			</div>

			{/* Component tree */}
			<div>
				<TreeItem
					element={currentPage.layout}
					elementId="root"
					parentId=""
					index={0}
					depth={0}
					selectedId={selectedComponentId}
					expandedIds={expandedIds}
					onSelect={handleSelect}
					onToggleExpand={handleToggleExpand}
					onAddComponent={onAddComponent}
					onMoveComponent={onMoveComponent}
					onDelete={onDeleteComponent}
					onDuplicate={onDuplicateComponent}
				/>
			</div>
		</div>
	);
}

export default StructureTree;
