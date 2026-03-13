import { useState, useMemo } from "react";
import { format } from "date-fns";
import { Download, ChevronUp, ChevronDown, Database } from "lucide-react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import type {
	UsageReportResponse,
	WorkflowUsage,
	ConversationUsage,
	OrganizationUsage,
} from "@/services/usage";

interface AgentUsage {
	agent_name: string;
	run_count: number;
	input_tokens: number;
	output_tokens: number;
	ai_cost?: string;
}
import {
	formatCurrency,
	formatNumber,
	formatCpuSeconds,
	formatBytes,
	type SortConfig,
} from "./formatters";

// ============================================================================
// Shared sort icon helper
// ============================================================================

function SortIcon({ sort, column }: { sort: SortConfig; column: string }) {
	if (sort.by !== column) return null;
	return sort.dir === "desc" ? (
		<ChevronDown className="h-4 w-4" />
	) : (
		<ChevronUp className="h-4 w-4" />
	);
}

function useToggleSort(initial: SortConfig) {
	const [sort, setSort] = useState<SortConfig>(initial);
	const toggle = (column: string) => {
		setSort((prev) => ({
			by: column,
			dir: prev.by === column && prev.dir === "desc" ? "asc" : "desc",
		}));
	};
	return [sort, toggle] as const;
}

// ============================================================================
// CSV download helpers
// ============================================================================

function downloadCSV(filename: string, headers: string[], rows: (string | number)[][]) {
	const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
	const blob = new Blob([csv], { type: "text/csv" });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}

// ============================================================================
// Workflow Table
// ============================================================================

interface WorkflowTableProps {
	workflows: WorkflowUsage[] | undefined;
	isLoading: boolean;
	startDate: string;
	endDate: string;
	isDemo: boolean;
}

export function WorkflowTable({
	workflows,
	isLoading,
	startDate,
	endDate,
	isDemo,
}: WorkflowTableProps) {
	const [sort, toggleSort] = useToggleSort({ by: "cost", dir: "desc" });

	const sorted = useMemo(() => {
		if (!workflows) return [];
		return [...workflows].sort((a, b) => {
			const mult = sort.dir === "desc" ? -1 : 1;
			switch (sort.by) {
				case "name":
					return mult * a.workflow_name.localeCompare(b.workflow_name);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "tokens":
					return (
						mult *
						(a.input_tokens + a.output_tokens - (b.input_tokens + b.output_tokens))
					);
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
	}, [workflows, sort]);

	const handleExport = () => {
		if (!workflows) return;
		downloadCSV(
			`usage-by-workflow-${startDate}-${endDate}${isDemo ? "-demo" : ""}.csv`,
			["Workflow Name", "Executions", "Input Tokens", "Output Tokens", "AI Cost", "CPU Seconds", "Memory (MB)"],
			workflows.map((w) => [
				w.workflow_name,
				w.execution_count,
				w.input_tokens,
				w.output_tokens,
				w.ai_cost || "0",
				w.cpu_seconds,
				(w.memory_bytes / (1024 * 1024)).toFixed(2),
			]),
		);
	};

	return (
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
						onClick={handleExport}
						disabled={!workflows || workflows.length === 0}
					>
						<Download className="h-4 w-4 mr-2" />
						Export CSV
					</Button>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="space-y-2">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</div>
				) : sorted.length > 0 ? (
					<DataTable>
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("name")}
								>
									<div className="flex items-center gap-1">
										Workflow
										<SortIcon sort={sort} column="name" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("executions")}
								>
									<div className="flex items-center justify-end gap-1">
										Executions
										<SortIcon sort={sort} column="executions" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("tokens")}
								>
									<div className="flex items-center justify-end gap-1">
										Tokens
										<SortIcon sort={sort} column="tokens" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("cost")}
								>
									<div className="flex items-center justify-end gap-1">
										AI Cost
										<SortIcon sort={sort} column="cost" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("cpu")}
								>
									<div className="flex items-center justify-end gap-1">
										CPU
										<SortIcon sort={sort} column="cpu" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("memory")}
								>
									<div className="flex items-center justify-end gap-1">
										Memory
										<SortIcon sort={sort} column="memory" />
									</div>
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sorted.map((workflow, index) => (
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
	);
}

