/**
 * EntityNode - Custom React Flow node for dependency graph
 *
 * Displays an entity (workflow, form, app, agent) as a styled card
 * with color-coding by entity type.
 */

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
	Workflow,
	FileText,
	LayoutGrid,
	Bot,
	type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type EntityType = "workflow" | "form" | "app" | "agent";

export interface EntityNodeData extends Record<string, unknown> {
	label: string;
	entityType: EntityType;
	orgId: string | null;
	isRoot: boolean;
}

// Color configuration for each entity type
const entityConfig: Record<
	EntityType,
	{
		bgColor: string;
		borderColor: string;
		textColor: string;
		Icon: LucideIcon;
		label: string;
	}
> = {
	workflow: {
		bgColor: "bg-blue-50 dark:bg-blue-950/50",
		borderColor: "border-blue-300 dark:border-blue-700",
		textColor: "text-blue-700 dark:text-blue-300",
		Icon: Workflow,
		label: "Workflow",
	},
	form: {
		bgColor: "bg-green-50 dark:bg-green-950/50",
		borderColor: "border-green-300 dark:border-green-700",
		textColor: "text-green-700 dark:text-green-300",
		Icon: FileText,
		label: "Form",
	},
	app: {
		bgColor: "bg-purple-50 dark:bg-purple-950/50",
		borderColor: "border-purple-300 dark:border-purple-700",
		textColor: "text-purple-700 dark:text-purple-300",
		Icon: LayoutGrid,
		label: "App",
	},
	agent: {
		bgColor: "bg-orange-50 dark:bg-orange-950/50",
		borderColor: "border-orange-300 dark:border-orange-700",
		textColor: "text-orange-700 dark:text-orange-300",
		Icon: Bot,
		label: "Agent",
	},
};

function EntityNodeComponent({ data, selected }: NodeProps) {
	const nodeData = data as EntityNodeData;
	const config = entityConfig[nodeData.entityType];
	const Icon = config.Icon;

	return (
		<div
			className={cn(
				"px-4 py-3 rounded-lg border-2 shadow-sm transition-all duration-200 min-w-[180px] max-w-[250px]",
				config.bgColor,
				config.borderColor,
				selected && "ring-2 ring-primary ring-offset-2",
				nodeData.isRoot && "ring-2 ring-primary ring-offset-1",
			)}
		>
			{/* Handles for connections */}
			<Handle
				type="target"
				position={Position.Top}
				className="!bg-muted-foreground !w-2 !h-2"
			/>
			<Handle
				type="source"
				position={Position.Bottom}
				className="!bg-muted-foreground !w-2 !h-2"
			/>

			{/* Entity type badge */}
			<div className="flex items-center gap-2 mb-2">
				<div
					className={cn(
						"flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
						config.bgColor,
						config.textColor,
					)}
				>
					<Icon className="w-3 h-3" />
					<span>{config.label}</span>
				</div>
				{nodeData.isRoot && (
					<span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary text-primary-foreground">
						Root
					</span>
				)}
			</div>

			{/* Entity name */}
			<div
				className="font-medium text-sm text-foreground truncate"
				title={nodeData.label}
			>
				{nodeData.label}
			</div>

			{/* Organization indicator */}
			{nodeData.orgId && (
				<div className="mt-1 text-[10px] text-muted-foreground truncate">
					Org: {nodeData.orgId.slice(0, 8)}...
				</div>
			)}
			{!nodeData.orgId && (
				<div className="mt-1 text-[10px] text-muted-foreground">
					Global
				</div>
			)}
		</div>
	);
}

export const EntityNode = memo(EntityNodeComponent);
