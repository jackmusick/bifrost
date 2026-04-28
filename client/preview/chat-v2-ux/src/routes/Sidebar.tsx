import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Plus,
	Search,
	MessageSquare,
	FolderKanban,
	Sparkles,
	Settings2,
	Pin,
	MoreHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";

const PINNED = [
	{ id: "p1", title: "Onboarding playbook", preview: "Section 3 still needs..." },
	{ id: "p2", title: "Acme Corp setup", preview: "I created the initial folder..." },
];

const RECENT = [
	{
		id: "r1",
		title: "VPN performance — Acme",
		preview: "Likely the inbound rule on FortiGate",
		ts: "30m",
	},
	{
		id: "r2",
		title: "Welcome email draft",
		preview: "Here's a polished version",
		ts: "2h",
	},
	{
		id: "r3",
		title: "Outlook crash loop — RKL",
		preview: "Try resetting the autodiscover",
		ts: "4h",
	},
	{
		id: "r4",
		title: "Office365 baseline",
		preview: "All conditional access policies validated",
		ts: "yest",
	},
	{
		id: "r5",
		title: "Quick notes",
		preview: "Need to follow up with the customer",
		ts: "2d",
	},
	{
		id: "r6",
		title: "Recipe ideas for tonight",
		preview: "What's in the fridge",
		ts: "3d",
	},
];

const NAV = [
	{ icon: Plus, label: "New chat", primary: true },
	{ icon: FolderKanban, label: "Workspaces" },
	{ icon: Sparkles, label: "Artifacts" },
	{ icon: Settings2, label: "Customize" },
];

export function Sidebar() {
	const [active, setActive] = useState<string | null>("p2");
	const [search, setSearch] = useState("");

	const filteredPinned = search
		? PINNED.filter((c) =>
				(c.title + c.preview).toLowerCase().includes(search.toLowerCase()),
			)
		: PINNED;
	const filteredRecent = search
		? RECENT.filter((c) =>
				(c.title + c.preview).toLowerCase().includes(search.toLowerCase()),
			)
		: RECENT;

	return (
		<div className="flex">
			<aside className="w-72 h-screen border-r bg-sidebar text-sidebar-foreground flex flex-col">
				{/* Top primary nav */}
				<div className="p-2 border-b space-y-0.5">
					{NAV.map(({ icon: Icon, label, primary }) => (
						<button
							key={label}
							className={cn(
								"w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm",
								primary
									? "font-medium hover:bg-sidebar-accent"
									: "text-sidebar-foreground/85 hover:bg-sidebar-accent",
							)}
						>
							<Icon className="size-4" />
							<span>{label}</span>
						</button>
					))}
				</div>

				<div className="p-2">
					<div className="relative">
						<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
						<Input
							value={search}
							onChange={(e) => setSearch(e.target.value)}
							placeholder="Search chats"
							className="h-8 pl-8 text-sm"
						/>
					</div>
				</div>

				{/* Pinned */}
				{filteredPinned.length > 0 && (
					<div className="px-2 pb-1">
						<div className="px-2 py-1 text-[10px] font-medium tracking-wider uppercase text-muted-foreground">
							Pinned
						</div>
						<div className="space-y-0.5">
							{filteredPinned.map((c) => (
								<ChatRow
									key={c.id}
									title={c.title}
									preview={c.preview}
									pinned
									active={active === c.id}
									onClick={() => setActive(c.id)}
								/>
							))}
						</div>
					</div>
				)}

				{/* Recent */}
				<div className="px-2 pb-2 flex-1 overflow-y-auto">
					{filteredPinned.length > 0 && filteredRecent.length > 0 && (
						<div className="px-2 py-1 text-[10px] font-medium tracking-wider uppercase text-muted-foreground">
							Recent
						</div>
					)}
					<div className="space-y-0.5">
						{filteredRecent.map((c) => (
							<ChatRow
								key={c.id}
								title={c.title}
								preview={c.preview}
								ts={c.ts}
								active={active === c.id}
								onClick={() => setActive(c.id)}
							/>
						))}
					</div>
				</div>

				<div className="p-3 border-t">
					<div className="flex items-center gap-2 text-xs">
						<div className="size-7 rounded-full bg-primary/10 text-primary flex items-center justify-center font-medium text-xs">
							JM
						</div>
						<div className="min-w-0 flex-1">
							<div className="font-medium truncate">Jack Musick</div>
							<div className="text-[10px] text-muted-foreground truncate">
								gocovi.com · Senior Tech
							</div>
						</div>
						<button className="text-muted-foreground hover:text-foreground p-1 rounded">
							<MoreHorizontal className="size-3.5" />
						</button>
					</div>
				</div>
			</aside>

			<div className="flex-1 p-8 overflow-y-auto bg-background max-w-2xl">
				<h1 className="text-xl font-medium mb-4">Sidebar</h1>
				<div className="space-y-3 text-sm text-muted-foreground">
					<p>
						Refactored to match what you described. <strong className="text-foreground">No workspace folder tree.</strong>
					</p>
					<ul className="list-disc pl-5 space-y-1.5">
						<li>
							Top: primary nav — New chat, Workspaces (destination, not
							folder), Artifacts, Customize. Same shape as the screenshot
							you shared.
						</li>
						<li>
							Search box.
						</li>
						<li>
							Pinned section, then Recent. Both are flat lists across all
							your accessible chats — workspace doesn't fragment them.
						</li>
						<li>
							Workspace context appears <em>inside</em> the chat (right
							rail, when you're in a workspace), not in this sidebar.
						</li>
						<li>
							User block at the bottom (account / org / role context).
						</li>
					</ul>
					<p className="text-xs pt-3 border-t">
						See <code>/workspace-settings</code> for what entering a
						workspace looks like (right rail with context, scoped chat
						list, etc.) — that's where workspace-as-mode shows up.
					</p>
				</div>
			</div>
		</div>
	);
}

function ChatRow({
	title,
	preview,
	ts,
	pinned,
	active,
	onClick,
}: {
	title: string;
	preview: string;
	ts?: string;
	pinned?: boolean;
	active?: boolean;
	onClick?: () => void;
}) {
	return (
		<div
			onClick={onClick}
			className={cn(
				"group px-2 py-1.5 rounded-md cursor-pointer text-sm",
				active
					? "bg-sidebar-primary text-sidebar-primary-foreground"
					: "hover:bg-sidebar-accent",
			)}
		>
			<div className="flex items-center gap-2">
				{pinned ? (
					<Pin
						className={cn(
							"size-3 shrink-0",
							active ? "opacity-100" : "opacity-50",
						)}
					/>
				) : (
					<MessageSquare className="size-3.5 shrink-0 opacity-60" />
				)}
				<span className="font-medium truncate">{title}</span>
				{ts && (
					<span
						className={cn(
							"ml-auto text-[10px] opacity-0 group-hover:opacity-70",
							active && "text-sidebar-primary-foreground",
						)}
					>
						{ts}
					</span>
				)}
			</div>
			<div
				className={cn(
					"text-xs truncate mt-0.5",
					active
						? "text-sidebar-primary-foreground/70"
						: "text-muted-foreground",
				)}
			>
				{preview}
			</div>
		</div>
	);
}
