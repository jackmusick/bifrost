import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import {
	Plus,
	Search,
	MessageSquare,
	FolderKanban,
	Sparkles,
	Settings2,
	Pin,
	MoreHorizontal,
	Bot,
	Layers,
	Check,
	ChevronRight,
	Folder,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Composer } from "../components/Composer";
import { MESSAGES, TIER_GLYPH } from "../mock";

const NAV = [
	{ icon: Plus, label: "New chat", primary: true },
	{ icon: FolderKanban, label: "Workspaces" },
	{ icon: Sparkles, label: "Artifacts" },
	{ icon: Settings2, label: "Customize" },
];

const PINNED = [
	{ id: "p1", title: "Onboarding playbook", preview: "Section 3 still needs..." },
	{ id: "p2", title: "Acme Corp setup", preview: "I created the initial folder..." },
];
const RECENT = [
	{ id: "r1", title: "VPN performance — Acme", preview: "Likely the inbound rule on FortiGate", ts: "30m" },
	{ id: "r2", title: "Welcome email draft", preview: "Here's a polished version", ts: "2h" },
	{ id: "r3", title: "Outlook crash loop — RKL", preview: "Try resetting the autodiscover", ts: "4h" },
	{ id: "r4", title: "Office365 baseline", preview: "All conditional access policies validated", ts: "yest" },
];

export function FullChat() {
	const [active, setActive] = useState("p2");

	return (
		<div className="flex h-screen bg-background overflow-hidden">
			{/* Sidebar */}
			<aside className="w-72 border-r bg-sidebar text-sidebar-foreground flex flex-col">
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
							placeholder="Search chats"
							className="h-8 pl-8 text-sm"
						/>
					</div>
				</div>

				{PINNED.length > 0 && (
					<div className="px-2 pb-1">
						<div className="px-2 py-1 text-[10px] font-medium tracking-wider uppercase text-muted-foreground">
							Pinned
						</div>
						<div className="space-y-0.5">
							{PINNED.map((c) => (
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

				<div className="px-2 pb-2 flex-1 overflow-y-auto">
					<div className="px-2 py-1 text-[10px] font-medium tracking-wider uppercase text-muted-foreground">
						Recent
					</div>
					<div className="space-y-0.5">
						{RECENT.map((c) => (
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

			{/* Main */}
			<main className="flex-1 flex flex-col overflow-hidden relative">
				<div className="h-14 border-b flex items-center justify-between px-4 gap-4 shrink-0">
					<div className="min-w-0 flex-1">
						<h1 className="text-sm font-medium truncate">Acme Corp setup</h1>
						<div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
							<Folder className="size-3" />
							<span>Customer Onboarding</span>
							<span>·</span>
							<Bot className="size-3" />
							<span>Onboarding Assistant</span>
						</div>
					</div>
					<div className="flex items-center gap-3 shrink-0">
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger asChild>
									<div className="flex items-center gap-2">
										<Progress value={32} className="w-20 h-1.5" />
										<span className="text-xs tabular-nums text-muted-foreground">
											32k / 200k
										</span>
									</div>
								</TooltipTrigger>
								<TooltipContent side="bottom" className="text-xs">
									System: 3.2k · Knowledge: 8k · History: 21k
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
						<div className="flex items-center gap-0.5 text-xs text-muted-foreground">
							⚡ ⚡ ⚖ ⚖ ⚖ 💎 💎 ⚡
						</div>
						<button className="p-1 rounded-md hover:bg-accent">
							<MoreHorizontal className="size-4 text-muted-foreground" />
						</button>
					</div>
				</div>

				<div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 pb-40">
					{MESSAGES.map((m) => {
						if (m.role === "user") {
							return (
								<div key={m.id} className="flex justify-end">
									<div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-3.5 py-2 text-sm max-w-md">
										{m.content}
									</div>
								</div>
							);
						}
						return (
							<div key={m.id} className="flex gap-3">
								<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
									<Bot className="size-4" />
								</div>
								<div className="flex-1 space-y-2">
									{m.delegated && (
										<div className="rounded-md border bg-card border-l-2 border-l-primary">
											<div className="w-full flex items-center gap-2 p-3 text-left">
												<Check className="size-4 text-primary shrink-0" />
												<div className="flex-1 min-w-0">
													<div className="text-xs font-medium">
														Consulted{" "}
														<span className="text-primary">
															{m.delegated.agent_name}
														</span>
													</div>
													<div className="text-[11px] text-muted-foreground">
														{m.delegated.description}
													</div>
												</div>
												<ChevronRight className="size-4 text-muted-foreground" />
											</div>
										</div>
									)}
									<div className="text-sm whitespace-pre-wrap">{m.content}</div>
									{m.tier && (
										<div className="text-xs text-muted-foreground flex items-center gap-2">
											<span>{TIER_GLYPH[m.tier]} {m.tier}</span>
											<span>·</span>
											<span>{m.tokens} tokens</span>
										</div>
									)}
								</div>
							</div>
						);
					})}

					<div className="relative flex items-center gap-3 py-1">
						<div className="flex-1 border-t border-border" />
						<div className="flex items-center gap-1.5 text-xs italic text-muted-foreground">
							<Layers className="size-3.5" />
							Compacted 4 earlier turns to free context space
						</div>
						<div className="flex-1 border-t border-border" />
					</div>
				</div>

				{/* Floating composer */}
				<div className="absolute inset-x-0 bottom-0">
					<Composer
						placeholder="Reply to Onboarding Assistant…"
						model="Balanced"
						tier="balanced"
					/>
				</div>
			</main>
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
