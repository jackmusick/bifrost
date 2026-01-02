/**
 * Editor Shell Component
 *
 * Visual editor interface for the App Builder with a 3-panel layout:
 * - Left Panel: Page tree navigator + component palette
 * - Center Panel: Drag-and-drop canvas
 * - Right Panel: Property editor
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import {
	ChevronLeft,
	ChevronRight,
	Eye,
	FileText,
	Navigation,
	Redo2,
	Save,
	Send,
	Undo2,
	Variable,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
	TooltipProvider,
} from "@/components/ui/tooltip";
import type {
	ApplicationDefinition,
	PageDefinition,
	ComponentType,
	LayoutType,
	LayoutContainer,
	AppComponent,
	NavigationConfig,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
import { EditorCanvas, type DragData, type DropTarget } from "./EditorCanvas";
import { PropertyEditor } from "./PropertyEditor";
import { PageTree } from "./PageTree";
import { ComponentPalette, type PaletteDragData } from "./ComponentPalette";
import { NavigationEditor } from "./NavigationEditor";
import { VariablePreview } from "./VariablePreview";

export interface EditorShellProps {
	/** The application definition being edited */
	definition: ApplicationDefinition;
	/** Callback when the definition changes */
	onDefinitionChange: (definition: ApplicationDefinition) => void;
	/** Currently selected component ID */
	selectedComponentId: string | null;
	/** Callback when a component is selected */
	onSelectComponent: (id: string | null) => void;
	/** Save callback */
	onSave: () => void;
	/** Publish callback */
	onPublish: () => void;
	/** Preview callback */
	onPreview: () => void;
}

/**
 * Generate a unique component ID
 */
