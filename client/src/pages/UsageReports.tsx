import { useState, useMemo } from "react";
import { format, subDays } from "date-fns";
import type { DateRange } from "react-day-picker";
import {
	DollarSign,
	Hash,
	Cpu,
	HardDrive,
	Download,
	AlertCircle,
	Sparkles,
	ChevronUp,
	ChevronDown,
	Database,
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
	useUsageReport,
	type UsageReportResponse,
	type UsageSource,
	type WorkflowUsage,
	type ConversationUsage,
	type OrganizationUsage,
	type UsageTrend,
} from "@/services/usage";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganizations } from "@/hooks/useOrganizations";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";

// ============================================================================
// Formatting Utilities
// ============================================================================

/**
 * Format a number as currency (USD)
 */
function formatCurrency(value: string | number | undefined): string {
	if (value === undefined || value === null) return "$0.00";
	const numValue = typeof value === "string" ? parseFloat(value) : value;
	if (isNaN(numValue)) return "$0.00";
	return numValue.toLocaleString("en-US", {
		style: "currency",
		currency: "USD",
	});
}

/**
 * Format a number with thousand separators
 */
function formatNumber(value: number | undefined): string {
	if (value === undefined || value === null) return "0";
	return value.toLocaleString();
}

/**
 * Format bytes to human-readable size (KB, MB, GB)
 */
function formatBytes(bytes: number | undefined): string {
	if (bytes === undefined || bytes === null || bytes === 0) return "0 B";
	const units = ["B", "KB", "MB", "GB", "TB"];
	const k = 1024;
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	const size = bytes / Math.pow(k, i);
	return `${size.toFixed(i > 0 ? 2 : 0)} ${units[i]}`;
}

/**
 * Format seconds to human-readable time
 */
function formatCpuSeconds(seconds: number | undefined): string {
	if (seconds === undefined || seconds === null) return "0s";
	if (seconds < 60) return `${seconds.toFixed(1)}s`;
	if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
	return `${(seconds / 3600).toFixed(2)}h`;
}

// ============================================================================
// Demo Data Generation
// ============================================================================

// Extended types for demo data
type DemoWorkflowUsage = WorkflowUsage & { organization_id: string };
type DemoConversationUsage = ConversationUsage & { organization_id: string };

// Demo workflow templates
const DEMO_WORKFLOW_TEMPLATES = [
	{
		name: "User Onboarding",
		inputTokens: 45000,
		outputTokens: 12000,
		cost: 0.85,
		cpuSeconds: 120,
		memoryBytes: 256 * 1024 * 1024,
		baseCount: 280,
	},
	{
		name: "Ticket Triage",
		inputTokens: 22000,
		outputTokens: 8000,
		cost: 0.42,
		cpuSeconds: 45,
		memoryBytes: 128 * 1024 * 1024,
		baseCount: 450,
	},
	{
		name: "Invoice Processing",
		inputTokens: 35000,
		outputTokens: 15000,
		cost: 0.68,
		cpuSeconds: 90,
		memoryBytes: 192 * 1024 * 1024,
		baseCount: 190,
	},
	{
		name: "Compliance Check",
		inputTokens: 78000,
		outputTokens: 25000,
		cost: 1.45,
		cpuSeconds: 180,
		memoryBytes: 384 * 1024 * 1024,
		baseCount: 75,
	},
	{
		name: "Data Backup Verification",
		inputTokens: 18000,
		outputTokens: 5000,
		cost: 0.32,
		cpuSeconds: 60,
		memoryBytes: 96 * 1024 * 1024,
		baseCount: 210,
	},
	{
		name: "Report Generation",
		inputTokens: 55000,
		outputTokens: 30000,
		cost: 1.12,
		cpuSeconds: 150,
		memoryBytes: 320 * 1024 * 1024,
		baseCount: 70,
	},
];

// Demo conversation templates
const DEMO_CONVERSATION_TEMPLATES = [
	{ title: "Help with deployment", messages: 12, inputTokens: 8500, outputTokens: 4200, cost: 0.18 },
	{ title: "Database migration questions", messages: 8, inputTokens: 5200, outputTokens: 3100, cost: 0.12 },
	{ title: "API integration support", messages: 15, inputTokens: 11000, outputTokens: 6500, cost: 0.25 },
	{ title: "Security audit discussion", messages: 6, inputTokens: 4000, outputTokens: 2200, cost: 0.09 },
	{ title: "Performance optimization", messages: 10, inputTokens: 7500, outputTokens: 4800, cost: 0.17 },
	{ title: "New feature planning", messages: 20, inputTokens: 15000, outputTokens: 9000, cost: 0.34 },
];

