import { useState, useMemo } from "react";
import { format, subDays } from "date-fns";
import type { DateRange } from "react-day-picker";
import {
	DollarSign,
	Clock,
	TrendingUp,
	Download,
	AlertCircle,
	Sparkles,
	ChevronUp,
	ChevronDown,
} from "lucide-react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
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
	useROISummary,
	useROIByWorkflow,
	useROIByOrganization,
	useROITrends,
	type ROISummary,
	type ROIByWorkflow,
	type ROIByOrganization,
	type ROITrends,
	type WorkflowROI,
} from "@/services/reports";
import { useAuth } from "@/contexts/AuthContext";
import { useOrgScope } from "@/hooks/useOrgScope";
import { useOrganizations } from "@/hooks/useOrganizations";

// ============================================================================
// Demo Data - Realistic sample data for UI development/demonstration
// ============================================================================

// Extended type to include organization_id for demo filtering
type DemoWorkflowROI = WorkflowROI & { organization_id: string };

// Demo workflow templates (workflow names and base metrics)
const DEMO_WORKFLOW_TEMPLATES = [
	{ name: "User Onboarding", timeSaved: 45, value: 75, baseCount: 2800 },
	{ name: "Ticket Triage", timeSaved: 15, value: 25, baseCount: 4500 },
	{ name: "Invoice Processing", timeSaved: 30, value: 50, baseCount: 1900 },
	{ name: "Compliance Check", timeSaved: 60, value: 120, baseCount: 750 },
	{
		name: "Data Backup Verification",
		timeSaved: 20,
		value: 35,
		baseCount: 2100,
	},
	{ name: "Report Generation", timeSaved: 25, value: 40, baseCount: 700 },
];

// Fallback demo workflows if no real orgs exist
const FALLBACK_DEMO_WORKFLOWS: DemoWorkflowROI[] = [
	{
		workflow_id: "demo-1",
		workflow_name: "User Onboarding",
		organization_id: "demo-org-1",
		execution_count: 2847,
		success_count: 2789,
		time_saved_per_execution: 45,
		value_per_execution: 75,
		total_time_saved: 125505,
		total_value: 209175,
	},
	{
		workflow_id: "demo-2",
		workflow_name: "Ticket Triage",
		organization_id: "demo-org-1",
		execution_count: 4521,
		success_count: 4432,
		time_saved_per_execution: 15,
		value_per_execution: 25,
		total_time_saved: 66480,
		total_value: 110800,
	},
	{
		workflow_id: "demo-3",
		workflow_name: "Invoice Processing",
		organization_id: "demo-org-2",
		execution_count: 1893,
		success_count: 1856,
		time_saved_per_execution: 30,
		value_per_execution: 50,
		total_time_saved: 55680,
		total_value: 92800,
	},
];

/**
 * Generate demo workflow data using real organizations if available
 */
function generateDemoWorkflows(
	realOrgs: Array<{ id: string; name: string }> | undefined,
): DemoWorkflowROI[] {
	if (!realOrgs || realOrgs.length === 0) {
		return FALLBACK_DEMO_WORKFLOWS;
	}

	const workflows: DemoWorkflowROI[] = [];

	// Distribute workflows across organizations
	DEMO_WORKFLOW_TEMPLATES.forEach((template, index) => {
		// Assign each workflow to an org (cycling through available orgs)
		const org = realOrgs[index % realOrgs.length];
		const variance = 0.9 + Math.random() * 0.2; // ±10% variance
		const executions = Math.floor(template.baseCount * variance);
		const successRate = 0.96 + Math.random() * 0.03;
		const successCount = Math.floor(executions * successRate);

		workflows.push({
			workflow_id: `demo-${index + 1}`,
			workflow_name: template.name,
			organization_id: org.id,
			execution_count: executions,
			success_count: successCount,
			time_saved_per_execution: template.timeSaved,
			value_per_execution: template.value,
			total_time_saved: successCount * template.timeSaved,
			total_value: successCount * template.value,
		});
	});

	return workflows;
}

