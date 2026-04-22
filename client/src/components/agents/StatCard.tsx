import { cn } from "@/lib/utils";
import {
	CARD_SURFACE,
	GAP_LABEL_VALUE,
	TONE_DOWN,
	TONE_MUTED,
	TONE_UP,
	TYPE_LABEL_UPPERCASE,
	TYPE_STAT_DELTA,
	TYPE_STAT_VALUE,
} from "./design-tokens";
import { Sparkline } from "./Sparkline";

export interface StatCardProps {
	label: string;
	value: string;
	/** Text line under the value. E.g. "+18% vs prior week". Optional. */
	delta?: string;
	/** Tone of the delta line. "up" = green, "down" = red, unset = muted. */
	deltaTone?: "up" | "down";
	/** Optional mini-sparkline rendered under the value/delta row. */
	sparkline?: number[];
	sparklineColorClass?: string;
	/** When true, theme the card with a red accent — used for "Needs review". */
	alert?: boolean;
	icon?: React.ReactNode;
	onClick?: () => void;
	className?: string;
}

/**
 * A single stat card matching the mockup's `.stat-card` spec:
 *  - small uppercase label
 *  - 22px semibold value
 *  - optional delta line under value
 *  - optional embedded sparkline
 *  - optional alert treatment (red label + value + border accent)
 */
export function StatCard({
	label,
	value,
	delta,
	deltaTone,
	sparkline,
	sparklineColorClass,
	alert,
	icon,
	onClick,
	className,
}: StatCardProps) {
	const interactive = !!onClick;
	return (
		<div
			role={interactive ? "button" : undefined}
			tabIndex={interactive ? 0 : undefined}
			onClick={onClick}
			onKeyDown={(e) => {
				if (interactive && (e.key === "Enter" || e.key === " ")) {
					e.preventDefault();
					onClick?.();
				}
			}}
			className={cn(
				CARD_SURFACE,
				"px-4 py-3.5 transition-colors",
				alert && "border-rose-500/40",
				interactive && "cursor-pointer hover:border-border/80",
				className,
			)}
			data-slot="stat-card"
		>
			<div
				className={cn(
					"flex items-center",
					GAP_LABEL_VALUE,
					TYPE_LABEL_UPPERCASE,
					alert && "text-rose-500",
				)}
			>
				{icon}
				{label}
			</div>
			<div
				className={cn(
					"mt-1.5",
					TYPE_STAT_VALUE,
					alert && "text-rose-500",
				)}
			>
				{value}
			</div>
			{delta ? (
				<div
					className={cn(
						"mt-1",
						TYPE_STAT_DELTA,
						deltaTone === "up"
							? TONE_UP
							: deltaTone === "down"
								? TONE_DOWN
								: TONE_MUTED,
					)}
				>
					{delta}
				</div>
			) : null}
			{sparkline && sparkline.length > 1 ? (
				<div className="mt-2 h-8">
					<Sparkline values={sparkline} colorClass={sparklineColorClass} />
				</div>
			) : null}
		</div>
	);
}
