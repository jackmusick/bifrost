/**
 * Navigation Editor for App Builder
 *
 * Visual editor for configuring application navigation (sidebar items).
 * Allows reordering, renaming, setting icons, and grouping pages.
 */

import { useState, useMemo } from "react";
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

interface NavItemEditorProps {
	item: NavItem;
	index: number;
	onUpdate: (index: number, item: NavItem) => void;
	onDelete: (index: number) => void;
	onMoveUp: (index: number) => void;
	onMoveDown: (index: number) => void;
	isFirst: boolean;
	isLast: boolean;
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
	onMoveUp,
	onMoveDown,
	isFirst,
	isLast,
	pages,
}: NavItemEditorProps) {
	const [isOpen, setIsOpen] = useState(false);

	const linkedPage = pages.find((p) => p.id === item.id);

	return (
		<div className="border rounded-lg bg-background">
			<Collapsible open={isOpen} onOpenChange={setIsOpen}>
				<div className="flex items-center gap-2 p-2">
					{/* Drag Handle */}
					<div className="flex flex-col gap-0.5">
						<Button
							variant="ghost"
							size="icon-sm"
							className="h-5 w-5"
							disabled={isFirst}
							onClick={() => onMoveUp(index)}
						>
							<ChevronDown className="h-3 w-3 rotate-180" />
						</Button>
						<Button
							variant="ghost"
							size="icon-sm"
							className="h-5 w-5"
							disabled={isLast}
							onClick={() => onMoveDown(index)}
						>
							<ChevronDown className="h-3 w-3" />
						</Button>
					</div>

					{/* Icon and Label */}
					<CollapsibleTrigger asChild>
						<Button
							variant="ghost"
							className="flex-1 justify-start gap-2 h-auto py-2"
						>
							{isOpen ? (
								<ChevronDown className="h-4 w-4 text-muted-foreground" />
							) : (
								<ChevronRight className="h-4 w-4 text-muted-foreground" />
							)}
							<NavIcon
								iconName={item.icon}
								className="h-4 w-4 text-primary"
							/>
							<span className="text-sm font-medium">
								{item.label}
							</span>
							{item.isSection && (
								<span className="ml-2 text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
									Section
								</span>
							)}
						</Button>
					</CollapsibleTrigger>

					{/* Delete Button */}
					<AlertDialog>
						<AlertDialogTrigger asChild>
							<Button
								variant="ghost"
								size="icon-sm"
								className="h-7 w-7"
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
							<div className="space-y-0.5">
								<Label>Section Header</Label>
								<p className="text-xs text-muted-foreground">
									Make this a group header for organizing
									items
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

	const items = navigation.sidebar || [];

	const handleUpdateItem = (index: number, item: NavItem) => {
		const newItems = [...items];
		newItems[index] = item;
		onNavigationChange({
			...navigation,
			sidebar: newItems,
		});
	};

	const handleDeleteItem = (index: number) => {
		const newItems = items.filter((_, i) => i !== index);
		onNavigationChange({
			...navigation,
			sidebar: newItems,
		});
	};

	const handleMoveUp = (index: number) => {
		if (index === 0) return;
		const newItems = [...items];
		[newItems[index - 1], newItems[index]] = [
			newItems[index],
			newItems[index - 1],
		];
		onNavigationChange({
			...navigation,
			sidebar: newItems,
		});
	};

	const handleMoveDown = (index: number) => {
		if (index === items.length - 1) return;
		const newItems = [...items];
		[newItems[index], newItems[index + 1]] = [
			newItems[index + 1],
			newItems[index],
		];
		onNavigationChange({
			...navigation,
			sidebar: newItems,
		});
	};

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
			<div className="flex items-center justify-between px-3 py-2 border-b">
				<div className="flex items-center gap-2">
					<Layout className="h-4 w-4 text-muted-foreground" />
					<h3 className="text-sm font-semibold">Navigation</h3>
				</div>
			</div>

			{/* Global Settings */}
			<div className="px-3 py-3 border-b space-y-3">
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
			<div className="flex-1 overflow-y-auto p-3 space-y-2">
				{items.length === 0 ? (
					<p className="text-xs text-muted-foreground text-center py-4 italic">
						No navigation items. Add pages to the sidebar below.
					</p>
				) : (
					items.map((item, index) => (
						<NavItemEditor
							key={item.id}
							item={item}
							index={index}
							onUpdate={handleUpdateItem}
							onDelete={handleDeleteItem}
							onMoveUp={handleMoveUp}
							onMoveDown={handleMoveDown}
							isFirst={index === 0}
							isLast={index === items.length - 1}
							pages={app.pages}
						/>
					))
				)}
			</div>

			{/* Add Buttons */}
			<div className="p-3 border-t space-y-2">
				{unlinkedPages.length > 0 && (
					<Button
						variant="outline"
						size="sm"
						className="w-full gap-2"
						onClick={handleAddItem}
					>
						<Plus className="h-3.5 w-3.5" />
						Add Page ({unlinkedPages.length} available)
					</Button>
				)}
				<Button
					variant="ghost"
					size="sm"
					className="w-full gap-2"
					onClick={handleAddSection}
				>
					<FolderOpen className="h-3.5 w-3.5" />
					Add Section Header
				</Button>
			</div>
		</div>
	);
}

export default NavigationEditor;
