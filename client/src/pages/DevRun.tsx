import { useState, useEffect, useCallback, useRef } from "react";
import {
	Terminal,
	Play,
	RefreshCw,
	Loader2,
	CheckCircle2,
	AlertCircle,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { webSocketService, type DevRunStateUpdate } from "@/services/websocket";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
	getDevRunState,
	continueDevRun,
	type DevRunStateResponse,
	type WorkflowParameterInfo,
} from "@/services/dev-run";

/**
 * Render a form field based on parameter type
 */
function ParameterField({
	param,
	value,
	onChange,
	error,
}: {
	param: WorkflowParameterInfo;
	value: unknown;
	onChange: (value: unknown) => void;
	error?: string;
}) {
	const label = param.label || param.name;
	const id = `param-${param.name}`;

	switch (param.type) {
		case "bool":
			return (
				<div className="flex flex-row items-center justify-between rounded-lg border p-3">
					<div className="space-y-0.5">
						<Label htmlFor={id} className="font-medium">
							{label}
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
					</div>
					<Checkbox
						id={id}
						checked={Boolean(value)}
						onCheckedChange={(checked) => onChange(checked)}
					/>
				</div>
			);

		case "int":
		case "float":
			return (
				<div className="space-y-2">
					<Label htmlFor={id}>
						{label}
						{param.required && (
							<span className="text-destructive ml-1">*</span>
						)}
					</Label>
					<Input
						id={id}
						type="number"
						step={param.type === "float" ? "any" : "1"}
						value={
							value !== undefined && value !== null
								? String(value)
								: ""
						}
						onChange={(e) => {
							const val = e.target.value;
							if (val === "") {
								onChange(param.default_value ?? undefined);
							} else {
								onChange(
									param.type === "int"
										? parseInt(val)
										: parseFloat(val),
								);
							}
						}}
						placeholder={
							param.default_value !== null
								? `Default: ${param.default_value}`
								: undefined
						}
					/>
					{error && (
						<p className="text-sm text-destructive">{error}</p>
					)}
				</div>
			);

		case "json":
		case "list":
		case "dict":
			return (
				<div className="space-y-2">
					<Label htmlFor={id}>
						{label}{" "}
						<span className="text-muted-foreground text-xs">
							({param.type})
						</span>
						{param.required && (
							<span className="text-destructive ml-1">*</span>
						)}
					</Label>
					<textarea
						id={id}
						className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
						value={
							typeof value === "string"
								? value
								: JSON.stringify(value, null, 2) || ""
						}
						onChange={(e) => {
							try {
								onChange(JSON.parse(e.target.value));
							} catch {
								// Keep as string if not valid JSON yet
								onChange(e.target.value);
							}
						}}
						placeholder={
							param.type === "list"
								? '["item1", "item2"]'
								: '{"key": "value"}'
						}
					/>
					{error && (
						<p className="text-sm text-destructive">{error}</p>
					)}
				</div>
			);

		default: // string
			return (
				<div className="space-y-2">
					<Label htmlFor={id}>
						{label}
						{param.required && (
							<span className="text-destructive ml-1">*</span>
						)}
					</Label>
					<Input
						id={id}
						type="text"
						value={
							value !== undefined && value !== null
								? String(value)
								: ""
						}
						onChange={(e) => onChange(e.target.value || undefined)}
						placeholder={
							param.default_value !== null
								? `Default: ${param.default_value}`
								: undefined
						}
					/>
					{error && (
						<p className="text-sm text-destructive">{error}</p>
					)}
				</div>
			);
	}
}

/**
 * DevRun page for CLI<->Web workflow parameter input
 */
