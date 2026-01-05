import { useState, useMemo } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
	AlertTriangle,
	ChevronDown,
	ChevronRight,
	Clock,
	FileCode,
	Bot,
	FormInput,
	AppWindow,
} from "lucide-react";
import type { components } from "@/lib/v1";

type PendingDeactivation = components["schemas"]["PendingDeactivation"];
type AvailableReplacement = components["schemas"]["AvailableReplacement"];
type AffectedEntity = components["schemas"]["AffectedEntity"];

interface WorkflowDeactivationDialogProps {
	pendingDeactivations: PendingDeactivation[];
	availableReplacements: AvailableReplacement[];
	open: boolean;
	onForceDeactivate: () => void;
	onApplyReplacements: (replacements: Record<string, string>) => void;
	onCancel: () => void;
}

function getEntityIcon(entityType: string) {
	switch (entityType) {
		case "form":
			return <FormInput className="h-3 w-3" />;
		case "agent":
			return <Bot className="h-3 w-3" />;
		case "app":
			return <AppWindow className="h-3 w-3" />;
		default:
			return <FileCode className="h-3 w-3" />;
	}
}

function getDecoratorBadge(decoratorType: string) {
	switch (decoratorType) {
		case "workflow":
			return <Badge variant="default">workflow</Badge>;
		case "tool":
			return <Badge variant="secondary">tool</Badge>;
		case "data_provider":
			return <Badge variant="outline">data provider</Badge>;
		default:
			return <Badge variant="outline">{decoratorType}</Badge>;
	}
}

function AffectedEntitiesSection({ entities }: { entities: AffectedEntity[] }) {
	const [isOpen, setIsOpen] = useState(false);

	if (entities.length === 0) return null;

	return (
		<Collapsible open={isOpen} onOpenChange={setIsOpen}>
			<CollapsibleTrigger className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400 hover:underline">
				{isOpen ? (
					<ChevronDown className="h-3 w-3" />
				) : (
					<ChevronRight className="h-3 w-3" />
				)}
				{entities.length} affected{" "}
				{entities.length === 1 ? "entity" : "entities"}
			</CollapsibleTrigger>
			<CollapsibleContent className="mt-1 pl-4 space-y-1">
				{entities.map((entity, idx) => (
					<div
						key={`${entity.entity_type}-${entity.id}-${idx}`}
						className="flex items-center gap-2 text-xs text-muted-foreground"
					>
						{getEntityIcon(entity.entity_type)}
						<span className="font-medium">{entity.name}</span>
						<span className="text-muted-foreground/60">
							({entity.reference_type})
						</span>
					</div>
				))}
			</CollapsibleContent>
		</Collapsible>
	);
}

/**
 * Dialog shown when saving a file would deactivate workflows that are in use.
 *
 * Gives the user the choice to:
 * 1. Select replacement functions to inherit workflow identities (preserves history)
 * 2. Force deactivate all (workflows become inactive, may break dependencies)
 * 3. Cancel the operation
 */
