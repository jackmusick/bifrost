/**
 * Agent Dialog Component
 *
 * Dialog for creating and editing AI agents.
 * Handles form state, validation, and API mutations.
 */

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Loader2, Check, ChevronsUpDown, X } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Form,
	FormControl,
	FormDescription,
	FormField,
	FormItem,
	FormLabel,
	FormMessage,
} from "@/components/ui/form";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
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
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import {
	useAgent,
	useAgents,
	useCreateAgent,
	useUpdateAgent,
} from "@/hooks/useAgents";
import { useToolsGrouped } from "@/hooks/useTools";
import { useRoles } from "@/hooks/useRoles";
import { useKnowledgeNamespaces } from "@/hooks/useKnowledge";
import { useAuth } from "@/contexts/AuthContext";
import { useCodingConfig } from "@/hooks/useLLMConfig";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import type { components } from "@/lib/v1";

type AgentChannel = components["schemas"]["AgentChannel"];
type AgentAccessLevel = components["schemas"]["AgentAccessLevel"];
type RolePublic = components["schemas"]["RolePublic"];

// Only "chat" is available for now - extensible for future channels
const CHANNELS: { value: AgentChannel; label: string }[] = [
	{ value: "chat", label: "Web Chat" },
];

const ACCESS_LEVELS: {
	value: AgentAccessLevel;
	label: string;
	description: string;
}[] = [
	{
		value: "authenticated",
		label: "Authenticated",
		description: "Available to all organizations",
	},
	{
		value: "role_based",
		label: "Role-Based",
		description: "Only assigned roles (none = platform admin only)",
	},
];

const formSchema = z.object({
	name: z
		.string()
		.min(1, "Name is required")
		.max(100, "Name must be 100 characters or less"),
	description: z
		.string()
		.max(500, "Description must be 500 characters or less")
		.optional(),
	system_prompt: z.string().min(1, "System prompt is required"),
	channels: z.array(z.enum(["chat", "voice", "teams", "slack"])),
	access_level: z.enum(["authenticated", "role_based"]),
	organization_id: z.string().nullable(),
	is_coding_mode: z.boolean(),
	tool_ids: z.array(z.string()),
	system_tools: z.array(z.string()),
	delegated_agent_ids: z.array(z.string()),
	role_ids: z.array(z.string()),
	knowledge_sources: z.array(z.string()),
});

type FormValues = z.infer<typeof formSchema>;