// Fallback demo org data if no real orgs exist
const FALLBACK_DEMO_ORGANIZATIONS: ROIByOrganization["organizations"] = [
	{
		organization_id: "demo-org-1",
		organization_name: "Acme Corp",
		execution_count: 4521,
		success_count: 4389,
		total_time_saved: 132300,
		total_value: 220500,
	},
	{
		organization_id: "demo-org-2",
		organization_name: "TechStart Inc",
		execution_count: 3847,
		success_count: 3732,
		total_time_saved: 98460,
		total_value: 164100,
	},
	{
		organization_id: "demo-org-3",
		organization_name: "Global Services LLC",
		execution_count: 2893,
		success_count: 2835,
		total_time_saved: 86790,
		total_value: 144650,
	},
];

/**
 * Generate demo organization data using real organizations if available
 */
function generateDemoOrganizations(
	realOrgs: Array<{ id: string; name: string }> | undefined,
): ROIByOrganization["organizations"] {
	if (!realOrgs || realOrgs.length === 0) {
		return FALLBACK_DEMO_ORGANIZATIONS;
	}

	// Generate demo metrics for each real organization
	return realOrgs.map((org, index) => {
		// Use index to create varied but consistent demo values
		const baseExecutions = 4500 - index * 800;
		const successRate = 0.95 + Math.random() * 0.03;
		const executions = Math.max(
			300,
			baseExecutions + Math.floor(Math.random() * 500),
		);
		const successCount = Math.floor(executions * successRate);
		const avgTimeSaved = 25 + Math.floor(Math.random() * 15); // 25-40 mins per execution
		const avgValue = 35 + Math.floor(Math.random() * 25); // $35-60 per execution

		return {
			organization_id: org.id,
			organization_name: org.name,
			execution_count: executions,
			success_count: successCount,
			total_time_saved: successCount * avgTimeSaved,
			total_value: successCount * avgValue,
		};
	});
}

/**
 * Generate demo trend data for the given date range
 */
function generateDemoTrends(startDate: string, endDate: string): ROITrends {
	const entries: ROITrends["entries"] = [];
	const start = new Date(startDate);
	const end = new Date(endDate);

	const currentDate = new Date(start);
	let dayIndex = 0;

	while (currentDate <= end) {
		const isWeekend =
			currentDate.getDay() === 0 || currentDate.getDay() === 6;
		const baseMultiplier = isWeekend ? 0.5 : 1;
		// Add slight upward trend and natural variance
		const trendMultiplier = 1 + dayIndex * 0.005;
		const variance = 0.85 + Math.random() * 0.3; // ±15%

		const dailyExecutions = Math.round(
			420 * baseMultiplier * trendMultiplier * variance,
		);
		const successRate = 0.92 + Math.random() * 0.06; // 92-98%
		const dailySuccess = Math.round(dailyExecutions * successRate);

		entries.push({
			period: format(currentDate, "yyyy-MM-dd"),
			execution_count: dailyExecutions,
			success_count: dailySuccess,
			time_saved: Math.round(dailySuccess * 28 * variance), // ~28 min avg
			value: Math.round(dailySuccess * 46 * variance * 100) / 100, // ~$46 avg
		});

		currentDate.setDate(currentDate.getDate() + 1);
		dayIndex++;
	}

	return {
		entries,
		granularity: "day",
		time_saved_unit: "minutes",
		value_unit: "USD",
	};
}

// ============================================================================
// Component
// ============================================================================

// Sort state type
type SortConfig = { by: string; dir: "asc" | "desc" };

