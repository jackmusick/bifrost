/**
 * Variable Preview Panel for App Builder Editor
 *
 * Displays available variables and context values that can be used in expressions.
 * Provides a way to browse and insert variable paths into property fields.
 */

import { useState, useMemo } from "react";
import {
	ChevronRight,
	ChevronDown,
	Copy,
	Check,
	Variable,
	User,
	Database,
	Workflow,
	FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type {
	ExpressionContext,
	PageDefinition,
} from "@/lib/app-builder-types";

interface VariablePreviewProps {
	/** Current expression context (for preview mode) */
	context?: Partial<ExpressionContext>;
	/** Current page definition */
	page?: PageDefinition;
	/** Whether we're in row action context (shows row.* variables) */
	isRowContext?: boolean;
	/** Callback when a variable path is clicked (for insertion) */
	onInsertVariable?: (path: string) => void;
	/** Additional CSS classes */
	className?: string;
}

interface VariableSectionProps {
	title: string;
	icon: React.ReactNode;
	paths: { path: string; type: string; description?: string }[];
	defaultOpen?: boolean;
	onInsertVariable?: (path: string) => void;
}

/**
 * Copy button with feedback
 */
function CopyButton({ value }: { value: string }) {
	const [copied, setCopied] = useState(false);

	const handleCopy = async () => {
		await navigator.clipboard.writeText(`{{ ${value} }}`);
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	};

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					variant="ghost"
					size="icon-sm"
					className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
					onClick={handleCopy}
				>
					{copied ? (
						<Check className="h-3 w-3 text-green-500" />
					) : (
						<Copy className="h-3 w-3" />
					)}
				</Button>
			</TooltipTrigger>
			<TooltipContent side="left">
				{copied ? "Copied!" : "Copy expression"}
			</TooltipContent>
		</Tooltip>
	);
}

/**
 * Collapsible section for a category of variables
 */
function VariableSection({
	title,
	icon,
	paths,
	defaultOpen = true,
	onInsertVariable,
}: VariableSectionProps) {
	const [isOpen, setIsOpen] = useState(defaultOpen);

	return (
		<Collapsible
			open={isOpen}
			onOpenChange={setIsOpen}
			className="border-b last:border-b-0"
		>
			<CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2 hover:bg-muted/50 transition-colors">
				{isOpen ? (
					<ChevronDown className="h-4 w-4 text-muted-foreground" />
				) : (
					<ChevronRight className="h-4 w-4 text-muted-foreground" />
				)}
				{icon}
				<span className="text-sm font-medium">{title}</span>
				<span className="ml-auto text-xs text-muted-foreground">
					{paths.length}
				</span>
			</CollapsibleTrigger>
			<CollapsibleContent>
				<div className="px-2 pb-2">
					{paths.map(({ path, type, description }) => (
						<div
							key={path}
							className="group flex items-center justify-between rounded px-2 py-1 hover:bg-muted/50 cursor-pointer"
							onClick={() => onInsertVariable?.(path)}
						>
							<div className="flex-1 min-w-0">
								<code className="text-xs font-mono text-primary break-all">
									{path}
								</code>
								<div className="flex items-center gap-2 mt-0.5">
									<span className="text-[10px] text-muted-foreground font-medium uppercase">
										{type}
									</span>
									{description && (
										<span className="text-[10px] text-muted-foreground truncate">
											• {description}
										</span>
									)}
								</div>
							</div>
							<CopyButton value={path} />
						</div>
					))}
					{paths.length === 0 && (
						<p className="text-xs text-muted-foreground px-2 py-2 italic">
							No variables available
						</p>
					)}
				</div>
			</CollapsibleContent>
		</Collapsible>
	);
}

/**
 * Variable Preview Panel
 *
 * Shows available variables organized by category with copy functionality.
 */
