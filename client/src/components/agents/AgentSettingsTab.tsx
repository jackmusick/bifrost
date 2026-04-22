/**
 * Settings tab for an agent's detail page.
 *
 * Form for AgentUpdate fields. Mirrors the existing AgentDialog (T19/AgentDialog.tsx)
 * but lives inside a tabbed page rather than a modal. Budget fields
 * (max_iterations, max_token_budget, llm_max_tokens) are server-gated to
 * platform admins (T19) and visually hidden here for non-admins.
 *
 * Visual spec mirrors /tmp/agent-mockup/src/pages/AgentDetailPage.tsx's
 * `.form-section` pattern: single column, uppercase section-title labels,
 * thin dividers between sections, no card chrome. Activation is an inline
 * row inside the Identity section — no right column.
 *
 * Two modes:
 *   - mode="create": empty form, POSTs to /api/agents on save, then the
 *     parent page navigates to /agents/:newId
 *   - mode="edit": prepopulated from `agent`, PUTs to /api/agents/:id
 */

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import { Button } from "@/components/ui/button";
import {
	Form,
	FormControl,
	FormDescription,
	FormField,
	FormItem,
	FormLabel,
	FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";

import { CARD_SURFACE, TYPE_LABEL_UPPERCASE } from "@/components/agents/design-tokens";
import { useAuth } from "@/contexts/AuthContext";
import {
	useCreateAgent,
	useUpdateAgent,
	type AgentPublic,
} from "@/hooks/useAgents";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type AgentChannel = components["schemas"]["AgentChannel"];
type AgentAccessLevel = components["schemas"]["AgentAccessLevel"];

const formSchema = z.object({
	name: z.string().min(1, "Name is required").max(100),
	description: z.string().max(500).optional(),
	system_prompt: z.string().min(1, "System prompt is required"),
	channels: z.array(z.enum(["chat", "voice", "teams", "slack"])),
	access_level: z.enum(["authenticated", "role_based"]),
	is_active: z.boolean(),
	max_iterations: z.number().min(1).max(200).nullable(),
	max_token_budget: z.number().min(1000).max(1_000_000).nullable(),
	llm_max_tokens: z.number().min(1).max(200_000).nullable(),
});

type FormValues = z.infer<typeof formSchema>;

export interface AgentSettingsTabProps {
	mode: "create" | "edit";
	agent?: AgentPublic | null;
	onCreated?: (newId: string) => void;
}

/**
 * Thin divided form section — mockup's `.form-section` in Tailwind.
 * Last-child drops the bottom divider via `last:border-b-0`.
 */
function FormSection({
	title,
	children,
	testId,
}: {
	title: string;
	children: React.ReactNode;
	testId?: string;
}) {
	return (
		<section
			className="border-b px-5 py-5 last:border-b-0"
			data-testid={testId}
		>
			<h3 className={cn("mb-3.5", TYPE_LABEL_UPPERCASE)}>{title}</h3>
			<div className="flex flex-col gap-3.5">{children}</div>
		</section>
	);
}

export function AgentSettingsTab({
	mode,
	agent,
	onCreated,
}: AgentSettingsTabProps) {
	const { isPlatformAdmin } = useAuth();
	const createAgent = useCreateAgent();
	const updateAgent = useUpdateAgent();

	const defaults: FormValues = {
		name: agent?.name ?? "",
		description: agent?.description ?? "",
		system_prompt: agent?.system_prompt ?? "",
		channels: ((agent?.channels as AgentChannel[] | undefined) ?? [
			"chat",
		]) as AgentChannel[],
		access_level: (agent?.access_level ?? "role_based") as
			| "authenticated"
			| "role_based",
		is_active: agent?.is_active ?? true,
		max_iterations: agent?.max_iterations ?? null,
		max_token_budget: agent?.max_token_budget ?? null,
		llm_max_tokens: agent?.llm_max_tokens ?? null,
	};

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: defaults,
		values: agent ? defaults : undefined,
	});

	// Reset on agent change so edit mode tracks the latest server state.
	useEffect(() => {
		if (agent) form.reset(defaults);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [agent?.id]);

	async function onSubmit(values: FormValues) {
		const body = {
			name: values.name,
			description: values.description || null,
			system_prompt: values.system_prompt,
			channels: values.channels,
			access_level: values.access_level as AgentAccessLevel,
			is_active: values.is_active,
			tool_ids: agent?.tool_ids ?? [],
			delegated_agent_ids: agent?.delegated_agent_ids ?? [],
			role_ids: agent?.role_ids ?? [],
			knowledge_sources: agent?.knowledge_sources ?? [],
			...(isPlatformAdmin
				? {
						max_iterations: values.max_iterations,
						max_token_budget: values.max_token_budget,
						llm_max_tokens: values.llm_max_tokens,
					}
				: {}),
		};

		if (mode === "create") {
			const result = (await createAgent.mutateAsync({
				body: body as Parameters<
					typeof createAgent.mutateAsync
				>[0]["body"],
			})) as AgentPublic;
			if (result?.id) onCreated?.(result.id);
		} else if (agent?.id) {
			await updateAgent.mutateAsync({
				params: { path: { agent_id: agent.id } },
				body: body as Parameters<
					typeof updateAgent.mutateAsync
				>[0]["body"],
			});
		}
	}

	const pending = createAgent.isPending || updateAgent.isPending;

	return (
		<Form {...form}>
			<form
				onSubmit={form.handleSubmit(onSubmit)}
				className={cn("overflow-hidden", CARD_SURFACE)}
				data-testid="agent-settings-form"
			>
				<FormSection title="Identity">
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
								<FormLabel>Description</FormLabel>
								<FormControl>
									<Input
										placeholder="What this agent specializes in"
										{...field}
									/>
								</FormControl>
								<FormMessage />
							</FormItem>
						)}
					/>
					<FormField
						control={form.control}
						name="is_active"
						render={({ field }) => (
							<FormItem className="flex items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2.5">
								<div className="flex flex-col">
									<FormLabel className="m-0">
										{field.value
											? "Agent is active"
											: "Agent is paused"}
									</FormLabel>
									<FormDescription>
										{field.value
											? "Triggers will be accepted."
											: "Triggers will be rejected."}
									</FormDescription>
								</div>
								<FormControl>
									<Switch
										aria-label="Toggle agent active"
										checked={field.value}
										onCheckedChange={field.onChange}
									/>
								</FormControl>
							</FormItem>
						)}
					/>
				</FormSection>

				<FormSection title="Behavior">
					<FormField
						control={form.control}
						name="system_prompt"
						render={({ field }) => (
							<FormItem>
								<FormLabel>System prompt</FormLabel>
								<FormControl>
									<Textarea
										className="min-h-[200px] font-mono text-sm"
										placeholder="You are a helpful assistant…"
										{...field}
									/>
								</FormControl>
								<FormDescription>
									Instructions the agent follows on every run.
								</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>
					<FormField
						control={form.control}
						name="access_level"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Access level</FormLabel>
								<Select
									value={field.value}
									onValueChange={field.onChange}
								>
									<FormControl>
										<SelectTrigger aria-label="Access level">
											<SelectValue />
										</SelectTrigger>
									</FormControl>
									<SelectContent>
										<SelectItem value="authenticated">
											Authenticated
										</SelectItem>
										<SelectItem value="role_based">
											Role-based
										</SelectItem>
									</SelectContent>
								</Select>
								<FormMessage />
							</FormItem>
						)}
					/>
				</FormSection>

				{isPlatformAdmin ? (
					<FormSection title="Budgets" testId="budget-card">
						<div className="grid grid-cols-1 gap-4 md:grid-cols-3">
							<FormField
								control={form.control}
								name="max_iterations"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Max iterations</FormLabel>
										<FormControl>
											<Input
												type="number"
												value={field.value ?? ""}
												onChange={(e) =>
													field.onChange(
														e.target.value
															? Number(e.target.value)
															: null,
													)
												}
											/>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>
							<FormField
								control={form.control}
								name="max_token_budget"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Max token budget</FormLabel>
										<FormControl>
											<Input
												type="number"
												value={field.value ?? ""}
												onChange={(e) =>
													field.onChange(
														e.target.value
															? Number(e.target.value)
															: null,
													)
												}
											/>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>
							<FormField
								control={form.control}
								name="llm_max_tokens"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Max tokens / response</FormLabel>
										<FormControl>
											<Input
												type="number"
												value={field.value ?? ""}
												onChange={(e) =>
													field.onChange(
														e.target.value
															? Number(e.target.value)
															: null,
													)
												}
											/>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>
						</div>
					</FormSection>
				) : null}

				<div className="flex items-center justify-end gap-2 border-t bg-muted/30 px-5 py-3">
					<Button type="submit" disabled={pending}>
						{pending
							? "Saving…"
							: mode === "create"
								? "Create agent"
								: "Save changes"}
					</Button>
				</div>
			</form>
		</Form>
	);
}
