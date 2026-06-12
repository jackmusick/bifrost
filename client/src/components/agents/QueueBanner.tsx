/**
 * Banner for the FleetPage / agent detail page summarising the tuning queue.
 *
 * Shown when there are flagged runs awaiting review/tuning. Renders a count,
 * a short description, and a primary action ("Open tuning" / "Review now").
 *
 * Optionally dismissible — the parent owns dismiss state so it persists
 * across navigations / view toggles.
 */

import { Sparkles, X } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface QueueBannerProps {
	/** Number of flagged runs in the queue. The banner renders nothing when 0. */
	count: number;
	/** Optional override for the description copy. */
	description?: string;
	/** Optional href for the action button. Rendered as a React Router Link so
	 *  navigation stays in-SPA. */
	actionHref?: string;
	/** Action button label. Defaults to "Open tuning". */
	actionLabel?: string;
	/** Click handler. Either this or actionHref should be provided. */
	onAction?: () => void;
	/** When provided, renders a close button that calls this. */
	onDismiss?: () => void;
	className?: string;
}

export function QueueBanner({
	count,
	description,
	actionHref,
	actionLabel = "Open tuning",
	onAction,
	onDismiss,
	className,
}: QueueBannerProps) {
	if (count <= 0) return null;
	const subtitle =
		description ??
		"Each flag carries its own diagnosis conversation. Open tuning to propose a unified change.";

	const actionContent = (
		<>
			<Sparkles size={13} /> {actionLabel}
		</>
	);

	return (
		<div
			className={cn(
				"flex items-center justify-between gap-3 rounded-2xl bg-rose-500/10 shadow-sm ring-1 ring-rose-500/30 px-4 py-3",
				className,
			)}
			data-slot="queue-banner"
			role="status"
		>
			<div className="flex min-w-0 items-start gap-3">
				<span
					className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-rose-500"
					aria-hidden
				/>
				<div className="min-w-0">
					<div className="text-sm font-medium">
						{count} flagged run{count === 1 ? "" : "s"} in tuning queue
					</div>
					<div className="mt-0.5 text-xs text-muted-foreground">
						{subtitle}
					</div>
				</div>
			</div>
			<div className="flex shrink-0 items-center gap-2">
				{actionHref ? (
					<Button size="sm" className="text-xs" asChild>
						<Link to={actionHref}>{actionContent}</Link>
					</Button>
				) : onAction ? (
					<Button
						type="button"
						size="sm"
						className="text-xs"
						onClick={onAction}
					>
						{actionContent}
					</Button>
				) : null}
				{onDismiss ? (
					<Button
						type="button"
						variant="ghost"
						size="icon-sm"
						onClick={onDismiss}
						aria-label="Dismiss"
						className="text-muted-foreground"
					>
						<X size={14} />
					</Button>
				) : null}
			</div>
		</div>
	);
}
