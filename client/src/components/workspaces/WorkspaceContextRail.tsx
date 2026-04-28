/**
 * WorkspaceContextRail — chat-ux-design §16.2 right-rail.
 *
 * A passive context view of the active workspace's configuration. Editing
 * happens in the WorkspaceSettingsSheet, never inline here.
 */

import { Edit3, FolderKanban, Wrench, BookOpen, Bot } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Workspace } from "@/services/workspaceService";

interface Props {
	workspace: Workspace;
	onEdit?: () => void;
}

const SCOPE_LABEL: Record<Workspace["scope"], string> = {
	personal: "Private",
	org: "Org",
	role: "Role",
};

export function WorkspaceContextRail({ workspace, onEdit }: Props) {
	const tools = workspace.enabled_tool_ids;
	const knowledge = workspace.enabled_knowledge_source_ids;

	return (
		<aside className="hidden xl:flex flex-col w-80 shrink-0 border-l bg-card">
			<header className="px-4 py-3 border-b flex items-start justify-between gap-2">
				<div className="min-w-0 flex items-start gap-2.5">
					<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
						<FolderKanban className="h-4 w-4" />
					</div>
					<div className="min-w-0">
						<div className="flex items-center gap-2 flex-wrap">
							<span className="font-medium text-sm truncate">
								{workspace.name}
							</span>
							<Badge
								variant="secondary"
								className="text-[10px] px-1.5 py-0"
							>
								{SCOPE_LABEL[workspace.scope]}
							</Badge>
						</div>
						{workspace.description && (
							<p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
								{workspace.description}
							</p>
						)}
					</div>
				</div>
				{onEdit && (
					<Button
						variant="ghost"
						size="icon-sm"
						onClick={onEdit}
						title="Edit"
					>
						<Edit3 className="h-3.5 w-3.5" />
					</Button>
				)}
			</header>

			<div className="flex-1 overflow-y-auto px-4 py-3 space-y-5 text-sm">
				<Section
					icon={<Bot className="h-3.5 w-3.5" />}
					label="Default agent"
				>
					{workspace.default_agent_id ? (
						<span className="font-mono text-xs text-muted-foreground">
							{workspace.default_agent_id}
						</span>
					) : (
						<MutedNote>No default agent</MutedNote>
					)}
				</Section>

				<Section
					icon={<Edit3 className="h-3.5 w-3.5" />}
					label="Instructions"
				>
					{workspace.instructions ? (
						<p className="text-xs text-muted-foreground line-clamp-3 whitespace-pre-wrap">
							{workspace.instructions}
						</p>
					) : (
						<MutedNote>No custom instructions</MutedNote>
					)}
				</Section>

				<Section
					icon={<BookOpen className="h-3.5 w-3.5" />}
					label="Knowledge"
				>
					{knowledge && knowledge.length > 0 ? (
						<ChipRow items={knowledge} />
					) : (
						<MutedNote>No knowledge sources scoped</MutedNote>
					)}
				</Section>

				<Section
					icon={<Wrench className="h-3.5 w-3.5" />}
					label="Tools"
				>
					{tools && tools.length > 0 ? (
						<>
							<ChipRow items={tools} />
							<p className="text-[11px] text-muted-foreground mt-2">
								Effective tools = these ∩ agent's tools.
							</p>
						</>
					) : (
						<MutedNote>
							No tool restriction (agent's tools pass through).
						</MutedNote>
					)}
				</Section>
			</div>
		</aside>
	);
}

function Section({
	icon,
	label,
	children,
}: {
	icon: React.ReactNode;
	label: string;
	children: React.ReactNode;
}) {
	return (
		<section>
			<div className="flex items-center gap-1.5 text-[10px] font-medium tracking-wider uppercase text-muted-foreground mb-1.5">
				{icon}
				{label}
			</div>
			{children}
		</section>
	);
}

function ChipRow({ items }: { items: string[] }) {
	const display = items.slice(0, 6);
	const more = items.length - display.length;
	return (
		<div className="flex flex-wrap gap-1">
			{display.map((id) => (
				<Badge
					key={id}
					variant="secondary"
					className="text-[10px] px-1.5 py-0 font-mono max-w-full truncate"
				>
					{id.slice(0, 8)}
				</Badge>
			))}
			{more > 0 && (
				<Badge variant="outline" className="text-[10px] px-1.5 py-0">
					+{more}
				</Badge>
			)}
		</div>
	);
}

function MutedNote({ children }: { children: React.ReactNode }) {
	return <p className="text-xs text-muted-foreground">{children}</p>;
}
