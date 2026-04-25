import { useId } from "react";

import { cn } from "@/lib/utils";

export interface SparklineProps {
	values: number[];
	className?: string;
	/** Tailwind text-* class, e.g. "text-emerald-400". Drives both line + fill gradient. */
	colorClass?: string;
	strokeWidth?: number;
}

/**
 * Inline-SVG area sparkline. No recharts dependency.
 * Matches the mockup's Sparkline.tsx visual — thin line with a soft fill gradient below.
 */
export function Sparkline({
	values,
	className,
	colorClass = "text-primary",
	strokeWidth = 1.5,
}: SparklineProps) {
	const gradientId = useId();
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

	const areaPath = `M0,${h} L${points.split(" ").join(" L")} L${w},${h} Z`;

	return (
		<svg
			viewBox={`0 0 ${w} ${h}`}
			preserveAspectRatio="none"
			className={cn("h-full w-full", colorClass, className)}
			aria-hidden
		>
			<defs>
				<linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" stopColor="currentColor" stopOpacity={0.35} />
					<stop offset="100%" stopColor="currentColor" stopOpacity={0} />
				</linearGradient>
			</defs>
			<path d={areaPath} fill={`url(#${gradientId})`} />
			<polyline
				points={points}
				fill="none"
				stroke="currentColor"
				strokeWidth={strokeWidth}
				strokeLinejoin="round"
				strokeLinecap="round"
			/>
		</svg>
	);
}