// ============================================================================
// Conversation Table
// ============================================================================

interface ConversationTableProps {
	conversations: ConversationUsage[] | undefined;
	isLoading: boolean;
	startDate: string;
	endDate: string;
	isDemo: boolean;
}

export function ConversationTable({
	conversations,
	isLoading,
	startDate,
	endDate,
	isDemo,
}: ConversationTableProps) {
	const [sort, toggleSort] = useToggleSort({ by: "cost", dir: "desc" });

	const sorted = useMemo(() => {
		if (!conversations) return [];
		return [...conversations].sort((a, b) => {
			const mult = sort.dir === "desc" ? -1 : 1;
			switch (sort.by) {
				case "title":
					return (
						mult *
						(a.conversation_title || "").localeCompare(b.conversation_title || "")
					);
				case "messages":
					return mult * (a.message_count - b.message_count);
				case "tokens":
					return (
						mult *
						(a.input_tokens + a.output_tokens - (b.input_tokens + b.output_tokens))
					);
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				default:
					return 0;
			}
		});
	}, [conversations, sort]);

	const handleExport = () => {
		if (!conversations) return;
		downloadCSV(
			`usage-by-conversation-${startDate}-${endDate}${isDemo ? "-demo" : ""}.csv`,
			["Conversation Title", "Message Count", "Input Tokens", "Output Tokens", "AI Cost"],
			conversations.map((c) => [
				c.conversation_title || "Untitled",
				c.message_count,
				c.input_tokens,
				c.output_tokens,
				c.ai_cost || "0",
			]),
		);
	};

	return (
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
						onClick={handleExport}
						disabled={!conversations || conversations.length === 0}
					>
						<Download className="h-4 w-4 mr-2" />
						Export CSV
					</Button>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="space-y-2">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</div>
				) : sorted.length > 0 ? (
					<DataTable>
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("title")}
								>
									<div className="flex items-center gap-1">
										Conversation
										<SortIcon sort={sort} column="title" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("messages")}
								>
									<div className="flex items-center justify-end gap-1">
										Messages
										<SortIcon sort={sort} column="messages" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("tokens")}
								>
									<div className="flex items-center justify-end gap-1">
										Tokens
										<SortIcon sort={sort} column="tokens" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("cost")}
								>
									<div className="flex items-center justify-end gap-1">
										AI Cost
										<SortIcon sort={sort} column="cost" />
									</div>
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sorted.map((conversation) => (
								<DataTableRow key={conversation.conversation_id}>
									<DataTableCell className="font-medium">
										{conversation.conversation_title || "Untitled"}
									</DataTableCell>
									<DataTableCell className="text-right">
										{formatNumber(conversation.message_count)}
									</DataTableCell>
									<DataTableCell className="text-right">
										{formatNumber(
											conversation.input_tokens + conversation.output_tokens,
										)}
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
	);
}

// ============================================================================
// Organization Table
// ============================================================================

interface OrganizationTableProps {
	organizations: OrganizationUsage[] | undefined;
	isLoading: boolean;
	startDate: string;
	endDate: string;
	isDemo: boolean;
}

