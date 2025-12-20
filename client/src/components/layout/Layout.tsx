import { Outlet } from "react-router-dom";
import { useState } from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { NoAccess } from "@/components/NoAccess";
import { Skeleton } from "@/components/ui/skeleton";
import { PasskeySetupBanner } from "@/components/PasskeySetupBanner";

export function Layout() {
	const { isLoading, isPlatformAdmin, isOrgUser } = useAuth();
	const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
	const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
		// Load collapsed state from localStorage
		return localStorage.getItem("sidebar-collapsed") === "true";
	});

	const hasAccess = isPlatformAdmin || isOrgUser;

	// Show loading state while checking authentication
	if (isLoading) {
		return (
			<div className="min-h-screen bg-background">
				<Header />
				<div className="flex">
					<main className="flex-1 p-6 lg:p-8">
						<div className="space-y-6">
							<Skeleton className="h-12 w-64" />
							<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
								{[...Array(6)].map((_, i) => (
									<Skeleton key={i} className="h-64 w-full" />
								))}
							</div>
						</div>
					</main>
				</div>
			</div>
		);
	}

	// Show no access page if user has no role (only authenticated, no PlatformAdmin or OrgUser)
	if (!hasAccess) {
		return <NoAccess />;
	}

	const toggleSidebar = () => {
		const newState = !isSidebarCollapsed;
		setIsSidebarCollapsed(newState);
		localStorage.setItem("sidebar-collapsed", String(newState));
	};

	return (
		<div className="h-screen flex bg-background overflow-hidden">
			{/* Sidebar - full height with logo */}
			<Sidebar
				isMobileMenuOpen={isMobileMenuOpen}
				setIsMobileMenuOpen={setIsMobileMenuOpen}
				isCollapsed={isSidebarCollapsed}
			/>

			{/* Main content area with header */}
			<div className="flex-1 flex flex-col overflow-hidden">
				<Header
					onMobileMenuToggle={() => setIsMobileMenuOpen(true)}
					onSidebarToggle={toggleSidebar}
					isSidebarCollapsed={isSidebarCollapsed}
				/>
				<main className="flex-1 overflow-auto p-6 lg:p-8">
					<PasskeySetupBanner />
					<Outlet />
				</main>
			</div>
		</div>
	);
}
