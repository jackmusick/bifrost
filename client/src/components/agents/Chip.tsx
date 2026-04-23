import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TYPE_MONO } from "./design-tokens";

export type ChipTone = "muted" | "primary" | "emerald" | "rose" | "yellow";

export interface ChipProps {
	children: ReactNode;
	/** Label shown before the value, e.g. `ticket_id` in `ticket_id 4822`. */
	label?: string;
	tone?: ChipTone;
	mono?: boolean;
	className?: string;
}

const TONE_CLASSES: Record<ChipTone, string> = {
	muted: "bg-muted/60 text-muted-foreground border-border",
	primary: "bg-primary/15 text-primary border-transparent",
	emerald: "bg-emerald-500/15 text-emerald-500 border-transparent",
	rose: "bg-rose-500/15 text-rose-500 border-transparent",
	yellow: "bg-yellow-500/15 text-yellow-500 border-transparent",
};

/**
 * Consistent tag pill for captured metadata (`ticket_id 4822`, `customer Globex`).
 * Rounded, small, supports an optional muted `label` prefix rendered at lower
 * weight. Mono treatment for IDs/hashes.
 */
export function Chip({
	children,
	label,
	tone = "muted",
	mono,
	className,
}: ChipProps) {
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11.5px] font-medium",
				TONE_CLASSES[tone],
				className,
			)}
		>
			{label ? (
				<span className="text-muted-foreground/80">{label}</span>
			) : null}
			<span className={mono ? TYPE_MONO : undefined}>{children}</span>
		</span>
	);
}
