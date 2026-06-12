/**
 * Unified Workflow Selector Component
 *
 * A reusable component for selecting workflows with org scope filtering.
 * Supports both simple Select (default) and searchable Combobox modes.
 *
 * Used consistently in forms, apps, agents, and anywhere workflows are selected.
 */

import { useEffect, useMemo, useState } from "react";
import {
	AlertTriangle,
	ChevronsUpDown,
	Globe,
	Loader2,
	X,
} from "lucide-react";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { $api } from "@/lib/api-client";
import { fetchWorkflowRolesBatch } from "@/hooks/useWorkflowRoles";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type ExecutableType = components["schemas"]["ExecutableType"];

/**
 * Extended workflow metadata with role information
 */
interface WorkflowWithRoleStatus extends WorkflowMetadata {
	roleIds?: string[];
	hasMismatch?: boolean;
	missingRoleNames?: string[];
}

export interface WorkflowSelectorProps {
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
	/** Whether the selector is disabled */
	disabled?: boolean;
	/**
	 * Organization scope filter:
	 * - undefined: Use current user's org + global (default)
	 * - "all": Show all workflows (platform admins only)
	 * - "global": Show only global workflows
	 * - UUID string: Show specific org + global
	 */
	scope?: string;
	/**
	 * Filter by workflow type:
	 * - undefined: Show all types
	 * - "workflow": Only standard workflows
	 * - "tool": Only AI agent tools
	 * - "data_provider": Only data providers
	 */
	type?: ExecutableType;
	/**
	 * Variant for the selector:
	 * - "select": Simple dropdown (default, good for small lists)
	 * - "combobox": Searchable dropdown (better for many workflows)
	 */
	variant?: "select" | "combobox";
	/**
	 * Show organization badge on org-scoped workflows
	 */
	showOrgBadge?: boolean;
	/**
	 * Show role badges and mismatch warnings on workflows.
	 * When enabled, fetches roles for each workflow and displays them.
	 */
	showRoleBadges?: boolean;
	/**
	 * Entity role IDs to compare against workflow roles for mismatch detection.
	 * Only used when showRoleBadges is true.
	 */
	entityRoleIds?: string[];
	/**
	 * Map of role ID to role name for displaying role names in warnings.
	 * Only used when showRoleBadges is true and entityRoleIds is provided.
	 */
	entityRoleNames?: Record<string, string>;
}

/**
 * Unified Workflow Selector
 *
 * @example
 * // Simple select (default)
 * <WorkflowSelector
 *   value={workflowId}
 *   onChange={setWorkflowId}
 *   placeholder="Select a workflow"
 * />
 *
 * @example
 * // Searchable combobox with scope
 * <WorkflowSelector
 *   value={workflowId}
 *   onChange={setWorkflowId}
 *   variant="combobox"
 *   scope={orgId}
 *   type="workflow"
 * />
 */