// Fallback demo orgs
const FALLBACK_DEMO_ORGS = [
	{ id: "demo-org-1", name: "Acme Corp" },
	{ id: "demo-org-2", name: "TechStart Inc" },
	{ id: "demo-org-3", name: "Global Services LLC" },
];

interface DemoDataParams {
	startDate: string;
	endDate: string;
	orgId: string | null;
	source: UsageSource;
	realOrgs: Array<{ id: string; name: string }> | undefined;
}

/**
 * Generate demo data that mirrors API response structure.
 */
function generateDemoData(params: DemoDataParams): UsageReportResponse {
	const { startDate, endDate, orgId, source, realOrgs } = params;
	const orgs = realOrgs && realOrgs.length > 0 ? realOrgs : FALLBACK_DEMO_ORGS;

	// Generate workflows with org assignments
	const allWorkflows: DemoWorkflowUsage[] = DEMO_WORKFLOW_TEMPLATES.map(
		(template, index) => {
			const org = orgs[index % orgs.length];
			const variance = 0.9 + Math.random() * 0.2;
			const executions = Math.floor(template.baseCount * variance);

			return {
				workflow_name: template.name,
				organization_id: org.id,
				execution_count: executions,
				input_tokens: Math.floor(template.inputTokens * executions * variance),
				output_tokens: Math.floor(template.outputTokens * executions * variance),
				ai_cost: (template.cost * executions * variance).toFixed(2),
				cpu_seconds: Math.floor(template.cpuSeconds * executions * variance),
				memory_bytes: template.memoryBytes,
			};
		},
	);

	// Generate conversations with org assignments
	const allConversations: DemoConversationUsage[] = DEMO_CONVERSATION_TEMPLATES.map(
		(template, index) => {
			const org = orgs[index % orgs.length];
			const variance = 0.85 + Math.random() * 0.3;

			return {
				conversation_id: `demo-conv-${index + 1}`,
				conversation_title: template.title,
				organization_id: org.id,
				message_count: Math.floor(template.messages * variance),
				input_tokens: Math.floor(template.inputTokens * variance),
				output_tokens: Math.floor(template.outputTokens * variance),
				ai_cost: (template.cost * variance).toFixed(2),
			};
		},
	);

	// Filter by org
	const filteredWorkflows = orgId
		? allWorkflows.filter((w) => w.organization_id === orgId)
		: allWorkflows;

	const filteredConversations = orgId
		? allConversations.filter((c) => c.organization_id === orgId)
		: allConversations;

	// Filter by source
	const includeWorkflows = source === "all" || source === "executions";
	const includeConversations = source === "all" || source === "chat";

	// Calculate summary from filtered data
	let totalInputTokens = 0;
	let totalOutputTokens = 0;
	let totalAiCost = 0;
	let totalCpuSeconds = 0;
	let peakMemoryBytes = 0;
	let totalAiCalls = 0;

	if (includeWorkflows) {
		for (const w of filteredWorkflows) {
			totalInputTokens += w.input_tokens;
			totalOutputTokens += w.output_tokens;
			totalAiCost += parseFloat(w.ai_cost || "0");
			totalCpuSeconds += w.cpu_seconds;
			peakMemoryBytes = Math.max(peakMemoryBytes, w.memory_bytes);
			totalAiCalls += w.execution_count;
		}
	}

	if (includeConversations) {
		for (const c of filteredConversations) {
			totalInputTokens += c.input_tokens;
			totalOutputTokens += c.output_tokens;
			totalAiCost += parseFloat(c.ai_cost || "0");
			totalAiCalls += c.message_count;
		}
	}

	// Generate trends
	const start = new Date(startDate);
	const end = new Date(endDate);
	const dayCount = Math.max(
		1,
		Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1,
	);

	const dailyCost = totalAiCost / dayCount;
	const dailyInputTokens = totalInputTokens / dayCount;
	const dailyOutputTokens = totalOutputTokens / dayCount;

	const trends: UsageTrend[] = [];
	const currentDate = new Date(start);
	let dayIndex = 0;

	while (currentDate <= end) {
		const isWeekend = currentDate.getDay() === 0 || currentDate.getDay() === 6;
		const baseMultiplier = isWeekend ? 0.5 : 1;
		const trendMultiplier = 1 + dayIndex * 0.003;
		const variance = 0.85 + Math.random() * 0.3;
		const dayFactor = baseMultiplier * trendMultiplier * variance;

		trends.push({
			date: format(currentDate, "yyyy-MM-dd"),
			ai_cost: (dailyCost * dayFactor).toFixed(2),
			input_tokens: Math.round(dailyInputTokens * dayFactor),
			output_tokens: Math.round(dailyOutputTokens * dayFactor),
		});

		currentDate.setDate(currentDate.getDate() + 1);
		dayIndex++;
	}

	// Build by-organization data
	const orgMetrics = new Map<
		string,
		{
			name: string;
			execution_count: number;
			conversation_count: number;
			input_tokens: number;
			output_tokens: number;
			ai_cost: number;
		}
	>();

	for (const workflow of allWorkflows) {
		const existing = orgMetrics.get(workflow.organization_id);
		const orgName =
			orgs.find((o) => o.id === workflow.organization_id)?.name ?? "Unknown";

		if (existing) {
			existing.execution_count += workflow.execution_count;
			existing.input_tokens += workflow.input_tokens;
			existing.output_tokens += workflow.output_tokens;
			existing.ai_cost += parseFloat(workflow.ai_cost || "0");
		} else {
			orgMetrics.set(workflow.organization_id, {
				name: orgName,
				execution_count: workflow.execution_count,
				conversation_count: 0,
				input_tokens: workflow.input_tokens,
				output_tokens: workflow.output_tokens,
				ai_cost: parseFloat(workflow.ai_cost || "0"),
			});
		}
	}

	for (const conv of allConversations) {
		const existing = orgMetrics.get(conv.organization_id);
		if (existing) {
			existing.conversation_count += 1;
			existing.input_tokens += conv.input_tokens;
			existing.output_tokens += conv.output_tokens;
			existing.ai_cost += parseFloat(conv.ai_cost || "0");
		}
	}

	const byOrganization: OrganizationUsage[] = Array.from(orgMetrics.entries()).map(
		([id, metrics]) => ({
			organization_id: id,
			organization_name: metrics.name,
			execution_count: metrics.execution_count,
			conversation_count: metrics.conversation_count,
			input_tokens: metrics.input_tokens,
			output_tokens: metrics.output_tokens,
			ai_cost: metrics.ai_cost.toFixed(2),
		}),
	);

	return {
		summary: {
			total_ai_cost: totalAiCost.toFixed(2),
			total_input_tokens: totalInputTokens,
			total_output_tokens: totalOutputTokens,
			total_ai_calls: totalAiCalls,
			total_cpu_seconds: totalCpuSeconds,
			peak_memory_bytes: peakMemoryBytes,
		},
		trends,
		by_workflow: includeWorkflows ? filteredWorkflows : undefined,
		by_conversation: includeConversations ? filteredConversations : undefined,
		by_organization: byOrganization,
	};
}

