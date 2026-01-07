/**
 * DependencyCanvas - Mind-map visualization of entity dependencies
 *
 * Displays a graph showing how workflows, forms, apps, and agents
 * are connected through their dependencies.
 */

import { useState, useMemo } from "react";
import { Network } from "lucide-react";
import {
	ToggleGroup,
	ToggleGroupItem,
} from "@/components/ui/toggle-group";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { DependencyGraph } from "@/components/dependencies/DependencyGraph";
import {
	useDependencyGraph,
	type EntityType,
} from "@/hooks/useDependencyGraph";
import { useWorkflows } from "@/hooks/useWorkflows";
import { useForms } from "@/hooks/useForms";
import { useAgents } from "@/hooks/useAgents";
import { $api } from "@/lib/api-client";

// Type for entity options in the picker
interface EntityOption {
	id: string;
	name: string;
}

export function DependencyCanvas() {
	const [viewType, setViewType] = useState<EntityType>("workflow");
	const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>();
	const [depth, setDepth] = useState(2);

	// Fetch entities for the picker based on view type
	const { data: workflows, isLoading: loadingWorkflows } = useWorkflows();
	const { data: forms, isLoading: loadingForms } = useForms();
	const { data: agents, isLoading: loadingAgents } = useAgents();
	const { data: apps, isLoading: loadingApps } = $api.useQuery(
		"get",
		"/api/applications",
	);

	// Get entity options based on view type
	const entityOptions = useMemo((): EntityOption[] => {
		switch (viewType) {
			case "workflow":
				return (
					workflows?.map((w) => ({
						id: w.id,
						name: w.name,
					})) ?? []
				);
			case "form":
				return (
					forms?.map((f) => ({
						id: f.id,
						name: f.name,
					})) ?? []
				);
			case "app":
				return (
					(apps as { applications?: { id: string; name: string }[] })?.applications?.map(
						(a) => ({
							id: a.id,
							name: a.name,
						}),
					) ?? []
				);
			case "agent":
				return (
					agents?.map((a) => ({
						id: a.id,
						name: a.name,
					})) ?? []
				);
			default:
				return [];
		}
	}, [viewType, workflows, forms, apps, agents]);

	// Loading state for entity picker
	const isLoadingEntities =
		(viewType === "workflow" && loadingWorkflows) ||
		(viewType === "form" && loadingForms) ||
		(viewType === "app" && loadingApps) ||
		(viewType === "agent" && loadingAgents);

	// Fetch dependency graph
	const {
		data: graphData,
		isLoading: loadingGraph,
		error: graphError,
	} = useDependencyGraph(
		selectedEntityId ? viewType : undefined,
		selectedEntityId,
		depth,
	);

	// Handle view type change - reset entity selection
	const handleViewTypeChange = (value: string) => {
		if (value) {
			setViewType(value as EntityType);
			setSelectedEntityId(undefined);
		}
	};

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col">
			{/* Header */}
			<div className="flex items-center justify-between mb-6">
				<div>
					<div className="flex items-center gap-3">
						<Network className="h-8 w-8 text-primary" />
						<h1 className="text-4xl font-extrabold tracking-tight">
							Dependencies
						</h1>
					</div>
					<p className="mt-2 text-muted-foreground">
						Visualize how workflows, forms, apps, and agents are connected
					</p>
				</div>
			</div>

			{/* Controls */}
			<div className="flex flex-wrap items-end gap-6 mb-6">
				{/* View Type Toggle */}
				<div className="flex flex-col gap-2">
					<Label className="text-sm text-muted-foreground">View By</Label>
					<ToggleGroup
						type="single"
						value={viewType}
						onValueChange={handleViewTypeChange}
						className="justify-start"
					>
						<ToggleGroupItem value="workflow" aria-label="By Workflow">
							Workflow
						</ToggleGroupItem>
						<ToggleGroupItem value="form" aria-label="By Form">
							Form
						</ToggleGroupItem>
						<ToggleGroupItem value="app" aria-label="By App">
							App
						</ToggleGroupItem>
						<ToggleGroupItem value="agent" aria-label="By Agent">
							Agent
						</ToggleGroupItem>
					</ToggleGroup>
				</div>

				{/* Entity Picker */}
				<div className="flex flex-col gap-2 min-w-[250px]">
					<Label className="text-sm text-muted-foreground">
						Select {viewType.charAt(0).toUpperCase() + viewType.slice(1)}
					</Label>
					<Select
						value={selectedEntityId}
						onValueChange={setSelectedEntityId}
						disabled={isLoadingEntities}
					>
						<SelectTrigger>
							<SelectValue
								placeholder={
									isLoadingEntities
										? "Loading..."
										: `Choose a ${viewType}...`
								}
							/>
						</SelectTrigger>
						<SelectContent>
							{entityOptions.map((entity) => (
								<SelectItem key={entity.id} value={entity.id}>
									{entity.name}
								</SelectItem>
							))}
							{entityOptions.length === 0 && !isLoadingEntities && (
								<div className="py-2 px-2 text-sm text-muted-foreground">
									No {viewType}s found
								</div>
							)}
						</SelectContent>
					</Select>
				</div>

				{/* Depth Selector */}
				<div className="flex flex-col gap-2">
					<Label className="text-sm text-muted-foreground">Depth</Label>
					<Select
						value={String(depth)}
						onValueChange={(v) => setDepth(parseInt(v, 10))}
					>
						<SelectTrigger className="w-[100px]">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="1">1 level</SelectItem>
							<SelectItem value="2">2 levels</SelectItem>
							<SelectItem value="3">3 levels</SelectItem>
							<SelectItem value="4">4 levels</SelectItem>
							<SelectItem value="5">5 levels</SelectItem>
						</SelectContent>
					</Select>
				</div>

				{/* Stats */}
				{graphData && graphData.nodes && graphData.edges && (
					<div className="flex items-center gap-2 ml-auto">
						<Badge variant="outline">
							{graphData.nodes.length} nodes
						</Badge>
						<Badge variant="outline">
							{graphData.edges.length} connections
						</Badge>
					</div>
				)}
			</div>

			{/* Graph Canvas */}
			<div className="flex-1 min-h-0 rounded-lg border bg-background/50 overflow-hidden">
				{!selectedEntityId ? (
					<div className="h-full flex items-center justify-center">
						<div className="text-center max-w-md">
							<Network className="h-16 w-16 text-muted-foreground/50 mx-auto mb-4" />
							<h3 className="text-lg font-semibold text-muted-foreground mb-2">
								Select an Entity
							</h3>
							<p className="text-sm text-muted-foreground">
								Choose a {viewType} from the dropdown above to visualize its
								dependencies. Click on any node in the graph to explore its
								connections.
							</p>
						</div>
					</div>
				) : loadingGraph ? (
					<div className="h-full flex items-center justify-center">
						<div className="flex flex-col items-center gap-4">
							<Skeleton className="h-32 w-32 rounded-full" />
							<div className="text-sm text-muted-foreground">
								Loading dependency graph...
							</div>
						</div>
					</div>
				) : graphError ? (
					<div className="h-full flex items-center justify-center">
						<div className="text-center max-w-md">
							<div className="text-destructive text-lg font-semibold mb-2">
								Error Loading Graph
							</div>
							<p className="text-sm text-muted-foreground">
								{graphError instanceof Error
									? graphError.message
									: "Failed to load dependency graph"}
							</p>
						</div>
					</div>
				) : graphData && graphData.nodes && graphData.edges ? (
					<DependencyGraph
						nodes={graphData.nodes}
						edges={graphData.edges}
						rootId={graphData.root_id}
					/>
				) : null}
			</div>
		</div>
	);
}

export default DependencyCanvas;