export function WorkflowSelector({
	value,
	onChange,
	placeholder = "Select a workflow",
	allowClear = true,
	className,
	disabled = false,
	scope,
	type,
	variant = "select",
	showOrgBadge = false,
	showRoleBadges = false,
	entityRoleIds = [],
	entityRoleNames = {},
}: WorkflowSelectorProps) {
	// State for workflow roles when showRoleBadges is enabled
	const [workflowRolesMap, setWorkflowRolesMap] = useState<
		Map<string, string[]>
	>(new Map());
	const [isLoadingRoles, setIsLoadingRoles] = useState(false);

	// Fetch workflows with scope and type filtering
	const {
		data: workflows,
		isLoading,
		error,
	} = $api.useQuery("get", "/api/workflows", {
		params: {
			query: {
				scope: scope,
				type: type,
			},
		},
	});

	// Fetch workflow roles when showRoleBadges is enabled
	useEffect(() => {
		if (!showRoleBadges || !workflows || workflows.length === 0) return;

		const loadRoles = async () => {
			setIsLoadingRoles(true);
			try {
				const workflowIds = workflows.map((w) => w.id);
				const roleMap = await fetchWorkflowRolesBatch(workflowIds);
				setWorkflowRolesMap(roleMap);
			} catch (error) {
				console.error("Failed to load workflow roles:", error);
			} finally {
				setIsLoadingRoles(false);
			}
		};

		loadRoles();
	}, [showRoleBadges, workflows]);

	// Enhance workflows with role status information
	const workflowsWithRoleStatus: WorkflowWithRoleStatus[] = useMemo(() => {
		if (!workflows) return [];

		return workflows.map((workflow) => {
			if (!showRoleBadges) return workflow;

			const roleIds = workflowRolesMap.get(workflow.id) || [];
			const roleIdSet = new Set(roleIds);

			// Find entity roles that are NOT in the workflow's roles
			const missingRoleIds = entityRoleIds.filter((id) => !roleIdSet.has(id));
			const missingRoleNames = missingRoleIds.map(
				(id) => entityRoleNames[id] || id.slice(0, 8),
			);
			const hasMismatch =
				missingRoleIds.length > 0 && entityRoleIds.length > 0;

			return {
				...workflow,
				roleIds,
				hasMismatch,
				missingRoleNames,
			};
		});
	}, [
		workflows,
		showRoleBadges,
		workflowRolesMap,
		entityRoleIds,
		entityRoleNames,
	]);

	// Sort workflows: global first (no org), then alphabetically by name
	const sortedWorkflows = useMemo(() => {
		return [...workflowsWithRoleStatus].sort((a, b) => {
			// Global workflows (no org_id) come first
			const aIsGlobal = !a.organization_id;
			const bIsGlobal = !b.organization_id;
			if (aIsGlobal !== bIsGlobal) {
				return aIsGlobal ? -1 : 1;
			}
			// Then sort alphabetically by name
			return (a.name ?? "").localeCompare(b.name ?? "");
		});
	}, [workflowsWithRoleStatus]);

	// Find the selected workflow for display
	const selectedWorkflow = useMemo(() => {
		if (!value || !sortedWorkflows) return null;
		return (
			sortedWorkflows.find((w) => w.id === value || w.name === value) ?? null
		);
	}, [value, sortedWorkflows]);

	if (isLoading || (showRoleBadges && isLoadingRoles)) {
		return (
			<div
				className={cn(
					"flex items-center gap-2 h-10 px-3 rounded-md bg-muted/50 ring-1 ring-foreground/5",
					className,
				)}
			>
				<Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
				<span className="text-sm text-muted-foreground">
					{isLoading ? "Loading workflows..." : "Loading role info..."}
				</span>
			</div>
		);
	}

	if (error) {
		return (
			<div
				className={cn(
					"flex items-center h-10 px-3 rounded-md bg-destructive/10 ring-1 ring-destructive/50",
					className,
				)}
			>
				<span className="text-sm text-destructive">
					Failed to load workflows
				</span>
			</div>
		);
	}

	// Render workflow item content (shared between Select and Combobox)
	const renderWorkflowItem = (workflow: WorkflowWithRoleStatus) => (
		<div className="flex flex-col gap-0.5">
			<div className="flex items-center gap-2">
				<span>{workflow.name}</span>
				{showOrgBadge && !workflow.organization_id && (
					<Badge
						variant="outline"
						className="text-xs px-1.5 py-0 h-5 text-muted-foreground"
					>
						<Globe className="h-3 w-3 mr-1" />
						Global
					</Badge>
				)}
				{/* Role mismatch warning */}
				{showRoleBadges && workflow.hasMismatch && (
					<Badge
						variant="outline"
						className="text-xs px-1.5 py-0 h-5 text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-700"
					>
						<AlertTriangle className="h-3 w-3 mr-1" />
						Missing roles
					</Badge>
				)}
			</div>
			{workflow.description && (
				<span className="text-xs text-muted-foreground truncate max-w-[250px]">
					{workflow.description}
				</span>
			)}
			{/* Show missing role names if there's a mismatch */}
			{showRoleBadges &&
				workflow.hasMismatch &&
				workflow.missingRoleNames &&
				workflow.missingRoleNames.length > 0 && (
					<span className="text-xs text-amber-600 dark:text-amber-400">
						Missing: {workflow.missingRoleNames.join(", ")}
					</span>
				)}
		</div>
	);

	// Combobox variant with search
	if (variant === "combobox") {
		return (
			<ComboboxWorkflowSelector
				value={value}
				onChange={onChange}
				placeholder={placeholder}
				allowClear={allowClear}
				className={className}
				disabled={disabled}
				workflows={sortedWorkflows}
				selectedWorkflow={selectedWorkflow}
				renderItem={renderWorkflowItem}
				showOrgBadge={showOrgBadge}
			/>
		);
	}

	// Select variant (default)
	return (
		<Select
			value={value ?? ""}
			onValueChange={(val) =>
				onChange(val === "__clear__" ? undefined : val)
			}
			disabled={disabled}
		>
			<SelectTrigger className={className}>
				<SelectValue placeholder={placeholder}>
					{selectedWorkflow ? (
						<div className="flex items-center gap-2">
							<span>{selectedWorkflow.name}</span>
							{showOrgBadge && !selectedWorkflow.organization_id && (
								<Badge
									variant="outline"
									className="text-xs px-1 py-0 h-4"
								>
									<Globe className="h-3 w-3" />
								</Badge>
							)}
							{selectedWorkflow.hasMismatch && (
								<AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
							)}
						</div>
					) : (
						placeholder
					)}
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
							{renderWorkflowItem(workflow)}
						</SelectItem>
					))
				)}
			</SelectContent>
		</Select>
	);
}

