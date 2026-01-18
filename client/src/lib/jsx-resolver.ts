/**
 * JSX File Resolver
 *
 * Fetches and compiles JSX files from the API with caching.
 * Handles component resolution for custom app components.
 */

import React from "react";
import { createComponent } from "./jsx-runtime";
import { authFetch } from "./api-client";

/**
 * Cached component entry
 */
interface ComponentCache {
	component: React.ComponentType;
	compiledAt: number;
}

/**
 * JSX file response from the API
 */
interface JsxFileResponse {
	id: string;
	app_version_id: string;
	path: string;
	source: string;
	compiled: string | null;
	created_at: string;
	updated_at: string;
}

/**
 * Cache for compiled components
 * Key format: `{appId}:{versionId}:{path}`
 */
const componentCache = new Map<string, ComponentCache>();

/**
 * Build cache key from app, version, and path
 */
function buildCacheKey(
	appId: string,
	versionId: string,
	path: string,
): string {
	return `${appId}:${versionId}:${path}`;
}

/**
 * Fetch a JSX file from the API
 *
 * @param appId - Application ID
 * @param versionId - Version ID (draft or published)
 * @param path - File path (e.g., "components/ClientCard")
 * @returns The file response or null if not found
 */
export async function resolveFile(
	appId: string,
	versionId: string,
	path: string,
): Promise<JsxFileResponse | null> {
	try {
		// URL-encode the path since it may contain slashes
		const encodedPath = encodeURIComponent(path);
		const response = await authFetch(
			`/api/apps/${appId}/versions/${versionId}/files/${encodedPath}`,
		);

		if (!response.ok) {
			if (response.status === 404) {
				return null;
			}
			throw new Error(`Failed to fetch file: ${response.statusText}`);
		}

		return response.json();
	} catch (error) {
		console.error(`Error fetching JSX file ${path}:`, error);
		return null;
	}
}

/**
 * Resolve multiple components for an app
 *
 * Fetches, compiles, and caches components. Uses the compiled version
 * from the API if available, otherwise compiles on the client.
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 * @param componentNames - Names of components to resolve (e.g., ["ClientCard", "DataGrid"])
 * @returns Map of component name to React component
 */
export async function resolveAppComponents(
	appId: string,
	versionId: string,
	componentNames: string[],
): Promise<Record<string, React.ComponentType>> {
	const components: Record<string, React.ComponentType> = {};

	// Filter out built-in components
	const customNames = componentNames.filter(
		(name) => !isBuiltInComponent(name),
	);

	for (const name of customNames) {
		const cacheKey = buildCacheKey(appId, versionId, `components/${name}`);

		// Check cache first
		const cached = componentCache.get(cacheKey);
		if (cached) {
			components[name] = cached.component;
			continue;
		}

		// Fetch from API
		const file = await resolveFile(appId, versionId, `components/${name}`);
		if (!file) {
			console.warn(`Component not found: ${name}`);
			continue;
		}

		// Use compiled version if available, otherwise compile on client
		const source = file.compiled || file.source;
		const useCompiled = !!file.compiled;

		// Extract any nested custom component dependencies
		// For now, we don't recursively resolve to avoid circular dependencies
		// In a full implementation, we would track a dependency graph
		const component = createComponent(source, {}, useCompiled);

		// Cache the compiled component
		componentCache.set(cacheKey, {
			component,
			compiledAt: Date.now(),
		});

		components[name] = component;
	}

	return components;
}

/**
 * Extract component names from JSX source code
 *
 * Uses regex to find all PascalCase component references in JSX.
 * This is a simple heuristic - a full AST parser would be more accurate.
 *
 * @param source - JSX source code
 * @returns Array of unique component names
 *
 * @example
 * ```typescript
 * extractComponentNames('<Card><ClientCard name="test" /></Card>')
 * // Returns: ["Card", "ClientCard"]
 * ```
 */
export function extractComponentNames(source: string): string[] {
	// Match JSX opening tags with PascalCase names
	// e.g., <ComponentName, <Card>, <MyComponent123>
	const matches = source.matchAll(/<([A-Z][a-zA-Z0-9]*)/g);
	const names = new Set<string>();

	for (const match of matches) {
		names.add(match[1]);
	}

	return Array.from(names);
}

