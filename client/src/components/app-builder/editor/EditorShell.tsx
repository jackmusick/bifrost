/**
 * Editor Shell Component
 *
 * Visual editor interface for the App Builder with a 3-panel layout:
 * - Left Panel: Page tree navigator + Structure tree
 * - Center Panel: Live preview (click to select)
 * - Right Panel: Property editor
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import {
	ChevronLeft,
	ChevronRight,
	FileText,
	Layers,
	Navigation,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import {
	createDefaultComponent,
	insertIntoTree,
	removeFromTree,
	moveInTree,
	updateInTree,
	generatePageId,
	findElementInTree,
} from "@/lib/app-builder-tree";
import { AppRenderer } from "../AppRenderer";
import { PropertyEditor } from "./PropertyEditor";
import { PageTree } from "./PageTree";
import { StructureTree } from "./StructureTree";
import { NavigationEditor } from "./NavigationEditor";
import { VariablePreview } from "./VariablePreview";

/**
 * Component data for save operations
 */
export interface ComponentSaveData {
	componentId: string;
	type: string;
	props: Record<string, unknown>;
	parentId: string | null;
	order: number;
}

export interface EditorShellProps {
	/** The application definition being edited */
	definition: ApplicationDefinition;
	/** Callback when the definition changes */
	onDefinitionChange: (definition: ApplicationDefinition) => void;
	/** Currently selected component ID */
	selectedComponentId: string | null;
	/** Callback when a component is selected */
	onSelectComponent: (id: string | null) => void;
	/** Current page ID being edited */
	pageId?: string;
	/** Callback when a component is created (for real-time saves) */
	onComponentCreate?: (data: ComponentSaveData) => void;
	/** Callback when a component's props are updated (for real-time saves) */
	onComponentUpdate?: (
		componentId: string,
		props: Record<string, unknown>,
	) => void;
	/** Callback when a component is deleted (for real-time saves) */
	onComponentDelete?: (componentId: string) => void;
	/** Callback when a component is moved (for real-time saves) */
	onComponentMove?: (
		componentId: string,
		newParentId: string | null,
		newOrder: number,
	) => void;
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
	pageId: externalPageId,
	onComponentCreate,
	onComponentUpdate,
	onComponentDelete,
	onComponentMove,
}: EditorShellProps) {
	// Panel collapse state
	const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);
	const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);

	// Right panel tab state
	const [rightPanelTab, setRightPanelTab] = useState<
		"properties" | "variables"
	>("properties");

	// Current page being edited - use external pageId if provided, otherwise first page
	// Controlled/uncontrolled: prefer external pageId when provided
	const [internalPageId, setInternalPageId] = useState<string>(
		externalPageId || definition.pages[0]?.id || "",
	);

	// Use external pageId if provided, otherwise use internal state
	const currentPageId = externalPageId || internalPageId;

	// Handler for setting current page - works in both controlled and uncontrolled modes
	const handleSetCurrentPageId = useCallback(
		(pageId: string) => {
			if (!externalPageId) {
				setInternalPageId(pageId);
			}
			// In controlled mode, the parent handles page changes
		},
		[externalPageId],
	);

	// Left panel tab - now "structure" (tree view), "pages", or "navigation"
	const [leftPanelTab, setLeftPanelTab] = useState<
		"structure" | "pages" | "navigation"
	>("structure");

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

	// Handle adding a new component from the StructureTree
	const handleAddComponent = useCallback(
		(
			parentId: string,
			componentType: ComponentType | LayoutType,
			position: "inside" | "before" | "after",
		) => {
			if (!currentPage) return;

			const elementToInsert = createDefaultComponent(componentType);

			// Map position to insertIntoTree format
			const insertPosition = position === "inside" ? "inside" : position;

			const updatedLayout = insertIntoTree(
				currentPage.layout,
				elementToInsert,
				parentId,
				insertPosition,
			);

			updatePageLayout(currentPage.id, updatedLayout);

			// Select the newly added component (components have IDs, layouts don't need selection)
			if (!isLayoutContainer(elementToInsert)) {
				const componentId = (elementToInsert as AppComponent).id;
				onSelectComponent(componentId);

				// Call granular create callback if provided
				if (onComponentCreate) {
					// Find the newly inserted element to get its actual parent and order
					const insertedInfo = findElementInTree(
						updatedLayout,
						componentId,
					);
					if (insertedInfo) {
						onComponentCreate({
							componentId,
							type: (elementToInsert as AppComponent).type,
							props:
								(elementToInsert as AppComponent).props || {},
							parentId:
								insertedInfo.parentPath === "root"
									? null
									: insertedInfo.parentPath,
							order: insertedInfo.index,
						});
					}
				}
			}
		},
		[currentPage, updatePageLayout, onSelectComponent, onComponentCreate],
	);

	// Handle moving a component within the StructureTree
	const handleMoveComponent = useCallback(
		(
			sourceId: string,
			targetId: string,
			position: "before" | "after" | "inside",
		) => {
			if (!currentPage) return;

			const moveResult = moveInTree(
				currentPage.layout,
				sourceId,
				targetId,
				position,
			);

			if (moveResult.moved) {
				updatePageLayout(currentPage.id, moveResult.layout);

				// Call granular move callback if provided
				if (onComponentMove) {
					// Find the moved element to get its new parent and order
					const movedInfo = findElementInTree(
						moveResult.layout,
						sourceId,
					);
					if (movedInfo) {
						onComponentMove(
							sourceId,
							movedInfo.parentPath === "root"
								? null
								: movedInfo.parentPath,
							movedInfo.index,
						);
					}
				}
			}
		},
		[currentPage, updatePageLayout, onComponentMove],
	);

	// Handle duplicating a component
	const handleDuplicateComponent = useCallback(
		(componentId: string) => {
			if (!currentPage) return;

			// Find the element to duplicate
			const found = findElementInTree(currentPage.layout, componentId);
			if (!found) return;

			// Deep clone the element (and regenerate IDs)
			const cloned = JSON.parse(JSON.stringify(found.element)) as
				| LayoutContainer
				| AppComponent;

			// Regenerate IDs for the cloned element and all children
			function regenerateIds(el: LayoutContainer | AppComponent): void {
				if (!isLayoutContainer(el) && el.id) {
					(el as AppComponent).id =
						`comp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
				}
				if (isLayoutContainer(el)) {
					for (const child of el.children) {
						regenerateIds(child);
					}
				}
			}
			regenerateIds(cloned);

			// Insert after the original
			const updatedLayout = insertIntoTree(
				currentPage.layout,
				cloned,
				componentId,
				"after",
			);

			updatePageLayout(currentPage.id, updatedLayout);

			// Select the new component
			if (!isLayoutContainer(cloned)) {
				const newComponentId = (cloned as AppComponent).id;
				onSelectComponent(newComponentId);

				// Call granular create callback if provided
				if (onComponentCreate) {
					const insertedInfo = findElementInTree(
						updatedLayout,
						newComponentId,
					);
					if (insertedInfo) {
						onComponentCreate({
							componentId: newComponentId,
							type: (cloned as AppComponent).type,
							props: (cloned as AppComponent).props || {},
							parentId:
								insertedInfo.parentPath === "root"
									? null
									: insertedInfo.parentPath,
							order: insertedInfo.index,
						});
					}
				}
			}
		},
		[currentPage, updatePageLayout, onSelectComponent, onComponentCreate],
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

			// Call granular delete callback if provided
			onComponentDelete?.(componentId);
		},
		[
			currentPage,
			updatePageLayout,
			selectedComponentId,
			onSelectComponent,
			onComponentDelete,
		],
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

			// Call granular update callback if provided
			// Only for non-layout components (layout containers don't have a component_id)
			if (onComponentUpdate && "props" in updates && updates.props) {
				onComponentUpdate(selectedComponentId, updates.props);
			}
		},
		[selectedComponentId, currentPage, updatePageLayout, onComponentUpdate],
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
		handleSetCurrentPageId(newPageId);
	}, [definition, onDefinitionChange, handleSetCurrentPageId]);

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
				handleSetCurrentPageId(updatedPages[0].id);
			}
		},
		[definition, onDefinitionChange, currentPageId, handleSetCurrentPageId],
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
		<div className="flex h-full flex-col">
			{/* Main content area - 3 panel layout */}
			<div className="flex flex-1 overflow-hidden">
				{/* Left Panel - Page tree + Component palette */}
				<div
					className={cn(
						"flex shrink-0 flex-col border-r bg-background transition-all duration-200",
						isLeftPanelCollapsed ? "w-10" : "w-64",
					)}
				>
					{isLeftPanelCollapsed ? (
						/* Collapsed state - just expand button */
						<div className="flex h-8 items-center justify-center border-b">
							<Button
								variant="ghost"
								size="icon-sm"
								className="h-8 w-8 rounded-none"
								onClick={() => setIsLeftPanelCollapsed(false)}
							>
								<ChevronRight className="h-4 w-4" />
							</Button>
						</div>
					) : (
						/* Expanded state - tabs with collapse button */
						<Tabs
							value={leftPanelTab}
							onValueChange={(v) =>
								setLeftPanelTab(
									v as "structure" | "pages" | "navigation",
								)
							}
							className="flex flex-1 flex-col overflow-hidden"
						>
							<div className="flex items-center border-b h-8">
								<TabsList className="flex-1 grid grid-cols-3 rounded-none bg-transparent h-8 p-0">
									<TabsTrigger
										value="structure"
										className="rounded-none data-[state=active]:shadow-none data-[state=active]:bg-muted h-8"
										title="Structure"
									>
										<Layers className="h-4 w-4" />
									</TabsTrigger>
									<TabsTrigger
										value="pages"
										className="rounded-none data-[state=active]:shadow-none data-[state=active]:bg-muted h-8"
										title="Pages"
									>
										<FileText className="h-4 w-4" />
									</TabsTrigger>
									<TabsTrigger
										value="navigation"
										className="rounded-none data-[state=active]:shadow-none data-[state=active]:bg-muted h-8"
										title="Navigation"
									>
										<Navigation className="h-4 w-4" />
									</TabsTrigger>
								</TabsList>
								<Button
									variant="ghost"
									size="icon-sm"
									className="shrink-0 h-8 w-8 rounded-none"
									onClick={() =>
										setIsLeftPanelCollapsed(true)
									}
								>
									<ChevronLeft className="h-4 w-4" />
								</Button>
							</div>

							<TabsContent
								value="structure"
								className="flex-1 overflow-hidden mt-0"
							>
								<StructureTree
									pages={definition.pages}
									selectedPageId={currentPageId}
									selectedComponentId={selectedComponentId}
									onSelectPage={handleSetCurrentPageId}
									onSelectComponent={onSelectComponent}
									onAddComponent={handleAddComponent}
									onMoveComponent={handleMoveComponent}
									onDeleteComponent={handleDelete}
									onDuplicateComponent={
										handleDuplicateComponent
									}
									className="h-full"
								/>
							</TabsContent>

							<TabsContent
								value="pages"
								className="flex-1 overflow-hidden mt-0"
							>
								<PageTree
									pages={definition.pages}
									selectedPageId={currentPageId}
									onSelectPage={handleSetCurrentPageId}
									onAddPage={handleAddPage}
									onDeletePage={handleDeletePage}
									onReorderPages={handleReorderPages}
									className="h-full"
								/>
							</TabsContent>

							<TabsContent
								value="navigation"
								className="flex-1 overflow-hidden mt-0"
							>
								<NavigationEditor
									app={definition}
									onNavigationChange={handleNavigationChange}
									className="h-full"
								/>
							</TabsContent>
						</Tabs>
					)}
				</div>

				{/* Center Panel - Live Preview */}
				<div className="flex flex-1 flex-col overflow-hidden bg-muted/50">
					{currentPage ? (
						<div className="flex-1 overflow-auto p-4">
							<div className="mx-auto max-w-5xl rounded-lg border bg-background shadow-sm p-4 min-h-full">
								<AppRenderer
									definition={currentPage}
									isPreview={true}
									selectedComponentId={selectedComponentId}
									onSelectComponent={onSelectComponent}
								/>
							</div>
						</div>
					) : (
						<div className="flex h-full items-center justify-center">
							<div className="text-center text-muted-foreground">
								<FileText className="mx-auto mb-2 h-8 w-8 opacity-50" />
								<div className="text-sm">No page selected</div>
							</div>
						</div>
					)}
				</div>

				{/* Right Panel - Property editor + Variables tabs */}
				<div
					className={cn(
						"flex shrink-0 flex-col border-l bg-background transition-all duration-200",
						isRightPanelCollapsed ? "w-10" : "w-80",
					)}
				>
					{isRightPanelCollapsed ? (
						/* Collapsed state - just expand button */
						<div className="flex h-8 items-center justify-center border-b">
							<Button
								variant="ghost"
								size="icon-sm"
								className="h-8 w-8 rounded-none"
								onClick={() => setIsRightPanelCollapsed(false)}
							>
								<ChevronLeft className="h-4 w-4" />
							</Button>
						</div>
					) : (
						/* Expanded state - tabbed interface */
						<Tabs
							value={rightPanelTab}
							onValueChange={(v) =>
								setRightPanelTab(
									v as "properties" | "variables",
								)
							}
							className="flex flex-1 flex-col overflow-hidden"
						>
							{/* Header with tabs and collapse button */}
							<div className="flex items-center border-b h-8">
								<TabsList className="flex-1 rounded-none bg-transparent h-8 p-0">
									<TabsTrigger
										value="properties"
										className="text-xs rounded-none data-[state=active]:shadow-none data-[state=active]:bg-muted h-8"
									>
										Properties
									</TabsTrigger>
									<TabsTrigger
										value="variables"
										className="text-xs rounded-none data-[state=active]:shadow-none data-[state=active]:bg-muted h-8"
									>
										Variables
									</TabsTrigger>
								</TabsList>
								<Button
									variant="ghost"
									size="icon-sm"
									className="shrink-0 h-8 w-8 rounded-none"
									onClick={() =>
										setIsRightPanelCollapsed(true)
									}
								>
									<ChevronRight className="h-4 w-4" />
								</Button>
							</div>

							{/* Properties Tab */}
							<TabsContent
								value="properties"
								className="flex-1 overflow-hidden mt-0"
							>
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
									className="h-full"
								/>
							</TabsContent>

							{/* Variables Tab */}
							<TabsContent
								value="variables"
								className="flex-1 overflow-hidden mt-0"
							>
								<VariablePreview
									page={currentPage}
									className="h-full"
								/>
							</TabsContent>
						</Tabs>
					)}
				</div>
			</div>
		</div>
	);
}

export default EditorShell;
