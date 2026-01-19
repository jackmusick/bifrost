/**
 * OrganizationScopeDialog Component
 *
 * Reusable dialog for assigning organization scope to entities (workflows, forms, agents).
 * Supports both single-entity and multi-entity modes.
 *
 * Single entity mode: Simple dropdown with confirm button
 * Multi-entity mode: "Apply to all" row + per-entity dropdowns
 */

import { useState, useEffect, useMemo } from "react";
import { Loader2, FileCode, FormInput, Bot } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";

export type ScopedEntityType = "workflow" | "form" | "agent";

export interface ScopedEntity {
	/** File path or unique identifier */
	path: string;
	/** Display name (optional, defaults to path basename) */
	name?: string;
	/** Type of entity */
	entityType: ScopedEntityType;
	/** Current organization ID (null = global, undefined = not set) */
	currentOrgId?: string | null;
}

export interface OrganizationScopeDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	/** Entities to assign scope to */
	entities: ScopedEntity[];
	/** Callback with org assignments: { [path]: orgId | null } */
	onConfirm: (assignments: Record<string, string | null>) => void;
	/** Optional loading state for confirm button */
	isConfirming?: boolean;
	/** Optional title override */
	title?: string;
	/** Optional description override */
	description?: string;
}

const ENTITY_ICONS: Record<ScopedEntityType, React.ReactNode> = {
	workflow: <FileCode className="h-4 w-4 text-blue-500" />,
	form: <FormInput className="h-4 w-4 text-green-500" />,
	agent: <Bot className="h-4 w-4 text-purple-500" />,
};

const ENTITY_LABELS: Record<ScopedEntityType, string> = {
	workflow: "Workflow",
	form: "Form",
	agent: "Agent",
};

/**
 * Get display name from path
 */
function getDisplayName(entity: ScopedEntity): string {
	if (entity.name) return entity.name;
	const parts = entity.path.split("/");
	const filename = parts[parts.length - 1];
	// Remove extension for cleaner display
	return filename.replace(/\.(py|yaml|yml|json)$/, "");
}