/**
 * Clear all cached components for an app
 *
 * Call this when files are updated to ensure fresh compilation.
 *
 * @param appId - Application ID to clear cache for
 */
export function clearAppCache(appId: string): void {
	for (const key of componentCache.keys()) {
		if (key.startsWith(`${appId}:`)) {
			componentCache.delete(key);
		}
	}
}

/**
 * Clear cache for a specific app version
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 */
export function clearVersionCache(appId: string, versionId: string): void {
	const prefix = `${appId}:${versionId}:`;
	for (const key of componentCache.keys()) {
		if (key.startsWith(prefix)) {
			componentCache.delete(key);
		}
	}
}

/**
 * Clear cache for a specific file
 *
 * @param appId - Application ID
 * @param versionId - Version ID
 * @param path - File path
 */
export function clearFileCache(
	appId: string,
	versionId: string,
	path: string,
): void {
	const key = buildCacheKey(appId, versionId, path);
	componentCache.delete(key);
}

/**
 * Get cache statistics for debugging
 */
export function getCacheStats(): { size: number; keys: string[] } {
	return {
		size: componentCache.size,
		keys: Array.from(componentCache.keys()),
	};
}

/**
 * Check if a component name is a built-in platform component
 *
 * Built-in components are provided by the platform scope and don't need
 * to be fetched from the API. This includes:
 * - React built-ins (Fragment, Suspense)
 * - Layout components (Column, Row, Grid, Card)
 * - Typography (Heading, Text)
 * - Data display (DataTable, Badge, Avatar, etc.)
 * - Form elements (Input, Select, Button, etc.)
 * - Feedback (Dialog, Alert, etc.)
 *
 * @param name - Component name to check
 * @returns true if the component is a built-in
 */
