import {
	LineChart,
	Line,
	XAxis,
	YAxis,
	CartesianGrid,
	Tooltip,
	ResponsiveContainer,
	Legend,
} from "recharts";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
	CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ResourceMetricsEntry } from "@/services/metrics";

interface ResourceTrendChartProps {
	data: ResourceMetricsEntry[];
	isLoading?: boolean;
}

export function ResourceTrendChart({
	data,
	isLoading,
}: ResourceTrendChartProps) {
	if (isLoading) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Resource Utilization</CardTitle>
					<CardDescription>
						Memory and CPU trends over time
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Skeleton className="h-[300px] w-full" />
				</CardContent>
			</Card>
		);
	}

	// Transform data for chart (reverse for chronological order)
	const chartData = [...data].reverse().map((entry) => ({
		date: new Date(entry.date).toLocaleDateString("en-US", {
			month: "short",
			day: "numeric",
		}),
		memory_mb: Math.round(entry.avg_memory_bytes / (1024 * 1024)),
		cpu_seconds: Number(entry.avg_cpu_seconds.toFixed(2)),
		executions: entry.execution_count,
	}));

	if (chartData.length === 0) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Resource Utilization</CardTitle>
					<CardDescription>
						Memory and CPU trends over time
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex items-center justify-center h-[300px] text-muted-foreground">
						No resource data available
					</div>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle>Resource Utilization</CardTitle>
				<CardDescription>
					Average memory and CPU per execution (7 days)
				</CardDescription>
			</CardHeader>
			<CardContent>
				<ResponsiveContainer width="100%" height={300}>
					<LineChart data={chartData}>
						<CartesianGrid
							strokeDasharray="3 3"
							className="stroke-muted"
						/>
						<XAxis
							dataKey="date"
							className="text-xs"
							tick={{ fontSize: 12 }}
						/>
						<YAxis
							yAxisId="left"
							className="text-xs"
							tick={{ fontSize: 12 }}
							label={{
								value: "MB",
								angle: -90,
								position: "insideLeft",
								fontSize: 12,
							}}
						/>
						<YAxis
							yAxisId="right"
							orientation="right"
							className="text-xs"
							tick={{ fontSize: 12 }}
							label={{
								value: "CPU (s)",
								angle: 90,
								position: "insideRight",
								fontSize: 12,
							}}
						/>
						<Tooltip
							contentStyle={{
								backgroundColor: "hsl(var(--card))",
								border: "1px solid hsl(var(--border))",
								borderRadius: "6px",
							}}
							formatter={(value: number, name: string) => {
								if (name === "memory_mb")
									return [`${value} MB`, "Avg Memory"];
								if (name === "cpu_seconds")
									return [`${value}s`, "Avg CPU"];
								return [value, name];
							}}
							labelFormatter={(label) => `Date: ${label}`}
						/>
						<Legend
							formatter={(value) => {
								if (value === "memory_mb")
									return "Avg Memory (MB)";
								if (value === "cpu_seconds")
									return "Avg CPU (s)";
								return value;
							}}
						/>
						<Line
							yAxisId="left"
							type="monotone"
							dataKey="memory_mb"
							stroke="hsl(var(--chart-1, 220 70% 50%))"
							strokeWidth={2}
							dot={{ r: 3 }}
							activeDot={{ r: 5 }}
						/>
						<Line
							yAxisId="right"
							type="monotone"
							dataKey="cpu_seconds"
							stroke="hsl(var(--chart-2, 160 60% 45%))"
							strokeWidth={2}
							dot={{ r: 3 }}
							activeDot={{ r: 5 }}
						/>
					</LineChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}
