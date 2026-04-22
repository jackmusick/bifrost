/**
 * AgentTunePage — consolidated tuning workflow for an agent.
 *
 * Routes:
 *   /agents/:id/tune
 *
 * Layout mirrors /tmp/agent-mockup/src/pages/TuneChatPage.tsx:
 *   - Left sidebar: list of flagged runs, current prompt preview.
 *   - Main: chat-style log of the tuning conversation. Proposals and dry-run
 *     results render *inside* the assistant's bubble as nested slots (via
 *     ChatBubbleSlot), not as floating sibling cards — that was the Phase-7b
 *     T71 redesign. Actions ("Dry-run", "Apply") are inline on the proposal
 *     slot.
 *
 * NOTE: the diff display is a simple before/after side-by-side. We don't pull
 * in a real diff library here — ConsolidatedProposalResponse only carries
 * `proposed_prompt`, not a structured diff. // TODO: real diff library
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	ArrowLeft,
	Check,
	FileText,
	Loader2,
	PlayCircle,
	Sparkles,
	ThumbsDown,
} from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { ChatComposer } from "@/components/ui/chat-composer";
import { Skeleton } from "@/components/ui/skeleton";

import { ChatBubble, ChatBubbleSlot } from "@/components/agents/ChatBubble";
import {
	TONE_MUTED,
	TYPE_LABEL_UPPERCASE,
	TYPE_MUTED,
} from "@/components/agents/design-tokens";

import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import {
	useApplyTuning,
	useTuningDryRun,
	useTuningSession,
	type ConsolidatedDryRunResponse,
	type ConsolidatedProposal,
} from "@/services/agentTuning";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type AgentRun = components["schemas"]["AgentRunResponse"];

type ChatMessage =
	| { kind: "system"; content: string }
	| { kind: "user"; content: string }
	| { kind: "assistant"; content: string }
	| { kind: "proposal"; proposal: ConsolidatedProposal }
	| { kind: "dryrun"; result: ConsolidatedDryRunResponse };

export function AgentTunePage() {
	const { id: agentId } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const { data: agent } = useAgent(agentId);
	const { data: flaggedResp, isLoading: flaggedLoading } = useAgentRuns({
		agentId,
		verdict: "down",
	});

	const flagged = useMemo<AgentRun[]>(
		() => (flaggedResp?.items ?? []) as AgentRun[],
		[flaggedResp],
	);

	const tuningSession = useTuningSession();
	const tuningDryRun = useTuningDryRun();
	const applyTuning = useApplyTuning();

	const [proposal, setProposal] = useState<ConsolidatedProposal | null>(null);
	const [messages, setMessages] = useState<ChatMessage[]>([
		{
			kind: "system",
			content:
				"I'll consolidate context from this agent's flagged runs and propose a single prompt change. Nothing applies until you say so.",
		},
	]);

	const scrollRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const el = scrollRef.current;
		if (!el) return;
		el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
	}, [messages.length]);

	function pushMessage(m: ChatMessage) {
		setMessages((prev) => [...prev, m]);
	}

	function handleSend(text: string) {
		pushMessage({ kind: "user", content: text });
		pushMessage({
			kind: "assistant",
			content:
				"Got it — pulling a consolidated proposal across the flagged runs.",
		});
		runProposal();
	}

	function runProposal() {
		if (!agentId) return;
		tuningSession.mutate(
			{ params: { path: { agent_id: agentId } } },
			{
				onSuccess: (data) => {
					const p = data as ConsolidatedProposal;
					setProposal(p);
					pushMessage({ kind: "proposal", proposal: p });
				},
				onError: () => {
					toast.error("Failed to generate proposal");
				},
			},
		);
	}

	function runDryRun() {
		if (!agentId || !proposal) return;
		tuningDryRun.mutate(
			{
				params: { path: { agent_id: agentId } },
				body: { proposed_prompt: proposal.proposed_prompt },
			},
			{
				onSuccess: (data) => {
					pushMessage({
						kind: "dryrun",
						result: data as ConsolidatedDryRunResponse,
					});
				},
				onError: () => {
					toast.error("Dry-run failed");
				},
			},
		);
	}

	function handleApply() {
		if (!agentId || !proposal) return;
		applyTuning.mutate(
			{
				params: { path: { agent_id: agentId } },
				body: { new_prompt: proposal.proposed_prompt },
			},
			{
				onSuccess: () => {
					toast.success("Prompt updated");
					queryClient.invalidateQueries({
						queryKey: ["get", "/api/agents"],
					});
					queryClient.invalidateQueries({ queryKey: ["agent-runs"] });
					navigate(`/agents/${agentId}`);
				},
				onError: () => {
					toast.error("Failed to apply tuning");
				},
			},
		);
	}

	const currentPrompt =
		(agent as unknown as { system_prompt?: string })?.system_prompt ?? "";

	return (
		<div
			className="mx-auto flex max-w-7xl flex-col gap-4"
			data-testid="agent-tune-page"
		>
			<Link
				to={agentId ? `/agents/${agentId}` : "/agents"}
				className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
			>
				<ArrowLeft className="h-3 w-3" />
				{agent?.name ?? "Back to agent"}
			</Link>

			<div className="flex flex-wrap items-start justify-between gap-3">
				<div>
					<h1 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
						<Sparkles className="h-5 w-5" />
						Tune agent
					</h1>
					<p className={cn("mt-1", TYPE_MUTED)}>
						Refine {agent?.name ?? "this agent"}&apos;s prompt against{" "}
						{flagged.length} flagged run
						{flagged.length === 1 ? "" : "s"}. Changes are dry-run before
						going live.
					</p>
				</div>
				<Button asChild variant="outline">
					<Link to={`/agents/${agentId}/review`}>
						<FileText className="h-4 w-4" />
						Back to review
					</Link>
				</Button>
			</div>

			<div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
				{/* Main chat column */}
				<Card className="flex min-h-[600px] flex-col overflow-hidden">
					<div
						ref={scrollRef}
						className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-5"
						data-testid="tune-messages"
					>
						{messages.map((m, i) => (
							<TuneMessage
								key={i}
								msg={m}
								onDryRun={runDryRun}
								onApply={handleApply}
								dryRunning={tuningDryRun.isPending}
								applying={applyTuning.isPending}
							/>
						))}
						{tuningSession.isPending ? (
							<div className="inline-flex w-fit items-center gap-2 rounded-2xl bg-muted px-3 py-2 text-xs text-muted-foreground">
								<Loader2 className="h-3 w-3 animate-spin" />
								Building proposal…
							</div>
						) : null}
					</div>
					<div className="border-t bg-muted/40 p-3">
						{!proposal ? (
							<div className="mb-2 flex items-center gap-2">
								<Button
									type="button"
									size="sm"
									onClick={runProposal}
									disabled={
										tuningSession.isPending || flagged.length === 0
									}
									data-testid="propose-button"
								>
									{tuningSession.isPending ? (
										<Loader2 className="h-3 w-3 animate-spin" />
									) : (
										<Sparkles className="h-3 w-3" />
									)}
									Propose change
								</Button>
							</div>
						) : null}
						<ChatComposer
							placeholder="Ask for another change, or focus on a pattern…"
							onSend={handleSend}
							pending={tuningSession.isPending}
						/>
					</div>
				</Card>

				{/* Sidebar */}
				<div className="flex flex-col gap-4">
					<Card>
						<CardHeader className="pb-2">
							<CardTitle className="text-sm">
								Flagged runs ({flagged.length})
							</CardTitle>
						</CardHeader>
						<CardContent
							className="max-h-[320px] overflow-y-auto p-0"
							data-testid="flagged-list"
						>
							{flaggedLoading ? (
								<div className="p-3">
									<Skeleton className="h-12 w-full" />
								</div>
							) : flagged.length === 0 ? (
								<p
									className={cn(
										"px-3 py-6 text-center text-xs",
										TONE_MUTED,
									)}
								>
									No flagged runs.
								</p>
							) : (
								<ul className="divide-y">
									{flagged.map((r) => (
										<li key={r.id}>
											<Link
												to={`/agents/${r.agent_id}/runs/${r.id}`}
												className="flex items-start gap-2 px-3 py-2 text-xs hover:bg-accent/40"
											>
												<div className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-rose-500/15 text-rose-500">
													<ThumbsDown className="h-3 w-3" />
												</div>
												<div className="min-w-0">
													<div className="truncate text-foreground">
														{r.asked || r.did || "Run"}
													</div>
													{r.verdict_note ? (
														<div
															className="truncate text-[11px] italic text-muted-foreground"
															title={
																r.verdict_note ?? undefined
															}
														>
															&quot;
															{r.verdict_note}
															&quot;
														</div>
													) : null}
												</div>
											</Link>
										</li>
									))}
								</ul>
							)}
						</CardContent>
					</Card>

					<Card>
						<CardHeader className="pb-2">
							<CardTitle className="text-sm">Current prompt</CardTitle>
						</CardHeader>
						<CardContent>
							<pre className="max-h-44 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">
								{currentPrompt || "(no system prompt set)"}
							</pre>
						</CardContent>
					</Card>
				</div>
			</div>
		</div>
	);
}

