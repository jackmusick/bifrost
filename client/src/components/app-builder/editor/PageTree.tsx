/**
 * Page Tree Navigator for App Builder Visual Editor
 *
 * Displays and manages the pages in an application with drag-and-drop reordering.
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
import { Button } from "@/components/ui/button";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Home, FileText, Plus, Trash2, GripVertical } from "lucide-react";
import type { PageDefinition } from "@/lib/app-builder-types";

/**
 * Drag data for page reordering
 */
interface PageDragData {
	type: "page";
	pageId: string;
	index: number;
	[key: string]: unknown;
}

/**
 * Type guard to check if data is PageDragData
 */
function isPageDragData(data: Record<string, unknown>): data is PageDragData {
	return data.type === "page" && typeof data.pageId === "string";
}

/**
 * Props for the PageTree component
 */
export interface PageTreeProps {
	/** List of pages in the application */
	pages: PageDefinition[];
	/** Currently selected page ID */
	selectedPageId: string | null;
	/** Callback when a page is selected */
	onSelectPage: (pageId: string) => void;
	/** Callback when the add page button is clicked */
	onAddPage: () => void;
	/** Callback when a page is deleted */
	onDeletePage: (pageId: string) => void;
	/** Callback when pages are reordered */
	onReorderPages: (pages: PageDefinition[]) => void;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Props for the PageItem component
 */
interface PageItemProps {
	page: PageDefinition;
	index: number;
	isSelected: boolean;
	onSelect: (pageId: string) => void;
	onDelete: (pageId: string) => void;
	onReorder: (fromIndex: number, toIndex: number) => void;
}

/**
 * Individual page item in the tree
 */
function PageItem({
	page,
	index,
	isSelected,
	onSelect,
	onDelete,
	onReorder,
}: PageItemProps) {
	const ref = useRef<HTMLDivElement>(null);
	const dragHandleRef = useRef<HTMLDivElement>(null);
	const [isDragging, setIsDragging] = useState(false);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [closestEdge, setClosestEdge] = useState<Edge | null>(null);
	const [isHovered, setIsHovered] = useState(false);

	const isHomePage = page.path === "/";
	const Icon = isHomePage ? Home : FileText;

	useEffect(() => {
		const el = ref.current;
		const handleEl = dragHandleRef.current;
		if (!el || !handleEl) return;

		const dragData: PageDragData = {
			type: "page",
			pageId: page.id,
			index,
		};

		return combine(
			draggable({
				element: el,
				dragHandle: handleEl,
				getInitialData: () => dragData,
				onDragStart: () => setIsDragging(true),
				onDrop: () => setIsDragging(false),
			}),
			dropTargetForElements({
				element: el,
				getData: ({ input, element: targetEl }) => {
					return attachClosestEdge(
						{ pageId: page.id, index },
						{
							input,
							element: targetEl,
							allowedEdges: ["top", "bottom"],
						},
					);
				},
				canDrop: ({ source }) => {
					// Prevent dropping on self
					return source.data.pageId !== page.id;
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

					if (!isPageDragData(source.data)) return;

					const edge = extractClosestEdge(self.data);
					const sourceIndex = source.data.index;
					let targetIndex = index;

					// Adjust target index based on drop edge
					if (edge === "bottom") {
						targetIndex = index + 1;
					}

					// Adjust for moving items down the list
					if (sourceIndex < targetIndex) {
						targetIndex -= 1;
					}

					if (sourceIndex !== targetIndex) {
						onReorder(sourceIndex, targetIndex);
					}
				},
			}),
		);
	}, [page.id, index, onReorder]);

	const handleClick = useCallback(() => {
		onSelect(page.id);
	}, [page.id, onSelect]);

	const handleDeleteClick = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onDelete(page.id);
		},
		[page.id, onDelete],
	);

	return (
		<div
			ref={ref}
			className={cn(
				"relative group flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-all duration-150",
				isDragging && "opacity-50",
				isSelected
					? "bg-primary text-primary-foreground"
					: isDraggedOver
						? "bg-muted"
						: "hover:bg-muted",
			)}
			onClick={handleClick}
			onMouseEnter={() => setIsHovered(true)}
			onMouseLeave={() => setIsHovered(false)}
			role="button"
			tabIndex={0}
			aria-selected={isSelected}
			onKeyDown={(e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					handleClick();
				}
			}}
		>
			{/* Drop indicator */}
			{closestEdge && (
				<div
					className={cn(
						"absolute left-0 right-0 h-0.5 bg-primary pointer-events-none z-10",
						closestEdge === "top" ? "-top-px" : "-bottom-px",
					)}
				/>
			)}

			{/* Drag handle */}
			<div
				ref={dragHandleRef}
				className={cn(
					"cursor-grab active:cursor-grabbing transition-opacity shrink-0",
					isHovered || isSelected ? "opacity-50" : "opacity-0",
				)}
				aria-label="Drag to reorder"
			>
				<GripVertical className="h-3 w-3" />
			</div>

			{/* Page icon */}
			<Icon
				className={cn(
					"h-4 w-4 shrink-0",
					isSelected
						? "text-primary-foreground"
						: "text-muted-foreground",
				)}
			/>

			{/* Page info */}
			<div className="flex-1 min-w-0">
				<div className="text-sm truncate">{page.title}</div>
			</div>

			{/* Path */}
			<span
				className={cn(
					"text-xs shrink-0",
					isSelected
						? "text-primary-foreground/70"
						: "text-muted-foreground",
				)}
			>
				{page.path}
			</span>

			{/* Delete button */}
			<button
				onClick={handleDeleteClick}
				className={cn(
					"p-1 rounded hover:bg-destructive/20 transition-opacity shrink-0",
					isHovered ? "opacity-100" : "opacity-0",
					isSelected && "hover:bg-primary-foreground/20",
				)}
				aria-label={`Delete ${page.title}`}
			>
				<Trash2 className="h-3 w-3" />
			</button>
		</div>
	);
}

