/**
 * CreateWorkspaceDialog — Private / Shared toggle.
 *
 * Top-level choice is "who can use this workspace": **Private** (just you) or
 * **Shared** (your organization, optionally narrowed to a role). When Shared,
 * the role default is "Everyone in my organization" — selecting a role narrows
 * visibility to that role.
 *
 * Platform admins additionally see an Organization picker; org users are
 * pinned to their own organization.
 *
 * The inner form mounts only when the dialog is open, so each open is a fresh
 * snapshot — no useEffect-reset gymnastics needed.
 */

import { useState } from "react";
import { Check, ChevronsUpDown, Lock, Users } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useAuth } from "@/contexts/AuthContext";
import { useRoles } from "@/hooks/useRoles";
import { cn } from "@/lib/utils";
import {
	useCreateWorkspace,
	type Workspace,
} from "@/services/workspaceService";
import type { components } from "@/lib/v1";

type RolePublic = components["schemas"]["RolePublic"];

interface Props {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onCreated?: (ws: Workspace) => void;
}

export function CreateWorkspaceDialog({
	open,
	onOpenChange,
	onCreated,
}: Props) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-md">
				<DialogHeader>
					<DialogTitle>New workspace</DialogTitle>
					<DialogDescription>
						Workspaces are folders for chats with shared instructions,
						tools, and knowledge.
					</DialogDescription>
				</DialogHeader>
				{open && (
					<CreateWorkspaceForm
						onCancel={() => onOpenChange(false)}
						onCreated={(ws) => {
							onOpenChange(false);
							onCreated?.(ws);
						}}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}

type Mode = "private" | "shared";

function CreateWorkspaceForm({
	onCancel,
	onCreated,
}: {
	onCancel: () => void;
	onCreated: (ws: Workspace) => void;
}) {
	const { isPlatformAdmin, user } = useAuth();
	const create = useCreateWorkspace();
	const { data: roles } = useRoles();

	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [mode, setMode] = useState<Mode>("private");
	// Admins can pick any org; org users are pinned to their own.
	const [orgId, setOrgId] = useState<string | null>(
		isPlatformAdmin ? null : (user?.organizationId ?? null),
	);
	const [roleId, setRoleId] = useState<string | null>(null);
	const [rolesOpen, setRolesOpen] = useState(false);

	// Validation: name + (Shared requires an org if admin)
	const sharedOk =
		mode !== "shared" ||
		(isPlatformAdmin ? !!orgId : !!user?.organizationId);
	const canSubmit = name.trim().length > 0 && sharedOk;

	const handleSubmit = () => {
		if (!canSubmit) return;
		// Map UI choices → API contract.
		const scope =
			mode === "private" ? "personal" : roleId ? "role" : "org";
		const targetOrg =
			mode === "shared"
				? isPlatformAdmin
					? orgId
					: (user?.organizationId ?? null)
				: null;

		create.mutate(
			{
				body: {
					name: name.trim(),
					description: description.trim() || null,
					scope,
					organization_id: targetOrg,
					role_id: scope === "role" ? roleId : null,
				},
			},
			{
				onSuccess: (ws) => {
					toast.success("Workspace created");
					onCreated(ws);
				},
				onError: (err) => {
					toast.error("Failed to create workspace", {
						description:
							(err as Error)?.message ?? "Please try again.",
					});
				},
			},
		);
	};

	const selectedRole = roles?.find((r: RolePublic) => r.id === roleId);

	return (
		<>
			<div className="space-y-4 py-2">
				<div className="space-y-1.5">
					<Label htmlFor="ws-name">Name</Label>
					<Input
						id="ws-name"
						value={name}
						onChange={(e) => setName(e.target.value)}
						placeholder="e.g. Customer outreach"
						autoFocus
					/>
				</div>
				<div className="space-y-1.5">
					<Label htmlFor="ws-desc">Description (optional)</Label>
					<Textarea
						id="ws-desc"
						value={description}
						onChange={(e) => setDescription(e.target.value)}
						placeholder="What is this workspace for?"
						rows={2}
					/>
				</div>

				{/* Private / Shared toggle */}
				<div className="space-y-1.5">
					<Label>Who can use it</Label>
					<div
						role="radiogroup"
						className="grid grid-cols-2 gap-2"
					>
						<ModeOption
							icon={<Lock className="h-4 w-4" />}
							title="Private"
							subtitle="Only you"
							selected={mode === "private"}
							onClick={() => {
								setMode("private");
								setRoleId(null);
							}}
						/>
						<ModeOption
							icon={<Users className="h-4 w-4" />}
							title="Shared"
							subtitle="Your organization"
							selected={mode === "shared"}
							onClick={() => setMode("shared")}
						/>
					</div>
				</div>

				{mode === "shared" && (
					<>
						{isPlatformAdmin && (
							<div className="space-y-1.5">
								<Label>Organization</Label>
								<OrganizationSelect
									value={orgId}
									onChange={(v) => setOrgId(v ?? null)}
									showGlobal={false}
									placeholder="Select organization..."
								/>
							</div>
						)}

						<div className="space-y-1.5">
							<Label>Role</Label>
							<Popover open={rolesOpen} onOpenChange={setRolesOpen}>
								<PopoverTrigger asChild>
									<Button
										variant="outline"
										role="combobox"
										aria-expanded={rolesOpen}
										className="w-full justify-between font-normal"
									>
										<span
											className={cn(
												selectedRole
													? ""
													: "text-muted-foreground",
											)}
										>
											{selectedRole
												? selectedRole.name
												: "Everyone in my organization"}
										</span>
										<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
									</Button>
								</PopoverTrigger>
								<PopoverContent
									className="w-[var(--radix-popover-trigger-width)] p-0"
									align="start"
								>
									<Command>
										<CommandInput placeholder="Search roles…" />
										<CommandList>
											<CommandEmpty>
												No roles found.
											</CommandEmpty>
											<CommandGroup>
												<CommandItem
													value="__everyone__"
													onSelect={() => {
														setRoleId(null);
														setRolesOpen(false);
													}}
												>
													<div className="flex flex-1 items-center gap-2">
														<Checkbox
															checked={roleId === null}
														/>
														<div className="flex flex-col">
															<span className="font-medium">
																Everyone in my organization
															</span>
															<span className="text-xs text-muted-foreground">
																Default
															</span>
														</div>
													</div>
													<Check
														className={cn(
															"ml-auto h-4 w-4",
															roleId === null
																? "opacity-100"
																: "opacity-0",
														)}
													/>
												</CommandItem>
												{(roles ?? []).map(
													(role: RolePublic) => (
														<CommandItem
															key={role.id}
															value={role.name ?? ""}
															onSelect={() => {
																setRoleId(role.id);
																setRolesOpen(false);
															}}
														>
															<div className="flex flex-1 items-center gap-2">
																<Checkbox
																	checked={
																		roleId ===
																		role.id
																	}
																/>
																<div className="flex flex-col">
																	<span className="font-medium">
																		{role.name}
																	</span>
																	{role.description ? (
																		<span className="text-xs text-muted-foreground">
																			{
																				role.description
																			}
																		</span>
																	) : null}
																</div>
															</div>
															<Check
																className={cn(
																	"ml-auto h-4 w-4",
																	roleId ===
																		role.id
																		? "opacity-100"
																		: "opacity-0",
																)}
															/>
														</CommandItem>
													),
												)}
											</CommandGroup>
										</CommandList>
									</Command>
								</PopoverContent>
							</Popover>
							{selectedRole && (
								<div className="flex flex-wrap gap-1.5 rounded-md border bg-muted/40 p-2">
									<Badge variant="secondary">
										{selectedRole.name}
									</Badge>
								</div>
							)}
						</div>
					</>
				)}
			</div>

			<DialogFooter>
				<Button variant="outline" onClick={onCancel}>
					Cancel
				</Button>
				<Button
					onClick={handleSubmit}
					disabled={!canSubmit || create.isPending}
				>
					{create.isPending ? "Creating..." : "Create workspace"}
				</Button>
			</DialogFooter>
		</>
	);
}

function ModeOption({
	icon,
	title,
	subtitle,
	selected,
	onClick,
}: {
	icon: React.ReactNode;
	title: string;
	subtitle: string;
	selected: boolean;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			role="radio"
			aria-checked={selected}
			onClick={onClick}
			className={cn(
				"flex items-start gap-2.5 p-3 rounded-md border text-left transition-colors",
				selected
					? "border-primary bg-primary/5 ring-1 ring-primary"
					: "hover:bg-accent/50",
			)}
		>
			<div
				className={cn(
					"size-7 rounded-md flex items-center justify-center shrink-0",
					selected
						? "bg-primary/15 text-primary"
						: "bg-muted text-muted-foreground",
				)}
			>
				{icon}
			</div>
			<div className="min-w-0">
				<div className="font-medium text-sm">{title}</div>
				<div className="text-xs text-muted-foreground">{subtitle}</div>
			</div>
		</button>
	);
}
