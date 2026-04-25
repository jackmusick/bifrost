import { cn } from "@/lib/utils";
import { RADIUS_BUTTON, RADIUS_INNER } from "./design-tokens";

export interface PillTabItem {
	value: string;
	label: string;
	/** Optional count badge rendered after the label — e.g. "Runs 14". */
	count?: number;
	disabled?: boolean;
}

export interface PillTabsProps {
	items: PillTabItem[];
	value: string;
	onValueChange: (v: string) => void;
	className?: string;
}

/**
 * Pill-style tab bar matching the mockup's `.tabs` + `.tab.active` spec.
 * Rounded group container on elevated-2 bg, active tab fills with card bg + border.
 *
 * Intentionally separate from shadcn's Tabs — the visual spec and count-badge
 * affordance are specific to the agent surfaces.
 */
export function PillTabs({
	items,
	value,
	onValueChange,
	className,
}: PillTabsProps) {
	return (
		<div
			role="tablist"
			className={cn(
				"inline-flex items-center gap-0.5 border bg-muted/60 p-[3px]",
				RADIUS_INNER,
				className,
			)}
		>
			{items.map((item) => {
				const active = item.value === value;
				return (
					<button
						key={item.value}
						type="button"
						role="tab"
						aria-selected={active}
						disabled={item.disabled}
						onClick={() => !item.disabled && onValueChange(item.value)}
						className={cn(
							"inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] transition-colors",
							RADIUS_BUTTON,
							active
								? "border border-border bg-card text-foreground shadow-sm"
								: "border border-transparent text-muted-foreground hover:text-foreground",
							item.disabled && "opacity-40 cursor-not-allowed",
						)}
					>
						{item.label}
						{item.count != null && item.count > 0 ? (
							<span
								className={cn(
									"inline-flex items-center justify-center rounded-full px-1.5 py-px text-[11px] font-medium tabular-nums",
									active
										? "bg-muted text-foreground"
										: "bg-muted/60 text-muted-foreground",
								)}
							>
								{item.count}
							</span>
						) : null}
					</button>
				);
			})}
		</div>
	);
}
