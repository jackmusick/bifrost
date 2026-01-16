/**
 * App Shell Component
 *
 * Provides a self-contained layout for running App Builder applications.
 * Includes a header with app branding and a sidebar for multi-page navigation.
 */

import { useState, useMemo } from "react";
import { NavLink, useNavigate, Outlet } from "react-router-dom";
import {
	ChevronDown,
	Home,
	Menu,
	PanelLeftClose,
	PanelLeft,
	X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/contexts/AuthContext";
import type {
	ApplicationDefinition,
	NavItem,
	ExpressionContext,
	WorkflowResult,
} from "@/types/app-builder";
import { evaluateExpression } from "@/lib/expression-parser";
import { hasPageAccess } from "@/lib/app-builder-permissions";
import { getIcon } from "@/lib/icons";
import { WorkflowStatusIndicator } from "./WorkflowStatusIndicator";
import { AppUpdateIndicator } from "./AppUpdateIndicator";
import { NewVersionBanner } from "./NewVersionBanner";
import { useAppBuilderStore } from "@/stores/app-builder.store";

interface AppShellProps {
	/** The application definition */
	app: ApplicationDefinition;
	/** Current page ID */
	currentPageId?: string;
	/** Avatar URL for the current user */
	avatarUrl?: string | null;
	/** Whether to show the back button */
	showBackButton?: boolean;
	/** Children to render in the main content area (alternative to Outlet) */
	children?: React.ReactNode;
	/** Map of execution ID to workflow name for active workflows */
	activeWorkflowNames?: Map<string, string>;
	/** Result of the last completed workflow */
	lastCompletedResult?: WorkflowResult;
	/** Callback to clear the workflow result after display */
	onClearWorkflowResult?: () => void;
	/**
	 * Custom navigation handler for page changes.
	 * When provided, sidebar links will call this instead of using react-router.
	 * Useful for editor preview mode where we want to stay on the editor page.
	 */
	onNavigate?: (pageId: string) => void;
	/** Info about the last app update (for showing attribution) */
	lastUpdate?: { userName: string; timestamp: Date } | null;
	/** Whether a new published version is available */
	newVersionAvailable?: boolean;
	/** Callback to refresh the app when new version is clicked */
	onRefresh?: () => void;
	/** Whether we're in preview mode (affects header sticky positioning) */
	isPreview?: boolean;
}

/**
 * App Shell provides the chrome around a running App Builder application.
 * It handles navigation between pages and provides a consistent header/sidebar.
 */
export function AppShell({
	app,
	currentPageId,
	avatarUrl,
	showBackButton = true,
	children,
	activeWorkflowNames,
	lastCompletedResult,
	onClearWorkflowResult,
	onNavigate,
	lastUpdate,
	newVersionAvailable,
	onRefresh,
	isPreview: _isPreview = false,
}: AppShellProps) {
	const navigate = useNavigate();
	// Get base path from store - correctly handles preview mode
	const basePath = useAppBuilderStore((state) => state.getBasePath());
	const { user, logout } = useAuth();
	const [isCollapsed, setIsCollapsed] = useState(false);
	const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

	const userName = user?.name || user?.email?.split("@")[0] || "User";
	const userEmail = user?.email || "";

	// Get current page
	const currentPage = useMemo(() => {
		if (!currentPageId) return app.pages[0];
		return app.pages.find((p) => p.id === currentPageId) || app.pages[0];
	}, [app.pages, currentPageId]);

	// Build navigation items from navigation config or default from pages
	const navItems = useMemo((): NavItem[] => {
		if (app.navigation?.sidebar && app.navigation.sidebar.length > 0) {
			return app.navigation.sidebar;
		}
		// Generate default navigation from pages
		return app.pages.map((page) => ({
			id: page.id,
			label: page.title,
			icon: "home",
			path: page.path,
		}));
	}, [app.navigation, app.pages]);

	// Expression context for visibility evaluation
	const expressionContext: Partial<ExpressionContext> = useMemo(
		() => ({
			user: user
				? {
						id: user.id,
						name: user.name || "",
						email: user.email || "",
						role: user.roles?.[0] || "user",
					}
				: undefined,
			variables: {},
			data: {},
		}),
		[user],
	);

	// Get user roles for permission checks
	const userRoles = useMemo(() => user?.roles || [], [user?.roles]);

	// Filter visible nav items based on visibility expressions and page permissions
	const visibleNavItems = useMemo(() => {
		return navItems.filter((item) => {
			// Check visibility expression
			if (item.visible) {
				try {
					if (
						evaluateExpression(
							item.visible,
							expressionContext as ExpressionContext,
						) === false
					) {
						return false;
					}
				} catch {
					return true;
				}
			}

			// Check page-level permissions
			const page = app.pages.find((p) => p.id === item.id);
			if (page && page.permission) {
				return hasPageAccess(page, userRoles, expressionContext);
			}

			return true;
		});
	}, [navItems, expressionContext, app.pages, userRoles]);

	const showSidebar = app.navigation?.show_sidebar !== false;
	// showHeader is defined in navigation config but header is always shown currently
	// Can be used in the future to hide the header for embedded apps

	// Get initials for avatar
	const getInitials = () => {
		if (user?.name) {
			return user.name
				.split(" ")
				.map((n) => n[0])
				.join("")
				.toUpperCase()
				.slice(0, 2);
		}
		return userEmail[0]?.toUpperCase() || "U";
	};

	const hasMultiplePages = app.pages.length > 1 && showSidebar;

	return (
		<div className="flex flex-1 bg-background overflow-hidden">
			{/* Desktop Sidebar - Only show if multiple pages */}
			{hasMultiplePages && (
				<aside
					className={cn(
						"hidden md:flex flex-col h-full bg-background transition-all duration-300",
						isCollapsed ? "w-16" : "w-64",
					)}
				>
					{/* App Title */}
					<div
						className={cn(
							"flex items-center flex-shrink-0",
							isCollapsed
								? "justify-center px-4 h-16"
								: "justify-start px-4 lg:px-6 h-16",
						)}
					>
						{isCollapsed ? (
							<div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
								<span className="text-lg font-bold text-primary">
									{app.name[0]?.toUpperCase()}
								</span>
							</div>
						) : (
							<h1 className="text-lg font-semibold truncate">
								{app.name}
							</h1>
						)}
					</div>

					{/* Page Navigation */}
					<nav
						className={cn(
							"flex-1 flex flex-col gap-1 overflow-y-auto",
							isCollapsed ? "px-2 py-4" : "p-4",
						)}
					>
						{visibleNavItems.map((item) => {
							const IconComponent = getIcon(item.icon);
							const page = app.pages.find(
								(p) => p.id === item.id,
							);
							// Normalize path to avoid double slashes
							const path = (
								item.path ||
								page?.path ||
								""
							).replace(/^\//, "");

							// Section headers
							if (item.is_section) {
								if (isCollapsed) return null;
								return (
									<div
										key={item.id}
										className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground mt-2 first:mt-0"
									>
										{item.label}
									</div>
								);
							}

							// Check if this nav item is currently active
							const isCurrentPage =
								item.id === currentPageId ||
								(currentPage &&
									(item.id === currentPage.id ||
										path === currentPage.path?.replace(/^\//, "")));

							const linkClassName = cn(
								"flex items-center text-sm font-medium transition-colors rounded-md",
								"hover:bg-accent hover:text-accent-foreground",
								isCurrentPage
									? "bg-accent text-accent-foreground"
									: "text-muted-foreground",
								isCollapsed
									? "justify-center w-10 h-10 mx-auto"
									: "gap-3 px-3 py-2",
							);

							// If onNavigate is provided, use button instead of router NavLink
							if (onNavigate) {
								return (
									<button
										key={item.id}
										type="button"
										title={isCollapsed ? item.label : undefined}
										className={linkClassName}
										onClick={() => onNavigate(item.id)}
									>
										<IconComponent
											className={cn(
												isCollapsed ? "h-5 w-5" : "h-4 w-4",
											)}
										/>
										{!isCollapsed && item.label}
									</button>
								);
							}

							return (
								<NavLink
									key={item.id}
									to={`${basePath}/${path}`}
									title={isCollapsed ? item.label : undefined}
									className={linkClassName}
								>
									<IconComponent
										className={cn(
											isCollapsed ? "h-5 w-5" : "h-4 w-4",
										)}
									/>
									{!isCollapsed && item.label}
								</NavLink>
							);
						})}
					</nav>
				</aside>
			)}

			{/* Mobile Sidebar Overlay */}
			{hasMultiplePages && isMobileMenuOpen && (
				<div
					className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm md:hidden"
					onClick={() => setIsMobileMenuOpen(false)}
				>
					<aside
						className="fixed left-0 top-0 h-screen w-64 border-r bg-background flex flex-col"
						onClick={(e) => e.stopPropagation()}
					>
						{/* App Title with Close */}
						<div className="h-16 flex items-center justify-between border-b px-4">
							<h1 className="text-lg font-semibold truncate">
								{app.name}
							</h1>
							<Button
								variant="ghost"
								size="icon"
								onClick={() => setIsMobileMenuOpen(false)}
							>
								<X className="h-5 w-5" />
							</Button>
						</div>

						{/* Page Navigation */}
						<nav className="flex-1 flex flex-col gap-1 p-4 overflow-y-auto">
							{visibleNavItems.map((item) => {
								const IconComponent = getIcon(item.icon);
								const page = app.pages.find(
									(p) => p.id === item.id,
								);
								// Normalize path to avoid double slashes
								const path = (
									item.path ||
									page?.path ||
									""
								).replace(/^\//, "");

								// Section headers
								if (item.is_section) {
									return (
										<div
											key={item.id}
											className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground mt-2 first:mt-0"
										>
											{item.label}
										</div>
									);
								}

								// Check if this nav item is currently active
								const isCurrentPage =
									item.id === currentPageId ||
									(currentPage &&
										(item.id === currentPage.id ||
											path === currentPage.path?.replace(/^\//, "")));

								const mobileLinkClassName = cn(
									"flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors rounded-md",
									"hover:bg-accent hover:text-accent-foreground",
									isCurrentPage
										? "bg-accent text-accent-foreground"
										: "text-muted-foreground",
								);

								// If onNavigate is provided, use button instead of router NavLink
								if (onNavigate) {
									return (
										<button
											key={item.id}
											type="button"
											className={mobileLinkClassName}
											onClick={() => {
												onNavigate(item.id);
												setIsMobileMenuOpen(false);
											}}
										>
											<IconComponent className="h-4 w-4" />
											{item.label}
										</button>
									);
								}

								return (
									<NavLink
										key={item.id}
										to={`${basePath}/${path}`}
										onClick={() =>
											setIsMobileMenuOpen(false)
										}
										className={mobileLinkClassName}
									>
										<IconComponent className="h-4 w-4" />
										{item.label}
									</NavLink>
								);
							})}
						</nav>
					</aside>
				</div>
			)}

			{/* Main Content Area */}
			<div className="flex-1 flex flex-col min-w-0 h-full border-l">
				{/* Header */}
				<header className="flex-shrink-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
					<div className="flex h-16 items-center px-4 lg:px-6">
						{/* Mobile Menu Button */}
						{hasMultiplePages && (
							<Button
								variant="ghost"
								size="icon"
								className="md:hidden mr-2"
								onClick={() => setIsMobileMenuOpen(true)}
							>
								<Menu className="h-5 w-5" />
							</Button>
						)}

						{/* Desktop Sidebar Toggle */}
						{hasMultiplePages && (
							<Button
								variant="ghost"
								size="icon"
								className="hidden md:flex mr-2"
								onClick={() => setIsCollapsed(!isCollapsed)}
								title={
									isCollapsed
										? "Expand sidebar"
										: "Collapse sidebar"
								}
							>
								{isCollapsed ? (
									<PanelLeft className="h-5 w-5" />
								) : (
									<PanelLeftClose className="h-5 w-5" />
								)}
							</Button>
						)}

						{/* Back Button */}
						{showBackButton && (
							<Button
								variant="ghost"
								size="sm"
								onClick={() => navigate("/apps")}
								className="mr-4"
							>
								<Home className="h-4 w-4 mr-2" />
								Back to Apps
							</Button>
						)}

						{/* App Name (single page apps or collapsed sidebar) */}
						{(!hasMultiplePages || isCollapsed) && (
							<h1 className="text-lg font-semibold truncate mr-4">
								{app.name}
							</h1>
						)}

						{/* Current Page Title */}
						{currentPage && hasMultiplePages && (
							<span className="text-sm text-muted-foreground hidden md:inline">
								{currentPage.title}
							</span>
						)}

						{/* Workflow Status Indicator */}
						{activeWorkflowNames && (
							<div className="ml-4 hidden sm:block">
								<WorkflowStatusIndicator
									activeWorkflowNames={activeWorkflowNames}
									lastCompletedResult={lastCompletedResult}
									onClearResult={onClearWorkflowResult}
								/>
							</div>
						)}

						{/* App Update Indicator */}
						{lastUpdate && (
							<div className="ml-4 hidden sm:block">
								<AppUpdateIndicator lastUpdate={lastUpdate} />
							</div>
						)}

						{/* New Version Banner */}
						{newVersionAvailable && onRefresh && (
							<div className="ml-4 hidden sm:block">
								<NewVersionBanner
									isVisible={newVersionAvailable}
									onRefresh={onRefresh}
								/>
							</div>
						)}

						{/* Spacer */}
						<div className="flex-1" />

						{/* Theme Toggle */}
						<div className="mr-2">
							<ThemeToggle />
						</div>

						{/* User Menu */}
						<DropdownMenu>
							<DropdownMenuTrigger asChild>
								<Button variant="ghost" className="gap-2">
									<Avatar className="h-6 w-6">
										<AvatarImage
											src={avatarUrl || undefined}
										/>
										<AvatarFallback className="text-xs">
											{getInitials()}
										</AvatarFallback>
									</Avatar>
									<span className="hidden md:inline-block">
										{userName}
									</span>
									<ChevronDown className="h-4 w-4" />
								</Button>
							</DropdownMenuTrigger>
							<DropdownMenuContent align="end" className="w-48">
								<DropdownMenuItem onClick={logout}>
									Log out
								</DropdownMenuItem>
							</DropdownMenuContent>
						</DropdownMenu>
					</div>
				</header>

				{/* Page Content */}
				<main className="flex-1 overflow-auto p-6">
					{children || <Outlet />}
				</main>
			</div>
		</div>
	);
}

/**
 * Minimal App Shell for embedded apps
 * No header, just the content
 */
export function AppShellMinimal({ children }: { children: React.ReactNode }) {
	return (
		<div className="min-h-screen bg-background">
			<main className="p-6">{children}</main>
		</div>
	);
}
