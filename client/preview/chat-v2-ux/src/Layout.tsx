import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

const ROUTES = [
	{ to: "/", label: "Index" },
	{ to: "/full", label: "Full chat (composed)" },
	{ to: "/sidebar", label: "Sidebar (global)" },
	{ to: "/header", label: "Chat header" },
	{ to: "/picker", label: "Model picker" },
	{ to: "/workspace-settings", label: "Workspace mode" },
	{ to: "/admin-settings", label: "Admin AI settings" },
	{ to: "/attachments", label: "Attachments" },
	{ to: "/edit-retry", label: "Edit + retry" },
	{ to: "/compaction", label: "Compaction" },
	{ to: "/delegation", label: "Delegation" },
];

export function Layout() {
	return (
		<div className="flex h-screen bg-background text-foreground">
			<nav className="w-56 border-r bg-sidebar text-sidebar-foreground flex flex-col">
				<div className="p-4 border-b">
					<div className="font-medium text-sm">Chat V2 UX preview</div>
					<div className="text-xs text-muted-foreground mt-1">
						Bifrost spec prototypes
					</div>
				</div>
				<div className="flex-1 overflow-y-auto p-2 space-y-0.5">
					{ROUTES.map((r) => (
						<NavLink
							key={r.to}
							to={r.to}
							end={r.to === "/"}
							className={({ isActive }) =>
								cn(
									"block px-3 py-2 rounded-md text-sm",
									isActive
										? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
										: "text-sidebar-foreground/80 hover:bg-sidebar-accent/60",
								)
							}
						>
							{r.label}
						</NavLink>
					))}
				</div>
				<div className="p-3 border-t text-xs text-muted-foreground">
					<div>Read the spec:</div>
					<code className="text-[10px] break-all">
						docs/superpowers/specs/2026-04-27-chat-ux-design.md
					</code>
				</div>
			</nav>
			<main className="flex-1 overflow-y-auto">
				<Outlet />
			</main>
		</div>
	);
}