export function isBuiltInComponent(name: string): boolean {
	const builtIns = new Set([
		// React built-ins
		"Fragment",
		"Suspense",

		// Layout
		"Column",
		"Row",
		"Grid",
		"Card",
		"CardHeader",
		"CardTitle",
		"CardDescription",
		"CardContent",
		"CardFooter",
		"Tabs",
		"TabsList",
		"TabsTrigger",
		"TabsContent",
		"TabItem",
		"Separator",
		"ScrollArea",
		"Collapsible",
		"CollapsibleTrigger",
		"CollapsibleContent",
		"Accordion",
		"AccordionItem",
		"AccordionTrigger",
		"AccordionContent",

		// Typography
		"Heading",
		"Text",

		// Data Display
		"DataTable",
		"Table",
		"TableHeader",
		"TableBody",
		"TableFooter",
		"TableHead",
		"TableRow",
		"TableCell",
		"TableCaption",
		"Badge",
		"Avatar",
		"AvatarImage",
		"AvatarFallback",
		"Progress",
		"Skeleton",
		"Stat",
		"Calendar",
		"HoverCard",
		"HoverCardTrigger",
		"HoverCardContent",
		"Tooltip",
		"TooltipTrigger",
		"TooltipContent",
		"TooltipProvider",

		// Forms
		"Form",
		"FormField",
		"FormItem",
		"FormLabel",
		"FormControl",
		"FormDescription",
		"FormMessage",
		"Input",
		"Textarea",
		"TextInput",
		"TextArea",
		"NumberInput",
		"Select",
		"SelectTrigger",
		"SelectValue",
		"SelectContent",
		"SelectItem",
		"SelectGroup",
		"SelectLabel",
		"SelectSeparator",
		"Checkbox",
		"Switch",
		"RadioGroup",
		"RadioGroupItem",
		"Label",
		"Slider",
		"DatePicker",
		"FileUpload",
		"Command",
		"CommandInput",
		"CommandList",
		"CommandEmpty",
		"CommandGroup",
		"CommandItem",
		"CommandSeparator",
		"Combobox",
		"Popover",
		"PopoverTrigger",
		"PopoverContent",

		// Actions
		"Button",
		"Link",
		"Toggle",
		"ToggleGroup",
		"ToggleGroupItem",
		"DropdownMenu",
		"DropdownMenuTrigger",
		"DropdownMenuContent",
		"DropdownMenuItem",
		"DropdownMenuCheckboxItem",
		"DropdownMenuRadioItem",
		"DropdownMenuLabel",
		"DropdownMenuSeparator",
		"DropdownMenuShortcut",
		"DropdownMenuGroup",
		"DropdownMenuSub",
		"DropdownMenuSubContent",
		"DropdownMenuSubTrigger",
		"DropdownMenuRadioGroup",
		"ContextMenu",
		"ContextMenuTrigger",
		"ContextMenuContent",
		"ContextMenuItem",
		"ContextMenuCheckboxItem",
		"ContextMenuRadioItem",
		"ContextMenuLabel",
		"ContextMenuSeparator",
		"ContextMenuShortcut",
		"ContextMenuGroup",
		"ContextMenuSub",
		"ContextMenuSubContent",
		"ContextMenuSubTrigger",
		"ContextMenuRadioGroup",
		"Menubar",
		"MenubarMenu",
		"MenubarTrigger",
		"MenubarContent",
		"MenubarItem",
		"MenubarSeparator",
		"MenubarLabel",
		"MenubarCheckboxItem",
		"MenubarRadioGroup",
		"MenubarRadioItem",
		"MenubarShortcut",
		"MenubarSub",
		"MenubarSubContent",
		"MenubarSubTrigger",

		// Feedback
		"Dialog",
		"DialogTrigger",
		"DialogContent",
		"DialogHeader",
		"DialogFooter",
		"DialogTitle",
		"DialogDescription",
		"DialogClose",
		"Modal",
		"Alert",
		"AlertTitle",
		"AlertDescription",
		"AlertDialog",
		"AlertDialogTrigger",
		"AlertDialogContent",
		"AlertDialogHeader",
		"AlertDialogFooter",
		"AlertDialogTitle",
		"AlertDialogDescription",
		"AlertDialogAction",
		"AlertDialogCancel",
		"Toast",
		"Toaster",
		"Sheet",
		"SheetTrigger",
		"SheetContent",
		"SheetHeader",
		"SheetFooter",
		"SheetTitle",
		"SheetDescription",
		"SheetClose",
		"Drawer",
		"DrawerTrigger",
		"DrawerContent",
		"DrawerHeader",
		"DrawerFooter",
		"DrawerTitle",
		"DrawerDescription",
		"DrawerClose",

		// Navigation
		"Breadcrumb",
		"BreadcrumbList",
		"BreadcrumbItem",
		"BreadcrumbLink",
		"BreadcrumbPage",
		"BreadcrumbSeparator",
		"BreadcrumbEllipsis",
		"NavigationMenu",
		"NavigationMenuList",
		"NavigationMenuItem",
		"NavigationMenuTrigger",
		"NavigationMenuContent",
		"NavigationMenuLink",
		"NavigationMenuIndicator",
		"NavigationMenuViewport",
		"Pagination",
		"PaginationContent",
		"PaginationItem",
		"PaginationLink",
		"PaginationPrevious",
		"PaginationNext",
		"PaginationEllipsis",
		"Sidebar",
		"SidebarHeader",
		"SidebarNav",
		"SidebarLink",
		"SidebarFooter",
		"SidebarContent",
		"SidebarGroup",
		"SidebarGroupLabel",
		"SidebarGroupContent",
		"SidebarMenu",
		"SidebarMenuItem",
		"SidebarMenuButton",
		"SidebarMenuSub",
		"SidebarMenuSubItem",
		"SidebarMenuSubButton",
		"SidebarTrigger",
		"SidebarInset",
		"SidebarProvider",
		"SidebarRail",
		"SidebarSeparator",

		// Layout primitives
		"AspectRatio",
		"Resizable",
		"ResizableHandle",
		"ResizablePanel",
		"ResizablePanelGroup",

		// Data input
		"InputOTP",
		"InputOTPGroup",
		"InputOTPSlot",
		"InputOTPSeparator",

		// Charts (if using Recharts through shadcn)
		"ChartContainer",
		"ChartTooltip",
		"ChartTooltipContent",
		"ChartLegend",
		"ChartLegendContent",

		// Misc
		"Carousel",
		"CarouselContent",
		"CarouselItem",
		"CarouselPrevious",
		"CarouselNext",

		// Outlet for layouts
		"Outlet",
	]);

	return builtIns.has(name);
}