export function ROIReports() {
	const { isPlatformAdmin } = useAuth();
	const { isGlobalScope, scope } = useOrgScope();

	// Fetch real organizations for demo data generation
	const { data: orgsData } = useOrganizations();

	// Demo mode state
	const [showDemoData, setShowDemoData] = useState(false);

	// Default to last 30 days
	const [dateRange, setDateRange] = useState<DateRange | undefined>({
		from: subDays(new Date(), 30),
		to: new Date(),
	});

	// Sorting state for tables
	const [workflowSort, setWorkflowSort] = useState<SortConfig>({
		by: "value",
		dir: "desc",
	});
	const [orgSort, setOrgSort] = useState<SortConfig>({
		by: "value",
		dir: "desc",
	});

	// Format dates for API (YYYY-MM-DD)
	const startDate = dateRange?.from
		? format(dateRange.from, "yyyy-MM-dd")
		: "";
	const endDate = dateRange?.to ? format(dateRange.to, "yyyy-MM-dd") : "";

	// Memoize orgs array for stable reference
	// The API returns an array directly, not { organizations: [...] }
	const realOrgs = useMemo(() => {
		if (!orgsData || !Array.isArray(orgsData)) return undefined;
		return orgsData.map((o) => ({ id: o.id, name: o.name }));
	}, [orgsData]);

	// Generate demo data using real organizations if available
	const demoWorkflows = useMemo(
		() => generateDemoWorkflows(realOrgs),
		[realOrgs],
	);
	const demoOrganizations = useMemo(
		() => generateDemoOrganizations(realOrgs),
		[realOrgs],
	);

	// Filter demo data by org scope
	const scopedDemoWorkflows = useMemo(() => {
		if (isGlobalScope || !scope.orgId) return demoWorkflows;
		return demoWorkflows.filter((w) => w.organization_id === scope.orgId);
	}, [demoWorkflows, isGlobalScope, scope.orgId]);

	const scopedDemoOrganizations = useMemo(() => {
		if (isGlobalScope || !scope.orgId) return demoOrganizations;
		return demoOrganizations.filter(
			(o) => o.organization_id === scope.orgId,
		);
	}, [demoOrganizations, isGlobalScope, scope.orgId]);

	// Generate demo trends based on current date range
	const demoTrends = useMemo(
		() =>
			startDate && endDate
				? generateDemoTrends(startDate, endDate)
				: null,
		[startDate, endDate],
	);

	// Compute demo summary from scoped workflow data (so totals reflect org filter)
	const demoSummary: ROISummary | null = useMemo(() => {
		if (!startDate || !endDate) return null;

		// Aggregate totals from scoped workflows
		const totals = scopedDemoWorkflows.reduce(
			(acc, w) => ({
				total_executions: acc.total_executions + w.execution_count,
				successful_executions:
					acc.successful_executions + w.success_count,
				total_time_saved: acc.total_time_saved + w.total_time_saved,
				total_value: acc.total_value + w.total_value,
			}),
			{
				total_executions: 0,
				successful_executions: 0,
				total_time_saved: 0,
				total_value: 0,
			},
		);

		return {
			start_date: startDate,
			end_date: endDate,
			...totals,
			time_saved_unit: "minutes",
			value_unit: "USD",
		};
	}, [startDate, endDate, scopedDemoWorkflows]);

	const demoByWorkflow: ROIByWorkflow = useMemo(
		() => ({
			workflows: scopedDemoWorkflows,
			total_workflows: scopedDemoWorkflows.length,
			time_saved_unit: "minutes",
			value_unit: "USD",
		}),
		[scopedDemoWorkflows],
	);
	const demoByOrg: ROIByOrganization = useMemo(
		() => ({
			organizations: scopedDemoOrganizations,
			time_saved_unit: "minutes",
			value_unit: "USD",
		}),
		[scopedDemoOrganizations],
	);

	// Fetch real data (only used when not in demo mode)
	const {
		data: realSummary,
		isLoading: summaryLoading,
		error: summaryError,
	} = useROISummary(startDate, endDate);

	const {
		data: realByWorkflow,
		isLoading: workflowLoading,
		error: workflowError,
	} = useROIByWorkflow(startDate, endDate);

	const {
		data: realByOrg,
		isLoading: orgLoading,
		error: orgError,
	} = useROIByOrganization(startDate, endDate);

	const {
		data: realTrends,
		isLoading: trendsLoading,
		error: trendsError,
	} = useROITrends(startDate, endDate);

	// Use demo or real data based on toggle
	const summary = showDemoData ? demoSummary : realSummary;
	const byWorkflow = showDemoData ? demoByWorkflow : realByWorkflow;
	const byOrg = showDemoData ? demoByOrg : realByOrg;
	const trends = showDemoData ? demoTrends : realTrends;

	// Sorted workflows
	const sortedWorkflows = useMemo(() => {
		const workflows = byWorkflow?.workflows;
		if (!workflows) return [];
		return [...workflows].sort((a, b) => {
			const mult = workflowSort.dir === "desc" ? -1 : 1;
			switch (workflowSort.by) {
				case "name":
					return (
						mult * a.workflow_name.localeCompare(b.workflow_name)
					);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "time":
					return mult * (a.total_time_saved - b.total_time_saved);
				case "value":
					return mult * (a.total_value - b.total_value);
				default:
					return 0;
			}
		});
	}, [byWorkflow, workflowSort]);

	// Sorted organizations
	const sortedOrganizations = useMemo(() => {
		const organizations = byOrg?.organizations;
		if (!organizations) return [];
		return [...organizations].sort((a, b) => {
			const mult = orgSort.dir === "desc" ? -1 : 1;
			switch (orgSort.by) {
				case "name":
					return (
						mult *
						a.organization_name.localeCompare(b.organization_name)
					);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "time":
					return mult * (a.total_time_saved - b.total_time_saved);
				case "value":
					return mult * (a.total_value - b.total_value);
				default:
					return 0;
			}
		});
	}, [byOrg, orgSort]);

	// Sort toggle helpers
	const toggleWorkflowSort = (column: string) => {
		setWorkflowSort((prev) => ({
			by: column,
			dir: prev.by === column && prev.dir === "desc" ? "asc" : "desc",
		}));
	};

	const toggleOrgSort = (column: string) => {
		setOrgSort((prev) => ({
			by: column,
			dir: prev.by === column && prev.dir === "desc" ? "asc" : "desc",
		}));
	};

	// Loading states (instant when using demo data)
	const isLoading = showDemoData
		? false
		: summaryLoading || workflowLoading || orgLoading || trendsLoading;

	// Handle errors (no errors in demo mode)
	const hasError = showDemoData
		? false
		: !!(summaryError || workflowError || orgError || trendsError);

	// CSV Export handlers
	const downloadWorkflowCSV = () => {
		if (!byWorkflow?.workflows) return;

		const headers = [
			"Workflow Name",
			"Executions",
			"Total Time Saved (hrs)",
			"Total Value",
		];
		const rows = byWorkflow.workflows.map((w) => [
			w.workflow_name,
			w.execution_count,
			(w.total_time_saved / 60).toFixed(2),
			w.total_value.toFixed(2),
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `roi-by-workflow-${startDate}-${endDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	const downloadOrganizationCSV = () => {
		if (!byOrg?.organizations) return;

		const headers = [
			"Organization",
			"Executions",
			"Total Time Saved (hrs)",
			"Total Value",
		];
		const rows = byOrg.organizations.map((o) => [
			o.organization_name,
			o.execution_count,
			(o.total_time_saved / 60).toFixed(2),
			o.total_value.toFixed(2),
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `roi-by-organization-${startDate}-${endDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	return (
		<div className="space-y-6">
			{/* Header */}
			<div className="flex items-start justify-between">
				<div>
					<div className="flex items-center gap-3">
						<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
							ROI Reports
						</h1>
						{showDemoData && (
							<Badge
								variant="outline"
								className="bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800"
							>
								<Sparkles className="h-3 w-3 mr-1" />
								Demo Mode
							</Badge>
						)}
					</div>
					<p className="leading-7 mt-2 text-muted-foreground">
						Workflow automation value and time savings analytics
					</p>
				</div>

				{/* Demo Data Toggle - Only visible to platform admins */}
				{isPlatformAdmin && (
					<div className="flex items-center space-x-2 pt-2">
						<Switch
							id="demo-mode"
							checked={showDemoData}
							onCheckedChange={setShowDemoData}
						/>
						<Label
							htmlFor="demo-mode"
							className="text-sm text-muted-foreground cursor-pointer"
						>
							Show Demo Data
						</Label>
					</div>
				)}
			</div>

			{/* Demo Mode Banner */}
			{showDemoData && (
				<Alert className="bg-amber-50 border-amber-200 dark:bg-amber-950 dark:border-amber-800">
					<Sparkles className="h-4 w-4 text-amber-600 dark:text-amber-400" />
					<AlertDescription className="text-amber-800 dark:text-amber-200">
						Displaying sample data for demonstration purposes.
						Toggle off to view real ROI data.
					</AlertDescription>
				</Alert>
			)}

			{/* Date Range Picker */}
			<Card>
				<CardHeader>
					<CardTitle>Report Period</CardTitle>
					<CardDescription>
						Select a date range for the ROI report
					</CardDescription>
				</CardHeader>
				<CardContent>
					<DateRangePicker
						dateRange={dateRange}
						onDateRangeChange={setDateRange}
					/>
				</CardContent>
			</Card>

			{/* Error Alert */}
			{hasError && (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						Failed to load ROI data. Please try again later.
					</AlertDescription>
				</Alert>
			)}

			{/* Summary Cards */}
			<div className="grid gap-4 md:grid-cols-3">
				{/* Total Executions */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total Executions
						</CardTitle>
						<TrendingUp className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoading || (!showDemoData && summaryLoading) ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{(
									summary?.total_executions ?? 0
								).toLocaleString()}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							Workflow runs in period
						</p>
					</CardContent>
				</Card>

				{/* Total Time Saved */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total Time Saved
						</CardTitle>
						<Clock className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoading || (!showDemoData && summaryLoading) ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{summary
									? (summary.total_time_saved / 60).toFixed(1)
									: "0.0"}{" "}
								hrs
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							{summary?.time_saved_unit ?? "minutes"} saved by
							automation
						</p>
					</CardContent>
				</Card>

				{/* Total Value */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total Value
						</CardTitle>
						<DollarSign className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoading || (!showDemoData && summaryLoading) ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{(summary?.total_value ?? 0).toLocaleString(
									"en-US",
									{
										style: "currency",
										currency: "USD",
									},
								)}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							{summary?.value_unit ?? "USD"} value delivered
						</p>
					</CardContent>
				</Card>
			</div>

			{/* Trends Chart */}
			<Card>
				<CardHeader>
					<CardTitle>ROI Over Time</CardTitle>
					<CardDescription>
						Time savings and value trends during the selected period
					</CardDescription>
				</CardHeader>
				<CardContent>
					{isLoading || (!showDemoData && trendsLoading) ? (
						<Skeleton className="h-[300px] w-full" />
					) : trends?.entries && trends.entries.length > 0 ? (
						<ResponsiveContainer width="100%" height={300}>
							<LineChart
								data={trends.entries.map((entry) => ({
									...entry,
									time_saved_hours: entry.time_saved / 60,
								}))}
							>
								<CartesianGrid
									strokeDasharray="3 3"
									className="stroke-muted"
								/>
								<XAxis
									dataKey="period"
									className="text-xs"
									tick={{ fontSize: 12 }}
									tickFormatter={(value) =>
										format(new Date(value), "MMM dd")
									}
								/>
								<YAxis
									yAxisId="left"
									className="text-xs"
									tick={{ fontSize: 12 }}
									label={{
										value: "Hours Saved",
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
										value: "Value",
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
									formatter={(
										value: number,
										name: string,
									) => {
										if (name === "time_saved_hours")
											return [
												`${value.toFixed(2)} hrs`,
												"Time Saved",
											];
										if (name === "value")
											return [
												`${value.toFixed(2)}`,
												"Value",
											];
										return [value, name];
									}}
									labelFormatter={(label) =>
										format(new Date(label), "PPP")
									}
								/>
								<Legend
									formatter={(value) => {
										if (value === "time_saved_hours")
											return "Time Saved (hours)";
										if (value === "value")
											return `Value (${trends.value_unit})`;
										return value;
									}}
								/>
								<Line
									yAxisId="left"
									type="monotone"
									dataKey="time_saved_hours"
									stroke="hsl(var(--chart-1, 220 70% 50%))"
									strokeWidth={2}
									dot={{ r: 3 }}
									activeDot={{ r: 5 }}
								/>
								<Line
									yAxisId="right"
									type="monotone"
									dataKey="value"
									stroke="hsl(var(--chart-2, 160 60% 45%))"
									strokeWidth={2}
									dot={{ r: 3 }}
									activeDot={{ r: 5 }}
								/>
							</LineChart>
						</ResponsiveContainer>
					) : (
						<div className="flex items-center justify-center h-[300px] text-muted-foreground">
							No trend data available for this period
						</div>
					)}
				</CardContent>
			</Card>

			{/* Per-Workflow Table */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>ROI by Workflow</CardTitle>
							<CardDescription>
								Value delivered by each workflow
							</CardDescription>
						</div>
						<Button
							variant="outline"
							size="sm"
							onClick={downloadWorkflowCSV}
							disabled={
								!byWorkflow?.workflows ||
								byWorkflow.workflows.length === 0
							}
						>
							<Download className="h-4 w-4 mr-2" />
							Export CSV
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					{isLoading || (!showDemoData && workflowLoading) ? (
						<div className="space-y-2">
							<Skeleton className="h-10 w-full" />
							<Skeleton className="h-10 w-full" />
							<Skeleton className="h-10 w-full" />
						</div>
					) : sortedWorkflows.length > 0 ? (
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead
										className="cursor-pointer select-none hover:bg-muted/50"
										onClick={() =>
											toggleWorkflowSort("name")
										}
									>
										<div className="flex items-center gap-1">
											Workflow
											{workflowSort.by === "name" &&
												(workflowSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="text-right cursor-pointer select-none hover:bg-muted/50"
										onClick={() =>
											toggleWorkflowSort("executions")
										}
									>
										<div className="flex items-center justify-end gap-1">
											Executions
											{workflowSort.by === "executions" &&
												(workflowSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="text-right cursor-pointer select-none hover:bg-muted/50"
										onClick={() =>
											toggleWorkflowSort("time")
										}
									>
										<div className="flex items-center justify-end gap-1">
											Time Saved (hrs)
											{workflowSort.by === "time" &&
												(workflowSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="text-right cursor-pointer select-none hover:bg-muted/50"
										onClick={() =>
											toggleWorkflowSort("value")
										}
									>
										<div className="flex items-center justify-end gap-1">
											Value
											{workflowSort.by === "value" &&
												(workflowSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{sortedWorkflows.map((workflow) => (
									<DataTableRow key={workflow.workflow_id}>
										<DataTableCell className="font-medium">
											{workflow.workflow_name}
										</DataTableCell>
										<DataTableCell className="text-right">
											{workflow.execution_count.toLocaleString()}
										</DataTableCell>
										<DataTableCell className="text-right">
											{(
												workflow.total_time_saved / 60
											).toFixed(2)}
										</DataTableCell>
										<DataTableCell className="text-right">
											{workflow.total_value.toLocaleString(
												"en-US",
												{
													style: "currency",
													currency: "USD",
												},
											)}
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
						</DataTable>
					) : (
						<div className="flex items-center justify-center py-8 text-muted-foreground">
							No workflow data available for this period
						</div>
					)}
				</CardContent>
			</Card>

			{/* Per-Organization Table - Only shown in global scope */}
			{isGlobalScope && (
				<Card>
					<CardHeader>
						<div className="flex items-center justify-between">
							<div>
								<CardTitle>ROI by Organization</CardTitle>
								<CardDescription>
									Value delivered to each organization
								</CardDescription>
							</div>
							<Button
								variant="outline"
								size="sm"
								onClick={downloadOrganizationCSV}
								disabled={
									!byOrg?.organizations ||
									byOrg.organizations.length === 0
								}
							>
								<Download className="h-4 w-4 mr-2" />
								Export CSV
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						{isLoading || (!showDemoData && orgLoading) ? (
							<div className="space-y-2">
								<Skeleton className="h-10 w-full" />
								<Skeleton className="h-10 w-full" />
								<Skeleton className="h-10 w-full" />
							</div>
						) : sortedOrganizations.length > 0 ? (
							<DataTable>
								<DataTableHeader>
									<DataTableRow>
										<DataTableHead
											className="cursor-pointer select-none hover:bg-muted/50"
											onClick={() =>
												toggleOrgSort("name")
											}
										>
											<div className="flex items-center gap-1">
												Organization
												{orgSort.by === "name" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() =>
												toggleOrgSort("executions")
											}
										>
											<div className="flex items-center justify-end gap-1">
												Executions
												{orgSort.by === "executions" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() =>
												toggleOrgSort("time")
											}
										>
											<div className="flex items-center justify-end gap-1">
												Time Saved (hrs)
												{orgSort.by === "time" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() =>
												toggleOrgSort("value")
											}
										>
											<div className="flex items-center justify-end gap-1">
												Value
												{orgSort.by === "value" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
									</DataTableRow>
								</DataTableHeader>
								<DataTableBody>
									{sortedOrganizations.map((org) => (
										<DataTableRow key={org.organization_id}>
											<DataTableCell className="font-medium">
												{org.organization_name}
											</DataTableCell>
											<DataTableCell className="text-right">
												{org.execution_count.toLocaleString()}
											</DataTableCell>
											<DataTableCell className="text-right">
												{(
													org.total_time_saved / 60
												).toFixed(2)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{org.total_value.toLocaleString(
													"en-US",
													{
														style: "currency",
														currency: "USD",
													},
												)}
											</DataTableCell>
										</DataTableRow>
									))}
								</DataTableBody>
							</DataTable>
						) : (
							<div className="flex items-center justify-center py-8 text-muted-foreground">
								No organization data available for this period
							</div>
						)}
					</CardContent>
				</Card>
			)}
		</div>
	);
}
