/**
 * Strip of stat cards for the FleetPage.
 *
 * Inputs come from the FleetStatsResponse hook (T27). The total runs card can
 * optionally render a sparkline if the caller provides a daily breakdown
 * (the OpenAPI FleetStatsResponse does not include one today, so this is
 * a future extension point that doesn't add another API call).
 */

import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatCost, formatNumber } from "@/lib/utils";
import type { components } from "@/lib/v1";

type FleetStatsResponse = components["schemas"]["FleetStatsResponse"];

export interface FleetStatsProps {
	stats: FleetStatsResponse;
	/** Optional per-day run counts for a sparkline on the runs card. */
	runsByDay?: number[];
	/** Optional click handler on the needs-review card. */
	onNeedsReviewClick?: () => void;
	className?: string;
}

export function FleetStats({
	stats,
	runsByDay,
	onNeedsReviewClick,
	className,
}: FleetStatsProps) {
	const successPct = Math.round((stats.avg_success_rate ?? 0) * 100);
	return (
		<div
			className={cn(
				"grid gap-3 grid-cols-2 lg:grid-cols-3 xl:grid-cols-5",
				className,
			)}
			data-slot="fleet-stats"
		>
			<StatCard
				label="Runs (7d)"
				value={formatNumber(stats.total_runs)}
				sparkline={runsByDay}
			/>
			<StatCard
				label="Avg success rate"
				value={`${successPct}%`}
				valueColor={successColor(stats.avg_success_rate)}
			/>
			<StatCard
				label="Spend (7d)"
				value={formatCost(stats.total_cost_7d)}
			/>
			<StatCard
				label="Active agents"
				value={formatNumber(stats.active_agents)}
			/>
			<StatCard
				label="Needs review"
				value={formatNumber(stats.needs_review)}
				icon={
					stats.needs_review > 0 ? (
						<AlertTriangle size={11} />
					) : undefined
				}
				valueColor={
					stats.needs_review > 0
						? "text-rose-600 dark:text-rose-400"
						: undefined
				}
				onClick={
					stats.needs_review > 0 ? onNeedsReviewClick : undefined
				}
			/>
		</div>
	);
}

interface StatCardProps {
	label: string;
	value: string;
	icon?: React.ReactNode;
	valueColor?: string;
	sparkline?: number[];
	onClick?: () => void;
}

function StatCard({
	label,
	value,
	icon,
	valueColor,
	sparkline,
	onClick,
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
				"flex flex-col gap-1 rounded-lg border bg-card p-4 transition-colors",
				interactive && "cursor-pointer hover:bg-accent/40",
			)}
			data-slot="stat-card"
		>
			<div className="flex items-center gap-1 text-xs text-muted-foreground">
				{icon}
				{label}
			</div>
			<div className={cn("text-2xl font-semibold", valueColor)}>
				{value}
			</div>
			{sparkline && sparkline.length > 1 ? (
				<div className="mt-2 h-8">
					<Sparkline values={sparkline} />
				</div>
			) : null}
		</div>
	);
}

function successColor(rate: number | null | undefined): string | undefined {
	if (rate == null) return undefined;
	if (rate >= 0.9) return "text-emerald-600 dark:text-emerald-400";
	if (rate >= 0.75) return "text-yellow-600 dark:text-yellow-400";
	return "text-rose-600 dark:text-rose-400";
}

/** Inline-SVG sparkline — no recharts dependency. */
function Sparkline({ values }: { values: number[] }) {
	if (values.length < 2) return null;
	const w = 100;
	const h = 30;
	const max = Math.max(...values, 1);
	const min = Math.min(...values, 0);
	const range = Math.max(max - min, 1);
	const step = w / (values.length - 1);
	const points = values
		.map((v, i) => {
			const x = i * step;
			const y = h - ((v - min) / range) * h;
			return `${x.toFixed(2)},${y.toFixed(2)}`;
		})
		.join(" ");
	const areaPath = `M0,${h} L${points
		.split(" ")
		.join(" L")} L${w},${h} Z`;
	return (
		<svg
			viewBox={`0 0 ${w} ${h}`}
			preserveAspectRatio="none"
			className="h-full w-full"
			aria-hidden
		>
			<path
				d={areaPath}
				fill="currentColor"
				className="text-primary/15"
			/>
			<polyline
				points={points}
				fill="none"
				stroke="currentColor"
				strokeWidth={1.5}
				strokeLinejoin="round"
				strokeLinecap="round"
				className="text-primary"
			/>
		</svg>
	);
}

/** Re-export formatCost so consumers can format the cost string from the API. */
export { formatCost };
