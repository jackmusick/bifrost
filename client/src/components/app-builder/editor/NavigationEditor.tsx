/**
 * Navigation Editor for App Builder
 *
 * Visual editor for configuring application navigation (sidebar items).
 * Allows reordering, renaming, setting icons, and grouping pages.
 */

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
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
	Plus,
	Trash2,
	ChevronDown,
	ChevronRight,
	FolderOpen,
	Home,
	FileText,
	Settings,
	Users,
	BarChart3,
	Table2,
	Layout,
	Inbox,
	Calendar,
	GripVertical,
	type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
	AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import type {
	ApplicationDefinition,
	NavItem,
	NavigationConfig,
	PageDefinition,
} from "@/lib/app-builder-types";

interface NavigationEditorProps {
	/** Current application definition */
	app: ApplicationDefinition;
	/** Callback when navigation is updated */
	onNavigationChange: (navigation: NavigationConfig) => void;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Available icons for navigation items
 */
const ICON_OPTIONS: { value: string; label: string; icon: LucideIcon }[] = [
	{ value: "home", label: "Home", icon: Home },
	{ value: "file-text", label: "Document", icon: FileText },
	{ value: "settings", label: "Settings", icon: Settings },
	{ value: "users", label: "Users", icon: Users },
	{ value: "bar-chart", label: "Chart", icon: BarChart3 },
	{ value: "table", label: "Table", icon: Table2 },
	{ value: "layout", label: "Layout", icon: Layout },
	{ value: "inbox", label: "Inbox", icon: Inbox },
	{ value: "calendar", label: "Calendar", icon: Calendar },
	{ value: "folder", label: "Folder", icon: FolderOpen },
];

/**
 * Static icon lookup by name
 */
const ICON_MAP: Record<string, LucideIcon> = {
	home: Home,
	"file-text": FileText,
	settings: Settings,
	users: Users,
	"bar-chart": BarChart3,
	table: Table2,
	layout: Layout,
	inbox: Inbox,
	calendar: Calendar,
	folder: FolderOpen,
};

/**
 * Icon component wrapper to avoid creating components during render
 */
function NavIcon({
	iconName,
	className,
}: {
	iconName?: string;
	className?: string;
}) {
	const IconComponent = ICON_MAP[iconName || "home"] || Home;
	return <IconComponent className={className} />;
}

/**
 * Generate a unique section ID
 */
let sectionCounter = 0;
function generateSectionId(): string {
	sectionCounter += 1;
	return `section-${sectionCounter}-${Math.random().toString(36).slice(2, 7)}`;
}

/** Drag data for nav item reordering */
interface NavItemDragData {
	type: "nav-item";
	id: string;
	index: number;
	[key: string]: unknown;
}

interface NavItemEditorProps {
	item: NavItem;
	index: number;
	onUpdate: (index: number, item: NavItem) => void;
	onDelete: (index: number) => void;
	onReorder: (fromIndex: number, toIndex: number) => void;
	pages: PageDefinition[];
}

/**
 * Editor for a single navigation item
 */
function NavItemEditor({
	item,
	index,
	onUpdate,
	onDelete,
	onReorder,
	pages,
}: NavItemEditorProps) {
	const ref = useRef<HTMLDivElement>(null);
	const dragHandleRef = useRef<HTMLButtonElement>(null);
	const [isOpen, setIsOpen] = useState(false);
	const [isDragging, setIsDragging] = useState(false);
	const [closestEdge, setClosestEdge] = useState<Edge | null>(null);

	const linkedPage = pages.find((p) => p.id === item.id);

	// Set up drag and drop
	useEffect(() => {
		const el = ref.current;
		const handle = dragHandleRef.current;
		if (!el || !handle) return;

		const dragData: NavItemDragData = {
			type: "nav-item",
			id: item.id,
			index,
		};

		return combine(
			draggable({
				element: el,
				dragHandle: handle,
				getInitialData: () => dragData,
				onDragStart: () => setIsDragging(true),
				onDrop: () => setIsDragging(false),
			}),
			dropTargetForElements({
				element: el,
				getData: ({ input, element: targetEl }) => {
					return attachClosestEdge(
						{ id: item.id, index },
						{
							input,
							element: targetEl,
							allowedEdges: ["top", "bottom"],
						},
					);
				},
				canDrop: ({ source }) => {
					const data = source.data as NavItemDragData;
					return data.type === "nav-item" && data.id !== item.id;
				},
				onDrag: ({ self }) => {
					const edge = extractClosestEdge(self.data);
					setClosestEdge(edge);
				},
				onDragLeave: () => {
					setClosestEdge(null);
				},
				onDrop: ({ source, self }) => {
					setClosestEdge(null);
					const sourceData = source.data as NavItemDragData;
					const edge = extractClosestEdge(self.data);

					let targetIndex = index;
					if (edge === "bottom") {
						targetIndex = index + 1;
					}
					// Adjust for items being removed from earlier in the list
					if (sourceData.index < targetIndex) {
						targetIndex -= 1;
					}

					if (sourceData.index !== targetIndex) {
						onReorder(sourceData.index, targetIndex);
					}
				},
			}),
		);
	}, [item.id, index, onReorder]);

	return (
		<div
			ref={ref}
			className={cn(
				"border rounded-lg bg-background relative",
				isDragging && "opacity-50",
			)}
		>
			{/* Drop indicator */}
			{closestEdge === "top" && (
				<div className="absolute -top-0.5 left-0 right-0 h-0.5 bg-primary rounded-full" />
			)}
			{closestEdge === "bottom" && (
				<div className="absolute -bottom-0.5 left-0 right-0 h-0.5 bg-primary rounded-full" />
			)}

			<Collapsible open={isOpen} onOpenChange={setIsOpen}>
				<div className="flex items-center gap-1 p-2 group">
					{/* Drag Handle */}
					<button
						ref={dragHandleRef}
						className="cursor-grab active:cursor-grabbing p-1 text-muted-foreground hover:text-foreground shrink-0"
					>
						<GripVertical className="h-4 w-4" />
					</button>

					{/* Icon and Label */}
					<CollapsibleTrigger asChild>
						<Button
							variant="ghost"
							className="flex-1 justify-start gap-2 h-auto py-2 min-w-0"
						>
							{isOpen ? (
								<ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
							) : (
								<ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
							)}
							<NavIcon
								iconName={item.icon}
								className="h-4 w-4 text-primary shrink-0"
							/>
							<span className="text-sm font-medium truncate">
								{item.label}
							</span>
						</Button>
					</CollapsibleTrigger>

					{/* Delete Button - appears on hover */}
					<AlertDialog>
						<AlertDialogTrigger asChild>
							<Button
								variant="ghost"
								size="icon-sm"
								className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
							>
								<Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
							</Button>
						</AlertDialogTrigger>
						<AlertDialogContent>
							<AlertDialogHeader>
								<AlertDialogTitle>
									Remove from navigation?
								</AlertDialogTitle>
								<AlertDialogDescription>
									This will remove "{item.label}" from the
									sidebar navigation. The page will still
									exist but won't be visible in the sidebar.
								</AlertDialogDescription>
							</AlertDialogHeader>
							<AlertDialogFooter>
								<AlertDialogCancel>Cancel</AlertDialogCancel>
								<AlertDialogAction
									onClick={() => onDelete(index)}
								>
									Remove
								</AlertDialogAction>
							</AlertDialogFooter>
						</AlertDialogContent>
					</AlertDialog>
				</div>

				<CollapsibleContent>
					<div className="px-4 pb-4 space-y-4 border-t pt-4">
						{/* Label */}
						<div className="space-y-2">
							<Label htmlFor={`nav-label-${index}`}>Label</Label>
							<Input
								id={`nav-label-${index}`}
								value={item.label}
								onChange={(e) =>
									onUpdate(index, {
										...item,
										label: e.target.value,
									})
								}
								placeholder="Navigation label"
							/>
						</div>

						{/* Icon */}
						<div className="space-y-2">
							<Label>Icon</Label>
							<Select
								value={item.icon || "home"}
								onValueChange={(value) =>
									onUpdate(index, { ...item, icon: value })
								}
							>
								<SelectTrigger>
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									{ICON_OPTIONS.map((opt) => (
										<SelectItem
											key={opt.value}
											value={opt.value}
										>
											<div className="flex items-center gap-2">
												<opt.icon className="h-4 w-4" />
												{opt.label}
											</div>
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>

						{/* Link to Page */}
						{!item.isSection && (
							<div className="space-y-2">
								<Label>Linked Page</Label>
								<Select
									value={item.id}
									onValueChange={(value) => {
										const page = pages.find(
											(p) => p.id === value,
										);
										if (page) {
											onUpdate(index, {
												...item,
												id: page.id,
												label: item.label || page.title,
												path: page.path,
											});
										}
									}}
								>
									<SelectTrigger>
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										{pages.map((page) => (
											<SelectItem
												key={page.id}
												value={page.id}
											>
												{page.title} ({page.path})
											</SelectItem>
										))}
									</SelectContent>
								</Select>
								{linkedPage && (
									<p className="text-xs text-muted-foreground">
										Path: /{linkedPage.path}
									</p>
								)}
							</div>
						)}

						{/* Visibility Expression */}
						<div className="space-y-2">
							<Label htmlFor={`nav-visible-${index}`}>
								Visibility Expression{" "}
								<span className="text-muted-foreground font-normal">
									(optional)
								</span>
							</Label>
							<Input
								id={`nav-visible-${index}`}
								value={item.visible || ""}
								onChange={(e) =>
									onUpdate(index, {
										...item,
										visible: e.target.value || undefined,
									})
								}
								placeholder="e.g., {{ user.role === 'admin' }}"
								className="font-mono text-xs"
							/>
							<p className="text-xs text-muted-foreground">
								Leave empty to always show. Use expressions to
								conditionally hide.
							</p>
						</div>

						{/* Section Toggle */}
						<div className="flex items-center justify-between">
							<div className="space-y-0.5 min-w-0 flex-1 mr-2">
								<Label>Section</Label>
								<p className="text-xs text-muted-foreground">
									Group header for organizing items
								</p>
							</div>
							<Switch
								checked={item.isSection || false}
								onCheckedChange={(checked) =>
									onUpdate(index, {
										...item,
										isSection: checked,
									})
								}
							/>
						</div>
					</div>
				</CollapsibleContent>
			</Collapsible>
		</div>
	);
}

/**
 * Navigation Editor Component
 *
 * Allows editing of the application's navigation structure.
 */
export function NavigationEditor({
	app,
	onNavigationChange,
	className,
}: NavigationEditorProps) {
	// Build default navigation from pages if none exists
	const navigation = useMemo((): NavigationConfig => {
		if (app.navigation?.sidebar && app.navigation.sidebar.length > 0) {
			return app.navigation;
		}
		// Generate default navigation from pages
		return {
			showSidebar: true,
			showHeader: true,
			sidebar: app.pages.map((page, index) => ({
				id: page.id,
				label: page.title,
				icon: "home",
				path: page.path,
				order: index,
			})),
		};
	}, [app.navigation, app.pages]);

	const items = useMemo(() => navigation.sidebar || [], [navigation.sidebar]);

	const handleUpdateItem = (index: number, item: NavItem) => {
		const newItems = [...items];
		newItems[index] = item;
		onNavigationChange({
			...navigation,
			sidebar: newItems,
		});
	};

	const handleDeleteItem = useCallback(
		(index: number) => {
			const newItems = items.filter((_, i) => i !== index);
			onNavigationChange({
				...navigation,
				sidebar: newItems,
			});
		},
		[items, navigation, onNavigationChange],
	);

	const handleReorder = useCallback(
		(fromIndex: number, toIndex: number) => {
			const newItems = [...items];
			const [removed] = newItems.splice(fromIndex, 1);
			newItems.splice(toIndex, 0, removed);
			onNavigationChange({
				...navigation,
				sidebar: newItems,
			});
		},
		[items, navigation, onNavigationChange],
	);

	const handleAddItem = () => {
		// Find pages not in navigation
		const existingIds = new Set(items.map((i) => i.id));
		const availablePages = app.pages.filter((p) => !existingIds.has(p.id));

		if (availablePages.length > 0) {
			const page = availablePages[0];
			onNavigationChange({
				...navigation,
				sidebar: [
					...items,
					{
						id: page.id,
						label: page.title,
						icon: "home",
						path: page.path,
						order: items.length,
					},
				],
			});
		} else {
			// Add a section instead
			onNavigationChange({
				...navigation,
				sidebar: [
					...items,
					{
						id: generateSectionId(),
						label: "New Section",
						icon: "folder",
						isSection: true,
						order: items.length,
					},
				],
			});
		}
	};

	const handleAddSection = () => {
		onNavigationChange({
			...navigation,
			sidebar: [
				...items,
				{
					id: generateSectionId(),
					label: "New Section",
					icon: "folder",
					isSection: true,
					order: items.length,
				},
			],
		});
	};

	// Find pages not in navigation for "add" button
	const existingIds = new Set(items.map((i) => i.id));
	const unlinkedPages = app.pages.filter((p) => !existingIds.has(p.id));

	return (
		<div className={cn("flex flex-col h-full", className)}>
			{/* Global Settings */}
			<div className="px-3 py-2 border-b space-y-2">
				<div className="flex items-center justify-between">
					<Label className="text-xs">Show Sidebar</Label>
					<Switch
						checked={navigation.showSidebar !== false}
						onCheckedChange={(checked) =>
							onNavigationChange({
								...navigation,
								showSidebar: checked,
							})
						}
					/>
				</div>
				<div className="flex items-center justify-between">
					<Label className="text-xs">Show Header</Label>
					<Switch
						checked={navigation.showHeader !== false}
						onCheckedChange={(checked) =>
							onNavigationChange({
								...navigation,
								showHeader: checked,
							})
						}
					/>
				</div>
			</div>

			{/* Navigation Items */}
			<div className="flex-1 overflow-y-auto overflow-x-hidden">
				{items.length === 0 ? (
					<p className="text-xs text-muted-foreground text-center py-4 px-3 italic">
						No navigation items. Add pages to the sidebar below.
					</p>
				) : (
					<div>
						{items.map((item, index) => (
							<NavItemEditor
								key={item.id}
								item={item}
								index={index}
								onUpdate={handleUpdateItem}
								onDelete={handleDeleteItem}
								onReorder={handleReorder}
								pages={app.pages}
							/>
						))}
					</div>
				)}
			</div>

			{/* Add Buttons */}
			<div className="border-t">
				{unlinkedPages.length > 0 && (
					<Button
						variant="ghost"
						size="sm"
						className="w-full gap-2 rounded-none h-9 border-b"
						onClick={handleAddItem}
					>
						<Plus className="h-3.5 w-3.5" />
						Add Page ({unlinkedPages.length})
					</Button>
				)}
				<Button
					variant="ghost"
					size="sm"
					className="w-full gap-2 rounded-none h-9"
					onClick={handleAddSection}
				>
					<FolderOpen className="h-3.5 w-3.5" />
					Add Section
				</Button>
			</div>
		</div>
	);
}

export default NavigationEditor;