// ──────────────────────────────────────────────────────────────────────────
// Chat message dispatch
// ──────────────────────────────────────────────────────────────────────────

function TuneMessage({
	msg,
	onDryRun,
	onApply,
	dryRunning,
	applying,
}: {
	msg: ChatMessage;
	onDryRun: () => void;
	onApply: () => void;
	dryRunning: boolean;
	applying: boolean;
}) {
	if (msg.kind === "system") {
		return <ChatBubble kind="system">{msg.content}</ChatBubble>;
	}
	if (msg.kind === "user") {
		return <ChatBubble kind="user">{msg.content}</ChatBubble>;
	}
	if (msg.kind === "assistant") {
		return <ChatBubble kind="assistant">{msg.content}</ChatBubble>;
	}
	if (msg.kind === "proposal") {
		return (
			<ProposalBubble
				proposal={msg.proposal}
				onDryRun={onDryRun}
				onApply={onApply}
				dryRunning={dryRunning}
				applying={applying}
			/>
		);
	}
	return <DryRunBubble result={msg.result} />;
}

// ──────────────────────────────────────────────────────────────────────────
// Proposal + Dry-run bubbles — both render as assistant ChatBubbles with a
// nested ChatBubbleSlot carrying the diff / results inline.
// ──────────────────────────────────────────────────────────────────────────

