/**
 * Workflow Parameter Editor Component
 *
 * Renders workflow parameters based on workflow metadata.
 * Unlike WorkflowParametersForm, this allows dynamic expressions ({{ row.* }}, {{ field.* }}).
 * Used in App Builder for configuring workflow action parameters.
 */

import { useMemo } from "react";
import { Loader2, Info } from "lucide-react";
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
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useWorkflows } from "@/hooks/useWorkflows";
import type { components } from "@/lib/v1";

type WorkflowParameter = components["schemas"]["WorkflowParameter"];
type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

export interface WorkflowParameterEditorProps {
	/** Selected workflow ID */
	workflowId?: string;
	/** Current parameter values (string expressions or actual values) */
	value: Record<string, unknown>;
	/** Callback when values change */
	onChange: (value: Record<string, unknown>) => void;
	/** Whether this is for row actions (shows {{ row.* }} hints) */
	isRowAction?: boolean;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Get expression hint based on context
 */
function getExpressionHint(isRowAction: boolean): string {
	if (isRowAction) {
		return "Use {{ row.fieldName }} for row data, {{ variables.name }} for page variables";
	}
	return "Use {{ variables.name }} for page variables, {{ field.name }} for form inputs";
}

/**
 * Workflow Parameter Editor
 *
 * Shows workflow parameters with type-appropriate inputs that accept expressions.
 *
 * @example
 * <WorkflowParameterEditor
 *   workflowId="workflow-123"
 *   value={{ id: "{{ row.id }}", name: "Test" }}
 *   onChange={(params) => updateActionParams(params)}
 *   isRowAction={true}
 * />
 */
export function WorkflowParameterEditor({
	workflowId,
	value,
	onChange,
	isRowAction = false,
	className,
}: WorkflowParameterEditorProps) {
	const { data: workflows, isLoading, error } = useWorkflows();

	// Find the selected workflow
	const workflow = useMemo<WorkflowMetadata | undefined>(() => {
		if (!workflows || !workflowId) return undefined;
		return workflows.find((w) => w.id === workflowId);
	}, [workflows, workflowId]);

	const parameters = workflow?.parameters ?? [];

	const handleParameterChange = (paramName: string, paramValue: unknown) => {
		onChange({
			...value,
			[paramName]: paramValue,
		});
	};

	// No workflow selected
	if (!workflowId) {
		return (
			<div
				className={cn(
					"text-sm text-muted-foreground italic",
					className,
				)}
			>
				Select a workflow to configure parameters
			</div>
		);
	}

	// Loading state
	if (isLoading) {
		return (
			<div
				className={cn(
					"flex items-center gap-2 text-muted-foreground",
					className,
				)}
			>
				<Loader2 className="h-4 w-4 animate-spin" />
				<span className="text-sm">Loading workflow parameters...</span>
			</div>
		);
	}

	// Error state
	if (error) {
		return (
			<div className={cn("text-sm text-destructive", className)}>
				Failed to load workflow metadata
			</div>
		);
	}

	// Workflow not found
	if (!workflow) {
		return (
			<div
				className={cn(
					"text-sm text-muted-foreground italic",
					className,
				)}
			>
				Workflow not found
			</div>
		);
	}

	// No parameters
	if (parameters.length === 0) {
		return (
			<div
				className={cn(
					"text-sm text-muted-foreground italic",
					className,
				)}
			>
				This workflow has no parameters
			</div>
		);
	}

	const expressionHint = getExpressionHint(isRowAction);

	return (
		<div className={cn("space-y-4", className)}>
			{/* Expression hint */}
			<div className="flex items-start gap-2 rounded-md bg-muted/50 p-3 text-sm">
				<Info className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
				<span className="text-muted-foreground">{expressionHint}</span>
			</div>

			{/* Parameter inputs */}
			{parameters.map((param) => (
				<ParameterInput
					key={param.name}
					parameter={param}
					value={value[param.name]}
					onChange={(paramValue) =>
						handleParameterChange(param.name, paramValue)
					}
					isRowAction={isRowAction}
				/>
			))}
		</div>
	);
}

interface ParameterInputProps {
	parameter: WorkflowParameter;
	value: unknown;
	onChange: (value: unknown) => void;
	isRowAction: boolean;
}

/**
 * Individual parameter input renderer
 * All inputs accept string expressions ({{ }}) except checkboxes
 */
function ParameterInput({
	parameter,
	value,
	onChange,
	isRowAction,
}: ParameterInputProps) {
	const displayName = parameter.label || parameter.name;
	const stringValue =
		value !== undefined && value !== null ? String(value) : "";

	// Check if value looks like an expression
	const isExpression = typeof value === "string" && value.includes("{{");

	// Get placeholder based on context
	const getPlaceholder = (): string => {
		if (parameter.default_value != null) {
			return `Default: ${parameter.default_value}`;
		}
		if (isRowAction) {
			return `e.g., {{ row.${parameter.name} }}`;
		}
		return `Value or {{ expression }}`;
	};

	// For options (Literal types), show a select but allow manual expression entry
	if (parameter.options && parameter.options.length > 0) {
		return (
			<div className="space-y-2">
				<Label className="flex items-center gap-1.5">
					{displayName}
					{parameter.required && (
						<span className="text-destructive">*</span>
					)}
					{parameter.description && (
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger asChild>
									<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
								</TooltipTrigger>
								<TooltipContent>
									<p className="max-w-xs">
										{parameter.description}
									</p>
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
					)}
				</Label>

				{/* Show text input if value is an expression, otherwise show select */}
				{isExpression ? (
					<Input
						value={stringValue}
						onChange={(e) => onChange(e.target.value)}
						placeholder={getPlaceholder()}
						className="font-mono text-sm"
					/>
				) : (
					<Select
						value={stringValue}
						onValueChange={(newValue) => onChange(newValue)}
					>
						<SelectTrigger>
							<SelectValue placeholder={getPlaceholder()} />
						</SelectTrigger>
						<SelectContent>
							{parameter.options.map((option) => (
								<SelectItem
									key={option.value}
									value={option.value}
								>
									{option.label}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				)}

				<p className="text-xs text-muted-foreground">
					Type {"{{ expression }}"} to use a dynamic value
				</p>
			</div>
		);
	}

	// Boolean type - checkbox, but allow expression
	if (parameter.type === "bool") {
		return (
			<div className="space-y-2">
				{isExpression ? (
					// Expression mode - show text input
					<>
						<Label className="flex items-center gap-1.5">
							{displayName}
							{parameter.required && (
								<span className="text-destructive">*</span>
							)}
						</Label>
						<Input
							value={stringValue}
							onChange={(e) => onChange(e.target.value)}
							placeholder={getPlaceholder()}
							className="font-mono text-sm"
						/>
						<p className="text-xs text-muted-foreground">
							Clear to use checkbox instead
						</p>
					</>
				) : (
					// Checkbox mode
					<div className="flex flex-row items-center justify-between rounded-lg border p-3">
						<div className="space-y-0.5">
							<Label className="font-medium flex items-center gap-1.5">
								{displayName}
								{parameter.required && (
									<span className="text-destructive">*</span>
								)}
								{parameter.description && (
									<TooltipProvider>
										<Tooltip>
											<TooltipTrigger asChild>
												<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
											</TooltipTrigger>
											<TooltipContent>
												<p className="max-w-xs">
													{parameter.description}
												</p>
											</TooltipContent>
										</Tooltip>
									</TooltipProvider>
								)}
							</Label>
							<p className="text-xs text-muted-foreground">
								Type {"{{ expression }}"} in field below for
								dynamic value
							</p>
						</div>
						<Checkbox
							checked={value === true || value === "true"}
							onCheckedChange={(checked) => onChange(checked)}
						/>
					</div>
				)}
			</div>
		);
	}

	// Number types - text input that accepts expressions
	if (parameter.type === "int" || parameter.type === "float") {
		return (
			<div className="space-y-2">
				<Label className="flex items-center gap-1.5">
					{displayName}
					<span className="text-xs text-muted-foreground">
						({parameter.type})
					</span>
					{parameter.required && (
						<span className="text-destructive">*</span>
					)}
					{parameter.description && (
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger asChild>
									<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
								</TooltipTrigger>
								<TooltipContent>
									<p className="max-w-xs">
										{parameter.description}
									</p>
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
					)}
				</Label>
				<Input
					value={stringValue}
					onChange={(e) => {
						const val = e.target.value;
						// If it's an expression, keep as string
						if (val.includes("{{")) {
							onChange(val);
						} else if (val === "") {
							onChange(undefined);
						} else {
							// Try to parse as number
							const num =
								parameter.type === "int"
									? parseInt(val)
									: parseFloat(val);
							onChange(isNaN(num) ? val : num);
						}
					}}
					placeholder={getPlaceholder()}
				/>
			</div>
		);
	}

	// JSON/Dict types - textarea that accepts expressions
	if (
		parameter.type === "json" ||
		parameter.type === "dict" ||
		parameter.type === "list"
	) {
		return (
			<div className="space-y-2">
				<Label className="flex items-center gap-1.5">
					{displayName}
					<span className="text-xs text-muted-foreground">
						({parameter.type})
					</span>
					{parameter.required && (
						<span className="text-destructive">*</span>
					)}
					{parameter.description && (
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger asChild>
									<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
								</TooltipTrigger>
								<TooltipContent>
									<p className="max-w-xs">
										{parameter.description}
									</p>
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
					)}
				</Label>
				<textarea
					className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
					value={
						typeof value === "string"
							? value
							: value !== undefined
								? JSON.stringify(value, null, 2)
								: ""
					}
					onChange={(e) => {
						const val = e.target.value;
						// If it's an expression, keep as string
						if (val.includes("{{")) {
							onChange(val);
						} else if (val === "") {
							onChange(undefined);
						} else {
							// Try to parse as JSON
							try {
								onChange(JSON.parse(val));
							} catch {
								onChange(val);
							}
						}
					}}
					placeholder={
						parameter.type === "list"
							? '["item1", "item2"] or {{ row.items }}'
							: '{"key": "value"} or {{ row.data }}'
					}
				/>
			</div>
		);
	}

	// Default: string/text input
	return (
		<div className="space-y-2">
			<Label className="flex items-center gap-1.5">
				{displayName}
				{parameter.required && (
					<span className="text-destructive">*</span>
				)}
				{parameter.description && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
							</TooltipTrigger>
							<TooltipContent>
								<p className="max-w-xs">
									{parameter.description}
								</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
			</Label>
			<Input
				value={stringValue}
				onChange={(e) => onChange(e.target.value || undefined)}
				placeholder={getPlaceholder()}
			/>
		</div>
	);
}

export default WorkflowParameterEditor;