export function OrganizationTable({
	organizations,
	isLoading,
	startDate,
	endDate,
	isDemo,
}: OrganizationTableProps) {
	const [sort, toggleSort] = useToggleSort({ by: "cost", dir: "desc" });

	const sorted = useMemo(() => {
		if (!organizations) return [];
		return [...organizations].sort((a, b) => {
			const mult = sort.dir === "desc" ? -1 : 1;
			switch (sort.by) {
				case "name":
					return mult * a.organization_name.localeCompare(b.organization_name);
				case "executions":
					return mult * (a.execution_count - b.execution_count);
				case "conversations":
					return mult * (a.conversation_count - b.conversation_count);
				case "tokens":
					return (
						mult *
						(a.input_tokens + a.output_tokens - (b.input_tokens + b.output_tokens))
					);
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				default:
					return 0;
			}
		});
	}, [organizations, sort]);

	const handleExport = () => {
		if (!organizations) return;
		downloadCSV(
			`usage-by-organization-${startDate}-${endDate}${isDemo ? "-demo" : ""}.csv`,
			["Organization", "Executions", "Conversations", "Input Tokens", "Output Tokens", "AI Cost"],
			organizations.map((o) => [
				o.organization_name,
				o.execution_count,
				o.conversation_count,
				o.input_tokens,
				o.output_tokens,
				o.ai_cost || "0",
			]),
		);
	};

	return (
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
						onClick={handleExport}
						disabled={!organizations || organizations.length === 0}
					>
						<Download className="h-4 w-4 mr-2" />
						Export CSV
					</Button>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="space-y-2">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</div>
				) : sorted.length > 0 ? (
					<DataTable>
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("name")}
								>
									<div className="flex items-center gap-1">
										Organization
										<SortIcon sort={sort} column="name" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("executions")}
								>
									<div className="flex items-center justify-end gap-1">
										Executions
										<SortIcon sort={sort} column="executions" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("conversations")}
								>
									<div className="flex items-center justify-end gap-1">
										Conversations
										<SortIcon sort={sort} column="conversations" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("tokens")}
								>
									<div className="flex items-center justify-end gap-1">
										Tokens
										<SortIcon sort={sort} column="tokens" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("cost")}
								>
									<div className="flex items-center justify-end gap-1">
										AI Cost
										<SortIcon sort={sort} column="cost" />
									</div>
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sorted.map((org) => (
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
	);
}

// ============================================================================
// Knowledge Storage Table
// ============================================================================

interface KnowledgeStorageTableProps {
	data: UsageReportResponse | null | undefined;
	isLoading: boolean;
	startDate: string;
	isDemo: boolean;
}