export function OrganizationScopeDialog({
	open,
	onOpenChange,
	entities,
	onConfirm,
	isConfirming = false,
	title,
	description,
}: OrganizationScopeDialogProps) {

	// Track assignments for each entity path
	// null = Global, string = org ID, undefined = not yet assigned
	const [assignments, setAssignments] = useState<Record<string, string | null | undefined>>({});

	// "Apply to all" value for multi-entity mode
	const [applyToAllValue, setApplyToAllValue] = useState<string | null | undefined>(undefined);

	const isSingleEntity = entities.length === 1;

	// Initialize assignments from entity currentOrgId values when dialog opens
	useEffect(() => {
		if (open && entities.length > 0) {
			const initial: Record<string, string | null | undefined> = {};
			for (const entity of entities) {
				// Use currentOrgId if provided, otherwise undefined (pending)
				initial[entity.path] = entity.currentOrgId;
			}
			setAssignments(initial);
			setApplyToAllValue(undefined);
		}
	}, [open, entities]);

	// Check if all entities have an assignment (not undefined)
	const allAssigned = useMemo(() => {
		return entities.every((entity) => assignments[entity.path] !== undefined);
	}, [entities, assignments]);

	// Count of pending assignments
	const pendingCount = useMemo(() => {
		return entities.filter((entity) => assignments[entity.path] === undefined).length;
	}, [entities, assignments]);

	const handleEntityChange = (path: string, value: string | null | undefined) => {
		setAssignments((prev) => ({
			...prev,
			[path]: value,
		}));
	};

	const handleApplyToAll = (value: string | null | undefined) => {
		setApplyToAllValue(value);
		// Apply to all entities
		const newAssignments: Record<string, string | null | undefined> = {};
		for (const entity of entities) {
			newAssignments[entity.path] = value;
		}
		setAssignments(newAssignments);
	};

	const handleConfirm = () => {
		// Convert undefined to null for the callback (shouldn't happen if button is disabled correctly)
		const result: Record<string, string | null> = {};
		for (const entity of entities) {
			const value = assignments[entity.path];
			result[entity.path] = value ?? null;
		}
		onConfirm(result);
	};

	const handleClose = () => {
		if (!isConfirming) {
			onOpenChange(false);
		}
	};

	// Dynamic title/description based on mode
	const dialogTitle = title || (isSingleEntity
		? "Assign Organization"
		: `Assign Organizations (${entities.length} entities)`);

	const dialogDescription = description || (isSingleEntity
		? `Choose which organization can access this ${ENTITY_LABELS[entities[0].entityType].toLowerCase()}.`
		: "Choose which organizations can access these entities. Global entities are available to all organizations.");

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="sm:max-w-[500px]">
				<DialogHeader>
					<DialogTitle>{dialogTitle}</DialogTitle>
					<DialogDescription>{dialogDescription}</DialogDescription>
				</DialogHeader>

				<div className="py-4">
					{isSingleEntity ? (
						// Single entity mode - simple dropdown
						<div className="space-y-4">
							<div className="flex items-center gap-2 p-3 rounded-md bg-muted/50">
								{ENTITY_ICONS[entities[0].entityType]}
								<div className="flex flex-col">
									<span className="font-medium">{getDisplayName(entities[0])}</span>
									<span className="text-xs text-muted-foreground">
										{ENTITY_LABELS[entities[0].entityType]}
									</span>
								</div>
							</div>

							<div className="space-y-2">
								<Label>Organization</Label>
								<OrganizationSelect
									value={assignments[entities[0].path]}
									onChange={(value) => handleEntityChange(entities[0].path, value)}
									showGlobal={true}
									showAll={false}
									placeholder="Select organization..."
								/>
							</div>
						</div>
					) : (
						// Multi-entity mode
						<div className="space-y-4">
							{/* Apply to all row */}
							<div className="space-y-2">
								<Label>Apply to all entities</Label>
								<OrganizationSelect
									value={applyToAllValue}
									onChange={handleApplyToAll}
									showGlobal={true}
									showAll={false}
									placeholder="Select to apply to all..."
								/>
							</div>

							<Separator />

							{/* Per-entity list */}
							<div className="space-y-2">
								<Label>Individual assignments</Label>
								{pendingCount > 0 && (
									<p className="text-xs text-yellow-600 dark:text-yellow-500">
										{pendingCount} of {entities.length} entities need assignment
									</p>
								)}
							</div>

							<div className="max-h-[240px] overflow-y-auto pr-2 space-y-3">
								{entities.map((entity) => (
									<div
										key={entity.path}
										className="flex items-center gap-3 p-2 rounded-md border bg-card"
									>
										<div className="flex items-center gap-2 flex-1 min-w-0">
											{ENTITY_ICONS[entity.entityType]}
											<div className="flex flex-col min-w-0">
												<span className="font-medium truncate">
													{getDisplayName(entity)}
												</span>
												<span className="text-xs text-muted-foreground">
													{ENTITY_LABELS[entity.entityType]}
												</span>
											</div>
										</div>

										<div className="w-[180px] shrink-0">
											<OrganizationSelect
												value={assignments[entity.path]}
												onChange={(value) => handleEntityChange(entity.path, value)}
												showGlobal={true}
												showAll={false}
												placeholder="Select..."
											/>
										</div>
									</div>
								))}
							</div>
						</div>
					)}
				</div>

				<DialogFooter>
					<Button variant="outline" onClick={handleClose} disabled={isConfirming}>
						Cancel
					</Button>
					<Button onClick={handleConfirm} disabled={!allAssigned || isConfirming}>
						{isConfirming && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
						{isConfirming ? "Saving..." : "Confirm"}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
