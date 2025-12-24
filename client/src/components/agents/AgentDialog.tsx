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
import { useToolWorkflows } from "@/hooks/useWorkflows";
import { useRoles } from "@/hooks/useRoles";
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
	{ value: "public", label: "Public", description: "Anyone can access" },
	{
		value: "authenticated",
		label: "Authenticated",
		description: "Any authenticated user",
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
	access_level: z.enum(["public", "authenticated", "role_based"]),
	tool_ids: z.array(z.string()),
	delegated_agent_ids: z.array(z.string()),
	role_ids: z.array(z.string()),
});

type FormValues = z.infer<typeof formSchema>;

interface AgentDialogProps {
	agentId?: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function AgentDialog({ agentId, open, onOpenChange }: AgentDialogProps) {
	const isEditing = !!agentId;
	const { data: agent, isLoading: isLoadingAgent } = useAgent(
		agentId ?? undefined,
	);
	const { data: allAgents } = useAgents();
	const { data: toolWorkflows } = useToolWorkflows();
	const { data: roles } = useRoles();
	const createAgent = useCreateAgent();
	const updateAgent = useUpdateAgent();

	const [channelsOpen, setChannelsOpen] = useState(false);
	const [toolsOpen, setToolsOpen] = useState(false);
	const [delegationsOpen, setDelegationsOpen] = useState(false);
	const [rolesOpen, setRolesOpen] = useState(false);

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: {
			name: "",
			description: "",
			system_prompt: "",
			channels: ["chat"],
			access_level: "role_based",
			tool_ids: [],
			delegated_agent_ids: [],
			role_ids: [],
		},
	});

	const accessLevel = form.watch("access_level");

	// Load existing agent data when editing
	useEffect(() => {
		if (agent && isEditing) {
			form.reset({
				name: agent.name,
				description: agent.description ?? "",
				system_prompt: agent.system_prompt,
				channels: (agent.channels as AgentChannel[]) || ["chat"],
				access_level: agent.access_level,
				tool_ids: agent.tool_ids ?? [],
				delegated_agent_ids: agent.delegated_agent_ids ?? [],
				role_ids: agent.role_ids ?? [],
			});
		} else if (!isEditing && open) {
			form.reset({
				name: "",
				description: "",
				system_prompt: "",
				channels: ["chat"],
				access_level: "role_based",
				tool_ids: [],
				delegated_agent_ids: [],
				role_ids: [],
			});
		}
	}, [agent, isEditing, form, open]);

	// Filter out current agent from delegation options
	const delegationOptions = allAgents?.filter((a) => a.id !== agentId) ?? [];

	const handleClose = () => {
		form.reset();
		onOpenChange(false);
	};

	const onSubmit = async (values: FormValues) => {
		try {
			if (isEditing && agentId) {
				await updateAgent.mutateAsync({
					params: { path: { agent_id: agentId } },
					body: {
						name: values.name,
						description: values.description || null,
						system_prompt: values.system_prompt,
						channels: values.channels,
						access_level: values.access_level,
						tool_ids: values.tool_ids,
						delegated_agent_ids: values.delegated_agent_ids,
						role_ids: values.role_ids,
					},
				});
			} else {
				await createAgent.mutateAsync({
					body: {
						name: values.name,
						description: values.description || null,
						system_prompt: values.system_prompt,
						channels: values.channels,
						access_level: values.access_level,
						tool_ids: values.tool_ids,
						delegated_agent_ids: values.delegated_agent_ids,
						role_ids: values.role_ids,
					},
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
			<DialogContent className="sm:max-w-[900px] max-h-[90vh] overflow-y-auto">
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
							className="space-y-6"
						>
							{/* Two-column layout */}
							<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
								{/* Left column: System Prompt */}
								<div className="space-y-4">
									<FormField
										control={form.control}
										name="system_prompt"
										render={({ field }) => (
											<FormItem className="h-full flex flex-col">
												<FormLabel>
													System Prompt
												</FormLabel>
												<FormControl>
													<Textarea
														placeholder="You are a helpful sales assistant..."
														className="resize-none font-mono text-sm flex-1 min-h-[400px]"
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
								<div className="space-y-4">
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
																						<button
																							type="button"
																							className="ml-1 ring-offset-background rounded-full outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
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
																						>
																							<X className="h-3 w-3" />
																						</button>
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

									{/* Tools (Workflows) */}
									<FormField
										control={form.control}
										name="tool_ids"
										render={({ field }) => (
											<FormItem>
												<FormLabel>Tools</FormLabel>
												<Popover
													open={toolsOpen}
													onOpenChange={setToolsOpen}
												>
													<PopoverTrigger asChild>
														<FormControl>
															<Button
																variant="outline"
																role="combobox"
																aria-expanded={
																	toolsOpen
																}
																className="w-full justify-between h-auto min-h-10"
															>
																{field.value
																	?.length >
																0 ? (
																	<div className="flex flex-wrap gap-1">
																		{field.value.map(
																			(
																				toolId,
																			) => {
																				const workflow =
																					toolWorkflows?.find(
																						(
																							w,
																						) =>
																							w.id ===
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
																						{workflow?.name ||
																							toolId}
																						<button
																							type="button"
																							className="ml-1 ring-offset-background rounded-full outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
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
																											toolId,
																									),
																								);
																							}}
																						>
																							<X className="h-3 w-3" />
																						</button>
																					</Badge>
																				);
																			},
																		)}
																	</div>
																) : (
																	<span className="text-muted-foreground">
																		Select
																		tools...
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
															<CommandInput placeholder="Search tools..." />
															<CommandList>
																<CommandEmpty>
																	No tools
																	found.
																</CommandEmpty>
																<CommandGroup>
																	{toolWorkflows?.map(
																		(
																			workflow,
																		) => (
																			<CommandItem
																				key={
																					workflow.id
																				}
																				value={
																					workflow.name
																				}
																				onSelect={() => {
																					const current =
																						field.value ||
																						[];
																					if (
																						current.includes(
																							workflow.id,
																						)
																					) {
																						field.onChange(
																							current.filter(
																								(
																									id,
																								) =>
																									id !==
																									workflow.id,
																							),
																						);
																					} else {
																						field.onChange(
																							[
																								...current,
																								workflow.id,
																							],
																						);
																					}
																				}}
																			>
																				<Check
																					className={cn(
																						"mr-2 h-4 w-4",
																						field.value?.includes(
																							workflow.id,
																						)
																							? "opacity-100"
																							: "opacity-0",
																					)}
																				/>
																				<div className="flex flex-col">
																					<span>
																						{
																							workflow.name
																						}
																					</span>
																					{workflow.description && (
																						<span className="text-xs text-muted-foreground">
																							{
																								workflow.description
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
													Workflows this agent can
													execute as tools
												</FormDescription>
												<FormMessage />
											</FormItem>
										)}
									/>

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
																						<button
																							type="button"
																							className="ml-1 ring-offset-background rounded-full outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
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
																						>
																							<X className="h-3 w-3" />
																						</button>
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
								</div>
							</div>

							<DialogFooter>
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
