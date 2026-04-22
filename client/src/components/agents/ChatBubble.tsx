import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export type ChatBubbleKind = "user" | "assistant" | "system";

export interface ChatBubbleProps {
	kind: ChatBubbleKind;
	children: ReactNode;
	/** Optional timestamp shown in 10.5px subtle tone under the bubble. */
	time?: ReactNode;
	/**
	 * Nested tool-result blocks (proposals, dry-run previews, etc.) rendered
	 * below the prose, *inside* the same bubble. Assistant bubbles only.
	 */
	slots?: ReactNode;
	className?: string;
}

/**
 * Message bubble for per-flag chat + tune conversations.
 *
 * Layout:
 *   user      → right-aligned, primary-tinted background
 *   assistant → left-aligned with sparkles avatar, muted-2 bg + border
 *   system    → centered, muted, no avatar
 *
 * When `slots` is passed on an assistant bubble, each slot renders as a nested
 * block inside the same bubble below the prose — styled as a tool-result card
 * so it's visually inside the assistant's turn, not a floating sibling card.
 * This is the pattern used for ProposalTurn + DryRunTurn in tune chat.
 */
export function ChatBubble({
	kind,
	children,
	time,
	slots,
	className,
}: ChatBubbleProps) {
	if (kind === "user") {
		return (
			<div className={cn("flex flex-col items-end", className)}>
				<div className="max-w-[92%] whitespace-pre-wrap rounded-[10px] bg-primary/15 px-3 py-2.5 text-[13.5px] leading-relaxed text-foreground">
					{children}
				</div>
				{time ? (
					<div className="mt-1 text-[10.5px] text-muted-foreground">
						{time}
					</div>
				) : null}
			</div>
		);
	}

	if (kind === "system") {
		return (
			<div className={cn("flex justify-center", className)}>
				<div className="rounded-full border bg-muted/40 px-3 py-1 text-[12px] text-muted-foreground">
					{children}
				</div>
			</div>
		);
	}

	// assistant
	return (
		<div className={cn("flex items-start gap-2", className)}>
			<div
				aria-hidden
				className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-purple-500 text-background"
			>
				<Sparkles className="h-[11px] w-[11px]" />
			</div>
			<div className="min-w-0 flex-1 rounded-[10px] border bg-muted/40 px-3 py-2.5 text-[13.5px] leading-relaxed text-foreground">
				<div className="whitespace-pre-wrap">{children}</div>
				{slots ? <div className="mt-3 space-y-2">{slots}</div> : null}
				{time ? (
					<div className="mt-1 text-[10.5px] text-muted-foreground">
						{time}
					</div>
				) : null}
			</div>
		</div>
	);
}

// ──────────────────────────────────────────────────────────────────────────
// Slot helpers — nested tool-result blocks rendered inside assistant bubbles
// ──────────────────────────────────────────────────────────────────────────

export interface ChatBubbleSlotProps {
	title: ReactNode;
	titleTone?: "primary" | "emerald" | "yellow";
	actions?: ReactNode;
	children: ReactNode;
}

/**
 * Nested block inside a ChatBubble slot. Bordered card on base bg with a small
 * colored title line and an optional action row at the bottom.
 */
export function ChatBubbleSlot({
	title,
	titleTone = "primary",
	actions,
	children,
}: ChatBubbleSlotProps) {
	const titleColor =
		titleTone === "emerald"
			? "text-emerald-500"
			: titleTone === "yellow"
				? "text-yellow-500"
				: "text-primary";
	return (
		<div className="rounded-md border bg-background/60 p-2.5">
			<div
				className={cn(
					"mb-2 text-[12px] font-medium",
					titleColor,
				)}
			>
				{title}
			</div>
			<div>{children}</div>
			{actions ? (
				<div className="mt-2.5 flex flex-wrap items-center gap-2">
					{actions}
				</div>
			) : null}
		</div>
	);
}
