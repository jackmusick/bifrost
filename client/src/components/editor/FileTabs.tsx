import { X, Cloud, Loader2, CloudCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useEditorStore } from "@/stores/editorStore";
import { useEditorSession } from "@/hooks/useEditorSession";
import { fileService } from "@/services/fileService";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
	ContextMenu,
	ContextMenuContent,
	ContextMenuItem,
	ContextMenuSeparator,
	ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
	draggable,
	dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { FileTabConflictMenu } from "@/components/editor/FileTabConflictMenu";

/**
 * File tabs component
 * Horizontally scrollable tabs for open files with drag-and-drop reordering
 * Each tab shows file name, unsaved indicator, and close button
 * Right-click for context menu: Close, Close Others, Close All
 */
export function FileTabs() {
	const {
		tabs,
		activeTabIndex,
		setActiveTab,
		closeTab,
		closeAllTabs,
		closeOtherTabs,
		openFileInTab,
		setLoadingFile,
		reorderTabs,
		setConflictState,
	} = useEditorSession();

	// Handle tab click - only load from server if content is empty
	const handleTabClick = async (index: number) => {
		if (index === activeTabIndex) return; // Already active

		const tab = tabs[index];
		if (!tab) return;

		// If content already loaded, check for conflicts before switching
		if (tab.content !== "" && tab.etag) {
			try {
				const serverFile = await fileService.readFile(tab.file.path);

				// Check if server content changed
				if (serverFile.etag !== tab.etag) {
					// If there are no unsaved changes, just accept the server version silently
					if (!tab.unsavedChanges) {
						const newTabs = [...tabs];
						newTabs[index] = {
							...tab,
							content: serverFile.content,
							etag: serverFile.etag,
							encoding: serverFile.encoding as "utf-8" | "base64",
						};
						useEditorStore.setState({ tabs: newTabs });
					} else {
						// Only show conflict if we have unsaved local changes
						setConflictState(index, "content_changed");
					}
				}
			} catch (error: unknown) {
				// Check if file was deleted (404)
				if (error instanceof Error && error.message.includes("404")) {
					setConflictState(index, "path_not_found");
				}
				// Ignore other errors (network issues, etc.)
			}

			// Switch to tab
			setActiveTab(index);
			return;
		}

		// Otherwise, load from server (first time opening)
		try {
			setLoadingFile(true);
			const response = await fileService.readFile(tab.file.path);
			openFileInTab(
				tab.file,
				response.content,
				response.encoding as "utf-8" | "base64",
				response.etag,
			);
		} catch {
			toast.error("Failed to load file");
			setLoadingFile(false);
			// Still switch to the tab even if loading fails
			setActiveTab(index);
		}
	};

	if (tabs.length === 0) {
		return null;
	}

	return (
		<div className="flex h-10 items-center border-b bg-muted/30 overflow-x-auto">
			<div className="flex min-w-full">
				{tabs.map((tab, index) => (
					<FileTab
						key={tab.file.path}
						tab={tab}
						index={index}
						isActive={index === activeTabIndex}
						onTabClick={() => handleTabClick(index)}
						onClose={() => closeTab(index)}
						onCloseOthers={() => closeOtherTabs(index)}
						onCloseAll={() => closeAllTabs()}
						onReorder={reorderTabs}
					/>
				))}
			</div>
		</div>
	);
}

interface FileTabProps {
	tab: {
		file: { name: string; path: string };
		unsavedChanges: boolean;
		saveState?: "clean" | "dirty" | "saving" | "saved" | "conflict";
		conflictReason?:
			| "content_changed"
			| "path_not_found"
			| "workflows_would_deactivate";
		serverContentDiffers?: boolean;
	};
	index: number;
	isActive: boolean;
	onTabClick: () => void;
	onClose: () => void;
	onCloseOthers: () => void;
	onCloseAll: () => void;
	onReorder: (fromIndex: number, toIndex: number) => void;
}

function FileTab({
	tab,
	index,
	isActive,
	onTabClick,
	onClose,
	onCloseOthers,
	onCloseAll,
	onReorder,
}: FileTabProps) {
	const resolveConflict = useEditorStore((state) => state.resolveConflict);
	const tabRef = useRef<HTMLDivElement>(null);
	const [isDragging, setIsDragging] = useState(false);
	const [isDropTarget, setIsDropTarget] = useState(false);

	useEffect(() => {
		const element = tabRef.current;
		if (!element) return;

		return combine(
			draggable({
				element,
				getInitialData: () => ({ index, type: "file-tab" }),
				onDragStart: () => setIsDragging(true),
				onDrop: () => setIsDragging(false),
			}),
			dropTargetForElements({
				element,
				getData: () => ({ index, type: "file-tab" }),
				canDrop: ({ source }) => {
					return (
						source.data["type"] === "file-tab" &&
						source.data["index"] !== index
					);
				},
				onDragEnter: () => setIsDropTarget(true),
				onDragLeave: () => setIsDropTarget(false),
				onDrop: ({ source }) => {
					setIsDropTarget(false);
					const sourceIndex = source.data["index"];
					if (
						typeof sourceIndex === "number" &&
						sourceIndex !== index
					) {
						onReorder(sourceIndex, index);
					}
				},
			}),
		);
	}, [index, onReorder]);

	return (
		<ContextMenu>
			<ContextMenuTrigger asChild>
				<div
					ref={tabRef}
					className={cn(
						"group flex items-center gap-2 border-r px-3 py-2 text-sm transition-all min-w-[120px] max-w-[200px] cursor-pointer",
						isActive
							? "bg-background text-foreground"
							: "bg-muted/30 text-muted-foreground hover:bg-muted/50",
						isDragging && "opacity-50",
						isDropTarget &&
							"bg-primary/20 border-l-2 border-l-primary",
					)}
				>
					{/* Clickable area for tab */}
					<div
						onClick={onTabClick}
						className="flex items-center gap-2 flex-1 min-w-0"
					>
						{/* Save state icon - always show cloud */}
						{tab.saveState === "conflict" && tab.conflictReason ? (
							<FileTabConflictMenu
								fileName={tab.file.name}
								conflictReason={tab.conflictReason}
								onResolve={(action) =>
									resolveConflict(index, action)
								}
							/>
						) : tab.saveState === "dirty" ? (
							<Cloud className="h-3.5 w-3.5 flex-shrink-0 text-blue-500" />
						) : tab.saveState === "saving" ? (
							<Loader2 className="h-3.5 w-3.5 flex-shrink-0 text-blue-500 animate-spin" />
						) : tab.saveState === "saved" ? (
							<CloudCheck className="h-3.5 w-3.5 flex-shrink-0 text-green-500" />
						) : (
							<Cloud className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50" />
						)}

						{/* File name */}
						<span className="flex-1 truncate text-left">
							{tab.file.name}
						</span>
					</div>

					{/* Close button - always visible */}
					<button
						onClick={(e) => {
							e.stopPropagation();
							onClose();
						}}
						className="flex-shrink-0 rounded p-0.5 hover:bg-muted-foreground/20 opacity-0 group-hover:opacity-100 transition-opacity"
						title="Close"
					>
						<X className="h-3 w-3" />
					</button>
				</div>
			</ContextMenuTrigger>
			<ContextMenuContent>
				<ContextMenuItem onClick={onClose}>Close</ContextMenuItem>
				<ContextMenuItem onClick={onCloseOthers}>
					Close Others
				</ContextMenuItem>
				<ContextMenuSeparator />
				<ContextMenuItem onClick={onCloseAll}>
					Close All
				</ContextMenuItem>
			</ContextMenuContent>
		</ContextMenu>
	);
}