function generateComponentId(): string {
	return `comp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Generate a unique page ID
 */
function generatePageId(): string {
	return `page_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Create a default component with the given type
 */
function createDefaultComponent(
	type: ComponentType | LayoutType,
): AppComponent | LayoutContainer {
	const id = generateComponentId();

	// Check if it's a layout type
	if (type === "row" || type === "column" || type === "grid") {
		return {
			type,
			children: [],
			gap: 16,
			padding: 16,
		} as LayoutContainer;
	}

	// Component types
	switch (type) {
		case "heading":
			return {
				id,
				type: "heading",
				props: {
					text: "New Heading",
					level: 2,
				},
			};
		case "text":
			return {
				id,
				type: "text",
				props: {
					text: "Enter your text here...",
				},
			};
		case "html":
			return {
				id,
				type: "html",
				props: {
					content:
						'<div className="p-4 bg-muted rounded-lg">\n  <p>Custom HTML or JSX content</p>\n</div>',
				},
			};
		case "button":
			return {
				id,
				type: "button",
				props: {
					label: "Click Me",
					actionType: "navigate",
					variant: "default",
				},
			};
		case "card":
			return {
				id,
				type: "card",
				props: {
					title: "Card Title",
					description: "Card description",
				},
			};
		case "stat-card":
			return {
				id,
				type: "stat-card",
				props: {
					title: "Metric",
					value: "0",
				},
			};
		case "image":
			return {
				id,
				type: "image",
				props: {
					src: "https://via.placeholder.com/400x200",
					alt: "Placeholder image",
				},
			};
		case "divider":
			return {
				id,
				type: "divider",
				props: {
					orientation: "horizontal",
				},
			};
		case "spacer":
			return {
				id,
				type: "spacer",
				props: {
					size: 24,
				},
			};
		case "badge":
			return {
				id,
				type: "badge",
				props: {
					text: "Badge",
					variant: "default",
				},
			};
		case "progress":
			return {
				id,
				type: "progress",
				props: {
					value: 50,
					showLabel: true,
				},
			};
		case "data-table":
			return {
				id,
				type: "data-table",
				props: {
					dataSource: "tableName",
					columns: [
						{ key: "id", header: "ID" },
						{ key: "name", header: "Name" },
					],
					paginated: true,
					pageSize: 10,
				},
			};
		case "tabs":
			return {
				id,
				type: "tabs",
				props: {
					items: [
						{
							id: "tab1",
							label: "Tab 1",
							content: { type: "column", children: [], gap: 8 },
						},
						{
							id: "tab2",
							label: "Tab 2",
							content: { type: "column", children: [], gap: 8 },
						},
					],
					orientation: "horizontal",
				},
			};
		case "text-input":
			return {
				id,
				type: "text-input",
				props: {
					fieldId: `field_${id.slice(-6)}`,
					label: "Label",
					placeholder: "Enter text...",
				},
			};
		case "number-input":
			return {
				id,
				type: "number-input",
				props: {
					fieldId: `field_${id.slice(-6)}`,
					label: "Number",
					placeholder: "0",
				},
			};
		case "select":
			return {
				id,
				type: "select",
				props: {
					fieldId: `field_${id.slice(-6)}`,
					label: "Select",
					placeholder: "Select an option",
					options: [
						{ value: "option1", label: "Option 1" },
						{ value: "option2", label: "Option 2" },
					],
				},
			};
		case "checkbox":
			return {
				id,
				type: "checkbox",
				props: {
					fieldId: `field_${id.slice(-6)}`,
					label: "Checkbox label",
				},
			};
		case "file-viewer":
			return {
				id,
				type: "file-viewer",
				props: {
					src: "https://example.com/file.pdf",
					displayMode: "inline",
				},
			};
		case "modal":
			return {
				id,
				type: "modal",
				props: {
					title: "Modal Title",
					description: "Modal description",
					triggerLabel: "Open Modal",
					content: {
						type: "column",
						children: [],
						gap: 16,
						padding: 16,
					},
					showCloseButton: true,
				},
			};
		default:
			// Handle unknown component types - should not happen
			return {
				id,
				type: "text",
				props: {
					text: `Unknown component type: ${type}`,
				},
			};
	}
}

/**
 * Insert an element into the layout tree
 */
function insertIntoTree(
	layout: LayoutContainer,
	newElement: LayoutContainer | AppComponent,
	targetId: string,
	position: "before" | "after" | "inside",
	parentId?: string,
): LayoutContainer {
	const currentId = parentId || "root";

	// If target is this container itself, add to its children
	if (targetId === currentId) {
		if (position === "before") {
			return {
				...layout,
				children: [newElement, ...layout.children],
			};
		}
		// "after" or "inside" - add to end
		return {
			...layout,
			children: [...layout.children, newElement],
		};
	}

	// Clone layout and process children
	const newChildren: (LayoutContainer | AppComponent)[] = [];

	for (let i = 0; i < layout.children.length; i++) {
		const child = layout.children[i];
		const childId = isLayoutContainer(child)
			? `${currentId}-layout-${i}`
			: child.id;

		if (childId === targetId) {
			if (position === "before") {
				newChildren.push(newElement);
				newChildren.push(child);
			} else if (position === "after") {
				newChildren.push(child);
				newChildren.push(newElement);
			} else if (position === "inside" && isLayoutContainer(child)) {
				newChildren.push({
					...child,
					children: [...child.children, newElement],
				});
			} else {
				// Can't add inside non-container, add after instead
				newChildren.push(child);
				newChildren.push(newElement);
			}
		} else if (isLayoutContainer(child)) {
			// Recursively process container children
			newChildren.push(
				insertIntoTree(child, newElement, targetId, position, childId),
			);
		} else {
			newChildren.push(child);
		}
	}

	return {
		...layout,
		children: newChildren,
	};
}

/**
 * Remove an element from the layout tree
 */
function removeFromTree(
	layout: LayoutContainer,
	targetId: string,
	parentId?: string,
): { layout: LayoutContainer; removed: LayoutContainer | AppComponent | null } {
	let removed: LayoutContainer | AppComponent | null = null;

	const newChildren: (LayoutContainer | AppComponent)[] = [];

	for (let i = 0; i < layout.children.length; i++) {
		const child = layout.children[i];
		const childId = isLayoutContainer(child)
			? `${parentId || "root"}-layout-${i}`
			: child.id;

		if (childId === targetId) {
			removed = child;
			// Don't add to newChildren - this removes it
		} else if (isLayoutContainer(child)) {
			const result = removeFromTree(child, targetId, childId);
			newChildren.push(result.layout);
			if (result.removed) removed = result.removed;
		} else {
			newChildren.push(child);
		}
	}

	return {
		layout: { ...layout, children: newChildren },
		removed,
	};
}

/**
 * Find an element in the layout tree by ID and return its reference along with
 * info about its location. This helps us track elements even after indices change.
 */
function findElementInTree(
	layout: LayoutContainer,
	targetId: string,
	parentId?: string,
): {
	element: LayoutContainer | AppComponent;
	parentPath: string;
	index: number;
} | null {
	const currentId = parentId || "root";

	for (let i = 0; i < layout.children.length; i++) {
		const child = layout.children[i];
		const childId = isLayoutContainer(child)
			? `${currentId}-layout-${i}`
			: child.id;

		if (childId === targetId) {
			return { element: child, parentPath: currentId, index: i };
		}

		if (isLayoutContainer(child)) {
			const result = findElementInTree(child, targetId, childId);
			if (result) return result;
		}
	}

	return null;
}

/**
 * Move an element within the layout tree using element references instead of IDs.
 * This avoids the issue where removing an element shifts indices
 * and invalidates index-based layout container IDs.
 */
function moveInTree(
	layout: LayoutContainer,
	sourceId: string,
	targetId: string,
	position: "before" | "after" | "inside",
): { layout: LayoutContainer; moved: boolean } {
	// Don't move an element onto itself
	if (sourceId === targetId) {
		return { layout, moved: false };
	}

	// Find the actual source and target elements BEFORE any modifications
	const sourceInfo = findElementInTree(layout, sourceId);
	const targetInfo = findElementInTree(layout, targetId);

	if (!sourceInfo || !targetInfo) {
		return { layout, moved: false };
	}

	// Store references to the actual target element (not by ID)
	// We'll use this to find it again after removal
	const targetElement = targetInfo.element;

	// First remove the source
	const removeResult = removeFromTree(layout, sourceId);
	if (!removeResult.removed) {
		return { layout, moved: false };
	}

	const elementToMove = removeResult.removed;
	const layoutAfterRemoval = removeResult.layout;

	// Now find where the target element is in the modified tree
	// We do this by searching for the same object reference
	const newTargetId = findElementId(layoutAfterRemoval, targetElement);

	if (!newTargetId) {
		// Target was a child of source (which we removed), so fail gracefully
		return { layout, moved: false };
	}

	// Insert at the target position using the updated ID
	const insertResult = insertIntoTree(
		layoutAfterRemoval,
		elementToMove,
		newTargetId,
		position,
	);

	return { layout: insertResult, moved: true };
}

/**
 * Find an element's ID by its object reference in the tree.
 * This is used after tree modifications when index-based IDs may have changed.
 */
function findElementId(
	layout: LayoutContainer,
	targetElement: LayoutContainer | AppComponent,
	parentId?: string,
): string | null {
	const currentId = parentId || "root";

	for (let i = 0; i < layout.children.length; i++) {
		const child = layout.children[i];
		const childId = isLayoutContainer(child)
			? `${currentId}-layout-${i}`
			: child.id;

		// Compare by reference for layouts, by id for components
		if (child === targetElement) {
			return childId;
		}
		if (!isLayoutContainer(child) && !isLayoutContainer(targetElement)) {
			if (
				(child as AppComponent).id ===
				(targetElement as AppComponent).id
			) {
				return childId;
			}
		}

		if (isLayoutContainer(child)) {
			const result = findElementId(child, targetElement, childId);
			if (result) return result;
		}
	}

	return null;
}

/**
 * Update an element in the layout tree
 */
function updateInTree(
	layout: LayoutContainer,
	targetId: string,
	updates: Partial<AppComponent | LayoutContainer>,
	parentId?: string,
): LayoutContainer {
	const newChildren: (LayoutContainer | AppComponent)[] = [];

	for (let i = 0; i < layout.children.length; i++) {
		const child = layout.children[i];
		const childId = isLayoutContainer(child)
			? `${parentId || "root"}-layout-${i}`
			: child.id;

		if (childId === targetId) {
			// Apply updates to this element
			newChildren.push({ ...child, ...updates } as
				| LayoutContainer
				| AppComponent);
		} else if (isLayoutContainer(child)) {
			// Recursively update container children
			newChildren.push(updateInTree(child, targetId, updates, childId));
		} else {
			newChildren.push(child);
		}
	}

	return { ...layout, children: newChildren };
}

/**
 * Editor Shell Component
 *
 * The main visual editor interface for building App Builder applications.
 * Features a 3-panel layout with page tree, canvas, and property editor.
 */
export function EditorShell({
	definition,
	onDefinitionChange,
	selectedComponentId,
	onSelectComponent,
	onSave,
	onPublish,
	onPreview,
}: EditorShellProps) {
	// Panel collapse state
	const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
	const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
	const [showVariablePreview, setShowVariablePreview] = useState(false);

	// Current page being edited
	const [currentPageId, setCurrentPageId] = useState<string>(
		definition.pages[0]?.id || "",
	);

	// Left panel tab
	const [leftPanelTab, setLeftPanelTab] = useState<
		"pages" | "components" | "navigation"
	>("pages");

	// Get current page
	const currentPage = useMemo(
		() => definition.pages.find((p) => p.id === currentPageId),
		[definition.pages, currentPageId],
	);

	// Find selected component in the tree
	const selectedComponent = useMemo(() => {
		if (!selectedComponentId || !currentPage) return null;

		// Special case for root layout
		if (selectedComponentId === "root") {
			return currentPage.layout;
		}

		function findComponent(
			element: LayoutContainer | AppComponent,
			parentId?: string,
			index?: number,
		): AppComponent | LayoutContainer | null {
			if (isLayoutContainer(element)) {
				// Check if this layout matches
				const layoutId = parentId
					? `${parentId}-layout-${index}`
					: "root";
				if (layoutId === selectedComponentId) {
					return element;
				}

				// Search children
				for (let i = 0; i < element.children.length; i++) {
					const child = element.children[i];
					const found = findComponent(child, layoutId, i);
					if (found) return found;
				}
			} else {
				// It's a component
				if (element.id === selectedComponentId) {
					return element;
				}
			}
			return null;
		}

		return findComponent(currentPage.layout);
	}, [selectedComponentId, currentPage]);

	// Update the definition with a new page layout
	const updatePageLayout = useCallback(
		(pageId: string, newLayout: LayoutContainer) => {
			const updatedPages = definition.pages.map((p) =>
				p.id === pageId ? { ...p, layout: newLayout } : p,
			);
			onDefinitionChange({ ...definition, pages: updatedPages });
		},
		[definition, onDefinitionChange],
	);

	// Handle drop from palette or canvas reorder
	const handleCanvasDrop = useCallback(
		(source: DragData, target: DropTarget) => {
			if (!currentPage) return;

			// Check if this is a new component from palette
			if (
				source.type === "palette" ||
				(source as unknown as PaletteDragData).type === "new-component"
			) {
				const paletteData = source as unknown as PaletteDragData;
				const componentType =
					paletteData.componentType || source.componentType;
				if (!componentType) return;

				const elementToInsert = createDefaultComponent(componentType);

				// Insert at target position
				const updatedLayout = insertIntoTree(
					currentPage.layout,
					elementToInsert,
					target.id,
					target.position,
				);

				updatePageLayout(currentPage.id, updatedLayout);

				// Select the newly added component
				if (!isLayoutContainer(elementToInsert)) {
					onSelectComponent(elementToInsert.id);
				}
			} else {
				// Moving existing component - use moveInTree to handle index-based IDs correctly
				const moveResult = moveInTree(
					currentPage.layout,
					source.id,
					target.id,
					target.position,
				);

				if (moveResult.moved) {
					updatePageLayout(currentPage.id, moveResult.layout);
				}
				// If not moved (same position, or invalid move), do nothing - element stays in place
			}
		},
		[currentPage, updatePageLayout, onSelectComponent],
	);

	// Handle component deletion
	const handleDelete = useCallback(
		(componentId: string) => {
			if (!currentPage) return;

			const { layout } = removeFromTree(currentPage.layout, componentId);
			updatePageLayout(currentPage.id, layout);

			// Clear selection if deleted component was selected
			if (selectedComponentId === componentId) {
				onSelectComponent(null);
			}
		},
		[currentPage, updatePageLayout, selectedComponentId, onSelectComponent],
	);

	// Keyboard shortcuts
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			// Don't trigger if user is typing in an input
			const target = e.target as HTMLElement;
			if (
				target.tagName === "INPUT" ||
				target.tagName === "TEXTAREA" ||
				target.isContentEditable
			) {
				return;
			}

			// Delete/Backspace to delete selected component
			if (
				(e.key === "Delete" || e.key === "Backspace") &&
				selectedComponentId &&
				selectedComponentId !== "root"
			) {
				e.preventDefault();
				handleDelete(selectedComponentId);
			}

			// Escape to deselect
			if (e.key === "Escape" && selectedComponentId) {
				e.preventDefault();
				onSelectComponent(null);
			}
		};

		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [selectedComponentId, handleDelete, onSelectComponent]);

	// Handle property changes from PropertyEditor
	const handlePropertyChange = useCallback(
		(updates: Partial<AppComponent | LayoutContainer>) => {
			if (!selectedComponentId || !currentPage) return;

			// Handle root layout updates
			if (selectedComponentId === "root") {
				const updatedLayout = {
					...currentPage.layout,
					...updates,
				} as LayoutContainer;
				updatePageLayout(currentPage.id, updatedLayout);
				return;
			}

			const updatedLayout = updateInTree(
				currentPage.layout,
				selectedComponentId,
				updates,
			);
			updatePageLayout(currentPage.id, updatedLayout);
		},
		[selectedComponentId, currentPage, updatePageLayout],
	);

	// Handle component deletion from PropertyEditor
	const handlePropertyEditorDelete = useCallback(() => {
		if (selectedComponentId && selectedComponentId !== "root") {
			handleDelete(selectedComponentId);
		}
	}, [selectedComponentId, handleDelete]);

	// Handle page property changes from PropertyEditor
	const handlePageChange = useCallback(
		(updates: Partial<PageDefinition>) => {
			if (!currentPage) return;

			const updatedPages = definition.pages.map((p) =>
				p.id === currentPage.id ? { ...p, ...updates } : p,
			);
			onDefinitionChange({ ...definition, pages: updatedPages });
		},
		[currentPage, definition, onDefinitionChange],
	);

	// Page management handlers
	const handleAddPage = useCallback(() => {
		const newPageId = generatePageId();
		const pageNumber = definition.pages.length + 1;
		const newPage: PageDefinition = {
			id: newPageId,
			title: `Page ${pageNumber}`,
			path: `/page-${pageNumber}`,
			layout: {
				type: "column",
				children: [],
				gap: 16,
				padding: 16,
			},
		};

		onDefinitionChange({
			...definition,
			pages: [...definition.pages, newPage],
		});

		// Select the new page
		setCurrentPageId(newPageId);
	}, [definition, onDefinitionChange]);

	const handleDeletePage = useCallback(
		(pageId: string) => {
			// Don't allow deleting the last page
			if (definition.pages.length <= 1) return;

			const updatedPages = definition.pages.filter(
				(p) => p.id !== pageId,
			);
			onDefinitionChange({ ...definition, pages: updatedPages });

			// If we deleted the current page, select the first remaining page
			if (currentPageId === pageId && updatedPages.length > 0) {
				setCurrentPageId(updatedPages[0].id);
			}
		},
		[definition, onDefinitionChange, currentPageId],
	);

	const handleReorderPages = useCallback(
		(newPages: PageDefinition[]) => {
			onDefinitionChange({ ...definition, pages: newPages });
		},
		[definition, onDefinitionChange],
	);

	// Handle navigation config changes
	const handleNavigationChange = useCallback(
		(navigation: NavigationConfig) => {
			onDefinitionChange({ ...definition, navigation });
		},
		[definition, onDefinitionChange],
	);

	return (
		<TooltipProvider>
			<div className="flex h-full flex-col bg-muted/30">
				{/* Toolbar */}
				<div className="flex h-12 shrink-0 items-center justify-between border-b bg-background px-4">
					{/* Left section - App info */}
					<div className="flex items-center gap-3">
						<h1 className="text-sm font-semibold">
							{definition.name}
						</h1>
						<span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
							v{definition.version}
						</span>
					</div>

					{/* Center section - Undo/Redo + Variable Preview */}
					<div className="flex items-center gap-1">
						<Tooltip>
							<TooltipTrigger asChild>
								<Button variant="ghost" size="icon-sm" disabled>
									<Undo2 className="h-4 w-4" />
								</Button>
							</TooltipTrigger>
							<TooltipContent>Undo</TooltipContent>
						</Tooltip>
						<Tooltip>
							<TooltipTrigger asChild>
								<Button variant="ghost" size="icon-sm" disabled>
									<Redo2 className="h-4 w-4" />
								</Button>
							</TooltipTrigger>
							<TooltipContent>Redo</TooltipContent>
						</Tooltip>
						<div className="mx-2 h-4 w-px bg-border" />
						<Tooltip>
							<TooltipTrigger asChild>
								<Button
									variant={
										showVariablePreview
											? "secondary"
											: "ghost"
									}
									size="icon-sm"
									onClick={() =>
										setShowVariablePreview(
											!showVariablePreview,
										)
									}
								>
									<Variable className="h-4 w-4" />
								</Button>
							</TooltipTrigger>
							<TooltipContent>
								{showVariablePreview
									? "Hide variables"
									: "Show available variables"}
							</TooltipContent>
						</Tooltip>
					</div>

					{/* Right section - Actions */}
					<div className="flex items-center gap-2">
						<Button variant="outline" size="sm" onClick={onPreview}>
							<Eye className="mr-1.5 h-4 w-4" />
							Preview
						</Button>
						<Button variant="outline" size="sm" onClick={onSave}>
							<Save className="mr-1.5 h-4 w-4" />
							Save Draft
						</Button>
						<Button size="sm" onClick={onPublish}>
							<Send className="mr-1.5 h-4 w-4" />
							Publish
						</Button>
					</div>
				</div>

				{/* Main content area - 3 panel layout */}
				<div className="flex flex-1 overflow-hidden">
					{/* Left Panel - Page tree + Component palette */}
					<div
						className={cn(
							"flex shrink-0 flex-col border-r bg-background transition-all duration-200",
							isLeftPanelCollapsed ? "w-12" : "w-64",
						)}
					>
						{/* Collapse toggle */}
						<div className="flex h-10 items-center justify-end border-b px-2">
							<Button
								variant="ghost"
								size="icon-sm"
								onClick={() =>
									setIsLeftPanelCollapsed(
										!isLeftPanelCollapsed,
									)
								}
							>
								{isLeftPanelCollapsed ? (
									<ChevronRight className="h-4 w-4" />
								) : (
									<ChevronLeft className="h-4 w-4" />
								)}
							</Button>
						</div>

						{/* Panel content */}
						{!isLeftPanelCollapsed && (
							<Tabs
								value={leftPanelTab}
								onValueChange={(v) =>
									setLeftPanelTab(
										v as
											| "pages"
											| "components"
											| "navigation",
									)
								}
								className="flex flex-1 flex-col overflow-hidden"
							>
								<TabsList className="mx-2 mt-2 grid w-auto grid-cols-3">
									<TabsTrigger
										value="pages"
										className="text-xs"
									>
										<FileText className="mr-1 h-3 w-3" />
										Pages
									</TabsTrigger>
									<TabsTrigger
										value="components"
										className="text-xs"
									>
										Components
									</TabsTrigger>
									<TabsTrigger
										value="navigation"
										className="text-xs"
									>
										<Navigation className="mr-1 h-3 w-3" />
										Nav
									</TabsTrigger>
								</TabsList>

								<TabsContent
									value="pages"
									className="flex-1 overflow-hidden mt-0"
								>
									<PageTree
										pages={definition.pages}
										selectedPageId={currentPageId}
										onSelectPage={setCurrentPageId}
										onAddPage={handleAddPage}
										onDeletePage={handleDeletePage}
										onReorderPages={handleReorderPages}
										className="h-full"
									/>
								</TabsContent>

								<TabsContent
									value="components"
									className="flex-1 overflow-hidden mt-0"
								>
									<ComponentPalette className="h-full" />
								</TabsContent>

								<TabsContent
									value="navigation"
									className="flex-1 overflow-hidden mt-0"
								>
									<NavigationEditor
										app={definition}
										onNavigationChange={
											handleNavigationChange
										}
										className="h-full"
									/>
								</TabsContent>
							</Tabs>
						)}
					</div>

					{/* Center Panel - Canvas */}
					<div className="flex flex-1 flex-col overflow-hidden">
						{currentPage ? (
							<EditorCanvas
								page={currentPage}
								selectedId={selectedComponentId}
								onSelect={onSelectComponent}
								onDrop={handleCanvasDrop}
								onDelete={handleDelete}
							/>
						) : (
							<div className="flex h-full items-center justify-center">
								<div className="text-center text-muted-foreground">
									<FileText className="mx-auto mb-2 h-8 w-8 opacity-50" />
									<div className="text-sm">
										No page selected
									</div>
								</div>
							</div>
						)}
					</div>

					{/* Right Panel - Property editor */}
					<div
						className={cn(
							"flex shrink-0 flex-col border-l bg-background transition-all duration-200",
							isRightPanelCollapsed ? "w-12" : "w-80",
						)}
					>
						{/* Collapse toggle */}
						<div className="flex h-10 items-center justify-start border-b px-2">
							<Button
								variant="ghost"
								size="icon-sm"
								onClick={() =>
									setIsRightPanelCollapsed(
										!isRightPanelCollapsed,
									)
								}
							>
								{isRightPanelCollapsed ? (
									<ChevronLeft className="h-4 w-4" />
								) : (
									<ChevronRight className="h-4 w-4" />
								)}
							</Button>
							{!isRightPanelCollapsed && (
								<span className="ml-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
									Properties
								</span>
							)}
						</div>

						{/* Panel content */}
						{!isRightPanelCollapsed && (
							<PropertyEditor
								component={selectedComponent}
								onChange={handlePropertyChange}
								onDelete={
									selectedComponentId &&
									selectedComponentId !== "root"
										? handlePropertyEditorDelete
										: undefined
								}
								page={
									selectedComponentId === "root"
										? currentPage
										: undefined
								}
								onPageChange={
									selectedComponentId === "root"
										? handlePageChange
										: undefined
								}
								className="flex-1 overflow-hidden"
							/>
						)}
					</div>

					{/* Variable Preview Panel (overlay) */}
					{showVariablePreview && (
						<div className="absolute right-80 top-12 bottom-0 w-72 border-l bg-background shadow-lg z-10">
							<VariablePreview
								page={currentPage}
								className="h-full"
							/>
						</div>
					)}
				</div>
			</div>
		</TooltipProvider>
	);
}

export default EditorShell;