export function VariablePreview({
	context,
	page,
	isRowContext = false,
	onInsertVariable,
	className,
}: VariablePreviewProps) {
	// Build user variables
	const userPaths = useMemo(() => {
		const paths: { path: string; type: string; description?: string }[] = [
			{ path: "user.id", type: "string", description: "User ID" },
			{ path: "user.name", type: "string", description: "Display name" },
			{
				path: "user.email",
				type: "string",
				description: "Email address",
			},
			{ path: "user.role", type: "string", description: "User role" },
		];
		return paths;
	}, []);

	// Build field variables from page inputs
	const fieldPaths = useMemo(() => {
		const paths: { path: string; type: string; description?: string }[] =
			[];
		// If we have context with field values, show them
		const fieldData = context?.field;
		if (fieldData) {
			for (const [key] of Object.entries(fieldData)) {
				paths.push({
					path: `field.${key}`,
					type: "any",
					description: "Input value",
				});
			}
		}
		// Add hint for input components
		paths.push({
			path: "field.<fieldId>",
			type: "any",
			description: "Input field value (use fieldId from input component)",
		});
		return paths;
	}, [context]);

	// Build data source variables
	const dataPaths = useMemo(() => {
		const paths: { path: string; type: string; description?: string }[] =
			[];
		const dataSources = page?.dataSources;
		if (dataSources) {
			for (const ds of dataSources) {
				paths.push({
					path: `data.${ds.id}`,
					type: ds.type === "static" ? "any" : "array|object",
					description: `Data source (${ds.type})`,
				});
			}
		}
		// Add hint
		if (paths.length === 0) {
			paths.push({
				path: "data.<dataSourceId>",
				type: "any",
				description: "Data from configured data sources",
			});
		}
		return paths;
	}, [page]);

	// Build workflow result variables
	const workflowPaths = useMemo(() => {
		const paths: { path: string; type: string; description?: string }[] = [
			{
				path: "workflow.executionId",
				type: "string",
				description: "Execution ID",
			},
			{
				path: "workflow.status",
				type: "string",
				description: "pending|running|completed|failed",
			},
			{
				path: "workflow.result",
				type: "any",
				description: "Workflow output data",
			},
			{
				path: "workflow.error",
				type: "string",
				description: "Error message (if failed)",
			},
		];
		return paths;
	}, []);

	// Build row context variables (for table actions)
	const rowPaths = useMemo(() => {
		if (!isRowContext) return [];
		return [
			{
				path: "row",
				type: "object",
				description: "Current row data object",
			},
			{
				path: "row.<fieldName>",
				type: "any",
				description:
					"Access row field by name (e.g., row.id, row.name)",
			},
		];
	}, [isRowContext]);

	// Build page variables
	const pagePaths = useMemo(() => {
		const paths: { path: string; type: string; description?: string }[] =
			[];
		const pageVariables = page?.variables;
		if (pageVariables) {
			for (const [key] of Object.entries(pageVariables)) {
				paths.push({
					path: `variables.${key}`,
					type: "any",
					description: "Page variable",
				});
			}
		}
		// Add hint
		paths.push({
			path: "variables.<name>",
			type: "any",
			description: "Page-level variables set via set-variable action",
		});
		return paths;
	}, [page]);

	// Build query params
	const queryPaths = useMemo(() => {
		return [
			{
				path: "query.<param>",
				type: "string",
				description: "URL query parameter (e.g., query.id)",
			},
			{
				path: "params.<param>",
				type: "string",
				description: "Route parameter (e.g., params.userId)",
			},
		];
	}, []);

	return (
		<div className={cn("flex flex-col h-full", className)}>
			<div className="flex items-center gap-2 px-3 py-2 border-b">
				<Variable className="h-4 w-4 text-muted-foreground" />
				<h3 className="text-sm font-semibold">Available Variables</h3>
			</div>
			<p className="px-3 py-2 text-xs text-muted-foreground border-b">
				Click a variable to copy its expression. Use{" "}
				<code className="bg-muted px-1 rounded">{"{{ path }}"}</code>{" "}
				syntax in any text field.
			</p>
			<div className="flex-1 overflow-y-auto">
				<VariableSection
					title="User"
					icon={<User className="h-4 w-4 text-blue-500" />}
					paths={userPaths}
					onInsertVariable={onInsertVariable}
				/>
				{isRowContext && (
					<VariableSection
						title="Row (Table Context)"
						icon={<FileText className="h-4 w-4 text-orange-500" />}
						paths={rowPaths}
						onInsertVariable={onInsertVariable}
					/>
				)}
				<VariableSection
					title="Form Fields"
					icon={<FileText className="h-4 w-4 text-green-500" />}
					paths={fieldPaths}
					defaultOpen={false}
					onInsertVariable={onInsertVariable}
				/>
				<VariableSection
					title="Data Sources"
					icon={<Database className="h-4 w-4 text-purple-500" />}
					paths={dataPaths}
					defaultOpen={false}
					onInsertVariable={onInsertVariable}
				/>
				<VariableSection
					title="Workflow Result"
					icon={<Workflow className="h-4 w-4 text-amber-500" />}
					paths={workflowPaths}
					defaultOpen={false}
					onInsertVariable={onInsertVariable}
				/>
				<VariableSection
					title="Page Variables"
					icon={<Variable className="h-4 w-4 text-cyan-500" />}
					paths={pagePaths}
					defaultOpen={false}
					onInsertVariable={onInsertVariable}
				/>
				<VariableSection
					title="URL Parameters"
					icon={<FileText className="h-4 w-4 text-gray-500" />}
					paths={queryPaths}
					defaultOpen={false}
					onInsertVariable={onInsertVariable}
				/>
			</div>
		</div>
	);
}

export default VariablePreview;