export function KnowledgeStorageTable({
	data,
	isLoading,
	startDate,
	isDemo,
}: KnowledgeStorageTableProps) {
	const [sort, toggleSort] = useToggleSort({ by: "size", dir: "desc" });

	const sorted = useMemo(() => {
		const storage = data?.knowledge_storage;
		if (!storage) return [];
		return [...storage].sort((a, b) => {
			const mult = sort.dir === "desc" ? -1 : 1;
			switch (sort.by) {
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
	}, [data?.knowledge_storage, sort]);

	const handleExport = () => {
		if (!data?.knowledge_storage) return;
		downloadCSV(
			`knowledge-storage-${data.knowledge_storage_as_of || startDate}${isDemo ? "-demo" : ""}.csv`,
			["Organization", "Namespace", "Documents", "Size (MB)", "Size (Bytes)"],
			data.knowledge_storage.map((s) => [
				s.organization_name,
				s.namespace,
				s.document_count,
				s.size_mb.toFixed(2),
				s.size_bytes,
			]),
		);
	};

	return (
		<Card>
			<CardHeader>
				<div className="flex items-center justify-between">
					<div>
						<div className="flex items-center gap-2">
							<CardTitle>Knowledge Storage</CardTitle>
							{data?.knowledge_storage_as_of && (
								<Badge
									variant="outline"
									className="text-xs font-normal"
								>
									As of{" "}
									{format(
										new Date(data.knowledge_storage_as_of),
										"MMM d, yyyy",
									)}
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
						onClick={handleExport}
						disabled={
							!data?.knowledge_storage || data.knowledge_storage.length === 0
						}
					>
						<Download className="h-4 w-4 mr-2" />
						Export CSV
					</Button>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="space-y-2">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</div>
				) : sorted.length > 0 ? (
					<DataTable>
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("org")}
								>
									<div className="flex items-center gap-1">
										Organization
										<SortIcon sort={sort} column="org" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("namespace")}
								>
									<div className="flex items-center gap-1">
										Namespace
										<SortIcon sort={sort} column="namespace" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("documents")}
								>
									<div className="flex items-center justify-end gap-1">
										Documents
										<SortIcon sort={sort} column="documents" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("size")}
								>
									<div className="flex items-center justify-end gap-1">
										Size
										<SortIcon sort={sort} column="size" />
									</div>
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sorted.map((storage, index) => (
								<DataTableRow
									key={`${storage.organization_id || "global"}-${storage.namespace}-${index}`}
								>
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
	);
}

// ============================================================================
// Agent Table
// ============================================================================

interface AgentTableProps {
	agents: AgentUsage[] | undefined;
	isLoading: boolean;
}

export function AgentTable({ agents, isLoading }: AgentTableProps) {
	const [sort, toggleSort] = useToggleSort({ by: "cost", dir: "desc" });

	const sorted = useMemo(() => {
		if (!agents) return [];
		return [...agents].sort((a, b) => {
			const mult = sort.dir === "desc" ? -1 : 1;
			switch (sort.by) {
				case "name":
					return mult * a.agent_name.localeCompare(b.agent_name);
				case "runs":
					return mult * (a.run_count - b.run_count);
				case "tokens":
					return (
						mult *
						(a.input_tokens + a.output_tokens - (b.input_tokens + b.output_tokens))
					);
				case "cost":
					return mult * (parseFloat(a.ai_cost || "0") - parseFloat(b.ai_cost || "0"));
				default:
					return 0;
			}
		});
	}, [agents, sort]);

	return (
		<Card>
			<CardHeader>
				<div>
					<CardTitle>Usage by Agent</CardTitle>
					<CardDescription>
						AI consumption per autonomous agent
					</CardDescription>
				</div>
			</CardHeader>
			<CardContent>
				{isLoading ? (
					<div className="space-y-2">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</div>
				) : sorted.length > 0 ? (
					<DataTable>
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("name")}
								>
									<div className="flex items-center gap-1">
										Agent
										<SortIcon sort={sort} column="name" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("runs")}
								>
									<div className="flex items-center justify-end gap-1">
										Runs
										<SortIcon sort={sort} column="runs" />
									</div>
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("tokens")}
								>
									<div className="flex items-center justify-end gap-1">
										Input Tokens
										<SortIcon sort={sort} column="tokens" />
									</div>
								</DataTableHead>
								<DataTableHead className="text-right">
									Output Tokens
								</DataTableHead>
								<DataTableHead
									className="text-right cursor-pointer select-none hover:bg-muted/50"
									onClick={() => toggleSort("cost")}
								>
									<div className="flex items-center justify-end gap-1">
										AI Cost
										<SortIcon sort={sort} column="cost" />
									</div>
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sorted.map((agent) => (
								<DataTableRow key={agent.agent_name}>
									<DataTableCell className="font-medium">
										{agent.agent_name}
									</DataTableCell>
									<DataTableCell className="text-right">
										{formatNumber(agent.run_count)}
									</DataTableCell>
									<DataTableCell className="text-right font-mono">
										{formatNumber(agent.input_tokens)}
									</DataTableCell>
									<DataTableCell className="text-right font-mono">
										{formatNumber(agent.output_tokens)}
									</DataTableCell>
									<DataTableCell className="text-right font-mono">
										{formatCurrency(agent.ai_cost || "0")}
									</DataTableCell>
								</DataTableRow>
							))}
						</DataTableBody>
					</DataTable>
				) : (
					<div className="flex items-center justify-center py-8 text-muted-foreground">
						No agent usage data for this period
					</div>
				)}
			</CardContent>
		</Card>
	);
}
