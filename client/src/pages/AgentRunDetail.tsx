/**
 * Agent Run Detail Page
 *
 * Two-column layout mirroring ExecutionDetails:
 * - Left (2/3): Result + Execution Steps timeline
 * - Right (1/3): Sidebar with run metadata, input, and context
 */

import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
	ArrowLeft,
	Bot,
	Clock,
	Cpu,
	Zap,
	Loader2,
	MessageSquare,
	Wrench,
	AlertCircle,
	AlertTriangle,
	CheckCircle,
	ChevronDown,
	ChevronRight,
	XCircle,
	Hash,
	User,
	CalendarClock,
	PlayCircle,
	Sparkles,
} from "lucide-react";
import { cn, formatNumber, formatCost, formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";
import { useAgentRun, useAgentRunStream, type AgentRunStep } from "@/services/agentRuns";

/** Render markdown text with GFM support */
function Markdown({ children }: { children: string }) {
	return (
		<ReactMarkdown
			remarkPlugins={[remarkGfm]}
			components={{
				// Minimal overrides for compact display
				p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
				ul: ({ children }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
				ol: ({ children }) => <ol className="list-decimal pl-4 mb-2">{children}</ol>,
				li: ({ children }) => <li className="mb-0.5">{children}</li>,
				code: ({ className, children, ...props }) => {
					const isInline = !className;
					if (isInline) {
						return (
							<code className="px-1 py-0.5 rounded bg-muted font-mono text-xs" {...props}>
								{children}
							</code>
						);
					}
					return (
						<pre className="p-3 rounded bg-muted overflow-x-auto mb-2">
							<code className="font-mono text-xs" {...props}>
								{children}
							</code>
						</pre>
					);
				},
				a: ({ children, href }) => (
					<a href={href} className="text-primary underline" target="_blank" rel="noopener noreferrer">
						{children}
					</a>
				),
				blockquote: ({ children }) => (
					<blockquote className="border-l-2 pl-3 italic text-muted-foreground mb-2">
						{children}
					</blockquote>
				),
				table: ({ children }) => (
					<div className="overflow-x-auto mb-2">
						<table className="min-w-full text-sm border-collapse">{children}</table>
					</div>
				),
				th: ({ children }) => (
					<th className="border-b px-2 py-1 text-left font-medium">{children}</th>
				),
				td: ({ children }) => (
					<td className="border-b px-2 py-1">{children}</td>
				),
			}}
		>
			{children}
		</ReactMarkdown>
	);
}

/** Large status icon for the sidebar status card (mirrors ExecutionStatusIcon) */
function AgentRunStatusIcon({ status }: { status: string }) {
	const size = "h-12 w-12";
	switch (status) {
		case "completed":
			return <CheckCircle className={`${size} text-green-500`} />;
		case "failed":
			return <XCircle className={`${size} text-red-500`} />;
		case "running":
			return <Loader2 className={`${size} text-blue-500 animate-spin`} />;
		case "queued":
			return <Clock className={`${size} text-gray-500`} />;
		case "budget_exceeded":
			return <AlertTriangle className={`${size} text-yellow-500`} />;
		default:
			return <Clock className={`${size} text-gray-500`} />;
	}
}

/** Status badge with proper colors and icons (mirrors ExecutionStatusBadge) */
function AgentRunStatusBadge({ status }: { status: string }) {
	switch (status) {
		case "completed":
			return (
				<Badge variant="default" className="bg-green-500">
					<CheckCircle className="mr-1 h-3 w-3" />
					Completed
				</Badge>
			);
		case "failed":
			return (
				<Badge variant="destructive">
					<XCircle className="mr-1 h-3 w-3" />
					Failed
				</Badge>
			);
		case "running":
			return (
				<Badge variant="secondary">
					<PlayCircle className="mr-1 h-3 w-3" />
					Running
				</Badge>
			);
		case "queued":
			return (
				<Badge variant="outline">
					<Clock className="mr-1 h-3 w-3" />
					Queued
				</Badge>
			);
		case "budget_exceeded":
			return (
				<Badge variant="secondary" className="bg-yellow-500">
					<AlertTriangle className="mr-1 h-3 w-3" />
					Budget Exceeded
				</Badge>
			);
		default:
			return <Badge variant="outline">{status}</Badge>;
	}
}

function stepIcon(type: string) {
	switch (type) {
		case "llm_request":
			return <Cpu className="h-4 w-4 text-blue-500" />;
		case "llm_response":
			return <MessageSquare className="h-4 w-4 text-green-500" />;
		case "tool_call":
			return <Wrench className="h-4 w-4 text-orange-500" />;
		case "tool_result":
			return <CheckCircle className="h-4 w-4 text-emerald-500" />;
		case "budget_warning":
			return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
		case "error":
			return <AlertCircle className="h-4 w-4 text-red-500" />;
		default:
			return <Zap className="h-4 w-4 text-gray-400" />;
	}
}

function stepLabel(type: string): string {
	switch (type) {
		case "llm_request":
			return "LLM Request";
		case "llm_response":
			return "LLM Response";
		case "tool_call":
			return "Tool Call";
		case "tool_result":
			return "Tool Result";
		case "budget_warning":
			return "Budget Warning";
		case "error":
			return "Error";
		default:
			return type;
	}
}

/** Unescape literal \n, \t, \' sequences from Python repr strings */
function unescapePythonRepr(value: string): string {
	return value
		.replace(/\\n/g, "\n")
		.replace(/\\t/g, "\t")
		.replace(/\\'/g, "'");
}

/** Render a tool result as markdown, unescaping Python repr artifacts. */
function ToolResultContent({ result }: { result: string }) {
	const cleaned = unescapePythonRepr(result);
	return (
		<div className="text-sm prose prose-sm dark:prose-invert max-w-none">
			<Markdown>{cleaned}</Markdown>
		</div>
	);
}

function ToolResultDisplay({ content }: { content: Record<string, unknown> }) {
	const [expanded, setExpanded] = useState(false);
	const result = content.result as string | undefined;
	const isError = content.is_error as boolean | undefined;
	const previewLength = 120;
	const isLong = result ? result.length > previewLength : false;

	return (
		<div
			className={cn(
				"border rounded-lg bg-card overflow-hidden",
				isError ? "border-destructive/30" : "border-emerald-500/30",
			)}
		>
			<button
				type="button"
				className="flex items-center gap-2 px-3 py-2 bg-muted/30 w-full text-left"
				onClick={() => result && setExpanded(!expanded)}
			>
				<Badge
					variant={isError ? "destructive" : "outline"}
					className="gap-1 font-normal"
				>
					{isError ? (
						<XCircle className="h-3 w-3" />
					) : (
						<CheckCircle className="h-3 w-3 text-emerald-500" />
					)}
					{isError ? "Error" : "Result"}
				</Badge>
				<span className="font-medium text-sm font-mono">
					{content.tool_name as string}
				</span>
				{result && (
					<span className="ml-auto">
						{expanded ? (
							<ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
						) : (
							<ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
						)}
					</span>
				)}
			</button>
			{result && expanded && (
				<div className="px-3 py-2 border-t">
					<ToolResultContent result={result} />
				</div>
			)}
			{result && !expanded && isLong && (
				<div className="px-3 py-1.5 border-t">
					<p className="text-xs text-muted-foreground truncate font-mono">
						{result.slice(0, previewLength)}…
					</p>
				</div>
			)}
		</div>
	);
}

/** Render the human-readable summary for a step. */
function StepSummary({ step }: { step: AgentRunStep }) {
	const c = step.content;
	if (!c) return null;

	switch (step.type) {
		case "llm_request":
			return (
				<p className="text-sm text-muted-foreground">
					Sending {(c.messages_count as number) ?? "?"} messages to{" "}
					<span className="font-mono text-xs">
						{(c.model as string) || "default"}
					</span>
					{(c.tools_count as number) > 0 && (
						<> with {c.tools_count as number} tools available</>
					)}
				</p>
			);

		case "llm_response": {
			const content = c.content as string | undefined;
			const toolCalls = c.tool_calls as
				| { name: string; arguments?: Record<string, unknown> }[]
				| undefined;
			return (
				<div className="space-y-2">
					{content && (
						<div className="text-sm prose prose-sm dark:prose-invert max-w-none">
							<Markdown>{content}</Markdown>
						</div>
					)}
					{toolCalls && toolCalls.length > 0 && (
						<div className="flex flex-wrap gap-1.5">
							<span className="text-xs text-muted-foreground pt-0.5">
								Calling:
							</span>
							{toolCalls.map((tc, i) => (
								<Badge
									key={i}
									variant="outline"
									className="text-xs font-mono"
								>
									{tc.name}
								</Badge>
							))}
						</div>
					)}
				</div>
			);
		}

		case "tool_call": {
			const args = c.arguments as Record<string, unknown> | undefined;
			const hasArgs = args && Object.keys(args).length > 0;
			return (
				<div
					className={cn(
						"border rounded-lg bg-card overflow-hidden",
						"border-orange-500/30",
					)}
				>
					<div className="flex items-center gap-2 px-3 py-2 bg-muted/30">
						<Badge variant="outline" className="gap-1 font-normal">
							<Wrench className="h-3 w-3 text-orange-500" />
							Tool Call
						</Badge>
						<span className="font-medium text-sm font-mono">
							{c.tool_name as string}
						</span>
					</div>
					{hasArgs && (
						<div className="px-3 py-2 border-t">
							<VariablesTreeView data={args} />
						</div>
					)}
				</div>
			);
		}

		case "tool_result":
			return <ToolResultDisplay content={c} />;

		case "budget_warning":
			return (
				<p className="text-sm text-yellow-600 dark:text-yellow-400">
					{c.reason === "token_budget_exceeded"
						? `Token budget exceeded (${(c.tokens_used as number)?.toLocaleString()} / ${(c.max_tokens as number)?.toLocaleString()} tokens)`
						: `Approaching iteration limit (${c.iterations_used as number} / ${c.max_iterations as number} iterations)`}
				</p>
			);

		case "error":
			return (
				<div className="space-y-1">
					{c.tool_name ? (
						<p className="text-sm font-mono text-xs">
							{c.tool_name as string}
						</p>
					) : null}
					<p className="text-sm text-destructive">
						{c.error as string}
					</p>
				</div>
			);

		default:
			return null;
	}
}

function StepCard({ step }: { step: AgentRunStep }) {
	return (
		<div className="flex gap-3 py-3 border-b last:border-0">
			<div className="mt-0.5">{stepIcon(step.type)}</div>
			<div className="flex-1 min-w-0">
				{/* Step header */}
				<div className="flex items-center gap-2 mb-1.5">
					<span className="font-mono text-xs text-muted-foreground">
						#{step.step_number}
					</span>
					<span className="text-xs font-medium">
						{stepLabel(step.type)}
					</span>
					{step.tokens_used != null && (
						<Badge variant="secondary" className="text-xs py-0">
							{step.tokens_used.toLocaleString()} tokens
						</Badge>
					)}
					{step.duration_ms != null && (
						<span className="text-xs text-muted-foreground">
							{(step.duration_ms / 1000).toFixed(1)}s
						</span>
					)}
				</div>

				{/* Human-readable summary */}
				<StepSummary step={step} />
			</div>
		</div>
	);
}

/** Render the output/result section. Text output shown as prose, structured as tree. */
function ResultSection({ output, error }: { output: unknown; error?: string | null }) {
	if (error) {
		return (
			<Card className="border-destructive">
				<CardHeader className="pb-2">
					<CardTitle className="text-sm text-destructive flex items-center gap-2">
						<AlertCircle className="h-4 w-4" />
						Error
					</CardTitle>
				</CardHeader>
				<CardContent>
					<pre className="text-sm whitespace-pre-wrap">{error}</pre>
				</CardContent>
			</Card>
		);
	}

	if (!output) return null;

	const outputObj = output as Record<string, unknown>;

	// If output has a "text" field, show it as prose
	const textContent = typeof outputObj.text === "string" ? outputObj.text : null;

	// Check for structured data beyond just "text"
	const structuredKeys = Object.keys(outputObj).filter((k) => k !== "text");
	const hasStructuredData = structuredKeys.length > 0;

	return (
		<Card>
			<CardHeader className="pb-2">
				<CardTitle className="text-sm flex items-center gap-2">
					<CheckCircle className="h-4 w-4 text-green-500" />
					Result
				</CardTitle>
			</CardHeader>
			<CardContent className="space-y-3">
				{textContent && (
					<div className="text-sm prose prose-sm dark:prose-invert max-w-none">
						<Markdown>{textContent}</Markdown>
					</div>
				)}
				{hasStructuredData && (
					<div className={textContent ? "border-t pt-3" : ""}>
						<VariablesTreeView
							data={
								structuredKeys.length === Object.keys(outputObj).length
									? outputObj
									: Object.fromEntries(
											structuredKeys.map((k) => [k, outputObj[k]]),
										)
							}
						/>
					</div>
				)}
				{!textContent && !hasStructuredData && typeof output === "string" && (
					<div className="text-sm prose prose-sm dark:prose-invert max-w-none">
						<Markdown>{output}</Markdown>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

export function AgentRunDetail() {
	const { runId } = useParams();
	const navigate = useNavigate();
	const [isAiUsageOpen, setIsAiUsageOpen] = useState(false);
	const isRunning = (s?: string) => s === "running" || s === "queued";

	// Fetch with polling fallback: poll every 3s while running, stop when complete.
	// This catches the race condition where the run completes between initial fetch
	// and WebSocket connection — same pattern as ExecutionDetails.
	// Uses function form since `run` isn't available during hook initialization.
	const { data: run, isLoading, refetch } = useAgentRun(runId, {
		refetchInterval: (query) => isRunning(query.state.data?.status) ? 3000 : false,
	});

	// Stable onComplete callback
	const handleStreamComplete = useCallback(() => {
		refetch();
	}, [refetch]);

	// Always subscribe to WebSocket when we have a runId — don't gate on isRunning.
	// This avoids the race condition where the run completes between initial fetch
	// and WebSocket connection. The onComplete callback refetches full data.
	useAgentRunStream(runId, {
		enabled: true,
		onComplete: handleStreamComplete,
	});

	if (isLoading) {
		return (
			<div className="space-y-4 p-6">
				<Skeleton className="h-8 w-64" />
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
					<div className="lg:col-span-2 space-y-4">
						<Skeleton className="h-48 w-full" />
						<Skeleton className="h-64 w-full" />
					</div>
					<Skeleton className="h-96 w-full" />
				</div>
			</div>
		);
	}

	if (!run) {
		return (
			<div className="text-center py-12 text-muted-foreground">
				<AlertCircle className="h-12 w-12 mx-auto mb-3 opacity-50" />
				<p>Agent run not found</p>
				<Button
					variant="outline"
					className="mt-4"
					onClick={() => navigate("/agent-runs")}
				>
					Back to Agent Runs
				</Button>
			</div>
		);
	}

	const isComplete = !isRunning(run.status);

	return (
		<div className="h-full overflow-y-auto">
			{/* Header */}
			<div className="sticky top-0 bg-background/80 backdrop-blur-sm py-6 border-b flex items-center gap-4 px-6 lg:px-8 z-10">
				<Button
					variant="ghost"
					size="icon"
					onClick={() => navigate("/agent-runs")}
				>
					<ArrowLeft className="h-4 w-4" />
				</Button>
				<div className="flex-1">
					<h1 className="text-4xl font-extrabold tracking-tight flex items-center gap-2">
						<Bot className="h-7 w-7" />
						{run.agent_name || "Agent Run"}
					</h1>
					<p className="mt-2 text-muted-foreground">
						Run ID: <span className="font-mono">{run.id}</span>
					</p>
				</div>
			</div>

			{/* Two-column layout */}
			<div className="p-6 lg:p-8">
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
					{/* Left Column - Result + Steps (2/3 width) */}
					<div className="lg:col-span-2 space-y-6">
						{/* Result */}
						{isComplete && (
							<ResultSection output={run.output} error={run.error} />
						)}

						{/* Running error (not yet complete) */}
						{!isComplete && run.error && (
							<Card className="border-destructive">
								<CardContent className="pt-4">
									<pre className="text-sm whitespace-pre-wrap text-destructive">
										{run.error}
									</pre>
								</CardContent>
							</Card>
						)}

						{/* Execution Steps */}
						<Card>
							<CardHeader>
								<CardTitle className="text-sm">
									Execution Steps ({run.steps?.length || 0})
								</CardTitle>
							</CardHeader>
							<CardContent>
								{run.steps && run.steps.length > 0 ? (
									<div>
										{run.steps.map((step: AgentRunStep) => (
											<StepCard key={step.id} step={step} />
										))}
									</div>
								) : (
									<p className="text-muted-foreground text-sm">
										{run.status === "running" || run.status === "queued"
											? "Waiting for steps..."
											: "No steps recorded"}
									</p>
								)}
							</CardContent>
						</Card>
					</div>

					{/* Right Column - Sidebar (1/3 width) */}
					<div className="space-y-4">
						{/* Status Card */}
						<Card>
							<CardHeader>
								<CardTitle className="text-sm">Run Status</CardTitle>
							</CardHeader>
							<CardContent>
								<div className="flex flex-col items-center justify-center py-4 text-center">
									<AgentRunStatusIcon status={run.status} />
									<div className="mt-4">
										<AgentRunStatusBadge status={run.status} />
									</div>
								</div>
							</CardContent>
						</Card>

						{/* Run Details */}
						<Card>
							<CardHeader className="pb-3">
								<CardTitle className="text-sm">Run Details</CardTitle>
							</CardHeader>
							<CardContent className="space-y-3 text-sm">
								<div className="flex items-center justify-between">
									<span className="text-muted-foreground flex items-center gap-1.5">
										<Zap className="h-3.5 w-3.5" />
										Iterations
									</span>
									<span className="font-medium">
										{run.iterations_used}
										{run.budget_max_iterations && (
											<span className="text-muted-foreground font-normal">
												{" "}/ {run.budget_max_iterations}
											</span>
										)}
									</span>
								</div>
								<div className="flex items-center justify-between">
									<span className="text-muted-foreground flex items-center gap-1.5">
										<Cpu className="h-3.5 w-3.5" />
										Tokens
									</span>
									<span className="font-medium">
										{run.tokens_used.toLocaleString()}
									</span>
								</div>
								<div className="flex items-center justify-between">
									<span className="text-muted-foreground flex items-center gap-1.5">
										<Clock className="h-3.5 w-3.5" />
										Duration
									</span>
									<span className="font-medium">
										{run.duration_ms != null
											? `${(run.duration_ms / 1000).toFixed(1)}s`
											: "\u2014"}
									</span>
								</div>
								<div className="flex items-center justify-between">
									<span className="text-muted-foreground flex items-center gap-1.5">
										<MessageSquare className="h-3.5 w-3.5" />
										Model
									</span>
									<span className="font-medium font-mono text-xs">
										{run.llm_model || "default"}
									</span>
								</div>
								<div className="flex items-center justify-between">
									<span className="text-muted-foreground flex items-center gap-1.5">
										<Hash className="h-3.5 w-3.5" />
										Trigger
									</span>
									<span className="font-medium">
										{run.trigger_type}
									</span>
								</div>
								{run.trigger_source && (
									<div className="flex items-center justify-between">
										<span className="text-muted-foreground flex items-center gap-1.5">
											<Zap className="h-3.5 w-3.5" />
											Source
										</span>
										<span className="font-medium truncate ml-2 max-w-[180px]" title={run.trigger_source}>
											{run.trigger_source}
										</span>
									</div>
								)}

								{/* Timestamps */}
								<div className="border-t pt-3 space-y-2">
									{run.started_at && (
										<div className="flex items-center justify-between">
											<span className="text-muted-foreground flex items-center gap-1.5">
												<CalendarClock className="h-3.5 w-3.5" />
												Started
											</span>
											<span className="text-xs">
												{new Date(run.started_at).toLocaleString()}
											</span>
										</div>
									)}
									{run.completed_at && (
										<div className="flex items-center justify-between">
											<span className="text-muted-foreground flex items-center gap-1.5">
												<CalendarClock className="h-3.5 w-3.5" />
												Completed
											</span>
											<span className="text-xs">
												{new Date(run.completed_at).toLocaleString()}
											</span>
										</div>
									)}
								</div>

								{/* Caller */}
								{run.caller_email && (
									<div className="border-t pt-3">
										<div className="flex items-center justify-between">
											<span className="text-muted-foreground flex items-center gap-1.5">
												<User className="h-3.5 w-3.5" />
												Caller
											</span>
											<span className="text-xs truncate ml-2 max-w-[180px]">
												{run.caller_name || run.caller_email}
											</span>
										</div>
									</div>
								)}
							</CardContent>
						</Card>

						{/* AI Usage */}
						{run.ai_usage && run.ai_usage.length > 0 && (
							<Card>
								<CardContent className="pt-4">
									<Collapsible
										open={isAiUsageOpen}
										onOpenChange={setIsAiUsageOpen}
									>
										<div className="flex items-center justify-between">
											<div className="flex items-center gap-2">
												<Sparkles className="h-4 w-4 text-purple-500" />
												<span className="text-sm font-medium">
													AI Usage
												</span>
												<Badge
													variant="secondary"
													className="text-xs"
												>
													{run.ai_totals?.call_count || run.ai_usage.length}{" "}
													{(run.ai_totals?.call_count || run.ai_usage.length) === 1
														? "call"
														: "calls"}
												</Badge>
											</div>
											<CollapsibleTrigger asChild>
												<Button variant="ghost" size="sm">
													<ChevronDown
														className={`h-4 w-4 transition-transform duration-200 ${
															isAiUsageOpen ? "rotate-180" : ""
														}`}
													/>
												</Button>
											</CollapsibleTrigger>
										</div>
										{run.ai_totals && (
											<p className="mt-1 text-xs text-muted-foreground">
												Total:{" "}
												{formatNumber(run.ai_totals.total_input_tokens)} in /{" "}
												{formatNumber(run.ai_totals.total_output_tokens)} out tokens
												{run.ai_totals.total_cost &&
													run.ai_totals.total_cost !== "0" &&
													` | ${formatCost(run.ai_totals.total_cost)}`}
											</p>
										)}
										<CollapsibleContent>
											<div className="mt-3 overflow-x-auto">
												<table className="w-full text-xs">
													<thead>
														<tr className="border-b">
															<th className="text-left py-2 pr-2 font-medium text-muted-foreground">Provider</th>
															<th className="text-left py-2 pr-2 font-medium text-muted-foreground">Model</th>
															<th className="text-right py-2 pr-2 font-medium text-muted-foreground">In</th>
															<th className="text-right py-2 pr-2 font-medium text-muted-foreground">Out</th>
															<th className="text-right py-2 pr-2 font-medium text-muted-foreground">Cost</th>
															<th className="text-right py-2 font-medium text-muted-foreground">Time</th>
														</tr>
													</thead>
													<tbody>
														{run.ai_usage.map((usage, index) => (
															<tr key={index} className="border-b last:border-0">
																<td className="py-2 pr-2 capitalize">{usage.provider}</td>
																<td className="py-2 pr-2 font-mono text-muted-foreground">
																	{usage.model.length > 20
																		? `${usage.model.substring(0, 18)}...`
																		: usage.model}
																</td>
																<td className="py-2 pr-2 text-right font-mono">{formatNumber(usage.input_tokens)}</td>
																<td className="py-2 pr-2 text-right font-mono">{formatNumber(usage.output_tokens)}</td>
																<td className="py-2 pr-2 text-right font-mono">{formatCost(usage.cost)}</td>
																<td className="py-2 text-right font-mono">{formatDuration(usage.duration_ms)}</td>
															</tr>
														))}
													</tbody>
													{run.ai_totals && (
														<tfoot>
															<tr className="bg-muted/50 font-medium">
																<td colSpan={2} className="py-2 pr-2">Total</td>
																<td className="py-2 pr-2 text-right font-mono">{formatNumber(run.ai_totals.total_input_tokens)}</td>
																<td className="py-2 pr-2 text-right font-mono">{formatNumber(run.ai_totals.total_output_tokens)}</td>
																<td className="py-2 pr-2 text-right font-mono">{formatCost(run.ai_totals.total_cost)}</td>
																<td className="py-2 text-right font-mono">{formatDuration(run.ai_totals.total_duration_ms)}</td>
															</tr>
														</tfoot>
													)}
												</table>
											</div>
										</CollapsibleContent>
									</Collapsible>
								</CardContent>
							</Card>
						)}

						{/* Input */}
						{run.input && (
							<Card>
								<CardHeader className="pb-3">
									<CardTitle className="text-sm">Input</CardTitle>
								</CardHeader>
								<CardContent>
									{typeof run.input === "object" &&
									run.input !== null ? (
										<VariablesTreeView
											data={
												run.input as Record<
													string,
													unknown
												>
											}
										/>
									) : (
										<pre className="text-xs font-mono whitespace-pre-wrap">
											{String(run.input)}
										</pre>
									)}
								</CardContent>
							</Card>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}