interface AgentDialogProps {
	agentId?: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function AgentDialog({ agentId, open, onOpenChange }: AgentDialogProps) {
	const isEditing = !!agentId;
	const { isPlatformAdmin, user } = useAuth();
	const { data: agent, isLoading: isLoadingAgent } = useAgent(
		agentId ?? undefined,
	);
	const { data: allAgents } = useAgents();
	const { data: toolsGrouped } = useToolsGrouped();
	const { data: roles } = useRoles();
	const {
		isConfigured: isCodingConfigured,
		isLoading: isCodingConfigLoading,
	} = useCodingConfig();
	const createAgent = useCreateAgent();
	const updateAgent = useUpdateAgent();

	const [channelsOpen, setChannelsOpen] = useState(false);
	const [toolsOpen, setToolsOpen] = useState(false);
	const [delegationsOpen, setDelegationsOpen] = useState(false);
	const [rolesOpen, setRolesOpen] = useState(false);
	const [knowledgeOpen, setKnowledgeOpen] = useState(false);

	// Default organization_id for org users is their org, for platform admins it's null (global)
	const defaultOrgId = isPlatformAdmin
		? null
		: (user?.organizationId ?? null);

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: {
			name: "",
			description: "",
			system_prompt: "",
			channels: ["chat"],
			access_level: "role_based",
			organization_id: defaultOrgId,
			is_coding_mode: false,
			tool_ids: [],
			system_tools: [],
			delegated_agent_ids: [],
			role_ids: [],
			knowledge_sources: [],
		},
	});

	// eslint-disable-next-line react-hooks/incompatible-library -- React Hook Form's watch() is intentionally used for dynamic form state
	const accessLevel = form.watch("access_level");
	const systemTools = form.watch("system_tools");
	const toolIds = form.watch("tool_ids");
	// Watch the agent's organization_id to filter knowledge sources appropriately
	// Agent's org determines what knowledge it can access (org + global cascade)
	const watchedOrgId = form.watch("organization_id");

	// Fetch knowledge namespaces based on agent's org scope
	// - null (global agent): show only global knowledge sources
	// - UUID (org agent): show org + global knowledge sources (cascade)
	const { data: knowledgeNamespaces } = useKnowledgeNamespaces(watchedOrgId);

	// Load existing agent data when editing
	useEffect(() => {
		if (agent && isEditing) {
			// Cast agent to access organization_id which may exist on the response
			const agentWithOrg = agent as typeof agent & {
				organization_id?: string | null;
				system_tools?: string[];
			};
			form.reset({
				name: agent.name,
				description: agent.description ?? "",
				system_prompt: agent.system_prompt,
				channels: (agent.channels as AgentChannel[]) || ["chat"],
				access_level: agent.access_level as
					| "authenticated"
					| "role_based",
				organization_id: agentWithOrg.organization_id ?? null,
				is_coding_mode: agent.is_coding_mode ?? false,
				tool_ids: agent.tool_ids ?? [],
				system_tools: agentWithOrg.system_tools ?? [],
				delegated_agent_ids: agent.delegated_agent_ids ?? [],
				role_ids: agent.role_ids ?? [],
				knowledge_sources: agent.knowledge_sources ?? [],
			});
		} else if (!isEditing && open) {
			form.reset({
				name: "",
				description: "",
				system_prompt: "",
				channels: ["chat"],
				access_level: "role_based",
				organization_id: defaultOrgId,
				is_coding_mode: false,
				tool_ids: [],
				system_tools: [],
				delegated_agent_ids: [],
				role_ids: [],
				knowledge_sources: [],
			});
		}
	}, [agent, isEditing, form, open, defaultOrgId]);

	// Filter out current agent from delegation options (and agents with null ids)
	const delegationOptions = allAgents?.filter((a): a is typeof a & { id: string } => a.id !== null && a.id !== agentId) ?? [];

	const handleClose = () => {
		form.reset();
		onOpenChange(false);
	};

	const onSubmit = async (values: FormValues) => {
		try {
			// Build the body with organization_id and system_tools
			const bodyWithOrg = {
				name: values.name,
				description: values.description || null,
				system_prompt: values.system_prompt,
				channels: values.channels,
				access_level: values.access_level,
				organization_id: values.organization_id,
				is_coding_mode: values.is_coding_mode,
				tool_ids: values.tool_ids,
				system_tools: values.system_tools,
				delegated_agent_ids: values.delegated_agent_ids,
				role_ids: values.role_ids,
				knowledge_sources: values.knowledge_sources,
			} as Parameters<typeof createAgent.mutateAsync>[0]["body"];

			if (isEditing && agentId) {
				await updateAgent.mutateAsync({
					params: { path: { agent_id: agentId } },
					body: bodyWithOrg as Parameters<
						typeof updateAgent.mutateAsync
					>[0]["body"],
				});
			} else {
				await createAgent.mutateAsync({
					body: bodyWithOrg,
				});
			}
			handleClose();
		} catch {
			// Error handling is done by the mutation hooks via toast
		}
	};

	const isPending = createAgent.isPending || updateAgent.isPending;

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="sm:max-w-[900px] max-h-[90vh] flex flex-col overflow-hidden">
				<DialogHeader>
					<DialogTitle>
						{isEditing ? "Edit Agent" : "Create Agent"}
					</DialogTitle>
					<DialogDescription>
						{isEditing
							? "Update the agent configuration"
							: "Create a new AI agent with a custom system prompt and tools"}
					</DialogDescription>
				</DialogHeader>

				{isEditing && isLoadingAgent ? (
					<div className="flex items-center justify-center py-8">
						<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
					</div>
				) : (
					<Form {...form}>
						<form
							onSubmit={form.handleSubmit(onSubmit)}
							className="flex flex-col flex-1 min-h-0"
						>
							{/* Two-column layout */}
							<div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 min-h-0 overflow-hidden">
								{/* Left column: System Prompt */}
								<div className="flex flex-col min-h-0">
									<FormField
										control={form.control}
										name="system_prompt"
										render={({ field }) => (
											<FormItem className="flex flex-col flex-1 min-h-0">
												<FormLabel>
													System Prompt
												</FormLabel>
												<FormControl className="flex-1 min-h-0">
													<Textarea
														placeholder="You are a helpful sales assistant..."
														className="resize-none font-mono text-sm h-full min-h-[200px]"
														{...field}
													/>
												</FormControl>
												<FormDescription>
													Instructions for the AI.
													This defines the agent's
													behavior and personality.
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>
								</div>

								{/* Right column: Other fields */}
								<div className="space-y-4 overflow-y-auto min-h-0 pr-2">
									{/* Organization Scope - Only show for platform admins */}
									{isPlatformAdmin && (
										<FormField
											control={form.control}
											name="organization_id"
											render={({ field }) => (
												<FormItem>
													<FormLabel>
														Organization
													</FormLabel>
													<FormControl>
														<OrganizationSelect
															value={field.value}
															onChange={
																field.onChange
															}
															showGlobal={true}
														/>
													</FormControl>
													<FormDescription>
														Global agents are
														available to all
														organizations
													</FormDescription>
													<FormMessage />
												</FormItem>
											)}
										/>
									)}

									<FormField
										control={form.control}
										name="name"
										render={({ field }) => (
											<FormItem>
												<FormLabel>Name</FormLabel>
												<FormControl>
													<Input
														placeholder="Sales Assistant"
														{...field}
													/>
												</FormControl>
												<FormMessage />
											</FormItem>
										)}
									/>

									<FormField
										control={form.control}
										name="description"
										render={({ field }) => (
											<FormItem>
												<FormLabel>
													Description
												</FormLabel>
												<FormControl>
													<Textarea
														placeholder="Helps with sales inquiries and product recommendations..."
														className="resize-none"
														rows={2}
														{...field}
													/>
												</FormControl>
												<FormDescription>
													Used for AI routing -
													describe what this agent
													specializes in
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Channels - Multi-select dropdown */}
									<FormField
										control={form.control}
										name="channels"
										render={({ field }) => (
											<FormItem>
												<FormLabel>Channels</FormLabel>
												<Popover
													open={channelsOpen}
													onOpenChange={
														setChannelsOpen
													}
												>
													<PopoverTrigger asChild>
														<FormControl>
															<Button
																variant="outline"
																role="combobox"
																aria-expanded={
																	channelsOpen
																}
																className="w-full justify-between h-auto min-h-10"
															>
																{field.value
																	?.length >
																0 ? (
																	<div className="flex flex-wrap gap-1">
																		{field.value.map(
																			(
																				channelValue,
																			) => {
																				const channel =
																					CHANNELS.find(
																						(
																							c,
																						) =>
																							c.value ===
																							channelValue,
																					);
																				return (
																					<Badge
																						key={
																							channelValue
																						}
																						variant="secondary"
																						className="mr-1"
																					>
																						{channel?.label ||
																							channelValue}
																						<X
																							className="ml-1 h-3 w-3 cursor-pointer hover:text-destructive"
																							onClick={(
																								e,
																							) => {
																								e.stopPropagation();
																								field.onChange(
																									field.value.filter(
																										(
																											v,
																										) =>
																											v !==
																											channelValue,
																									),
																								);
																							}}
																						/>
																					</Badge>
																				);
																			},
																		)}
																	</div>
																) : (
																	<span className="text-muted-foreground">
																		Select
																		channels...
																	</span>
																)}
																<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
															</Button>
														</FormControl>
													</PopoverTrigger>
													<PopoverContent
														className="w-[300px] p-0"
														align="start"
													>
														<Command>
															<CommandList>
																<CommandEmpty>
																	No channels
																	available.
																</CommandEmpty>
																<CommandGroup>
																	{CHANNELS.map(
																		(
																			channel,
																		) => (
																			<CommandItem
																				key={
																					channel.value
																				}
																				value={
																					channel.value
																				}
																				onSelect={() => {
																					const current =
																						field.value ||
																						[];
																					if (
																						current.includes(
																							channel.value,
																						)
																					) {
																						field.onChange(
																							current.filter(
																								(
																									v,
																								) =>
																									v !==
																									channel.value,
																							),
																						);
																					} else {
																						field.onChange(
																							[
																								...current,
																								channel.value,
																							],
																						);
																					}
																				}}
																			>
																				<Checkbox
																					checked={field.value?.includes(
																						channel.value,
																					)}
																					className="mr-2"
																				/>
																				{
																					channel.label
																				}
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															</CommandList>
														</Command>
													</PopoverContent>
												</Popover>
												<FormDescription>
													Which communication channels
													this agent is available on
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Access Level */}
									<FormField
										control={form.control}
										name="access_level"
										render={({ field }) => (
											<FormItem>
												<FormLabel>
													Access Level
												</FormLabel>
												<Select
													onValueChange={
														field.onChange
													}
													value={field.value}
												>
													<FormControl>
														<SelectTrigger>
															<SelectValue placeholder="Select access level" />
														</SelectTrigger>
													</FormControl>
													<SelectContent>
														{ACCESS_LEVELS.map(
															(level) => (
																<SelectItem
																	key={
																		level.value
																	}
																	value={
																		level.value
																	}
																>
																	<div className="flex flex-col">
																		<span>
																			{
																				level.label
																			}
																		</span>
																		<span className="text-xs text-muted-foreground">
																			{
																				level.description
																			}
																		</span>
																	</div>
																</SelectItem>
															),
														)}
													</SelectContent>
												</Select>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Coding Mode */}
									<FormField
										control={form.control}
										name="is_coding_mode"
										render={({ field }) => (
											<FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
												<FormControl>
													<Checkbox
														checked={field.value}
														disabled={
															isCodingConfigLoading ||
															isCodingConfigured ===
																false
														}
														onCheckedChange={(
															checked,
														) => {
															field.onChange(
																checked,
															);
															// Auto-select all system tools (including restricted) when enabling coding mode
															if (
																checked &&
																toolsGrouped
															) {
																const allSystemToolIds =
																	[
																		...(toolsGrouped.system?.map(
																			(
																				t,
																			) =>
																				t.id,
																		) ||
																			[]),
																		...(toolsGrouped.restricted?.map(
																			(
																				t,
																			) =>
																				t.id,
																		) ||
																			[]),
																	];
																form.setValue(
																	"system_tools",
																	allSystemToolIds,
																);
															}
														}}
													/>
												</FormControl>
												<div className="space-y-1 leading-none">
													<FormLabel className="flex items-center gap-2">
														Coding Mode
														{isCodingConfigured && (
															<Badge
																variant="secondary"
																className="text-xs"
															>
																Powered by
																Claude
															</Badge>
														)}
													</FormLabel>
													<FormDescription>
														{isCodingConfigured ===
														false ? (
															<span className="text-destructive">
																Requires
																Anthropic API
																configuration in
																Settings → LLM
															</span>
														) : (
															"Enables file access (read, write, edit) for workflow development. Uses Claude Agent SDK."
														)}
													</FormDescription>
												</div>
											</FormItem>
										)}
									/>

									{/* Roles - Only visible when role_based is selected */}
									{accessLevel === "role_based" && (
										<FormField
											control={form.control}
											name="role_ids"
											render={({ field }) => (
												<FormItem>
													<FormLabel>
														Assigned Roles{" "}
														{field.value?.length >
															0 &&
															`(${field.value.length})`}
													</FormLabel>
													<Popover
														open={rolesOpen}
														onOpenChange={
															setRolesOpen
														}
													>
														<PopoverTrigger asChild>
															<FormControl>
																<Button
																	variant="outline"
																	role="combobox"
																	aria-expanded={
																		rolesOpen
																	}
																	className="w-full justify-between font-normal"
																>
																	<span className="text-muted-foreground">
																		Select
																		roles...
																	</span>
																	<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
																</Button>
															</FormControl>
														</PopoverTrigger>
														<PopoverContent
															className="w-[var(--radix-popover-trigger-width)] p-0"
															align="start"
														>
															<Command>
																<CommandInput placeholder="Search roles..." />
																<CommandList>
																	<CommandEmpty>
																		No roles
																		found.
																	</CommandEmpty>
																	<CommandGroup>
																		{roles?.map(
																			(
																				role: RolePublic,
																			) => (
																				<CommandItem
																					key={
																						role.id
																					}
																					value={
																						role.name ||
																						""
																					}
																					onSelect={() => {
																						const current =
																							field.value ||
																							[];
																						if (
																							current.includes(
																								role.id,
																							)
																						) {
																							field.onChange(
																								current.filter(
																									(
																										id,
																									) =>
																										id !==
																										role.id,
																								),
																							);
																						} else {
																							field.onChange(
																								[
																									...current,
																									role.id,
																								],
																							);
																						}
																					}}
																				>
																					<div className="flex items-center gap-2 flex-1">
																						<Checkbox
																							checked={field.value?.includes(
																								role.id,
																							)}
																						/>
																						<div className="flex flex-col">
																							<span className="font-medium">
																								{
																									role.name
																								}
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
																							field.value?.includes(
																								role.id,
																							)
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
													{field.value?.length >
														0 && (
														<div className="flex flex-wrap gap-2 p-2 border rounded-md bg-muted/50">
															{field.value.map(
																(roleId) => {
																	const role =
																		roles?.find(
																			(
																				r: RolePublic,
																			) =>
																				r.id ===
																				roleId,
																		);
																	return (
																		<Badge
																			key={
																				roleId
																			}
																			variant="secondary"
																			className="gap-1"
																		>
																			{role?.name ||
																				roleId}
																			<X
																				className="h-3 w-3 cursor-pointer"
																				onClick={() =>
																					field.onChange(
																						field.value.filter(
																							(
																								id,
																							) =>
																								id !==
																								roleId,
																						),
																					)
																				}
																			/>
																		</Badge>
																	);
																},
															)}
														</div>
													)}
													<FormDescription>
														Users must have at least
														one of these roles to
														access this agent
													</FormDescription>
													<FormMessage />
												</FormItem>
											)}
										/>
									)}

									{/* Tools - Combined System and Workflow */}
									<FormItem>
										<FormLabel>
											Tools{" "}
											{(systemTools?.length || 0) +
												(toolIds?.length || 0) >
												0 &&
												`(${(systemTools?.length || 0) + (toolIds?.length || 0)})`}
										</FormLabel>
										<Popover
											open={toolsOpen}
											onOpenChange={setToolsOpen}
										>
											<PopoverTrigger asChild>
												<Button
													variant="outline"
													role="combobox"
													aria-expanded={toolsOpen}
													className="w-full justify-between h-auto min-h-10"
												>
													{(systemTools?.length ||
														0) +
														(toolIds?.length || 0) >
													0 ? (
														<div className="flex flex-wrap gap-1">
															{/* System tool badges (includes restricted) */}
															{systemTools?.map(
																(toolId) => {
																	const tool =
																		toolsGrouped?.system.find(
																			(
																				t,
																			) =>
																				t.id ===
																				toolId,
																		) ||
																		toolsGrouped?.restricted.find(
																			(
																				t,
																			) =>
																				t.id ===
																				toolId,
																		);
																	return (
																		<Badge
																			key={
																				toolId
																			}
																			variant="secondary"
																			className="mr-1 font-mono text-xs"
																		>
																			{tool?.name ||
																				toolId}
																			<X
																				className="ml-1 h-3 w-3 cursor-pointer hover:text-destructive"
																				onClick={(
																					e,
																				) => {
																					e.stopPropagation();
																					form.setValue(
																						"system_tools",
																						systemTools?.filter(
																							(
																								id,
																							) =>
																								id !==
																								toolId,
																						) ||
																							[],
																					);
																				}}
																			/>
																		</Badge>
																	);
																},
															)}
															{/* Workflow tool badges */}
															{toolIds?.map(
																(toolId) => {
																	const tool =
																		toolsGrouped?.workflow.find(
																			(
																				t,
																			) =>
																				t.id ===
																				toolId,
																		);
																	return (
																		<Badge
																			key={
																				toolId
																			}
																			variant="secondary"
																			className="mr-1"
																		>
																			{tool?.name ||
																				toolId}
																			<X
																				className="ml-1 h-3 w-3 cursor-pointer hover:text-destructive"
																				onClick={(
																					e,
																				) => {
																					e.stopPropagation();
																					form.setValue(
																						"tool_ids",
																						toolIds?.filter(
																							(
																								id,
																							) =>
																								id !==
																								toolId,
																						) ||
																							[],
																					);
																				}}
																			/>
																		</Badge>
																	);
																},
															)}
														</div>
													) : (
														<span className="text-muted-foreground">
															Select tools...
														</span>
													)}
													<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
												</Button>
											</PopoverTrigger>
											<PopoverContent
												className="w-[400px] p-0"
												align="start"
											>
												<Command>
													<CommandInput placeholder="Search tools..." />
													<CommandList>
														<CommandEmpty>
															No tools found.
														</CommandEmpty>

														{/* Restricted System Tools Group */}
														{toolsGrouped?.restricted &&
															toolsGrouped
																.restricted
																.length > 0 && (
																<CommandGroup heading="Restricted System Tools">
																	<p className="text-xs text-muted-foreground px-2 pb-2">
																		Never
																		available
																		to
																		non-admins
																	</p>
																	{toolsGrouped.restricted.map(
																		(
																			tool,
																		) => (
																			<CommandItem
																				key={
																					tool.id
																				}
																				value={`restricted-${tool.name}`}
																				onSelect={() => {
																					const current =
																						systemTools ||
																						[];
																					if (
																						current.includes(
																							tool.id,
																						)
																					) {
																						form.setValue(
																							"system_tools",
																							current.filter(
																								(
																									id,
																								) =>
																									id !==
																									tool.id,
																							),
																						);
																					} else {
																						form.setValue(
																							"system_tools",
																							[
																								...current,
																								tool.id,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						systemTools?.includes(
																							tool.id,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span className="font-mono text-sm">
																						{
																							tool.id
																						}
																					</span>
																					<span className="text-xs text-muted-foreground">
																						{
																							tool.description
																						}
																					</span>
																				</div>
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															)}

														{/* System Tools Group */}
														{toolsGrouped?.system &&
															toolsGrouped.system
																.length > 0 && (
																<CommandGroup heading="System Tools">
																	{toolsGrouped.system.map(
																		(
																			tool,
																		) => (
																			<CommandItem
																				key={
																					tool.id
																				}
																				value={`system-${tool.name}`}
																				onSelect={() => {
																					const current =
																						systemTools ||
																						[];
																					if (
																						current.includes(
																							tool.id,
																						)
																					) {
																						form.setValue(
																							"system_tools",
																							current.filter(
																								(
																									id,
																								) =>
																									id !==
																									tool.id,
																							),
																						);
																					} else {
																						form.setValue(
																							"system_tools",
																							[
																								...current,
																								tool.id,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						systemTools?.includes(
																							tool.id,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span className="font-mono text-sm">
																						{
																							tool.id
																						}
																					</span>
																					<span className="text-xs text-muted-foreground">
																						{
																							tool.description
																						}
																					</span>
																				</div>
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															)}

														{/* Workflow Tools Group */}
														{toolsGrouped?.workflow &&
															toolsGrouped
																.workflow
																.length > 0 && (
																<CommandGroup heading="Workflow Tools">
																	{toolsGrouped.workflow.map(
																		(
																			tool,
																		) => (
																			<CommandItem
																				key={
																					tool.id
																				}
																				value={`workflow-${tool.name}`}
																				onSelect={() => {
																					const current =
																						toolIds ||
																						[];
																					if (
																						current.includes(
																							tool.id,
																						)
																					) {
																						form.setValue(
																							"tool_ids",
																							current.filter(
																								(
																									id,
																								) =>
																									id !==
																									tool.id,
																							),
																						);
																					} else {
																						form.setValue(
																							"tool_ids",
																							[
																								...current,
																								tool.id,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						toolIds?.includes(
																							tool.id,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span>
																						{
																							tool.name
																						}
																					</span>
																					{tool.description && (
																						<span className="text-xs text-muted-foreground">
																							{
																								tool.description
																							}
																						</span>
																					)}
																				</div>
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															)}
													</CommandList>
												</Command>
											</PopoverContent>
										</Popover>
										<FormDescription>
											System tools and workflows this
											agent can use
										</FormDescription>
									</FormItem>

									{/* Delegated Agents */}
									<FormField
										control={form.control}
										name="delegated_agent_ids"
										render={({ field }) => (
											<FormItem>
												<FormLabel>
													Delegated Agents
												</FormLabel>
												<Popover
													open={delegationsOpen}
													onOpenChange={
														setDelegationsOpen
													}
												>
													<PopoverTrigger asChild>
														<FormControl>
															<Button
																variant="outline"
																role="combobox"
																aria-expanded={
																	delegationsOpen
																}
																className="w-full justify-between h-auto min-h-10"
															>
																{field.value
																	?.length >
																0 ? (
																	<div className="flex flex-wrap gap-1">
																		{field.value.map(
																			(
																				agentIdValue,
																			) => {
																				const delegateAgent =
																					delegationOptions.find(
																						(
																							a,
																						) =>
																							a.id ===
																							agentIdValue,
																					);
																				return (
																					<Badge
																						key={
																							agentIdValue
																						}
																						variant="secondary"
																						className="mr-1"
																					>
																						{delegateAgent?.name ||
																							agentIdValue}
																						<X
																							className="ml-1 h-3 w-3 cursor-pointer hover:text-destructive"
																							onClick={(
																								e,
																							) => {
																								e.stopPropagation();
																								field.onChange(
																									field.value.filter(
																										(
																											id,
																										) =>
																											id !==
																											agentIdValue,
																									),
																								);
																							}}
																						/>
																					</Badge>
																				);
																			},
																		)}
																	</div>
																) : (
																	<span className="text-muted-foreground">
																		Select
																		agents...
																	</span>
																)}
																<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
															</Button>
														</FormControl>
													</PopoverTrigger>
													<PopoverContent
														className="w-[400px] p-0"
														align="start"
													>
														<Command>
															<CommandInput placeholder="Search agents..." />
															<CommandList>
																<CommandEmpty>
																	No agents
																	found.
																</CommandEmpty>
																<CommandGroup>
																	{delegationOptions.map(
																		(
																			delegateAgent,
																		) => (
																			<CommandItem
																				key={
																					delegateAgent.id
																				}
																				value={
																					delegateAgent.name
																				}
																				onSelect={() => {
																					const current =
																						field.value ||
																						[];
																					if (
																						current.includes(
																							delegateAgent.id,
																						)
																					) {
																						field.onChange(
																							current.filter(
																								(
																									id,
																								) =>
																									id !==
																									delegateAgent.id,
																							),
																						);
																					} else {
																						field.onChange(
																							[
																								...current,
																								delegateAgent.id,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						field.value?.includes(
																							delegateAgent.id,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span>
																						{
																							delegateAgent.name
																						}
																					</span>
																					{delegateAgent.description && (
																						<span className="text-xs text-muted-foreground">
																							{
																								delegateAgent.description
																							}
																						</span>
																					)}
																				</div>
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															</CommandList>
														</Command>
													</PopoverContent>
												</Popover>
												<FormDescription>
													Other agents this agent can
													delegate tasks to
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

									{/* Knowledge Sources */}
									<FormField
										control={form.control}
										name="knowledge_sources"
										render={({ field }) => (
											<FormItem>
												<FormLabel>
													Knowledge Sources
												</FormLabel>
												<Popover
													open={knowledgeOpen}
													onOpenChange={
														setKnowledgeOpen
													}
												>
													<PopoverTrigger asChild>
														<FormControl>
															<Button
																variant="outline"
																role="combobox"
																aria-expanded={
																	knowledgeOpen
																}
																className="w-full justify-between h-auto min-h-10"
															>
																{field.value
																	?.length >
																0 ? (
																	<div className="flex flex-wrap gap-1">
																		{field.value.map(
																			(
																				namespace,
																			) => (
																				<Badge
																					key={
																						namespace
																					}
																					variant="secondary"
																					className="mr-1"
																				>
																					{
																						namespace
																					}
																					<X
																						className="ml-1 h-3 w-3 cursor-pointer hover:text-destructive"
																						onClick={(
																							e,
																						) => {
																							e.stopPropagation();
																							field.onChange(
																								field.value.filter(
																									(
																										ns,
																									) =>
																										ns !==
																										namespace,
																								),
																							);
																						}}
																					/>
																				</Badge>
																			),
																		)}
																	</div>
																) : (
																	<span className="text-muted-foreground">
																		Select
																		namespaces...
																	</span>
																)}
																<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
															</Button>
														</FormControl>
													</PopoverTrigger>
													<PopoverContent
														className="w-[400px] p-0"
														align="start"
													>
														<Command>
															<CommandInput placeholder="Search namespaces..." />
															<CommandList>
																<CommandEmpty>
																	No
																	namespaces
																	found.
																</CommandEmpty>
																<CommandGroup>
																	{knowledgeNamespaces?.map(
																		(
																			ns,
																		) => (
																			<CommandItem
																				key={
																					ns.namespace
																				}
																				value={
																					ns.namespace
																				}
																				onSelect={() => {
																					const current =
																						field.value ||
																						[];
																					if (
																						current.includes(
																							ns.namespace,
																						)
																					) {
																						field.onChange(
																							current.filter(
																								(
																									n,
																								) =>
																									n !==
																									ns.namespace,
																							),
																						);
																					} else {
																						field.onChange(
																							[
																								...current,
																								ns.namespace,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						field.value?.includes(
																							ns.namespace,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span>
																						{
																							ns.namespace
																						}
																					</span>
																					<span className="text-xs text-muted-foreground">
																						{
																							ns
																								.scopes
																								.total
																						}{" "}
																						documents
																					</span>
																				</div>
																			</CommandItem>
																		),
																	)}
																</CommandGroup>
															</CommandList>
														</Command>
													</PopoverContent>
												</Popover>
												{field.value?.length > 0 && (
													<div className="flex items-center gap-2 p-2 border rounded-md bg-muted/30">
														<Badge
															variant="secondary"
															className="font-mono text-xs"
														>
															search_knowledge
														</Badge>
														<span className="text-xs text-muted-foreground">
															tool auto-enabled
														</span>
													</div>
												)}
												<FormDescription>
													Knowledge namespaces this
													agent can search for
													context. Adding namespaces
													enables the search_knowledge
													tool.
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>
								</div>
							</div>

							<DialogFooter className="mt-6 flex-shrink-0">
								<Button
									type="button"
									variant="outline"
									onClick={handleClose}
								>
									Cancel
								</Button>
								<Button type="submit" disabled={isPending}>
									{isPending && (
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									)}
									{isPending
										? "Saving..."
										: isEditing
											? "Update Agent"
											: "Create Agent"}
								</Button>
							</DialogFooter>
						</form>
					</Form>
				)}
			</DialogContent>
		</Dialog>
	);
}
