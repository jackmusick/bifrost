import {
	BarChart,
	Bar,
	XAxis,
	YAxis,
	CartesianGrid,
	Tooltip,
	ResponsiveContainer,
	Cell,
} from "recharts";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
	CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { OrganizationMetricsSummary } from "@/hooks/useAdminMetrics";

interface ExecutionsByOrgChartProps {
	data: OrganizationMetricsSummary[];
	isLoading?: boolean;
}

// Color palette for bars
const COLORS = [
	"hsl(220 70% 50%)",
	"hsl(160 60% 45%)",
	"hsl(30 80% 55%)",
	"hsl(280 65% 60%)",
	"hsl(340 75% 55%)",
	"hsl(200 70% 50%)",
	"hsl(120 60% 45%)",
	"hsl(50 80% 50%)",
	"hsl(300 60% 55%)",
	"hsl(180 65% 45%)",
];

export function ExecutionsByOrgChart({
	data,
	isLoading,
}: ExecutionsByOrgChartProps) {
	if (isLoading) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Executions by Organization</CardTitle>
					<CardDescription>
						Top organizations by execution count
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Skeleton className="h-[300px] w-full" />
				</CardContent>
			</Card>
		);
	}

	const chartData = data.slice(0, 10).map((org) => ({
		name:
			org.organization_name.length > 15
				? org.organization_name.substring(0, 15) + "..."
				: org.organization_name,
		fullName: org.organization_name,
		executions: org.total_executions,
		successRate: org.success_rate,
	}));

	if (chartData.length === 0) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Executions by Organization</CardTitle>
					<CardDescription>
						Top organizations by execution count
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex items-center justify-center h-[300px] text-muted-foreground">
						No organization data available
					</div>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle>Executions by Organization</CardTitle>
				<CardDescription>
					Top {chartData.length} organizations by execution count (30
					days)
				</CardDescription>
			</CardHeader>
			<CardContent>
				<ResponsiveContainer width="100%" height={300}>
					<BarChart data={chartData} layout="vertical">
						<CartesianGrid
							strokeDasharray="3 3"
							className="stroke-muted"
						/>
						<XAxis
							type="number"
							className="text-xs"
							tick={{ fontSize: 12 }}
						/>
						<YAxis
							dataKey="name"
							type="category"
							className="text-xs"
							width={100}
							tick={{ fontSize: 11 }}
						/>
						<Tooltip
							contentStyle={{
								backgroundColor: "hsl(var(--card))",
								border: "1px solid hsl(var(--border))",
								borderRadius: "6px",
							}}
							formatter={(
								value: number,
								_name: string,
								props,
							) => [
								`${value.toLocaleString()} executions`,
								props.payload.fullName,
							]}
							labelFormatter={() => ""}
						/>
						<Bar dataKey="executions" radius={[0, 4, 4, 0]}>
							{chartData.map((_, index) => (
								<Cell
									key={`cell-${index}`}
									fill={COLORS[index % COLORS.length]}
								/>
							))}
						</Bar>
					</BarChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
}