/**
 * Page Tree Navigator Component
 *
 * Displays a list of pages in the application with support for:
 * - Selecting pages
 * - Adding new pages
 * - Deleting pages (with confirmation)
 * - Reordering pages via drag and drop
 *
 * @example
 * <PageTree
 *   pages={appPages}
 *   selectedPageId={currentPageId}
 *   onSelectPage={setCurrentPageId}
 *   onAddPage={handleAddPage}
 *   onDeletePage={handleDeletePage}
 *   onReorderPages={handleReorderPages}
 * />
 */
export function PageTree({
	pages,
	selectedPageId,
	onSelectPage,
	onAddPage,
	onDeletePage,
	onReorderPages,
	className = "",
}: PageTreeProps) {
	const [deleteConfirmPageId, setDeleteConfirmPageId] = useState<
		string | null
	>(null);

	const pageToDelete = deleteConfirmPageId
		? pages.find((p) => p.id === deleteConfirmPageId)
		: null;

	const handleDeleteRequest = useCallback((pageId: string) => {
		setDeleteConfirmPageId(pageId);
	}, []);

	const handleConfirmDelete = useCallback(() => {
		if (deleteConfirmPageId) {
			onDeletePage(deleteConfirmPageId);
			setDeleteConfirmPageId(null);
		}
	}, [deleteConfirmPageId, onDeletePage]);

	const handleCancelDelete = useCallback(() => {
		setDeleteConfirmPageId(null);
	}, []);

	const handleReorder = useCallback(
		(fromIndex: number, toIndex: number) => {
			const newPages = [...pages];
			const [movedPage] = newPages.splice(fromIndex, 1);
			newPages.splice(toIndex, 0, movedPage);
			onReorderPages(newPages);
		},
		[pages, onReorderPages],
	);

	return (
		<div className={cn("flex flex-col h-full", className)}>
			{/* Page list */}
			<div className="flex-1 overflow-y-auto">
				<div>
					{pages.map((page, index) => (
						<PageItem
							key={page.id}
							page={page}
							index={index}
							isSelected={page.id === selectedPageId}
							onSelect={onSelectPage}
							onDelete={handleDeleteRequest}
							onReorder={handleReorder}
						/>
					))}

					{pages.length === 0 && (
						<div className="text-sm text-muted-foreground text-center py-8 px-3">
							No pages yet.
							<br />
							Add your first page below.
						</div>
					)}
				</div>
			</div>

			{/* Add page button */}
			<div className="border-t">
				<Button
					variant="ghost"
					size="sm"
					className="w-full rounded-none h-9"
					onClick={onAddPage}
				>
					<Plus className="h-4 w-4" />
					Add Page
				</Button>
			</div>

			{/* Delete confirmation dialog */}
			<AlertDialog
				open={deleteConfirmPageId !== null}
				onOpenChange={(open) => {
					if (!open) handleCancelDelete();
				}}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Page</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete{" "}
							<span className="font-medium">
								{pageToDelete?.title || "this page"}
							</span>
							? This action cannot be undone and all components on
							this page will be permanently removed.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel onClick={handleCancelDelete}>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

export default PageTree;
