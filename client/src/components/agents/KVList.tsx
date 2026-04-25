import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { TONE_MUTED, TYPE_MONO } from "./design-tokens";

export interface KVItem {
	label: string;
	value: ReactNode;
	/** Render value with mono font at 12.5px (for keys, hashes, model names). */
	mono?: boolean;
}

export interface KVListProps {
	items: KVItem[];
	className?: string;
}

/**
 * 2-column definition list matching the mockup's `.kv` layout:
 *   `grid-template-columns: 120px 1fr`
 *   8px row gap, 14px column gap, 13px muted labels, normal-tone values.
 *
 * Used for Configuration / Budgets / Captured data / run sidebars.
 */
export function KVList({ items, className }: KVListProps) {
	return (
		<dl
			className={cn(
				"grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-[13px]",
				className,
			)}
		>
			{items.map((item, idx) => (
				<div key={idx} className="contents">
					<dt className={TONE_MUTED}>{item.label}</dt>
					<dd className={cn("m-0", item.mono && `truncate ${TYPE_MONO}`)}>
						{item.value}
					</dd>
				</div>
			))}
		</dl>
	);
}
