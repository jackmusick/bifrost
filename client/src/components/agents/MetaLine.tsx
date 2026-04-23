import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TONE_MUTED, TYPE_MUTED } from "./design-tokens";

export interface MetaLineProps {
	/** Ordered list of tokens — strings, numbers, or ready-made nodes. Nulls are skipped. */
	items: Array<ReactNode | null | undefined | false>;
	/** Separator character between items. Defaults to middle dot. */
	separator?: string;
	className?: string;
}

/**
 * Small muted inline strip like `"1h ago · 3.4s · 2 iter · 1,852 tok · $0.04"`.
 * Used on Run detail / flipbook / tune / agent headers wherever the mockup
 * shows a comma-or-dot separated set of tiny run stats.
 *
 * Items separate at 13px muted. Nulls / false / empty strings are skipped so
 * callers can conditionally include segments without noise.
 */
export function MetaLine({
	items,
	separator = "·",
	className,
}: MetaLineProps) {
	const visible = items.filter((it): it is ReactNode => {
		if (it == null || it === false) return false;
		if (typeof it === "string" && it.trim().length === 0) return false;
		return true;
	});
	if (visible.length === 0) return null;
	return (
		<div
			className={cn(
				"inline-flex flex-wrap items-center gap-2",
				TYPE_MUTED,
				className,
			)}
		>
			{visible.map((item, idx) => (
				<span key={idx} className="inline-flex items-center gap-2">
					{idx > 0 ? (
						<span aria-hidden className={TONE_MUTED}>
							{separator}
						</span>
					) : null}
					<span>{item}</span>
				</span>
			))}
		</div>
	);
}