// ============================================================================
// Component
// ============================================================================

type SortConfig = { by: string; dir: "asc" | "desc" };

export function UsageReports() {
	const { isPlatformAdmin } = useAuth();

	// Organization filter state (platform admins only)
	// undefined = all, null = global only, UUID string = specific org
	const [filterOrgId, setFilterOrgId] = useState<string | null | undefined>(undefined);

	// Derive isGlobalScope from filterOrgId for display logic
	const isGlobalScope = filterOrgId === undefined || filterOrgId === null;

	// Fetch real organizations for demo data generation
	const { data: orgsData } = useOrganizations({ enabled: isPlatformAdmin });

	// Demo mode state
	const [showDemoData, setShowDemoData] = useState(false);

	// Source filter (Executions | Chat | All)
	const [source, setSource] = useState<UsageSource>("all");

	// Default to last 30 days
	const [dateRange, setDateRange] = useState<DateRange | undefined>({
		from: subDays(new Date(), 30),
		to: new Date(),
	});

	// Sorting state for tables
	const [workflowSort, setWorkflowSort] = useState<SortConfig>({
		by: "cost",
		dir: "desc",
	});
	const [conversationSort, setConversationSort] = useState<SortConfig>({
		by: "cost",
		dir: "desc",
	});
	const [orgSort, setOrgSort] = useState<SortConfig>({
		by: "cost",
		dir: "desc",
	});
	const [storageSort, setStorageSort] = useState<SortConfig>({
		by: "size",
		dir: "desc",
	});

	// Format dates for API (YYYY-MM-DD)
	const startDate = dateRange?.from
		? format(dateRange.from, "yyyy-MM-dd")
		: "";
	const endDate = dateRange?.to ? format(dateRange.to, "yyyy-MM-dd") : "";

	// Memoize orgs array for stable reference
	const realOrgs = useMemo(() => {
		if (!orgsData || !Array.isArray(orgsData)) return undefined;
		return orgsData.map((o) => ({ id: o.id, name: o.name }));
	}, [orgsData]);

	// Demo data - pre-filtered like API
	// Use filterOrgId for filtering (undefined/null means show all orgs)
	const demoData = useMemo(() => {
		if (!startDate || !endDate) return null;
		return generateDemoData({
			startDate,
			endDate,
			orgId: filterOrgId ?? null,
			source,
			realOrgs,
		});
	}, [startDate, endDate, filterOrgId, source, realOrgs]);

	// Fetch real data
	const {
		data: realData,
		isLoading,
		error,
	} = useUsageReport(startDate, endDate, source, filterOrgId);

	// Use demo or real data
	const data = showDemoData ? demoData : realData;

	// Sorted workflows
	const sortedWorkflows = useMemo(() => {
		const workflows = data?.by_workflow;
		if (!workflows) return [];
		return [...workflows].sort((a, b) => {
			const mult = workflowSort.dir === "desc" ? -1 : 1;
			switch (workflowSort.by) {
				case "name":
					return mult * a.workflow_name.localeCompare(b.workflow_name);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "tokens":
					return mult * ((a.input_tokens + a.output_tokens) - (b.input_tokens + b.output_tokens));
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				case "cpu":
					return mult * (a.cpu_seconds - b.cpu_seconds);
				case "memory":
					return mult * (a.memory_bytes - b.memory_bytes);
				default:
					return 0;
			}
		});
	}, [data?.by_workflow, workflowSort]);

	// Sorted conversations
	const sortedConversations = useMemo(() => {
		const conversations = data?.by_conversation;
		if (!conversations) return [];
		return [...conversations].sort((a, b) => {
			const mult = conversationSort.dir === "desc" ? -1 : 1;
			switch (conversationSort.by) {
				case "title":
					return mult * (a.conversation_title || "").localeCompare(b.conversation_title || "");
				case "messages":
					return mult * (a.message_count - b.message_count);
				case "tokens":
					return mult * ((a.input_tokens + a.output_tokens) - (b.input_tokens + b.output_tokens));
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				default:
					return 0;
			}
		});
	}, [data?.by_conversation, conversationSort]);

	// Sorted organizations
	const sortedOrganizations = useMemo(() => {
		const organizations = data?.by_organization;
		if (!organizations) return [];
		return [...organizations].sort((a, b) => {
			const mult = orgSort.dir === "desc" ? -1 : 1;
			switch (orgSort.by) {
				case "name":
					return mult * a.organization_name.localeCompare(b.organization_name);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "conversations":
					return mult * (a.conversation_count - b.conversation_count);
				case "tokens":
					return mult * ((a.input_tokens + a.output_tokens) - (b.input_tokens + b.output_tokens));
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				default:
					return 0;
			}
		});
	}, [data?.by_organization, orgSort]);

	// Sorted knowledge storage
	const sortedStorage = useMemo(() => {
		const storage = data?.knowledge_storage;
		if (!storage) return [];
		return [...storage].sort((a, b) => {
			const mult = storageSort.dir === "desc" ? -1 : 1;
			switch (storageSort.by) {
				case "org":
					return mult * a.organization_name.localeCompare(b.organization_name);
				case "namespace":
					return mult * a.namespace.localeCompare(b.namespace);
				case "documents":
					return mult * (a.document_count - b.document_count);
				case "size":
					return mult * (a.size_bytes - b.size_bytes);
				default:
					return 0;
			}
		});
	}, [data?.knowledge_storage, storageSort]);

	// Sort toggle helpers
	const toggleWorkflowSort = (column: string) => {
		setWorkflowSort((prev) => ({
			by: column,
			dir: prev.by === column && prev.dir === "desc" ? "asc" : "desc",
		}));
	};

	const toggleConversationSort = (column: string) => {
		setConversationSort((prev) => ({
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

	const toggleStorageSort = (column: string) => {
		setStorageSort((prev) => ({
			by: column,
			dir: prev.by === column && prev.dir === "desc" ? "asc" : "desc",
		}));
	};

	// Loading state
	const isLoadingData = showDemoData ? false : isLoading;

	// Error state
	const hasError = showDemoData ? false : !!error;

	// CSV Export handlers
	const downloadWorkflowCSV = () => {
		if (!data?.by_workflow) return;

		const headers = [
			"Workflow Name",
			"Executions",
			"Input Tokens",
			"Output Tokens",
			"AI Cost",
			"CPU Seconds",
			"Memory (MB)",
		];
		const rows = data.by_workflow.map((w) => [
			w.workflow_name,
			w.execution_count,
			w.input_tokens,
			w.output_tokens,
			w.ai_cost || "0",
			w.cpu_seconds,
			(w.memory_bytes / (1024 * 1024)).toFixed(2),
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `usage-by-workflow-${startDate}-${endDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	const downloadConversationCSV = () => {
		if (!data?.by_conversation) return;

		const headers = [
			"Conversation Title",
			"Message Count",
			"Input Tokens",
			"Output Tokens",
			"AI Cost",
		];
		const rows = data.by_conversation.map((c) => [
			c.conversation_title || "Untitled",
			c.message_count,
			c.input_tokens,
			c.output_tokens,
			c.ai_cost || "0",
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `usage-by-conversation-${startDate}-${endDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	const downloadOrganizationCSV = () => {
		if (!data?.by_organization) return;

		const headers = [
			"Organization",
			"Executions",
			"Conversations",
			"Input Tokens",
			"Output Tokens",
			"AI Cost",
		];
		const rows = data.by_organization.map((o) => [
			o.organization_name,
			o.execution_count,
			o.conversation_count,
			o.input_tokens,
			o.output_tokens,
			o.ai_cost || "0",
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `usage-by-organization-${startDate}-${endDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	const downloadStorageCSV = () => {
		if (!data?.knowledge_storage) return;

		const headers = [
			"Organization",
			"Namespace",
			"Documents",
			"Size (MB)",
			"Size (Bytes)",
		];
		const rows = data.knowledge_storage.map((s) => [
			s.organization_name,
			s.namespace,
			s.document_count,
			s.size_mb.toFixed(2),
			s.size_bytes,
		]);

		const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `knowledge-storage-${data.knowledge_storage_as_of || startDate}${showDemoData ? "-demo" : ""}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	};

	// Show conversation table when source is chat or all
	const showConversationTable = source === "chat" || source === "all";

	return (
		<div className="space-y-6">
			{/* Header */}
			<div className="flex items-start justify-between">
				<div>
					<div className="flex items-center gap-3">
						<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
							Usage Reports
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
						AI usage and resource consumption analytics
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
						Toggle off to view real usage data.
					</AlertDescription>
				</Alert>
			)}

			{/* Filters: Date Range, Source Tabs, and Organization */}
			<Card>
				<CardHeader>
					<CardTitle>Report Period</CardTitle>
					<CardDescription>
						Select a date range and source for the usage report
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<DateRangePicker
						dateRange={dateRange}
						onDateRangeChange={setDateRange}
					/>

					<div className="flex items-center gap-4">
						<Label className="text-sm font-medium">Source:</Label>
						<Tabs
							value={source}
							onValueChange={(v) => setSource(v as UsageSource)}
						>
							<TabsList>
								<TabsTrigger value="all">All</TabsTrigger>
								<TabsTrigger value="executions">Executions</TabsTrigger>
								<TabsTrigger value="chat">Chat</TabsTrigger>
							</TabsList>
						</Tabs>
						{isPlatformAdmin && (
							<div className="w-64 ml-auto">
								<OrganizationSelect
									value={filterOrgId}
									onChange={setFilterOrgId}
									showAll={true}
									showGlobal={true}
									placeholder="All organizations"
								/>
							</div>
						)}
					</div>
				</CardContent>
			</Card>

			{/* Error Alert */}
			{hasError && (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						Failed to load usage data. Please try again later.
					</AlertDescription>
				</Alert>
			)}

			{/* Summary Cards */}
			<div className="grid gap-4 md:grid-cols-4">
				{/* Total AI Cost */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total AI Cost
						</CardTitle>
						<DollarSign className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{formatCurrency(data?.summary?.total_ai_cost)}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							USD spent on AI APIs
						</p>
					</CardContent>
				</Card>

				{/* Total Tokens */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total Tokens
						</CardTitle>
						<Hash className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{formatNumber(
									(data?.summary?.total_input_tokens ?? 0) +
									(data?.summary?.total_output_tokens ?? 0)
								)}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							Input + output tokens
						</p>
					</CardContent>
				</Card>

				{/* Total CPU Seconds */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Total CPU Time
						</CardTitle>
						<Cpu className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{formatCpuSeconds(data?.summary?.total_cpu_seconds)}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							Execution compute time
						</p>
					</CardContent>
				</Card>

				{/* Peak Memory */}
				<Card>
					<CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle className="text-sm font-medium">
							Peak Memory
						</CardTitle>
						<HardDrive className="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
							<Skeleton className="h-8 w-24" />
						) : (
							<div className="text-2xl font-bold">
								{formatBytes(data?.summary?.peak_memory_bytes)}
							</div>
						)}
						<p className="text-xs text-muted-foreground">
							Maximum memory usage
						</p>
					</CardContent>
				</Card>
			</div>

			{/* Trends Chart */}
			<Card>
				<CardHeader>
					<CardTitle>Cost Over Time</CardTitle>
					<CardDescription>
						AI cost trends during the selected period
					</CardDescription>
				</CardHeader>
				<CardContent>
					{isLoadingData ? (
						<Skeleton className="h-[300px] w-full" />
					) : data?.trends && data.trends.length > 0 ? (
						<ResponsiveContainer width="100%" height={300}>
							<LineChart data={data.trends}>
								<CartesianGrid
									strokeDasharray="3 3"
									className="stroke-muted"
								/>
								<XAxis
									dataKey="date"
									className="text-xs"
									tick={{ fontSize: 12 }}
									tickFormatter={(value) =>
										format(new Date(value), "MMM dd")
									}
								/>
								<YAxis
									className="text-xs"
									tick={{ fontSize: 12 }}
									tickFormatter={(value) => `$${value}`}
									label={{
										value: "Cost (USD)",
										angle: -90,
										position: "insideLeft",
										fontSize: 12,
									}}
								/>
								<Tooltip
									contentStyle={{
										backgroundColor: "hsl(var(--card))",
										border: "1px solid hsl(var(--border))",
										borderRadius: "6px",
									}}
									formatter={(value: string | number, name: string) => {
										if (name === "ai_cost")
											return [formatCurrency(value), "AI Cost"];
										return [formatNumber(value as number), name];
									}}
									labelFormatter={(label) =>
										format(new Date(label), "PPP")
									}
								/>
								<Legend
									formatter={(value) => {
										if (value === "ai_cost") return "AI Cost";
										if (value === "input_tokens") return "Input Tokens";
										if (value === "output_tokens") return "Output Tokens";
										return value;
									}}
								/>
								<Line
									type="monotone"
									dataKey="ai_cost"
									stroke="hsl(var(--chart-1, 220 70% 50%))"
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

			{/* By-Workflow Table */}
			{(source === "all" || source === "executions") && (
				<Card>
					<CardHeader>
						<div className="flex items-center justify-between">
							<div>
								<CardTitle>Usage by Workflow</CardTitle>
								<CardDescription>
									AI and resource consumption per workflow
								</CardDescription>
							</div>
							<Button
								variant="outline"
								size="sm"
								onClick={downloadWorkflowCSV}
								disabled={!data?.by_workflow || data.by_workflow.length === 0}
							>
								<Download className="h-4 w-4 mr-2" />
								Export CSV
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
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
											onClick={() => toggleWorkflowSort("name")}
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
											onClick={() => toggleWorkflowSort("executions")}
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
											onClick={() => toggleWorkflowSort("tokens")}
										>
											<div className="flex items-center justify-end gap-1">
												Tokens
												{workflowSort.by === "tokens" &&
													(workflowSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleWorkflowSort("cost")}
										>
											<div className="flex items-center justify-end gap-1">
												AI Cost
												{workflowSort.by === "cost" &&
													(workflowSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleWorkflowSort("cpu")}
										>
											<div className="flex items-center justify-end gap-1">
												CPU
												{workflowSort.by === "cpu" &&
													(workflowSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleWorkflowSort("memory")}
										>
											<div className="flex items-center justify-end gap-1">
												Memory
												{workflowSort.by === "memory" &&
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
									{sortedWorkflows.map((workflow, index) => (
										<DataTableRow key={`${workflow.workflow_name}-${index}`}>
											<DataTableCell className="font-medium">
												{workflow.workflow_name}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(workflow.execution_count)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(workflow.input_tokens + workflow.output_tokens)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatCurrency(workflow.ai_cost)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatCpuSeconds(workflow.cpu_seconds)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatBytes(workflow.memory_bytes)}
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
			)}

			{/* By-Conversation Table */}
			{showConversationTable && (
				<Card>
					<CardHeader>
						<div className="flex items-center justify-between">
							<div>
								<CardTitle>Usage by Conversation</CardTitle>
								<CardDescription>
									AI consumption per chat conversation
								</CardDescription>
							</div>
							<Button
								variant="outline"
								size="sm"
								onClick={downloadConversationCSV}
								disabled={!data?.by_conversation || data.by_conversation.length === 0}
							>
								<Download className="h-4 w-4 mr-2" />
								Export CSV
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
							<div className="space-y-2">
								<Skeleton className="h-10 w-full" />
								<Skeleton className="h-10 w-full" />
								<Skeleton className="h-10 w-full" />
							</div>
						) : sortedConversations.length > 0 ? (
							<DataTable>
								<DataTableHeader>
									<DataTableRow>
										<DataTableHead
											className="cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleConversationSort("title")}
										>
											<div className="flex items-center gap-1">
												Conversation
												{conversationSort.by === "title" &&
													(conversationSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleConversationSort("messages")}
										>
											<div className="flex items-center justify-end gap-1">
												Messages
												{conversationSort.by === "messages" &&
													(conversationSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleConversationSort("tokens")}
										>
											<div className="flex items-center justify-end gap-1">
												Tokens
												{conversationSort.by === "tokens" &&
													(conversationSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleConversationSort("cost")}
										>
											<div className="flex items-center justify-end gap-1">
												AI Cost
												{conversationSort.by === "cost" &&
													(conversationSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
									</DataTableRow>
								</DataTableHeader>
								<DataTableBody>
									{sortedConversations.map((conversation) => (
										<DataTableRow key={conversation.conversation_id}>
											<DataTableCell className="font-medium">
												{conversation.conversation_title || "Untitled"}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(conversation.message_count)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(conversation.input_tokens + conversation.output_tokens)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatCurrency(conversation.ai_cost)}
											</DataTableCell>
										</DataTableRow>
									))}
								</DataTableBody>
							</DataTable>
						) : (
							<div className="flex items-center justify-center py-8 text-muted-foreground">
								No conversation data available for this period
							</div>
						)}
					</CardContent>
				</Card>
			)}

			{/* By-Organization Table - Only shown in global scope */}
			{isGlobalScope && (
				<Card>
					<CardHeader>
						<div className="flex items-center justify-between">
							<div>
								<CardTitle>Usage by Organization</CardTitle>
								<CardDescription>
									AI consumption across organizations
								</CardDescription>
							</div>
							<Button
								variant="outline"
								size="sm"
								onClick={downloadOrganizationCSV}
								disabled={
									!data?.by_organization ||
									data.by_organization.length === 0
								}
							>
								<Download className="h-4 w-4 mr-2" />
								Export CSV
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						{isLoadingData ? (
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
											onClick={() => toggleOrgSort("name")}
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
											onClick={() => toggleOrgSort("executions")}
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
											onClick={() => toggleOrgSort("conversations")}
										>
											<div className="flex items-center justify-end gap-1">
												Conversations
												{orgSort.by === "conversations" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleOrgSort("tokens")}
										>
											<div className="flex items-center justify-end gap-1">
												Tokens
												{orgSort.by === "tokens" &&
													(orgSort.dir === "desc" ? (
														<ChevronDown className="h-4 w-4" />
													) : (
														<ChevronUp className="h-4 w-4" />
													))}
											</div>
										</DataTableHead>
										<DataTableHead
											className="text-right cursor-pointer select-none hover:bg-muted/50"
											onClick={() => toggleOrgSort("cost")}
										>
											<div className="flex items-center justify-end gap-1">
												AI Cost
												{orgSort.by === "cost" &&
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
												{formatNumber(org.execution_count)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(org.conversation_count)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatNumber(org.input_tokens + org.output_tokens)}
											</DataTableCell>
											<DataTableCell className="text-right">
												{formatCurrency(org.ai_cost)}
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

			{/* Knowledge Storage Table */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<div className="flex items-center gap-2">
								<CardTitle>Knowledge Storage</CardTitle>
								{data?.knowledge_storage_as_of && (
									<Badge variant="outline" className="text-xs font-normal">
										As of {format(new Date(data.knowledge_storage_as_of), "MMM d, yyyy")}
									</Badge>
								)}
							</div>
							<CardDescription>
								Storage consumption by organization and namespace
							</CardDescription>
						</div>
						<Button
							variant="outline"
							size="sm"
							onClick={downloadStorageCSV}
							disabled={!data?.knowledge_storage || data.knowledge_storage.length === 0}
						>
							<Download className="h-4 w-4 mr-2" />
							Export CSV
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					{isLoadingData ? (
						<div className="space-y-2">
							<Skeleton className="h-10 w-full" />
							<Skeleton className="h-10 w-full" />
							<Skeleton className="h-10 w-full" />
						</div>
					) : sortedStorage.length > 0 ? (
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead
										className="cursor-pointer select-none hover:bg-muted/50"
										onClick={() => toggleStorageSort("org")}
									>
										<div className="flex items-center gap-1">
											Organization
											{storageSort.by === "org" &&
												(storageSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="cursor-pointer select-none hover:bg-muted/50"
										onClick={() => toggleStorageSort("namespace")}
									>
										<div className="flex items-center gap-1">
											Namespace
											{storageSort.by === "namespace" &&
												(storageSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="text-right cursor-pointer select-none hover:bg-muted/50"
										onClick={() => toggleStorageSort("documents")}
									>
										<div className="flex items-center justify-end gap-1">
											Documents
											{storageSort.by === "documents" &&
												(storageSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
									<DataTableHead
										className="text-right cursor-pointer select-none hover:bg-muted/50"
										onClick={() => toggleStorageSort("size")}
									>
										<div className="flex items-center justify-end gap-1">
											Size
											{storageSort.by === "size" &&
												(storageSort.dir === "desc" ? (
													<ChevronDown className="h-4 w-4" />
												) : (
													<ChevronUp className="h-4 w-4" />
												))}
										</div>
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{sortedStorage.map((storage, index) => (
									<DataTableRow key={`${storage.organization_id || "global"}-${storage.namespace}-${index}`}>
										<DataTableCell className="font-medium">
											<div className="flex items-center gap-2">
												<Database className="h-4 w-4 text-muted-foreground" />
												{storage.organization_name}
											</div>
										</DataTableCell>
										<DataTableCell>
											<code className="text-sm bg-muted px-1.5 py-0.5 rounded">
												{storage.namespace}
											</code>
										</DataTableCell>
										<DataTableCell className="text-right">
											{formatNumber(storage.document_count)}
										</DataTableCell>
										<DataTableCell className="text-right">
											{storage.size_mb >= 1
												? `${storage.size_mb.toFixed(2)} MB`
												: formatBytes(storage.size_bytes)}
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
						</DataTable>
					) : (
						<div className="flex items-center justify-center py-8 text-muted-foreground">
							No knowledge storage data available
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
