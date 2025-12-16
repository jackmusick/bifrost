import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Play, Loader2 } from "lucide-react";
import type { components } from "@/lib/v1";
type WorkflowParameter = components["schemas"]["WorkflowParameter"];

interface WorkflowParametersFormProps {
	parameters: WorkflowParameter[];
	onExecute: (params: Record<string, unknown>) => void | Promise<void>;
	isExecuting?: boolean;
	showExecuteButton?: boolean;
	executeButtonText?: string;
	className?: string;
	// Controlled mode: pass values and onChange to lift state up
	values?: Record<string, unknown>;
	onChange?: (values: Record<string, unknown>) => void;
}

/**
 * Reusable form for entering workflow parameters
 * Used in both ExecuteWorkflow page and FormBuilder test launch workflow dialog
 */
export function WorkflowParametersForm({
	parameters,
	onExecute,
	isExecuting = false,
	showExecuteButton = true,
	executeButtonText = "Execute Workflow",
	className,
	values: controlledValues,
	onChange,
}: WorkflowParametersFormProps) {
	// Initialize internal state with default values (used when uncontrolled)
	const [internalValues, setInternalValues] = useState<
		Record<string, unknown>
	>(() =>
		parameters.reduce(
			(acc: Record<string, unknown>, param) => {
				acc[param.name] =
					param.default_value ?? (param.type === "bool" ? false : "");
				return acc;
			},
			{} as Record<string, unknown>,
		),
	);

	// Use controlled values if provided, otherwise use internal state
	const isControlled =
		controlledValues !== undefined && onChange !== undefined;
	const paramValues = isControlled ? controlledValues : internalValues;

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		await onExecute(paramValues);
	};

	const handleParameterChange = (paramName: string, value: unknown) => {
		const newValues = {
			...paramValues,
			[paramName]: value,
		};
		if (isControlled) {
			onChange(newValues);
		} else {
			setInternalValues(newValues);
		}
	};

	const renderParameterInput = (param: WorkflowParameter) => {
		const value = paramValues[param.name ?? ""];
		const displayName = param.label || param.name;

		switch (param.type) {
			case "bool":
				return (
					<div className="flex flex-row items-center justify-between rounded-lg border p-3">
						<div className="space-y-0.5">
							<Label
								htmlFor={param.name ?? "checkbox"}
								className="font-medium"
							>
								{displayName}
								{param.required && (
									<span className="text-destructive ml-1">
										*
									</span>
								)}
							</Label>
							{param.description && (
								<p className="text-xs text-muted-foreground">
									{param.description}
								</p>
							)}
						</div>
						<Checkbox
							id={param.name ?? "checkbox"}
							checked={!!value}
							onCheckedChange={(checked) =>
								handleParameterChange(param.name ?? "", checked)
							}
							disabled={isExecuting}
						/>
					</div>
				);

			case "int":
			case "float":
				return (
					<div className="space-y-2">
						<Label htmlFor={param.name ?? "number"}>
							{displayName}
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Input
							id={param.name ?? "number"}
							type="number"
							step={param.type === "float" ? "any" : "1"}
							value={(value as string | number | undefined) ?? ""}
							onChange={(e) =>
								handleParameterChange(
									param.name ?? "",
									e.target.value === ""
										? undefined
										: param.type === "int"
											? parseInt(e.target.value)
											: parseFloat(e.target.value),
								)
							}
							placeholder={
								param.default_value != null
									? `Default: ${param.default_value}`
									: undefined
							}
							required={param.required}
							disabled={isExecuting}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);

			case "json":
			case "dict":
				return (
					<div className="space-y-2">
						<Label htmlFor={param.name ?? "json"}>
							{displayName}{" "}
							<span className="text-muted-foreground text-xs">
								({param.type})
							</span>
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<textarea
							id={param.name ?? "json"}
							className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
							value={
								typeof value === "string"
									? value
									: JSON.stringify(value, null, 2) || ""
							}
							onChange={(e) => {
								try {
									handleParameterChange(
										param.name ?? "",
										JSON.parse(e.target.value),
									);
								} catch {
									// Keep as string if not valid JSON yet
									handleParameterChange(
										param.name ?? "",
										e.target.value,
									);
								}
							}}
							placeholder={
								param.type === "dict"
									? '{"key": "value"}'
									: "{}"
							}
							disabled={isExecuting}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);

			case "list":
				return (
					<div className="space-y-2">
						<Label htmlFor={param.name ?? "list"}>
							{displayName}{" "}
							<span className="text-muted-foreground text-xs">
								(list)
							</span>
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<textarea
							id={param.name ?? "list"}
							className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
							value={
								typeof value === "string"
									? value
									: JSON.stringify(value, null, 2) || ""
							}
							onChange={(e) => {
								try {
									handleParameterChange(
										param.name ?? "",
										JSON.parse(e.target.value),
									);
								} catch {
									// Keep as string if not valid JSON yet
									handleParameterChange(
										param.name ?? "",
										e.target.value,
									);
								}
							}}
							placeholder='["item1", "item2"]'
							disabled={isExecuting}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);

			default:
				// string, email
				return (
					<div className="space-y-2">
						<Label htmlFor={param.name ?? "text"}>
							{displayName}
							{param.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Input
							id={param.name ?? "text"}
							type={param.type === "email" ? "email" : "text"}
							value={(value as string) ?? ""}
							onChange={(e) =>
								handleParameterChange(
									param.name ?? "",
									e.target.value || undefined,
								)
							}
							placeholder={
								param.default_value != null
									? `Default: ${param.default_value}`
									: undefined
							}
							required={param.required}
							disabled={isExecuting}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);
		}
	};

	if (parameters.length === 0) {
		return (
			<div className={className}>
				<p className="text-sm text-muted-foreground">
					This workflow has no parameters.
				</p>
				{showExecuteButton && (
					<Button
						type="button"
						className="w-full mt-4"
						disabled={isExecuting}
						onClick={() => onExecute({})}
					>
						{isExecuting ? (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						) : (
							<Play className="mr-2 h-4 w-4" />
						)}
						{isExecuting ? "Executing..." : executeButtonText}
					</Button>
				)}
			</div>
		);
	}

	return (
		<form onSubmit={handleSubmit} className={className}>
			<div className="space-y-4">
				{parameters.map((param) => (
					<div key={param.name ?? "param"}>
						{renderParameterInput(param)}
					</div>
				))}
			</div>

			{showExecuteButton && (
				<Button
					type="submit"
					className="w-full mt-6"
					disabled={isExecuting}
				>
					{isExecuting ? (
						<Loader2 className="mr-2 h-4 w-4 animate-spin" />
					) : (
						<Play className="mr-2 h-4 w-4" />
					)}
					{isExecuting ? "Executing..." : executeButtonText}
				</Button>
			)}
		</form>
	);
}
