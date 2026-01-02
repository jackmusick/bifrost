/**
 * Workflow Picker Component
 *
 * Dropdown that fetches and displays available workflows for selection.
 * Used in Button actions, DataTable row actions, and anywhere a workflow needs to be selected.
 */

import { useMemo } from "react";
import { Loader2 } from "lucide-react";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useWorkflows } from "@/hooks/useWorkflows";

export interface WorkflowPickerProps {
	/** Currently selected workflow ID */
	value: string | undefined;
	/** Callback when workflow is selected */
	onChange: (workflowId: string | undefined) => void;
	/** Placeholder text */
	placeholder?: string;
	/** Whether to allow clearing the selection */
	allowClear?: boolean;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Workflow Picker
 *
 * Fetches available workflows and displays them in a searchable dropdown.
 *
 * @example
 * <WorkflowPicker
 *   value={props.workflowId}
 *   onChange={(id) => onChange({ props: { ...props, workflowId: id } })}
 *   placeholder="Select a workflow"
 * />
 */
export function WorkflowPicker({
	value,
	onChange,
	placeholder = "Select a workflow",
	allowClear = true,
	className,
}: WorkflowPickerProps) {
	const { data: workflows, isLoading, error } = useWorkflows();

	// Sort workflows alphabetically by name
	const sortedWorkflows = useMemo(() => {
		if (!workflows) return [];
		return [...workflows].sort((a, b) =>
			(a.name ?? "").localeCompare(b.name ?? ""),
		);
	}, [workflows]);

	// Find the selected workflow name for display
	const selectedWorkflow = useMemo(() => {
		if (!value || !workflows) return null;
		return workflows.find((w) => w.id === value || w.name === value);
	}, [value, workflows]);

	if (isLoading) {
		return (
			<div className="flex items-center gap-2 h-10 px-3 border rounded-md bg-muted/50">
				<Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
				<span className="text-sm text-muted-foreground">
					Loading workflows...
				</span>
			</div>
		);
	}

	if (error) {
		return (
			<div className="flex items-center h-10 px-3 border border-destructive/50 rounded-md bg-destructive/10">
				<span className="text-sm text-destructive">
					Failed to load workflows
				</span>
			</div>
		);
	}

	return (
		<Select
			value={value ?? ""}
			onValueChange={(val) =>
				onChange(val === "__clear__" ? undefined : val)
			}
		>
			<SelectTrigger className={className}>
				<SelectValue placeholder={placeholder}>
					{selectedWorkflow?.name ?? value ?? placeholder}
				</SelectValue>
			</SelectTrigger>
			<SelectContent>
				{allowClear && value && (
					<SelectItem
						value="__clear__"
						className="text-muted-foreground italic"
					>
						Clear selection
					</SelectItem>
				)}
				{sortedWorkflows.length === 0 ? (
					<div className="px-2 py-4 text-center text-sm text-muted-foreground">
						No workflows available
					</div>
				) : (
					sortedWorkflows.map((workflow) => (
						<SelectItem key={workflow.id} value={workflow.id}>
							<div className="flex flex-col">
								<span>{workflow.name}</span>
								{workflow.description && (
									<span className="text-xs text-muted-foreground truncate max-w-[250px]">
										{workflow.description}
									</span>
								)}
							</div>
						</SelectItem>
					))
				)}
			</SelectContent>
		</Select>
	);
}

export default WorkflowPicker;