function ProposalBubble({
	proposal,
	onDryRun,
	onApply,
	dryRunning,
	applying,
}: {
	proposal: ConsolidatedProposal;
	onDryRun: () => void;
	onApply: () => void;
	dryRunning: boolean;
	applying: boolean;
}) {
	return (
		<div data-testid="proposal-card">
		<ChatBubble
			kind="assistant"
			slots={
				<ChatBubbleSlot
					title="Proposed change"
					titleTone="primary"
					actions={
						<>
							<Button
								size="sm"
								variant="outline"
								onClick={onDryRun}
								disabled={dryRunning}
								data-testid="dryrun-button"
							>
								{dryRunning ? (
									<Loader2 className="h-3 w-3 animate-spin" />
								) : (
									<PlayCircle className="h-3 w-3" />
								)}
								Dry-run against all
							</Button>
							<Button
								size="sm"
								onClick={onApply}
								disabled={applying}
								data-testid="apply-button"
							>
								{applying ? (
									<Loader2 className="h-3 w-3 animate-spin" />
								) : (
									<Check className="h-3 w-3" />
								)}
								Accept
							</Button>
							<span className={cn("ml-auto text-[11px]", TONE_MUTED)}>
								Accept saves the new prompt live · Dry-run only simulates
							</span>
						</>
					}
				>
					<div className="grid gap-3 md:grid-cols-2">
						<div>
							<div className={cn("mb-1", TYPE_LABEL_UPPERCASE)}>
								Before
							</div>
							<pre
								className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-2 font-mono text-[11.5px] leading-relaxed"
								data-testid="proposal-before"
							>
								{/* TODO: real diff library — API only carries proposed_prompt. */}
								(current prompt — see sidebar)
							</pre>
						</div>
						<div>
							<div className={cn("mb-1", TYPE_LABEL_UPPERCASE)}>
								After
							</div>
							<pre
								className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2 font-mono text-[11.5px] leading-relaxed"
								data-testid="proposal-after"
							>
								{proposal.proposed_prompt}
							</pre>
						</div>
					</div>
					<div className={cn("mt-2 text-[11px]", TONE_MUTED)}>
						{proposal.summary}
					</div>
					<div className={cn("mt-0.5 text-[11px]", TONE_MUTED)}>
						Will affect {proposal.affected_run_ids.length} flagged run
						{proposal.affected_run_ids.length === 1 ? "" : "s"}.
					</div>
				</ChatBubbleSlot>
			}
			// Intentional: proposal replaces the assistant's prose with the slot
			// so the card-embedded-in-bubble reads as a single turn.
		>
			{/* Empty prose — the slot carries all the content. */}
			<span className="sr-only">Proposed change below.</span>
		</ChatBubble>
		</div>
	);
}

function DryRunBubble({ result }: { result: ConsolidatedDryRunResponse }) {
	const total = result.results.length;
	const pass = result.results.filter(
		(r) => !r.would_still_decide_same,
	).length;
	const allPass = pass === total && total > 0;
	return (
		<ChatBubble
			kind="assistant"
			slots={
				<ChatBubbleSlot
					title={allPass ? "Dry-run passed" : "Dry-run results"}
					titleTone={allPass ? "emerald" : "yellow"}
				>
					<p className={cn("mb-2 text-[11px]", TONE_MUTED)}>
						{pass} of {total} would change behavior with the new prompt.
					</p>
					<div className="grid gap-1.5" data-testid="dryrun-card">
						{result.results.map((r) => (
							<div
								key={r.run_id}
								className="rounded-md border bg-card p-2 text-xs"
							>
								<div className="flex items-center justify-between gap-2">
									<span className="font-mono text-[11px] text-muted-foreground">
										{r.run_id.slice(0, 8)}…
									</span>
									<Badge
										variant="outline"
										className={cn(
											"text-[10.5px]",
											r.would_still_decide_same
												? "border-yellow-500/40 text-yellow-500"
												: "border-emerald-500/40 text-emerald-500",
										)}
									>
										{r.would_still_decide_same
											? "Still wrong"
											: "Would change"}
									</Badge>
								</div>
								<div className={cn("mt-1", TONE_MUTED)}>
									{r.reasoning}
								</div>
								<div className="mt-0.5 text-[10.5px] text-muted-foreground">
									confidence: {Math.round(r.confidence * 100)}%
								</div>
							</div>
						))}
					</div>
				</ChatBubbleSlot>
			}
		>
			<span className="sr-only">Dry-run result below.</span>
		</ChatBubble>
	);
}

export default AgentTunePage;