export function WorkflowDeactivationDialog({
	pendingDeactivations,
	availableReplacements,
	open,
	onForceDeactivate,
	onApplyReplacements,
	onCancel,
}: WorkflowDeactivationDialogProps) {
	// Track selected replacement for each pending deactivation
	const [selectedReplacements, setSelectedReplacements] = useState<
		Record<string, string>
	>({});

	// Group available replacements by decorator type for smarter suggestions
	const replacementsByType = useMemo(() => {
		const grouped: Record<string, AvailableReplacement[]> = {};
		for (const r of availableReplacements) {
			const type = r.decorator_type;
			if (!grouped[type]) grouped[type] = [];
			grouped[type].push(r);
		}
		return grouped;
	}, [availableReplacements]);

	// Get compatible replacements for a pending deactivation
	const getCompatibleReplacements = (pd: PendingDeactivation) => {
		// Only show replacements of matching type
		return replacementsByType[pd.decorator_type] || [];
	};

	// Check if all deactivations have replacements selected
	const allHaveReplacements = pendingDeactivations.every(
		(pd) => selectedReplacements[pd.id],
	);

	// Count how many have affected entities (for warning emphasis)
	const deactivationsWithDependencies = pendingDeactivations.filter(
		(pd) => pd.affected_entities && pd.affected_entities.length > 0,
	);

	const handleApply = () => {
		onApplyReplacements(selectedReplacements);
	};

	return (
		<Dialog open={open} onOpenChange={(open) => !open && onCancel()}>
			<DialogContent className="sm:max-w-[700px] max-h-[80vh] overflow-hidden flex flex-col">
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-amber-500" />
						Workflows Would Be Deactivated
					</DialogTitle>
					<DialogDescription>
						{pendingDeactivations.length === 1
							? "This change would deactivate a workflow that may have execution history or dependencies."
							: `This change would deactivate ${pendingDeactivations.length} workflows that may have execution history or dependencies.`}
						{deactivationsWithDependencies.length > 0 && (
							<span className="text-amber-600 dark:text-amber-400 font-medium">
								{" "}
								{deactivationsWithDependencies.length}{" "}
								{deactivationsWithDependencies.length === 1
									? "has"
									: "have"}{" "}
								active dependencies that would break.
							</span>
						)}
					</DialogDescription>
				</DialogHeader>

				<div className="flex-1 overflow-y-auto space-y-4 py-4">
					{pendingDeactivations.map((pd) => {
						const compatibleReplacements =
							getCompatibleReplacements(pd);
						const hasReplacements =
							compatibleReplacements.length > 0;

						return (
							<div
								key={pd.id}
								className="border rounded-lg p-4 space-y-3"
							>
								{/* Header row */}
								<div className="flex items-start justify-between gap-4">
									<div className="space-y-1">
										<div className="flex items-center gap-2">
											<span className="font-medium">
												{pd.name}
											</span>
											{getDecoratorBadge(
												pd.decorator_type,
											)}
										</div>
										<div className="text-sm text-muted-foreground font-mono">
											{pd.function_name}
										</div>
										{pd.description && (
											<div className="text-sm text-muted-foreground">
												{pd.description}
											</div>
										)}
									</div>

									{/* Metadata badges */}
									<div className="flex flex-wrap gap-1 justify-end">
										{pd.has_executions && (
											<Badge
												variant="secondary"
												className="text-xs"
											>
												<Clock className="h-3 w-3 mr-1" />
												Has history
											</Badge>
										)}
										{pd.schedule && (
											<Badge
												variant="secondary"
												className="text-xs"
											>
												Scheduled
											</Badge>
										)}
										{pd.endpoint_enabled && (
											<Badge
												variant="secondary"
												className="text-xs"
											>
												HTTP endpoint
											</Badge>
										)}
									</div>
								</div>

								{/* Affected entities */}
								{pd.affected_entities &&
									pd.affected_entities.length > 0 && (
										<AffectedEntitiesSection
											entities={pd.affected_entities}
										/>
									)}

								{/* Replacement selector */}
								{hasReplacements && (
									<div className="pt-2 border-t">
										<label className="text-sm font-medium mb-1.5 block">
											Transfer identity to:
										</label>
										<Select
											value={
												selectedReplacements[pd.id] ||
												""
											}
											onValueChange={(value) =>
												setSelectedReplacements(
													(prev) => ({
														...prev,
														[pd.id]: value,
													}),
												)
											}
										>
											<SelectTrigger className="w-full">
												<SelectValue placeholder="Select a replacement function..." />
											</SelectTrigger>
											<SelectContent>
												{compatibleReplacements
													.sort(
														(a, b) =>
															b.similarity_score -
															a.similarity_score,
													)
													.map((r) => (
														<SelectItem
															key={
																r.function_name
															}
															value={
																r.function_name
															}
														>
															<div className="flex items-center gap-2">
																<span className="font-mono">
																	{
																		r.function_name
																	}
																</span>
																{r.similarity_score >=
																	0.5 && (
																	<Badge
																		variant="outline"
																		className="text-xs"
																	>
																		{Math.round(
																			r.similarity_score *
																				100,
																		)}
																		% match
																	</Badge>
																)}
															</div>
														</SelectItem>
													))}
											</SelectContent>
										</Select>
									</div>
								)}

								{!hasReplacements && (
									<div className="pt-2 border-t text-sm text-muted-foreground italic">
										No compatible replacement functions
										available. This workflow will be
										deactivated.
									</div>
								)}
							</div>
						);
					})}
				</div>

				<div className="text-sm text-muted-foreground space-y-2 border-t pt-4">
					<p>
						<strong>Transfer Identity:</strong> The selected
						function will inherit the workflow's UUID, preserving
						execution history, schedules, and all references.
					</p>
					<p>
						<strong>Deactivate All:</strong> All listed workflows
						will be marked inactive. Affected forms, agents, and
						apps may stop working.
					</p>
				</div>

				<DialogFooter className="flex gap-2 pt-2">
					<Button variant="outline" onClick={onCancel}>
						Cancel
					</Button>
					<Button
						variant="destructive"
						onClick={onForceDeactivate}
						disabled={deactivationsWithDependencies.length > 0}
						title={
							deactivationsWithDependencies.length > 0
								? "Cannot deactivate workflows with active dependencies"
								: undefined
						}
					>
						Deactivate All
					</Button>
					{availableReplacements.length > 0 && (
						<Button
							onClick={handleApply}
							disabled={!allHaveReplacements}
						>
							Apply Replacements
						</Button>
					)}
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