export function DevRun() {
	const { user } = useAuth();
	const [state, setState] = useState<DevRunStateResponse | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(
		null,
	);
	const [params, setParams] = useState<Record<string, unknown>>({});
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [wasSubmitted, setWasSubmitted] = useState(false);
	const initialFetchDone = useRef(false);

	// Handle state update from websocket or initial fetch
	const handleStateUpdate = useCallback(
		(data: DevRunStateUpdate | DevRunStateResponse | null) => {
			setState(data as DevRunStateResponse | null);
			setError(null);

			if (data) {
				// Initialize selected workflow (only if not already selected)
				if (!selectedWorkflow) {
					if (data.selected_workflow) {
						setSelectedWorkflow(data.selected_workflow);
					} else if (data.workflows.length === 1) {
						setSelectedWorkflow(data.workflows[0].name);
					}
				}
			}

			setIsLoading(false);
		},
		[selectedWorkflow],
	);

	// Initial fetch on mount
	const fetchState = useCallback(async () => {
		try {
			const data = await getDevRunState();
			handleStateUpdate(data);
		} catch (err) {
			setError(
				err instanceof Error
					? err.message
					: "Failed to load dev run state",
			);
			setIsLoading(false);
		}
	}, [handleStateUpdate]);

	// Subscribe to websocket updates
	useEffect(() => {
		if (!user?.id) return;

		// Initial fetch
		if (!initialFetchDone.current) {
			initialFetchDone.current = true;
			fetchState();
		}

		// Subscribe to devrun channel for this user
		const channel = `devrun:${user.id}`;
		webSocketService.connect([channel]);

		// Listen for state updates via websocket
		const unsubscribe = webSocketService.onDevRunState((wsState) => {
			handleStateUpdate(wsState);
		});

		return () => {
			unsubscribe();
			webSocketService.unsubscribe(channel);
		};
	}, [user?.id, fetchState, handleStateUpdate]);

	// Get current workflow
	const currentWorkflow = state?.workflows.find(
		(w) => w.name === selectedWorkflow,
	);

	// Initialize params with defaults when workflow changes
	useEffect(() => {
		if (currentWorkflow) {
			const defaults: Record<string, unknown> = {};
			for (const param of currentWorkflow.parameters) {
				if (
					param.default_value !== null &&
					param.default_value !== undefined
				) {
					defaults[param.name] = param.default_value;
				}
			}
			setParams((prev) => ({ ...defaults, ...prev }));
		}
	}, [currentWorkflow]);

	// Handle continue
	const handleContinue = async () => {
		if (!selectedWorkflow) {
			toast.error("Please select a workflow");
			return;
		}

		// Validate required params
		const workflow = state?.workflows.find(
			(w) => w.name === selectedWorkflow,
		);
		if (workflow) {
			for (const param of workflow.parameters) {
				if (
					param.required &&
					(params[param.name] === undefined ||
						params[param.name] === "")
				) {
					toast.error(
						`Parameter "${param.label || param.name}" is required`,
					);
					return;
				}
			}
		}

		setIsSubmitting(true);
		try {
			await continueDevRun({
				workflow_name: selectedWorkflow,
				params,
			});
			setWasSubmitted(true);
			toast.success("Workflow execution started");
		} catch (err) {
			toast.error(
				err instanceof Error ? err.message : "Failed to continue",
			);
		} finally {
			setIsSubmitting(false);
		}
	};

	// Loading state
	if (isLoading) {
		return (
			<div className="space-y-6">
				<div>
					<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
						Dev Run
					</h1>
					<p className="leading-7 mt-2 text-muted-foreground">
						Local workflow execution with web-based parameter input
					</p>
				</div>
				<Card>
					<CardContent className="pt-6 space-y-4">
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
						<Skeleton className="h-10 w-full" />
					</CardContent>
				</Card>
			</div>
		);
	}

	// Error state
	if (error) {
		return (
			<div className="space-y-6">
				<div>
					<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
						Dev Run
					</h1>
					<p className="leading-7 mt-2 text-muted-foreground">
						Local workflow execution with web-based parameter input
					</p>
				</div>
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertTitle>Error</AlertTitle>
					<AlertDescription>{error}</AlertDescription>
				</Alert>
				<Button onClick={fetchState} variant="outline">
					<RefreshCw className="mr-2 h-4 w-4" />
					Retry
				</Button>
			</div>
		);
	}

	// No active session state
	if (!state) {
		return (
			<div className="space-y-6">
				<div>
					<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
						Dev Run
					</h1>
					<p className="leading-7 mt-2 text-muted-foreground">
						Local workflow execution with web-based parameter input
					</p>
				</div>
				<Card>
					<CardContent className="pt-6">
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<Terminal className="h-16 w-16 text-muted-foreground mb-4" />
							<h3 className="text-lg font-semibold mb-2">
								No Active Session
							</h3>
							<p className="text-muted-foreground mb-4 max-w-md">
								Run{" "}
								<code className="bg-muted px-2 py-1 rounded text-sm">
									bifrost run &lt;file&gt;
								</code>{" "}
								in your terminal to start a workflow execution
								session.
							</p>
							<pre className="bg-muted p-4 rounded-lg text-sm text-left overflow-x-auto max-w-full">
								<code>
									{`# Example usage
bifrost run my_workflows.py

# With specific workflow
bifrost run my_workflows.py --workflow onboard_user`}
								</code>
							</pre>
						</div>
					</CardContent>
				</Card>
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<div>
				<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
					Dev Run
				</h1>
				<p className="leading-7 mt-2 text-muted-foreground">
					Local workflow execution with web-based parameter input
				</p>
			</div>

			{/* File path indicator */}
			<Alert>
				<Terminal className="h-4 w-4" />
				<AlertTitle>Active Session</AlertTitle>
				<AlertDescription className="font-mono text-sm break-all">
					{state.file_path}
				</AlertDescription>
			</Alert>

			{/* Pending state indicator */}
			{state.pending && (
				<Alert>
					<Loader2 className="h-4 w-4 animate-spin" />
					<AlertTitle>Execution Pending</AlertTitle>
					<AlertDescription>
						Waiting for CLI to pick up the execution...
					</AlertDescription>
				</Alert>
			)}

			{/* Submitted state indicator */}
			{wasSubmitted && !state.pending && (
				<Alert>
					<CheckCircle2 className="h-4 w-4 text-green-500" />
					<AlertTitle>Execution Sent</AlertTitle>
					<AlertDescription>
						Waiting for next Continue...
					</AlertDescription>
				</Alert>
			)}

			<Card>
				<CardHeader>
					<CardTitle>Workflow Parameters</CardTitle>
					<CardDescription>
						{state.workflows.length === 1
							? `Configure parameters for ${state.workflows[0].name}`
							: "Select a workflow and configure its parameters"}
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{/* Workflow selector (if multiple) */}
					{state.workflows.length > 1 && (
						<div className="space-y-2">
							<Label htmlFor="workflow-select">Workflow</Label>
							<Select
								value={selectedWorkflow || ""}
								onValueChange={setSelectedWorkflow}
							>
								<SelectTrigger id="workflow-select">
									<SelectValue placeholder="Select a workflow" />
								</SelectTrigger>
								<SelectContent>
									{state.workflows.map((w) => (
										<SelectItem key={w.name} value={w.name}>
											<div className="flex flex-col items-start">
												<span>{w.name}</span>
												{w.description && (
													<span className="text-xs text-muted-foreground">
														{w.description}
													</span>
												)}
											</div>
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>
					)}

					{/* Workflow description */}
					{currentWorkflow?.description && (
						<p className="text-sm text-muted-foreground">
							{currentWorkflow.description}
						</p>
					)}

					{/* Parameter fields */}
					{currentWorkflow &&
						currentWorkflow.parameters.length > 0 && (
							<div className="space-y-4">
								{currentWorkflow.parameters.map((param) => (
									<ParameterField
										key={param.name}
										param={param}
										value={params[param.name]}
										onChange={(value) =>
											setParams((prev) => ({
												...prev,
												[param.name]: value,
											}))
										}
									/>
								))}
							</div>
						)}

					{/* No parameters message */}
					{currentWorkflow &&
						currentWorkflow.parameters.length === 0 && (
							<p className="text-sm text-muted-foreground">
								This workflow has no parameters.
							</p>
						)}

					{/* Continue button */}
					<Button
						onClick={handleContinue}
						disabled={!selectedWorkflow || isSubmitting}
						className="w-full"
						size="lg"
					>
						{isSubmitting ? (
							<>
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								Sending...
							</>
						) : (
							<>
								<Play className="mr-2 h-4 w-4" />
								Continue
							</>
						)}
					</Button>
				</CardContent>
			</Card>
		</div>
	);
}
