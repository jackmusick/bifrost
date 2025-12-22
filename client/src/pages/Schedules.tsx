import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
	Clock,
	AlertCircle,
	ArrowRight,
	RefreshCw,
	Search,
	Play,
	Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import { formatDate } from "@/lib/utils";
import { useSchedules, useTriggerSchedule } from "@/hooks/useSchedules";
import { CronTester } from "@/components/schedules/CronTester";

export function Schedules() {
	const navigate = useNavigate();
	const [searchQuery, setSearchQuery] = useState("");
	const [triggeringWorkflows, setTriggeringWorkflows] = useState<Set<string>>(
		new Set(),
	);

	// Query hook for fetching schedules
	const {
		data: schedules,
		isLoading,
		error: queryError,
		refetch,
	} = useSchedules();
	const scheduleList = schedules || [];
	const error = queryError ? "Failed to load scheduled workflows" : null;

	// Mutation hook for triggering schedules
	const triggerMutation = useTriggerSchedule();

	const filteredSchedules = scheduleList.filter((schedule) => {
		const query = searchQuery.toLowerCase();
		return (
			schedule.name.toLowerCase().includes(query) ||
			(schedule.description?.toLowerCase().includes(query) ?? false) ||
			(schedule.schedule?.toLowerCase().includes(query) ?? false) ||
			(schedule.human_readable?.toLowerCase().includes(query) ?? false)
		);
	});

	const handleExecutionClick = (executionId: string | null | undefined) => {
		if (executionId) {
			navigate(`/history/${executionId}`);
		}
	};

	const handleTriggerSchedule = async (
		workflowId: string,
		workflowName: string,
	) => {
		try {
			setTriggeringWorkflows((prev) => new Set(prev).add(workflowName));

			triggerMutation.mutate(
				{
					body: {
						workflow_id: workflowId,
						input_data: {},
						form_id: null,
						transient: false,
						script_name: null,
					},
				},
				{
					onSuccess: (data) => {
						toast.success("Schedule triggered", {
							description: `${workflowName} has been queued for execution`,
						});

						// Navigate to execution details if we got an execution ID
						if (data?.execution_id) {
							navigate(`/history/${data.execution_id}`);
						}
					},
					onError: () => {
						toast.error("Failed to trigger schedule", {
							description: "An error occurred",
						});
					},
					onSettled: () => {
						setTriggeringWorkflows((prev) => {
							const next = new Set(prev);
							next.delete(workflowName);
							return next;
						});
					},
				},
			);
		} catch {
			toast.error("Failed to trigger schedule", {
				description: "An error occurred",
			});
			setTriggeringWorkflows((prev) => {
				const next = new Set(prev);
				next.delete(workflowName);
				return next;
			});
		}
	};

	if (isLoading) {
		return (
			<div className="space-y-4">
				<div className="h-12 bg-muted rounded animate-pulse" />
				<div className="space-y-2">
					{[1, 2, 3].map((i) => (
						<Skeleton key={i} className="h-12 w-full" />
					))}
				</div>
			</div>
		);
	}

	if (error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		);
	}

	if (scheduleList.length === 0) {
		return (
			<div className="space-y-4">
				<div>
					<h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
						<Clock className="h-8 w-8" />
						Scheduled Workflows
					</h1>
					<p className="text-muted-foreground mt-2">
						Workflows configured to run automatically on CRON
						schedules
					</p>
				</div>

				<Card>
					<CardHeader>
						<CardTitle className="flex items-center gap-2">
							<Clock className="h-5 w-5" />
							No Scheduled Workflows
						</CardTitle>
						<CardDescription>
							Define workflows with CRON schedules to enable
							automatic execution
						</CardDescription>
					</CardHeader>
					<CardContent className="space-y-4">
						<Alert>
							<AlertCircle className="h-4 w-4" />
							<AlertDescription>
								Workflows with a{" "}
								<code className="bg-muted px-2 py-1 rounded text-sm">
									schedule
								</code>{" "}
								parameter will appear here and execute
								automatically every 5 minutes based on their
								CRON expression.
							</AlertDescription>
						</Alert>

						<div>
							<h3 className="font-semibold mb-2">
								Example Workflow
							</h3>
							<div className="bg-muted p-4 rounded-lg overflow-x-auto">
								<pre className="text-sm">{`@workflow(
    name='my_scheduled_workflow',
    description='My Scheduled Workflow',
    schedule='0 9 * * *'  # Every day at 9:00 AM UTC
)
async def my_scheduled_workflow(context):
    return "Scheduled execution completed"`}</pre>
							</div>
						</div>

						<div>
							<h3 className="font-semibold mb-2">
								Common CRON Patterns
							</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
								<Card className="bg-muted/50">
									<CardContent className="p-3">
										<code className="text-sm font-mono">
											*/5 * * * *
										</code>
										<p className="text-xs text-muted-foreground mt-1">
											Every 5 minutes
										</p>
									</CardContent>
								</Card>
								<Card className="bg-muted/50">
									<CardContent className="p-3">
										<code className="text-sm font-mono">
											0 */6 * * *
										</code>
										<p className="text-xs text-muted-foreground mt-1">
											Every 6 hours
										</p>
									</CardContent>
								</Card>
								<Card className="bg-muted/50">
									<CardContent className="p-3">
										<code className="text-sm font-mono">
											0 9 * * *
										</code>
										<p className="text-xs text-muted-foreground mt-1">
											Daily at 9:00 AM
										</p>
									</CardContent>
								</Card>
								<Card className="bg-muted/50">
									<CardContent className="p-3">
										<code className="text-sm font-mono">
											0 0 * * 0
										</code>
										<p className="text-xs text-muted-foreground mt-1">
											Weekly on Sunday
										</p>
									</CardContent>
								</Card>
							</div>
						</div>
					</CardContent>
				</Card>
			</div>
		);
	}

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between gap-4">
				<div>
					<h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
						<Clock className="h-8 w-8" />
						Scheduled Workflows
					</h1>
					<p className="text-muted-foreground mt-2">
						Workflows configured to run automatically on CRON
						schedules
					</p>
				</div>
				<Button
					variant="outline"
					size="icon"
					onClick={() => refetch()}
					disabled={isLoading}
					title="Refresh schedules"
				>
					<RefreshCw
						className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
					/>
				</Button>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Schedules are checked every 5 minutes.{" "}
					<Dialog>
						<DialogTrigger asChild>
							<button className="underline hover:text-foreground transition-colors">
								Test CRON expressions
							</button>
						</DialogTrigger>
						<DialogContent className="max-w-2xl">
							<DialogHeader>
								<DialogTitle>
									CRON Expression Tester
								</DialogTitle>
								<DialogDescription>
									Test and validate CRON expressions before
									using them in workflows
								</DialogDescription>
							</DialogHeader>
							<CronTester />
						</DialogContent>
					</Dialog>
				</AlertDescription>
			</Alert>

			{scheduleList.length > 0 && (
				<div className="relative max-w-sm">
					<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
					<Input
						placeholder="Search schedules..."
						value={searchQuery}
						onChange={(e) => setSearchQuery(e.target.value)}
						className="pl-9"
					/>
				</div>
			)}

			<Card>
				<CardHeader>
					<CardTitle>Active Schedules</CardTitle>
					<CardDescription>
						{filteredSchedules.length} of {scheduleList.length}{" "}
						workflow{scheduleList.length !== 1 ? "s" : ""} scheduled
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="overflow-x-auto">
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead>Workflow</DataTableHead>
									<DataTableHead>Schedule</DataTableHead>
									<DataTableHead>Next Run</DataTableHead>
									<DataTableHead>Last Run</DataTableHead>
									<DataTableHead className="text-right">
										Executions
									</DataTableHead>
									<DataTableHead className="text-right">
										Action
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{filteredSchedules.map((schedule) => (
									<DataTableRow key={schedule.name}>
										<DataTableCell className="font-medium">
											<div>
												<p className="font-semibold">
													{schedule.description ||
														schedule.name}
												</p>
												<p className="text-xs text-muted-foreground">
													{schedule.name}
												</p>
											</div>
										</DataTableCell>
										<DataTableCell>
											<div className="space-y-1">
												<p className="font-mono text-sm">
													{schedule.schedule}
												</p>
												{schedule.validation_status !==
													"error" && (
													<p className="text-xs text-muted-foreground">
														{
															schedule.human_readable
														}
													</p>
												)}
												{schedule.validation_status ===
													"warning" &&
													schedule.validation_message && (
														<p className="text-xs text-yellow-600 dark:text-yellow-500">
															Minimum interval: 5
															minutes
														</p>
													)}
											</div>
										</DataTableCell>
										<DataTableCell>
											{schedule.validation_status ===
											"error" ? (
												<Badge variant="destructive">
													Invalid CRON
												</Badge>
											) : schedule.next_run_at ? (
												<div className="flex items-center gap-2">
													<span>
														{formatDate(
															schedule.next_run_at,
														)}
													</span>
													{schedule.is_overdue && (
														<Badge
															variant="destructive"
															className="text-xs"
														>
															Overdue
														</Badge>
													)}
												</div>
											) : (
												<span className="text-muted-foreground">
													Not scheduled
												</span>
											)}
										</DataTableCell>
										<DataTableCell>
											{schedule.last_run_at ? (
												<div className="flex items-center gap-2">
													<span>
														{formatDate(
															schedule.last_run_at,
														)}
													</span>
													{schedule.last_execution_id && (
														<Button
															variant="ghost"
															size="sm"
															onClick={() =>
																handleExecutionClick(
																	schedule.last_execution_id,
																)
															}
															className="h-6 px-2"
															title="View execution details"
														>
															<ArrowRight className="h-3 w-3" />
														</Button>
													)}
												</div>
											) : (
												<span className="text-muted-foreground">
													Never
												</span>
											)}
										</DataTableCell>
										<DataTableCell className="text-right">
											<Badge variant="secondary">
												{schedule.execution_count}
											</Badge>
										</DataTableCell>
										<DataTableCell className="text-right">
											<div className="flex items-center justify-end gap-0.5">
												<Button
													variant="outline"
													size="icon"
													onClick={() =>
														handleTriggerSchedule(
															schedule.id,
															schedule.name,
														)
													}
													disabled={triggeringWorkflows.has(
														schedule.name,
													)}
													className="h-8 w-8 rounded-r-none"
													title={
														triggeringWorkflows.has(
															schedule.name,
														)
															? "Running..."
															: "Run Now"
													}
												>
													<Play className="h-3.5 w-3.5" />
												</Button>
												<Button
													variant="outline"
													size="icon"
													onClick={() =>
														handleExecutionClick(
															schedule.last_execution_id,
														)
													}
													disabled={
														!schedule.last_execution_id
													}
													className="h-8 w-8 rounded-l-none border-l-0"
													title="View Last Execution"
												>
													<Eye className="h-3.5 w-3.5" />
												</Button>
											</div>
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
						</DataTable>
					</div>
					{filteredSchedules.length === 0 &&
						scheduleList.length > 0 && (
							<div className="text-center py-8 text-muted-foreground">
								No schedules match your search.
							</div>
						)}
				</CardContent>
			</Card>
		</div>
	);
}
