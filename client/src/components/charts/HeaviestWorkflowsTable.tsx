import { useNavigate } from "react-router-dom";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
	CardDescription,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronRight } from "lucide-react";
import type { WorkflowMetricsSummary } from "@/hooks/useAdminMetrics";

interface HeaviestWorkflowsTableProps {
	data: WorkflowMetricsSummary[];
	isLoading?: boolean;
	sortBy: "executions" | "memory" | "duration" | "cpu";
	onSortChange: (sort: "executions" | "memory" | "duration" | "cpu") => void;
}

function formatBytes(bytes: number): string {
	if (!bytes) return "0 MB";
	const mb = bytes / (1024 * 1024);
	if (mb < 1) return `${(bytes / 1024).toFixed(1)} KB`;
	if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
	return `${mb.toFixed(1)} MB`;
}

function formatDuration(ms: number): string {
	if (!ms) return "0s";
	if (ms < 1000) return `${ms}ms`;
	const seconds = ms / 1000;
	if (seconds < 60) return `${seconds.toFixed(1)}s`;
	const minutes = seconds / 60;
	return `${minutes.toFixed(1)}m`;
}

export function HeaviestWorkflowsTable({
	data,
	isLoading,
	sortBy,
	onSortChange,
}: HeaviestWorkflowsTableProps) {
	const navigate = useNavigate();

	if (isLoading) {
		return (
			<Card>
				<CardHeader>
					<CardTitle>Heaviest Workflows</CardTitle>
					<CardDescription>
						Workflows consuming most resources
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Skeleton className="h-[300px] w-full" />
				</CardContent>
			</Card>
		);
	}

	const handleRowClick = (workflowName: string) => {
		// Navigate to execution history filtered by workflow
		navigate(`/history?workflow_name=${encodeURIComponent(workflowName)}`);
	};

	const sortOptions: Array<{
		value: "executions" | "memory" | "duration" | "cpu";
		label: string;
	}> = [
		{ value: "executions", label: "Executions" },
		{ value: "memory", label: "Memory" },
		{ value: "duration", label: "Duration" },
		{ value: "cpu", label: "CPU" },
	];

	if (data.length === 0) {
		return (
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>Heaviest Workflows</CardTitle>
							<CardDescription>
								Workflows consuming most resources
							</CardDescription>
						</div>
					</div>
				</CardHeader>
				<CardContent>
					<div className="flex items-center justify-center h-[200px] text-muted-foreground">
						No workflow data available
					</div>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader>
				<div className="flex items-center justify-between">
					<div>
						<CardTitle>Heaviest Workflows</CardTitle>
						<CardDescription>
							Top workflows by resource consumption (30 days)
						</CardDescription>
					</div>
					<div className="flex gap-1">
						{sortOptions.map((option) => (
							<Badge
								key={option.value}
								variant={
									sortBy === option.value
										? "default"
										: "outline"
								}
								className="cursor-pointer"
								onClick={() => onSortChange(option.value)}
							>
								{option.label}
							</Badge>
						))}
					</div>
				</div>
			</CardHeader>
			<CardContent>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Workflow</TableHead>
							<TableHead className="text-right">Runs</TableHead>
							<TableHead className="text-right">
								Avg Memory
							</TableHead>
							<TableHead className="text-right">
								Avg Duration
							</TableHead>
							<TableHead className="text-right">
								Success
							</TableHead>
							<TableHead className="w-8"></TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{data.slice(0, 10).map((workflow) => (
							<TableRow
								key={workflow.workflow_name}
								className="cursor-pointer hover:bg-muted/50"
								onClick={() =>
									handleRowClick(workflow.workflow_name)
								}
							>
								<TableCell className="font-mono text-sm max-w-[200px] truncate">
									{workflow.workflow_name}
								</TableCell>
								<TableCell className="text-right">
									{workflow.total_executions.toLocaleString()}
								</TableCell>
								<TableCell className="text-right">
									{formatBytes(workflow.avg_memory_bytes)}
								</TableCell>
								<TableCell className="text-right">
									{formatDuration(workflow.avg_duration_ms)}
								</TableCell>
								<TableCell className="text-right">
									<Badge
										variant={
											workflow.success_rate >= 90
												? "default"
												: "destructive"
										}
									>
										{workflow.success_rate.toFixed(0)}%
									</Badge>
								</TableCell>
								<TableCell>
									<ChevronRight className="h-4 w-4 text-muted-foreground" />
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</CardContent>
		</Card>
	);
}
