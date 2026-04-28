import { useState } from "react";
import {
	Bot,
	BookOpen,
	Wrench,
	Cpu,
	FileText,
	ChevronDown,
	Plus,
	Search,
	MessageSquare,
	Pin,
	FolderKanban,
	Sparkles,
	Settings2,
	MoreHorizontal,
	Folder,
	Layers,
	ArrowLeft,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Composer } from "../components/Composer";
import { TIER_GLYPH } from "../mock";

const WORKSPACE_CHATS = [
	{ id: "o1", title: "Acme Corp setup", preview: "I created the initial folder structure", ts: "12m", pinned: true },
	{ id: "o2", title: "Welcome email draft", preview: "Here's a polished version", ts: "1h" },
	{ id: "o3", title: "Office365 baseline", preview: "All conditional access policies validated", ts: "3d" },
];

export function WorkspaceSettings() {
	const [active, setActive] = useState("o1");

	return (
		<div className="flex h-screen bg-background overflow-hidden">
			{/* Sidebar - same shape as the global one, but scoped to this workspace */}
			<aside className="w-72 border-r bg-sidebar text-sidebar-foreground flex flex-col">
				<div className="p-2 border-b">
					<button className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-sidebar-accent">
						<ArrowLeft className="size-3.5" />
						<span>All chats</span>
					</button>
				</div>
				<div className="px-3 pt-3 pb-2 border-b">
					<div className="flex items-center gap-2">
						<div className="size-8 rounded-md bg-primary/15 text-primary flex items-center justify-center">
							<FolderKanban className="size-4" />
						</div>
						<div className="min-w-0 flex-1">
							<div className="font-medium text-sm truncate">
								Customer Onboarding
							</div>
							<div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
								<Badge
									variant="secondary"
									className="text-[9px] py-0 h-3.5 px-1 font-normal"
								>
									Org
								</Badge>
								<span>3 conversations</span>
							</div>
						</div>
					</div>
				</div>
				<div className="p-2 space-y-0.5 border-b">
					<button className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm font-medium hover:bg-sidebar-accent">
						<Plus className="size-4" />
						New chat in this workspace
					</button>
					<button className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm text-sidebar-foreground/85 hover:bg-sidebar-accent">
						<Settings2 className="size-4" />
						Workspace settings
					</button>
				</div>
				<div className="p-2">
					<div className="relative">
						<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
						<Input
							placeholder="Search this workspace"
							className="h-8 pl-8 text-sm"
						/>
					</div>
				</div>
				<div className="px-2 pb-2 flex-1 overflow-y-auto">
					<div className="space-y-0.5">
						{WORKSPACE_CHATS.map((c) => (
							<div
								key={c.id}
								onClick={() => setActive(c.id)}
								className={cn(
									"group px-2 py-1.5 rounded-md cursor-pointer text-sm",
									active === c.id
										? "bg-sidebar-primary text-sidebar-primary-foreground"
										: "hover:bg-sidebar-accent",
								)}
							>
								<div className="flex items-center gap-2">
									{c.pinned ? (
										<Pin className="size-3 shrink-0 opacity-60" />
									) : (
										<MessageSquare className="size-3.5 shrink-0 opacity-60" />
									)}
									<span className="font-medium truncate">{c.title}</span>
									<span
										className={cn(
											"ml-auto text-[10px] opacity-0 group-hover:opacity-70",
											active === c.id && "text-sidebar-primary-foreground",
										)}
									>
										{c.ts}
									</span>
								</div>
								<div
									className={cn(
										"text-xs truncate mt-0.5",
										active === c.id
											? "text-sidebar-primary-foreground/70"
											: "text-muted-foreground",
									)}
								>
									{c.preview}
								</div>
							</div>
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

			{/* Main chat area */}
			<main className="flex-1 flex flex-col overflow-hidden relative">
				{/* Header */}
				<div className="h-14 border-b flex items-center justify-between px-4 gap-4 shrink-0">
					<div className="min-w-0 flex-1">
						<h1 className="text-sm font-medium truncate">
							Acme Corp setup
						</h1>
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

				{/* Conversation */}
				<div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 pb-40">
					<div className="flex justify-end">
						<div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-3.5 py-2 text-sm max-w-md">
							Help me draft the welcome email for Acme.
						</div>
					</div>
					<div className="flex gap-3">
						<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
							<Bot className="size-4" />
						</div>
						<div className="flex-1">
							<div className="text-sm">
								Drafted below. I pulled their tenant info from the
								Acme runbook and matched the tone of last quarter's
								onboarding emails.
							</div>
							<div className="text-xs text-muted-foreground mt-2 flex items-center gap-2">
								<span>{TIER_GLYPH.balanced} Balanced</span>
								<span>·</span>
								<span>1.2k tokens</span>
							</div>
						</div>
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

			{/* Right rail — Workspace context */}
			<aside className="w-80 border-l bg-card overflow-y-auto">
				<div className="p-4 border-b">
					<div className="flex items-center justify-between mb-1">
						<div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
							Workspace
						</div>
						<button className="text-xs text-muted-foreground hover:text-foreground">
							Edit
						</button>
					</div>
					<div className="font-medium text-sm">Customer Onboarding</div>
					<div className="text-xs text-muted-foreground">
						Shared workspace for new client provisioning. M365,
						networking baselines, welcome kit.
					</div>
				</div>

				<RailSection title="Default agent" icon={Bot}>
					<RailRow icon={Bot} title="Onboarding Assistant" subtitle="default" />
				</RailSection>

				<RailSection title="Instructions" icon={FileText} count="~520 tokens">
					<div className="text-xs text-muted-foreground italic line-clamp-3">
						You are helping Acme Corp during their onboarding. Always
						reference their tenant ID (acme.onmicrosoft.com) and use British
						English spelling.
					</div>
					<button className="text-xs text-primary mt-1.5 hover:underline">
						Show full
					</button>
				</RailSection>

				<RailSection title="Knowledge" icon={BookOpen} count="3 sources · ~8.2k tokens">
					<RailRow
						icon={BookOpen}
						title="Acme runbook (2025)"
						subtitle="~4.2k"
					/>
					<RailRow
						icon={BookOpen}
						title="Onboarding checklist"
						subtitle="~1.8k"
					/>
					<RailRow
						icon={BookOpen}
						title="M365 baseline policy"
						subtitle="~2.2k"
					/>
				</RailSection>

				<RailSection title="Tools" icon={Wrench} count="5 enabled">
					<div className="flex flex-wrap gap-1">
						{[
							"create_ticket",
							"send_email",
							"search_knowledge",
							"get_user",
							"deploy_intune_profile",
						].map((t) => (
							<Badge
								key={t}
								variant="secondary"
								className="font-mono text-[10px] font-normal"
							>
								{t}
							</Badge>
						))}
					</div>
					<div className="text-[11px] text-muted-foreground mt-2">
						Workspace ∩ Agent — only tools the agent has AND the
						workspace permits are usable in chat.
					</div>
				</RailSection>

				<RailSection title="Models" icon={Cpu}>
					<RailRow
						icon={() => <span>{TIER_GLYPH.balanced}</span>}
						title="Balanced (default)"
						subtitle="Claude Sonnet 4.6"
					/>
					<div className="text-[11px] text-muted-foreground mt-1.5">
						Premium restricted — the workspace allows only Fast and
						Balanced.
					</div>
				</RailSection>

				<div className="p-4 border-t bg-muted/30">
					<div className="flex items-center gap-2 mb-1.5">
						<Layers className="size-3.5 text-muted-foreground" />
						<div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
							Baseline cost
						</div>
					</div>
					<div className="text-base font-medium tabular-nums">
						~12.7k tokens
						<span className="text-xs text-muted-foreground font-normal">
							{" "}/ message
						</span>
					</div>
					<div className="text-[11px] text-muted-foreground mt-1">
						Tools schema: 1.4k · Knowledge: 8.2k · Instructions: 0.5k ·
						System: 2.6k
					</div>
				</div>
			</aside>
		</div>
	);
}

function RailSection({
	title,
	icon: Icon,
	count,
	children,
}: {
	title: string;
	icon: React.ComponentType<{ className?: string }>;
	count?: string;
	children: React.ReactNode;
}) {
	return (
		<div className="p-4 border-b space-y-2">
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
					<Icon className="size-3.5" />
					{title}
				</div>
				{count && (
					<span className="text-[10px] text-muted-foreground tabular-nums">
						{count}
					</span>
				)}
			</div>
			{children}
		</div>
	);
}

function RailRow({
	icon: Icon,
	title,
	subtitle,
}: {
	icon: React.ComponentType<{ className?: string }>;
	title: string;
	subtitle?: string;
}) {
	return (
		<div className="flex items-center gap-2 py-1 text-sm">
			<Icon className="size-3.5 text-muted-foreground shrink-0" />
			<div className="flex-1 min-w-0 truncate">{title}</div>
			{subtitle && (
				<div className="text-[10px] text-muted-foreground tabular-nums">
					{subtitle}
				</div>
			)}
		</div>
	);
}
