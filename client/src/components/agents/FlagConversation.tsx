/**
 * Per-flag tuning conversation.
 *
 * Presentational only — the parent owns the fetch + send mutation
 * (RunReviewSheet, AgentRunDetailPage). The component renders the message
 * stream and a ChatComposer; parent passes `pending` to lock the composer
 * while a send is in flight.
 *
 * Philosophy: every flag is a conversation, never a dead-end text box.
 * The tuning assistant always responds — diagnoses, asks clarifying
 * questions, proposes a change when ready. Changes are NOT applied
 * from here; that happens in the consolidated "Tune agent" flow.
 */

import { useEffect, useRef } from "react";
import { Sparkles, Loader2, CheckCircle, XCircle, PlayCircle } from "lucide-react";

import { ChatComposer } from "@/components/ui/chat-composer";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type FlagConversationResponse = components["schemas"]["FlagConversationResponse"];
type ConversationMessage = FlagConversationResponse["messages"][number];
type UserTurn = components["schemas"]["UserTurn"];
type AssistantTurn = components["schemas"]["AssistantTurn"];
type ProposalTurn = components["schemas"]["ProposalTurn"];
type DryRunTurn = components["schemas"]["DryRunTurn"];

export interface FlagConversationProps {
	conversation: FlagConversationResponse | null;
	onSend: (text: string) => void;
	pending?: boolean;
	onTestAgainstRun?: () => void;
}

export function FlagConversation({
	conversation,
	onSend,
	pending = false,
	onTestAgainstRun,
}: FlagConversationProps) {
	const messages = conversation?.messages ?? [];
	const scrollRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const el = scrollRef.current;
		if (!el) return;
		el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
	}, [messages.length, pending]);

	return (
		<div
			className="flex h-full flex-col"
			data-slot="flag-conversation"
		>
			<div
				ref={scrollRef}
				className="flex-1 min-h-0 overflow-y-auto px-4 py-3.5"
			>
				{messages.length === 0 ? (
					<EmptyState />
				) : (
					messages.map((m, i) => (
						<Bubble
							key={i}
							msg={m}
							onTestAgainstRun={onTestAgainstRun}
						/>
					))
				)}
				{pending ? (
					<div className="mt-2 inline-flex items-center gap-2 rounded-2xl bg-muted px-3 py-2 text-xs text-muted-foreground">
						<Loader2 size={13} className="animate-spin" />
						Thinking…
					</div>
				) : null}
			</div>
			<div className="border-t bg-muted/40 p-3">
				<ChatComposer
					placeholder="What should it have done?"
					onSend={onSend}
					pending={pending}
				/>
			</div>
		</div>
	);
}

function EmptyState() {
	return (
		<div className="rounded-2xl bg-muted/60 px-3.5 py-3 text-sm text-muted-foreground">
			Flag this run and tell me what went wrong. I&apos;ll help diagnose
			and propose a change — nothing touches the live prompt until you
			decide to tune.
		</div>
	);
}

function Bubble({
	msg,
	onTestAgainstRun,
}: {
	msg: ConversationMessage;
	onTestAgainstRun?: () => void;
}) {
	if (msg.kind === "user") {
		return <UserBubble msg={msg as UserTurn} />;
	}
	if (msg.kind === "assistant") {
		return <AssistantBubble msg={msg as AssistantTurn} />;
	}
	if (msg.kind === "proposal") {
		return (
			<ProposalBubble
				msg={msg as ProposalTurn}
				onTestAgainstRun={onTestAgainstRun}
			/>
		);
	}
	if (msg.kind === "dryrun") {
		return <DryRunBubble msg={msg as DryRunTurn} />;
	}
	return null;
}

function UserBubble({ msg }: { msg: UserTurn }) {
	return (
		<div className="mt-2 flex justify-end" data-bubble-kind="user">
			<div className="max-w-[92%] rounded-2xl bg-primary px-3.5 py-2 text-sm text-primary-foreground whitespace-pre-wrap break-words">
				{msg.content}
			</div>
		</div>
	);
}

function AvatarBadge() {
	return (
		<div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-purple-500 text-[#0b0d10]">
			<Sparkles size={11} />
		</div>
	);
}

function AssistantBubble({ msg }: { msg: AssistantTurn }) {
	return (
		<div
			className="mt-2 flex items-start gap-2"
			data-bubble-kind="assistant"
		>
			<AvatarBadge />
			<div className="max-w-[92%] rounded-2xl bg-muted px-3.5 py-2 text-sm whitespace-pre-wrap break-words">
				{msg.content}
			</div>
		</div>
	);
}

function ProposalBubble({
	msg,
	onTestAgainstRun,
}: {
	msg: ProposalTurn;
	onTestAgainstRun?: () => void;
}) {
	return (
		<div
			className="mt-2 flex items-start gap-2"
			data-bubble-kind="proposal"
		>
			<AvatarBadge />
			<div className="flex-1 rounded-2xl border bg-card px-3.5 py-2.5">
				<div className="mb-2 text-xs font-medium text-primary">
					Proposed change
				</div>
				<div className="mb-2.5 text-sm text-muted-foreground">
					{msg.summary}
				</div>
				<div className="rounded border bg-background p-2 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap">
					{msg.diff.map((d, i) => (
						<div
							key={i}
							className={cn(
								"my-0.5 rounded px-1",
								d.op === "add" &&
									"bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
								d.op === "remove" &&
									"bg-rose-500/10 text-rose-700 dark:text-rose-400",
								d.op === "keep" && "text-muted-foreground",
							)}
						>
							<span className="mr-1 opacity-50">
								{d.op === "add"
									? "+"
									: d.op === "remove"
										? "−"
										: " "}
							</span>
							{d.text}
						</div>
					))}
				</div>
				{onTestAgainstRun ? (
					<div className="mt-2.5 flex items-center gap-2">
						<button
							type="button"
							onClick={onTestAgainstRun}
							className="inline-flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
						>
							<PlayCircle size={12} /> Test against this run
						</button>
						<span className="text-[11.5px] text-muted-foreground">
							Sandbox · nothing is applied live
						</span>
					</div>
				) : null}
			</div>
		</div>
	);
}

function DryRunBubble({ msg }: { msg: DryRunTurn }) {
	const passed = msg.predicted === "up";
	return (
		<div
			className="mt-2 flex items-start gap-2"
			data-bubble-kind="dryrun"
		>
			<div
				className={cn(
					"mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full",
					passed
						? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
						: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400",
				)}
			>
				{passed ? <CheckCircle size={11} /> : <XCircle size={11} />}
			</div>
			<div className="flex-1 rounded-2xl border bg-card px-3.5 py-2.5">
				<div
					className={cn(
						"mb-2 text-xs font-medium",
						passed
							? "text-emerald-600 dark:text-emerald-400"
							: "text-yellow-600 dark:text-yellow-400",
					)}
				>
					{passed ? "Dry-run passed" : "Dry-run still wrong"}
				</div>
				<div className="grid grid-cols-2 gap-2">
					<div>
						<div className="mb-1 text-[10.5px] uppercase tracking-wider text-muted-foreground">
							Before
						</div>
						<div className="rounded bg-rose-500/10 px-2 py-1.5 text-xs">
							{msg.before}
						</div>
					</div>
					<div>
						<div className="mb-1 text-[10.5px] uppercase tracking-wider text-muted-foreground">
							After
						</div>
						<div
							className={cn(
								"rounded px-2 py-1.5 text-xs",
								passed
									? "bg-emerald-500/10"
									: "bg-yellow-500/10",
							)}
						>
							{msg.after}
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
