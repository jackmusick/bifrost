/**
 * WorkspaceSettingsSheet — chat-ux-design §16.3.
 *
 * M1 ships General + Instructions tabs functionally; Tools / Knowledge / Models
 * tabs are placeholders that surface their underlying contract values. Rich
 * pickers (model resolver UI, tool combobox warnings) belong to later milestones.
 *
 * The inner editor mounts only while the sheet is open, so each open is a fresh
 * snapshot — no useEffect-reset gymnastics needed.
 */

import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
	useDeleteWorkspace,
	useUpdateWorkspace,
	type Workspace,
} from "@/services/workspaceService";

interface Props {
	workspace: Workspace;
	open: boolean;
	onOpenChange: (open: boolean) => void;
	canManage: boolean;
}

const SCOPE_LABEL: Record<Workspace["scope"], string> = {
	personal: "Private",
	org: "Org",
	role: "Role",
};

const SCOPE_DISPLAY: Record<Workspace["scope"], string> = {
	personal: "Private (only you)",
	org: "Shared with the organization",
	role: "Shared with a role",
};

export function WorkspaceSettingsSheet({
	workspace,
	open,
	onOpenChange,
	canManage,
}: Props) {
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				className="sm:max-w-2xl flex flex-col p-0 gap-0"
			>
				<SheetHeader className="border-b">
					<SheetTitle className="flex items-center gap-2">
						{workspace.name}
						<Badge variant="secondary" className="text-[10px]">
							{SCOPE_LABEL[workspace.scope]}
						</Badge>
					</SheetTitle>
					<SheetDescription>
						Edit workspace fields. Scope is set at creation and cannot
						be changed.
					</SheetDescription>
				</SheetHeader>
				{open && (
					<WorkspaceSettingsEditor
						workspace={workspace}
						canManage={canManage}
						onClose={() => onOpenChange(false)}
					/>
				)}
			</SheetContent>
		</Sheet>
	);
}

function WorkspaceSettingsEditor({
	workspace,
	canManage,
	onClose,
}: {
	workspace: Workspace;
	canManage: boolean;
	onClose: () => void;
}) {
	const update = useUpdateWorkspace();
	const remove = useDeleteWorkspace();

	const [name, setName] = useState(workspace.name);
	const [description, setDescription] = useState(workspace.description ?? "");
	const [instructions, setInstructions] = useState(
		workspace.instructions ?? "",
	);

	const dirty =
		name !== workspace.name ||
		description !== (workspace.description ?? "") ||
		instructions !== (workspace.instructions ?? "");

	const handleSave = () => {
		update.mutate(
			{
				params: { path: { workspace_id: workspace.id } },
				body: {
					name: name.trim() || workspace.name,
					description: description.trim() || null,
					instructions: instructions.trim() || null,
				},
			},
			{
				onSuccess: () => {
					toast.success("Workspace saved");
					onClose();
				},
				onError: (err) =>
					toast.error("Save failed", {
						description: (err as Error)?.message,
					}),
			},
		);
	};

	const handleSoftDelete = () => {
		if (!window.confirm("Delete this workspace? This is reversible.")) {
			return;
		}
		remove.mutate(
			{ params: { path: { workspace_id: workspace.id } } },
			{
				onSuccess: () => {
					toast.success("Workspace deleted");
					onClose();
				},
				onError: (err) =>
					toast.error("Delete failed", {
						description: (err as Error)?.message,
					}),
			},
		);
	};

	return (
		<>
			<Tabs
				defaultValue="general"
				className="flex-1 min-h-0 flex flex-col"
			>
				<div className="border-b px-4 pt-3">
					<TabsList className="bg-transparent gap-1">
						<TabsTrigger value="general">General</TabsTrigger>
						<TabsTrigger value="tools">Tools</TabsTrigger>
						<TabsTrigger value="knowledge">Knowledge</TabsTrigger>
						<TabsTrigger value="instructions">
							Instructions
						</TabsTrigger>
					</TabsList>
				</div>

				<TabsContent
					value="general"
					className="flex-1 overflow-y-auto px-6 py-4 space-y-4 mt-0"
				>
					<div className="space-y-1.5">
						<Label htmlFor="ws-name">Name</Label>
						<Input
							id="ws-name"
							value={name}
							onChange={(e) => setName(e.target.value)}
							disabled={!canManage}
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="ws-desc">Description</Label>
						<Textarea
							id="ws-desc"
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							rows={3}
							disabled={!canManage}
						/>
					</div>
					<div className="space-y-1.5">
						<Label>Scope</Label>
						<Input
							value={SCOPE_DISPLAY[workspace.scope]}
							disabled
						/>
						<p className="text-[11px] text-muted-foreground">
							Scope is fixed at creation.
						</p>
					</div>
				</TabsContent>

				<TabsContent
					value="tools"
					className="flex-1 overflow-y-auto px-6 py-4 space-y-3 mt-0"
				>
					<p className="text-sm text-muted-foreground">
						If set, only these tools are available in this workspace.
						The agent's tools intersect with this set — workspaces can
						restrict but never expand an agent's tool list.
					</p>
					<div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
						Tool selection coming soon. Current value:{" "}
						{workspace.enabled_tool_ids === null ||
						workspace.enabled_tool_ids === undefined
							? "no restriction"
							: `${workspace.enabled_tool_ids.length} tool(s) enabled`}
						.
					</div>
				</TabsContent>

				<TabsContent
					value="knowledge"
					className="flex-1 overflow-y-auto px-6 py-4 space-y-3 mt-0"
				>
					<p className="text-sm text-muted-foreground">
						Knowledge sources added to chats in this workspace.
					</p>
					<div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
						Knowledge source selection coming soon. Current value:{" "}
						{workspace.enabled_knowledge_source_ids === null ||
						workspace.enabled_knowledge_source_ids === undefined
							? "no restriction"
							: `${workspace.enabled_knowledge_source_ids.length} source(s) enabled`}
						.
					</div>
				</TabsContent>

				<TabsContent
					value="instructions"
					className="flex-1 overflow-y-auto px-6 py-4 space-y-3 mt-0"
				>
					<Label htmlFor="ws-instructions">Custom instructions</Label>
					<Textarea
						id="ws-instructions"
						value={instructions}
						onChange={(e) => setInstructions(e.target.value)}
						rows={10}
						placeholder="Appended to the system prompt for chats in this workspace."
						disabled={!canManage}
					/>
				</TabsContent>
			</Tabs>

			<SheetFooter className="border-t flex-row justify-between sm:justify-between">
				{canManage && workspace.scope !== "personal" ? (
					<Button
						variant="outline"
						onClick={handleSoftDelete}
						disabled={remove.isPending}
						className="text-destructive"
					>
						Delete workspace
					</Button>
				) : (
					<span />
				)}
				<div className="flex gap-2">
					<Button variant="outline" onClick={onClose}>
						Cancel
					</Button>
					<Button
						onClick={handleSave}
						disabled={!canManage || !dirty || update.isPending}
					>
						{update.isPending ? "Saving..." : "Save"}
					</Button>
				</div>
			</SheetFooter>
		</>
	);
}
