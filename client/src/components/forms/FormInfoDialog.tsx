import { useState } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Combobox } from "@/components/ui/combobox";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { useRoles } from "@/hooks/useRoles";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import type { components } from "@/lib/v1";

type WorkflowParameter = components["schemas"]["WorkflowParameter"];
type Role = components["schemas"]["RolePublic"];
type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

interface FormInfoDialogProps {
	open: boolean;
	onClose: () => void;
	onSave: (info: {
		formName: string;
		formDescription: string;
		linkedWorkflow: string;
		launchWorkflowId: string | null;
		defaultLaunchParams: Record<string, unknown> | null;
		accessLevel: "authenticated" | "role_based";
		selectedRoleIds: string[];
		organizationId: string | null;
	}) => void;
	initialData?: {
		formName: string;
		formDescription: string;
		linkedWorkflow: string;
		launchWorkflowId?: string | null;
		defaultLaunchParams?: Record<string, unknown> | null;
		accessLevel?: "authenticated" | "role_based";
		selectedRoleIds?: string[];
		organizationId?: string | null;
	};
	/** Whether this is editing an existing form (org cannot be changed) */
	isEditing?: boolean;
}

export function FormInfoDialog({
	open,
	onClose,
	onSave,
	initialData,
	isEditing = false,
}: FormInfoDialogProps) {
	const [rolesPopoverOpen, setRolesPopoverOpen] = useState(false);
	const { isPlatformAdmin, user } = useAuth();

	const { data: metadata, isLoading: metadataLoading } =
		useWorkflowsMetadata() as {
			data?: { workflows?: WorkflowMetadata[] };
			isLoading: boolean;
		};

	// Fetch available roles using the hook
	const { data: roles, isLoading: rolesLoading } = useRoles();

	// Default organization_id for org users is their org, for platform admins it's null (global)
	const defaultOrgId = isPlatformAdmin ? null : (user?.organizationId ?? null);

	// Initialize form state from initialData
	const [formName, setFormName] = useState(() => initialData?.formName || "");
	const [formDescription, setFormDescription] = useState(
		() => initialData?.formDescription || "",
	);
	const [linkedWorkflow, setLinkedWorkflow] = useState(
		() => initialData?.linkedWorkflow || "",
	);
	const [launchWorkflowId, setLaunchWorkflowId] = useState<string>(
		() => initialData?.launchWorkflowId || "",
	);
	const [defaultLaunchParams, setDefaultLaunchParams] = useState<
		Record<string, unknown>
	>(
		() =>
			(initialData?.defaultLaunchParams as Record<string, unknown>) || {},
	);
	const [accessLevel, setAccessLevel] = useState<
		"authenticated" | "role_based"
	>(() => initialData?.accessLevel || "role_based");
	const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>(
		() => initialData?.selectedRoleIds || [],
	);
	const [organizationId, setOrganizationId] = useState<
		string | null | undefined
	>(() => initialData?.organizationId ?? defaultOrgId ?? null);

	// Get selected launch workflow metadata
	const selectedLaunchWorkflow = metadata?.workflows?.find(
		(w: WorkflowMetadata) => w.name === launchWorkflowId,
	);
	const launchWorkflowParams = selectedLaunchWorkflow?.parameters || [];

	const handleParameterChange = (paramName: string, value: unknown) => {
		setDefaultLaunchParams((prev) => ({
			...prev,
			[paramName]: value,
		}));
	};

	const renderParameterInput = (param: WorkflowParameter) => {
		const value = defaultLaunchParams[param.name ?? ""];

		switch (param.type) {
			case "bool":
				return (
					<div className="flex items-center space-x-2">
						<Checkbox
							id={`param-${param.name}`}
							checked={!!value}
							onCheckedChange={(checked) =>
								handleParameterChange(param.name ?? "", checked)
							}
						/>
						<Label
							htmlFor={`param-${param.name}`}
							className="text-sm font-normal"
						>
							{param.name}
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
							{!param.required && (
								<Badge
									variant="secondary"
									className="text-[10px] px-1 py-0 ml-2"
								>
									Optional
								</Badge>
							)}
							{param.description && (
								<span className="block text-xs text-muted-foreground mt-1">
									{param.description}
								</span>
							)}
						</Label>
					</div>
				);

			case "int":
			case "float":
				return (
					<div className="space-y-1.5">
						<Label
							htmlFor={`param-${param.name}`}
							className="text-sm flex items-center gap-2"
						>
							{param.name}
							{param.required && (
								<Badge
									variant="destructive"
									className="text-[10px] px-1 py-0"
								>
									Required
								</Badge>
							)}
							{!param.required && (
								<Badge
									variant="secondary"
									className="text-[10px] px-1 py-0"
								>
									Optional
								</Badge>
							)}
						</Label>
						<Input
							id={`param-${param.name}`}
							type="number"
							step={param.type === "float" ? "0.1" : "1"}
							value={(value as string | number | undefined) ?? ""}
							onChange={(e) =>
								handleParameterChange(
									param.name ?? "",
									param.type === "int"
										? parseInt(e.target.value)
										: parseFloat(e.target.value),
								)
							}
							placeholder={
								param.description ||
								`Enter default value for ${param.name}`
							}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);

			case "list":
				return (
					<div className="space-y-1.5">
						<Label
							htmlFor={`param-${param.name}`}
							className="text-sm flex items-center gap-2"
						>
							{param.name}
							{param.required && (
								<Badge
									variant="destructive"
									className="text-[10px] px-1 py-0"
								>
									Required
								</Badge>
							)}
							{!param.required && (
								<Badge
									variant="secondary"
									className="text-[10px] px-1 py-0"
								>
									Optional
								</Badge>
							)}
						</Label>
						<Input
							id={`param-${param.name}`}
							type="text"
							value={
								Array.isArray(value)
									? value.join(", ")
									: ((value as string) ?? "")
							}
							onChange={(e) =>
								handleParameterChange(
									param.name ?? "",
									e.target.value
										.split(",")
										.map((v) => v.trim()),
								)
							}
							placeholder={
								param.description || "Comma-separated values"
							}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);

			default:
				// string, email, json
				return (
					<div className="space-y-1.5">
						<Label
							htmlFor={`param-${param.name}`}
							className="text-sm flex items-center gap-2"
						>
							{param.name}
							{param.required && (
								<Badge
									variant="destructive"
									className="text-[10px] px-1 py-0"
								>
									Required
								</Badge>
							)}
							{!param.required && (
								<Badge
									variant="secondary"
									className="text-[10px] px-1 py-0"
								>
									Optional
								</Badge>
							)}
						</Label>
						<Input
							id={`param-${param.name}`}
							type={param.type === "email" ? "email" : "text"}
							value={(value as string) ?? ""}
							onChange={(e) =>
								handleParameterChange(
									param.name ?? "",
									e.target.value,
								)
							}
							placeholder={
								param.description ||
								`Enter default value for ${param.name}`
							}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);
		}
	};

	const handleSave = () => {
		// Handle "__none__" special value for launch workflow
		const finalLaunchWorkflowId =
			launchWorkflowId === "__none__" || !launchWorkflowId.trim()
				? null
				: launchWorkflowId.trim();

		// Only include defaultLaunchParams if launch workflow is set and params exist
		const finalDefaultParams =
			finalLaunchWorkflowId && Object.keys(defaultLaunchParams).length > 0
				? defaultLaunchParams
				: null;

		onSave({
			formName,
			formDescription,
			linkedWorkflow,
			launchWorkflowId: finalLaunchWorkflowId,
			defaultLaunchParams: finalDefaultParams,
			accessLevel,
			selectedRoleIds,
			organizationId: organizationId ?? null,
		});
		onClose();
	};

	const toggleRole = (roleId: string) => {
		setSelectedRoleIds((prev) =>
			prev.includes(roleId)
				? prev.filter((id) => id !== roleId)
				: [...prev, roleId],
		);
	};

	const handleLaunchWorkflowChange = (value: string) => {
		setLaunchWorkflowId(value);
		// Clear default params when launch workflow changes
		if (!value || value === "__none__") {
			setDefaultLaunchParams({});
		}
	};

	const removeRole = (roleId: string) => {
		setSelectedRoleIds((prev) => prev.filter((id) => id !== roleId));
	};

	const isSaveDisabled = !formName || !linkedWorkflow;

	return (
		<Dialog open={open} onOpenChange={onClose}>
			<DialogContent className="sm:max-w-[600px]">
				<DialogHeader>
					<DialogTitle>Form Information</DialogTitle>
					<DialogDescription>
						Configure basic details about the form and linked
						workflow
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-4">
					{/* Organization Scope - Only show for platform admins */}
					{isPlatformAdmin && (
						<div className="space-y-2">
							<Label htmlFor="organizationId">Organization</Label>
							<OrganizationSelect
								value={organizationId}
								onChange={(value) => setOrganizationId(value ?? null)}
								showGlobal={true}
								disabled={isEditing}
							/>
							<p className="text-xs text-muted-foreground">
								{isEditing
									? "Organization cannot be changed after form creation"
									: "Global forms are available to all organizations"}
							</p>
						</div>
					)}

					<div className="space-y-2">
						<Label htmlFor="formName">Form Name *</Label>
						<Input
							id="formName"
							placeholder="User Onboarding Form"
							value={formName}
							onChange={(e) => setFormName(e.target.value)}
						/>
					</div>

					<div className="space-y-2">
						<Label htmlFor="linkedWorkflow">
							Linked Workflow *
						</Label>
						<Combobox
							id="linkedWorkflow"
							value={linkedWorkflow}
							onValueChange={setLinkedWorkflow}
							options={
								metadata?.workflows?.map(
									(workflow: WorkflowMetadata) => {
										const option: {
											value: string;
											label: string;
											description?: string;
										} = {
											value: workflow.name ?? "",
											label: workflow.name ?? "Unnamed",
										};
										if (workflow.description) {
											option.description =
												workflow.description;
										}
										return option;
									},
								) ?? []
							}
							placeholder="Select a workflow"
							searchPlaceholder="Search workflows..."
							emptyText="No workflows found."
							isLoading={metadataLoading}
						/>
						<p className="text-xs text-muted-foreground">
							The workflow that will be executed when this form is
							submitted
						</p>
					</div>

					<div className="space-y-2">
						<Label htmlFor="formDescription">Description</Label>
						<Textarea
							id="formDescription"
							placeholder="Describe what this form does..."
							value={formDescription}
							onChange={(e) => setFormDescription(e.target.value)}
							rows={3}
						/>
					</div>

					<div className="space-y-2">
						<Label htmlFor="accessLevel">Access Level</Label>
						<Combobox
							id="accessLevel"
							value={accessLevel}
							onValueChange={(value: string) =>
								setAccessLevel(value as "authenticated" | "role_based")
							}
							options={[
								{
									value: "role_based",
									label: "Role-Based",
									description:
										"Only users with assigned roles can access",
								},
								{
									value: "authenticated",
									label: "Authenticated Users",
									description:
										"Any authenticated user can access",
								},
							]}
							placeholder="Select access level"
						/>
						<p className="text-xs text-muted-foreground">
							Controls who can view and execute this form
						</p>
					</div>

					{accessLevel === "role_based" && (
						<div className="space-y-2">
							<Label>
								Assigned Roles{" "}
								{selectedRoleIds.length > 0 &&
									`(${selectedRoleIds.length})`}
							</Label>
							<Popover
								open={rolesPopoverOpen}
								onOpenChange={setRolesPopoverOpen}
							>
								<PopoverTrigger asChild>
									<Button
										variant="outline"
										role="combobox"
										className="w-full justify-between font-normal"
										disabled={rolesLoading}
									>
										<span className="text-muted-foreground">
											{rolesLoading
												? "Loading roles..."
												: "Select roles..."}
										</span>
										<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
									</Button>
								</PopoverTrigger>
								<PopoverContent
									className="w-[var(--radix-popover-trigger-width)] p-0"
									align="start"
								>
									<Command>
										<CommandInput placeholder="Search roles..." />
										<CommandList>
											<CommandEmpty>
												No roles found.
											</CommandEmpty>
											<CommandGroup>
												{roles?.map((role: Role) => (
													<CommandItem
														key={role.id}
														value={role.name || ""}
														onSelect={() =>
															toggleRole(role.id)
														}
													>
														<div className="flex items-center gap-2 flex-1">
															<Checkbox
																checked={selectedRoleIds.includes(
																	role.id,
																)}
																onCheckedChange={() =>
																	toggleRole(
																		role.id,
																	)
																}
															/>
															<div className="flex flex-col">
																<span className="font-medium">
																	{role.name}
																</span>
																{role.description && (
																	<span className="text-xs text-muted-foreground">
																		{
																			role.description
																		}
																	</span>
																)}
															</div>
														</div>
														<Check
															className={cn(
																"ml-auto h-4 w-4",
																selectedRoleIds.includes(
																	role.id,
																)
																	? "opacity-100"
																	: "opacity-0",
															)}
														/>
													</CommandItem>
												))}
											</CommandGroup>
										</CommandList>
									</Command>
								</PopoverContent>
							</Popover>
							{selectedRoleIds.length > 0 && (
								<div className="flex flex-wrap gap-2 p-2 border rounded-md bg-muted/50">
									{selectedRoleIds.map((roleId) => {
										const role = roles?.find(
											(r: Role) => r.id === roleId,
										);
										return (
											<Badge
												key={roleId}
												variant="secondary"
												className="gap-1"
											>
												{role?.name || roleId}
												<X
													className="h-3 w-3 cursor-pointer"
													onClick={() =>
														removeRole(roleId)
													}
												/>
											</Badge>
										);
									})}
								</div>
							)}
							<p className="text-xs text-muted-foreground">
								Users must have at least one of these roles to
								access the form
							</p>
						</div>
					)}

					<div className="space-y-2">
						<Label htmlFor="launchWorkflowId">
							Launch Workflow (Optional)
						</Label>
						<Combobox
							id="launchWorkflowId"
							value={launchWorkflowId}
							onValueChange={handleLaunchWorkflowChange}
							options={[
								{
									value: "__none__",
									label: "None",
								},
								...(metadata?.workflows?.map(
									(workflow: WorkflowMetadata) => {
										const option: {
											value: string;
											label: string;
											description?: string;
										} = {
											value: workflow.name ?? "",
											label: workflow.name ?? "Unnamed",
										};
										if (workflow.description) {
											option.description =
												workflow.description;
										}
										return option;
									},
								) ?? []),
							]}
							placeholder="Select a workflow (or leave empty)"
							searchPlaceholder="Search workflows..."
							emptyText="No workflows found."
							isLoading={metadataLoading}
						/>
						<p className="text-xs text-muted-foreground">
							Workflow to execute when form loads (results
							available in context.workflow)
						</p>
					</div>

					{/* Default Launch Parameters */}
					{launchWorkflowId &&
						launchWorkflowId !== "__none__" &&
						launchWorkflowParams.length > 0 && (
							<div className="space-y-3 rounded-lg border p-4 bg-muted/50">
								<div>
									<Label className="text-sm font-medium">
										Default Launch Parameters
									</Label>
									<p className="text-xs text-muted-foreground mt-1">
										Set default values for workflow
										parameters. Required parameters must
										have either a default value or a form
										field with "Allow as Query Param"
										enabled.
									</p>
								</div>
								<div className="space-y-3">
									{launchWorkflowParams.map(
										(param: WorkflowParameter) => (
											<div key={param.name}>
												{renderParameterInput(param)}
											</div>
										),
									)}
								</div>
							</div>
						)}
				</div>

				<DialogFooter>
					<Button type="button" variant="outline" onClick={onClose}>
						Cancel
					</Button>
					<Button onClick={handleSave} disabled={isSaveDisabled}>
						Save
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