/**
 * Combobox variant with search capability
 */
function ComboboxWorkflowSelector({
	value,
	onChange,
	placeholder,
	allowClear,
	className,
	disabled,
	workflows,
	selectedWorkflow,
	renderItem,
	showOrgBadge,
}: {
	value: string | undefined;
	onChange: (value: string | undefined) => void;
	placeholder: string;
	allowClear: boolean;
	className?: string;
	disabled: boolean;
	workflows: WorkflowWithRoleStatus[];
	selectedWorkflow: WorkflowWithRoleStatus | null;
	renderItem: (workflow: WorkflowWithRoleStatus) => React.ReactNode;
	showOrgBadge: boolean;
}) {
	const [open, setOpen] = useState(false);

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>
				<Button
					variant="outline"
					role="combobox"
					aria-expanded={open}
					disabled={disabled}
					className={cn(
						"w-full justify-between font-normal",
						!value && "text-muted-foreground",
						className
					)}
				>
					{selectedWorkflow ? (
						<div className="flex items-center gap-2 truncate">
							<span className="truncate">
								{selectedWorkflow.name}
							</span>
							{showOrgBadge &&
								!selectedWorkflow.organization_id && (
									<Badge
										variant="outline"
										className="text-xs px-1 py-0 h-4"
									>
										<Globe className="h-3 w-3" />
									</Badge>
								)}
							{selectedWorkflow.hasMismatch && (
								<AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
							)}
						</div>
					) : (
						placeholder
					)}
					<div className="flex items-center gap-1 ml-2 shrink-0">
						{allowClear && value && (
							<X
								className="h-4 w-4 opacity-50 hover:opacity-100"
								onClick={(e) => {
									e.stopPropagation();
									onChange(undefined);
								}}
							/>
						)}
						<ChevronsUpDown className="h-4 w-4 opacity-50" />
					</div>
				</Button>
			</PopoverTrigger>
			<PopoverContent className="w-[400px] p-0" align="start">
				<Command>
					<CommandInput placeholder="Search workflows..." />
					<CommandList>
						<CommandEmpty>No workflows found.</CommandEmpty>
						<CommandGroup>
							{workflows.map((workflow) => (
								<CommandItem
									key={workflow.id}
									value={`${workflow.name} ${workflow.description ?? ""}`}
									data-checked={value === workflow.id}
									onSelect={() => {
										onChange(workflow.id);
										setOpen(false);
									}}
								>
									{renderItem(workflow)}
								</CommandItem>
							))}
						</CommandGroup>
					</CommandList>
				</Command>
			</PopoverContent>
		</Popover>
	);
}

export default WorkflowSelector;
