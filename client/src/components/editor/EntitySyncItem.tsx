/**
 * EntitySyncItem - Renders a single entity in the sync preview.
 *
 * Shows entity with appropriate icon and display name.
 * For apps, shows expandable file list.
 */

import { useState } from "react";
import {
	ChevronDown,
	ChevronRight,
	Plus,
	Minus,
	Edit3,
	AppWindow,
	Bot,
	FileText,
	Workflow,
	FileCode,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { SyncAction } from "@/hooks/useGitHub";

/** Icon mapping for entity types */
const ENTITY_ICONS = {
	form: { icon: FileText, className: "text-green-500" },
	agent: { icon: Bot, className: "text-orange-500" },
	app: { icon: AppWindow, className: "text-purple-500" },
	workflow: { icon: Workflow, className: "text-blue-500" },
	app_file: { icon: FileCode, className: "text-gray-500" },
} as const;

/** Get icon for action type (add/modify/delete) */
function getActionIcon(action: "add" | "modify" | "delete") {
	switch (action) {
		case "add":
			return <Plus className="h-3 w-3 text-green-500" />;
		case "modify":
			return <Edit3 className="h-3 w-3 text-blue-500" />;
		case "delete":
			return <Minus className="h-3 w-3 text-red-500" />;
	}
}

interface EntitySyncItemProps {
	/** The primary sync action (for single entities) or app metadata (for apps) */
	action: SyncAction;
	/** Child files for app entities */
	childFiles?: SyncAction[];
	/** Whether this is a conflict item */
	isConflict?: boolean;
	/** Resolution state for conflicts */
	resolution?: "keep_local" | "keep_remote";
	/** Callback for conflict resolution */
	onResolve?: (resolution: "keep_local" | "keep_remote") => void;
	/** Callback when item is clicked for preview */
	onClick?: () => void;
	/** Callback when child file is clicked for preview */
	onChildClick?: (childAction: SyncAction) => void;
}

export function EntitySyncItem({
	action,
	childFiles = [],
	isConflict = false,
	resolution,
	onResolve,
	onClick,
	onChildClick,
}: EntitySyncItemProps) {
	const [expanded, setExpanded] = useState(false);
	const entityType = action.entity_type as keyof typeof ENTITY_ICONS | null;
	const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
	const IconComponent = iconConfig?.icon ?? FileCode;
	const iconClassName = iconConfig?.className ?? "text-gray-500";

	const isApp = action.entity_type === "app";
	const hasChildren = isApp && childFiles.length > 0;

	return (
		<div className="py-1">
			{/* Main entity row */}
			<div
				onClick={onClick}
				className={cn(
					"flex items-center gap-2 text-xs py-1.5 px-2 rounded",
					isConflict && !resolution && "bg-orange-500/10",
					isConflict && resolution && "bg-green-500/10",
					!isConflict && "hover:bg-muted/30",
					onClick && "cursor-pointer"
				)}
			>
				{/* Expand/collapse for apps */}
				{hasChildren ? (
					<button
						onClick={(e) => {
							e.stopPropagation(); // Prevent triggering parent onClick
							setExpanded(!expanded);
						}}
						className="p-0.5 hover:bg-muted rounded"
					>
						{expanded ? (
							<ChevronDown className="h-3 w-3" />
						) : (
							<ChevronRight className="h-3 w-3" />
						)}
					</button>
				) : (
					<span className="w-4" /> // Spacer for alignment
				)}

				{/* Action icon */}
				{getActionIcon(action.action)}

				{/* Entity icon */}
				<IconComponent className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />

				{/* Display name */}
				<span className="flex-1 truncate" title={action.path}>
					{action.display_name || action.path}
				</span>

				{/* File count for apps */}
				{hasChildren && (
					<span className="text-xs text-muted-foreground">
						{childFiles.length} file{childFiles.length !== 1 ? "s" : ""}
					</span>
				)}
			</div>

			{/* Conflict resolution buttons */}
			{isConflict && onResolve && (
				<div className="flex gap-1 ml-8 mt-1">
					<button
						onClick={() => onResolve("keep_local")}
						className={cn(
							"px-2 py-0.5 text-xs rounded",
							resolution === "keep_local"
								? "bg-blue-500 text-white"
								: "bg-muted hover:bg-muted/80"
						)}
					>
						Keep Local
					</button>
					<button
						onClick={() => onResolve("keep_remote")}
						className={cn(
							"px-2 py-0.5 text-xs rounded",
							resolution === "keep_remote"
								? "bg-blue-500 text-white"
								: "bg-muted hover:bg-muted/80"
						)}
					>
						Keep Remote
					</button>
				</div>
			)}

			{/* Expanded app files */}
			{hasChildren && expanded && (
				<div className="ml-6 mt-1 border-l-2 border-muted pl-2 space-y-0.5">
					{childFiles.map((file) => (
						<div
							key={file.path}
							onClick={() => onChildClick?.(file)}
							className={cn(
								"flex items-center gap-2 text-xs py-0.5 px-1 text-muted-foreground rounded",
								onChildClick && "cursor-pointer hover:bg-muted/30"
							)}
						>
							{getActionIcon(file.action)}
							<FileCode className="h-3 w-3" />
							<span className="truncate">{file.display_name || file.path}</span>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
