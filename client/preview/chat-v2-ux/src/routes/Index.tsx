import { Link } from "react-router-dom";
import {
	MessageSquare,
	Folder,
	GitBranch,
	Cpu,
	Settings,
	Paperclip,
	Pencil,
	Layers,
	Users,
} from "lucide-react";

const SURFACES = [
	{
		to: "/full",
		icon: MessageSquare,
		title: "Full chat (composed)",
		desc: "All surfaces wired together — sidebar + header + messages + input. Click around.",
	},
	{
		to: "/sidebar",
		icon: Folder,
		title: "Sidebar (global)",
		desc: "Top primary nav (New chat, Workspaces, Artifacts, Customize). Pinned + Recent. No workspace folder tree — workspace is a destination, not a container in the sidebar.",
	},
	{
		to: "/header",
		icon: GitBranch,
		title: "Chat header",
		desc: "Visible-to-everyone model pill, context budget bar, cost tier strip. Compact button when budget is tight.",
	},
	{
		to: "/picker",
		icon: Cpu,
		title: "Model picker",
		desc: "OpenRouter-style. Aliases at top, available models, then a 'Restricted' section with provenance tooltips.",
	},
	{
		to: "/workspace-settings",
		icon: Folder,
		title: "Workspace mode",
		desc: "What entering a workspace looks like — sidebar re-scopes to the workspace's chats, right rail shows context (instructions, knowledge, tools, models, baseline cost). 'All chats' button at the top to exit.",
	},
	{
		to: "/admin-settings",
		icon: Settings,
		title: "Admin AI settings",
		desc: "Org model availability table + aliases + save-time orphan reference AlertDialog.",
	},
	{
		to: "/attachments",
		icon: Paperclip,
		title: "Attachments",
		desc: "Drag-drop overlay, attachment chips above the textarea, paste-screenshot, PDF token estimate.",
	},
	{
		to: "/edit-retry",
		icon: Pencil,
		title: "Edit + retry",
		desc: "Edit user message inline (with destructive AlertDialog), retry assistant message with optional model override.",
	},
	{
		to: "/compaction",
		icon: Layers,
		title: "Compaction",
		desc: "Inline ChatSystemEvent showing 'Compacted N earlier turns'. Persistent in scrollback.",
	},
	{
		to: "/delegation",
		icon: Users,
		title: "Multi-agent delegation",
		desc: "Inline Card embedded in the primary agent's response showing what a delegated agent contributed.",
	},
];

export function Index() {
	return (
		<div className="max-w-4xl mx-auto p-8 space-y-6">
			<div>
				<h1 className="text-2xl font-medium tracking-tight">
					Chat V2 — UX preview
				</h1>
				<p className="text-sm text-muted-foreground mt-1">
					Click any surface to see how it behaves. These prototypes are
					not connected to a real Bifrost backend; all data is mocked and
					all interactions are local.
				</p>
			</div>
			<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
				{SURFACES.map(({ to, icon: Icon, title, desc }) => (
					<Link
						to={to}
						key={to}
						className="group block p-4 rounded-md border bg-card hover:bg-accent/40 transition-colors"
					>
						<div className="flex items-start gap-3">
							<div className="rounded-md bg-primary/10 text-primary p-2">
								<Icon className="size-5" />
							</div>
							<div className="min-w-0">
								<div className="font-medium text-sm group-hover:text-primary">
									{title}
								</div>
								<div className="text-xs text-muted-foreground mt-1">
									{desc}
								</div>
							</div>
						</div>
					</Link>
				))}
			</div>
			<div className="text-xs text-muted-foreground border-t pt-4">
				Spec at <code>docs/superpowers/specs/2026-04-27-chat-ux-design.md</code>.
				Every surface here corresponds to a section in §16 of that spec.
			</div>
		</div>
	);
}
