import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import {
	GripVertical,
	Building2,
	Globe,
	Shield,
	Calendar,
	Network,
	Link,
	Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
	draggable,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { setCustomNativeDragPreview } from "@atlaskit/pragmatic-drag-and-drop/element/set-custom-native-drag-preview";
import { cn } from "@/lib/utils";
import { formatDateShort } from "@/lib/utils";
import type { EntityWithScope, EntityType, Organization } from "./types";
import { ENTITY_CONFIG } from "./types";

// Drag Preview Component
function DragPreview({
	count,
	entityName,
}: {
	count: number;
	entityName: string;
}) {
	return (
		<div className="flex items-center gap-2 rounded-2xl bg-card shadow-lg ring-1 ring-foreground/5 dark:ring-foreground/10 px-3 py-2">
			<GripVertical className="h-4 w-4 text-muted-foreground" />
			<span className="font-medium">
				{count > 1 ? `${count} entities` : entityName}
			</span>
			{count > 1 && (
				<Badge variant="secondary" className="ml-1">
					{count}
				</Badge>
			)}
		</div>
	);
}

// Entity Card Component
export interface EntityCardProps {
	entity: EntityWithScope;
	selected: boolean;
	onSelect: (selected: boolean) => void;
	onShowRelationships: (entityId: string, entityType: EntityType, entityName: string) => void;
	onDelete?: (entityId: string, entityName: string, entityType: EntityType) => void;
	organizations: Organization[];
	selectedIds: Set<string>;
	allEntities: EntityWithScope[];
}

export function EntityCard({
	entity,
	selected,
	onSelect,
	onShowRelationships,
	onDelete,
	organizations,
	selectedIds,
	allEntities,
}: EntityCardProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [dragging, setDragging] = useState(false);
	const [previewContainer, setPreviewContainer] = useState<HTMLElement | null>(
		null,
	);

	const config = ENTITY_CONFIG[entity.entityType];
	const Icon = config.icon;

	const orgName = entity.organizationId
		? organizations.find((o) => o.id === entity.organizationId)?.name ??
			"Unknown Org"
		: "Global";

	// Calculate drag count for preview
	const dragCount = selected ? selectedIds.size : 1;

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return draggable({
			element: el,
			getInitialData: () => {
				const idsToMove = selected ? Array.from(selectedIds) : [entity.id];

				return {
					type: "entity",
					entityIds: idsToMove,
					entityCount: idsToMove.length,
					entityTypes: idsToMove.map((id) => {
						const e = allEntities.find((ent) => ent.id === id);
						return e?.entityType ?? "unknown";
					}),
				};
			},
			onGenerateDragPreview: ({ nativeSetDragImage }) => {
				setCustomNativeDragPreview({
					nativeSetDragImage,
					render: ({ container }) => {
						setPreviewContainer(container);
					},
				});
			},
			onDragStart: () => setDragging(true),
			onDrop: () => {
				setDragging(false);
				setPreviewContainer(null);
			},
		});
	}, [entity.id, entity.name, selected, selectedIds, allEntities]);

	return (
		<>
			<div
				ref={ref}
				className={cn(
					"flex items-start gap-3 rounded-2xl shadow-sm ring-1 p-3 transition-all cursor-grab active:cursor-grabbing",
					dragging && "opacity-50 scale-95",
					selected
						? "ring-primary bg-accent"
						: "bg-card ring-foreground/5 hover:ring-primary/50 dark:ring-foreground/10 dark:hover:ring-primary/50",
				)}
			>
				<Checkbox
					checked={selected}
					onCheckedChange={onSelect}
					onClick={(e) => e.stopPropagation()}
					className="mt-0.5"
				/>

				<GripVertical className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />

				<div className="flex-1 min-w-0 space-y-1">
					{/* Row 1: Name + Type badge + Actions */}
					<div className="flex items-center justify-between gap-2">
						<div className="flex items-center gap-2 min-w-0">
							<Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
							<p className="font-medium truncate">{entity.name}</p>
						</div>
						<div className="flex items-center gap-1.5 shrink-0">
							<Badge variant="outline" className={cn(config.color)}>
								{config.label}
							</Badge>
							<Button
								variant="outline"
								size="icon"
								onClick={(e) => {
									e.stopPropagation();
									onShowRelationships(entity.id, entity.entityType, entity.name);
								}}
								title="Show dependencies"
							>
								<Network className="h-4 w-4" />
							</Button>
							{onDelete && (
								<Button
									variant="outline"
									size="icon"
									onClick={(e) => {
										e.stopPropagation();
										onDelete(entity.id, entity.name, entity.entityType);
									}}
									title={`Delete ${config.label.toLowerCase()}`}
									className="text-destructive hover:text-destructive hover:bg-destructive/10"
								>
									<Trash2 className="h-4 w-4" />
								</Button>
							)}
						</div>
					</div>

					{/* Row 2: Organization */}
					<div className="flex items-center gap-1 text-xs text-muted-foreground">
						{entity.organizationId ? (
							<Building2 className="h-3 w-3 shrink-0" />
						) : (
							<Globe className="h-3 w-3 shrink-0" />
						)}
						<span>{orgName}</span>
					</div>

					{/* Row 3: Access Level + Date + Used By Count */}
					<div className="flex items-center gap-4 text-xs text-muted-foreground">
						<span className="flex items-center gap-1">
							<Shield className="h-3 w-3 shrink-0" />
							{entity.accessLevel ?? "\u2014"}
						</span>
						<span className="flex items-center gap-1">
							<Calendar className="h-3 w-3 shrink-0" />
							{formatDateShort(entity.createdAt)}
						</span>
						{entity.usedByCount !== null && (
							<span
								className={cn(
									"flex items-center gap-1",
									entity.usedByCount === 0
										? "text-muted-foreground/50"
										: "text-muted-foreground",
								)}
							>
								<Link className="h-3 w-3 shrink-0" />
								{entity.entityType === "workflow"
									? entity.usedByCount === 0
										? "No refs"
										: `${entity.usedByCount} ref${entity.usedByCount === 1 ? "" : "s"}`
									: entity.usedByCount === 0
										? "No deps"
										: `Uses ${entity.usedByCount}`}
							</span>
						)}
					</div>
				</div>
			</div>
			{previewContainer &&
				createPortal(
					<DragPreview count={dragCount} entityName={entity.name} />,
					previewContainer,
				)}
		</>
	);
}
