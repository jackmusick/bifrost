import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { createPortal } from "react-dom";
import {
	Workflow,
	FileText,
	Bot,
	AppWindow,
	Globe,
	Building2,
	Shield,
	GripVertical,
	RefreshCw,
	Filter,
	X,
	Check,
	ArrowUp,
	ArrowDown,
	Calendar,
	Loader2,
	Network,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
	CommandSeparator,
} from "@/components/ui/command";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { useWorkflows, useUpdateWorkflow } from "@/hooks/useWorkflows";
import { useForms, useUpdateForm } from "@/hooks/useForms";
import { useAgents, useUpdateAgent } from "@/hooks/useAgents";
import { useApplications, useUpdateApplication } from "@/hooks/useApplications";
import { useOrganizations } from "@/hooks/useOrganizations";
import { useRoles } from "@/hooks/useRoles";
import {
	useDependencyGraph,
	type EntityType as DependencyEntityType,
	type GraphNode,
	type GraphEdge,
} from "@/hooks/useDependencyGraph";
import { DependencyGraph } from "@/components/dependencies/DependencyGraph";
import {
	draggable,
	dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { setCustomNativeDragPreview } from "@atlaskit/pragmatic-drag-and-drop/element/set-custom-native-drag-preview";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatDateShort } from "@/lib/utils";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type FormPublic = components["schemas"]["FormPublic"];
type AgentSummary = components["schemas"]["AgentSummary"];
type ApplicationPublic = components["schemas"]["ApplicationPublic"];
type Organization = components["schemas"]["OrganizationPublic"];
type Role = components["schemas"]["RolePublic"];

// Unified entity type for the management view
type EntityType = "workflow" | "form" | "agent" | "app";

interface EntityWithScope {
	id: string;
	name: string;
	entityType: EntityType;
	organizationId: string | null;
	accessLevel: string | null;
	createdAt: string;
	original: WorkflowMetadata | FormPublic | AgentSummary | ApplicationPublic;
}

// Relationship filter state
interface RelationshipFilter {
	entityId: string;
	entityType: EntityType;
	entityName: string;
}

// Sort options
type SortOption = "name" | "date" | "type";

// Helper to normalize entities into unified format
function normalizeEntities(
	workflows: WorkflowMetadata[] = [],
	forms: FormPublic[] = [],
	agents: AgentSummary[] = [],
	apps: ApplicationPublic[] = [],
): EntityWithScope[] {
	const entities: EntityWithScope[] = [];

	for (const w of workflows) {
		entities.push({
			id: w.id,
			name: w.name,
			entityType: "workflow",
			organizationId: w.organization_id ?? null,
			accessLevel: w.access_level ?? null,
			createdAt: w.created_at,
			original: w,
		});
	}

	for (const f of forms) {
		if (!f.is_active) continue;
		// FormPublic excludes organization_id, access_level, created_at from API response
		// Use defaults since these aren't available
		entities.push({
			id: f.id,
			name: f.name,
			entityType: "form",
			organizationId: null, // Forms don't expose organization_id in API response
			accessLevel: "role_based", // Default access level
			createdAt: new Date().toISOString(), // Forms don't expose created_at in API response
			original: f,
		});
	}

	for (const a of agents) {
		if (!a.is_active || !a.id) continue;
		entities.push({
			id: a.id,
			name: a.name,
			entityType: "agent",
			organizationId: (a as { organization_id?: string | null }).organization_id ?? null,
			accessLevel: (a as { access_level?: string | null }).access_level ?? null,
			createdAt: a.created_at,
			original: a,
		});
	}

	for (const app of apps) {
		entities.push({
			id: app.id,
			name: app.name,
			entityType: "app",
			organizationId: app.organization_id ?? null,
			accessLevel: app.access_level ?? null,
			createdAt: app.created_at ?? new Date().toISOString(),
			original: app,
		});
	}

	return entities;
}

// Entity type icons and colors
const ENTITY_CONFIG = {
	workflow: {
		icon: Workflow,
		color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
		label: "Workflow",
	},
	form: {
		icon: FileText,
		color: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
		label: "Form",
	},
	agent: {
		icon: Bot,
		color: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
		label: "Agent",
	},
	app: {
		icon: AppWindow,
		color: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
		label: "App",
	},
} as const;

// Drag Preview Component
function DragPreview({
	count,
	entityName,
}: {
	count: number;
	entityName: string;
}) {
	return (
		<div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 shadow-lg">
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
interface EntityCardProps {
	entity: EntityWithScope;
	selected: boolean;
	onSelect: (selected: boolean) => void;
	onShowRelationships: (entityId: string, entityType: EntityType, entityName: string) => void;
	organizations: Organization[];
	selectedIds: Set<string>;
	allEntities: EntityWithScope[];
}

function EntityCard({
	entity,
	selected,
	onSelect,
	onShowRelationships,
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
					"flex items-start gap-3 rounded-lg border p-3 transition-all cursor-grab active:cursor-grabbing",
					dragging && "opacity-50 scale-95",
					selected
						? "border-primary bg-accent"
						: "bg-card hover:border-primary/50",
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

					{/* Row 3: Access Level + Date */}
					<div className="flex items-center gap-4 text-xs text-muted-foreground">
						<span className="flex items-center gap-1">
							<Shield className="h-3 w-3 shrink-0" />
							{entity.accessLevel ?? "—"}
						</span>
						<span className="flex items-center gap-1">
							<Calendar className="h-3 w-3 shrink-0" />
							{formatDateShort(entity.createdAt)}
						</span>
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

// Organization Drop Target Component
interface OrgDropTargetProps {
	organization: Organization | null;
	onDrop: (entityIds: string[], orgId: string | null) => void;
}

function OrgDropTarget({ organization, onDrop }: OrgDropTargetProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [dragCount, setDragCount] = useState(0);

	const isGlobal = organization === null;
	const name = isGlobal ? "Global" : organization.name;

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return dropTargetForElements({
			element: el,
			getData: () => ({
				type: "org-target",
				orgId: isGlobal ? null : organization.id,
			}),
			canDrop: ({ source }) => source.data["type"] === "entity",
			onDragEnter: ({ source }) => {
				setIsDraggedOver(true);
				setDragCount((source.data["entityCount"] as number) || 1);
			},
			onDragLeave: () => {
				setIsDraggedOver(false);
				setDragCount(0);
			},
			onDrop: ({ source }) => {
				setIsDraggedOver(false);
				setDragCount(0);
				const entityIds = source.data["entityIds"] as string[];
				onDrop(entityIds, isGlobal ? null : organization.id);
			},
		});
	}, [organization, isGlobal, onDrop]);

	return (
		<div
			ref={ref}
			className={cn(
				"flex items-center gap-2 px-4 py-4 rounded-lg border-2 border-dashed transition-all",
				isDraggedOver
					? "border-primary bg-primary/10"
					: "border-muted-foreground/25 hover:border-muted-foreground/50",
			)}
		>
			{isGlobal ? (
				<Globe className="h-4 w-4 text-muted-foreground" />
			) : (
				<Building2 className="h-4 w-4 text-muted-foreground" />
			)}
			<span className="text-sm font-medium">{name}</span>
			{isDraggedOver && dragCount > 1 && (
				<Badge variant="secondary" className="ml-auto">
					{dragCount}
				</Badge>
			)}
		</div>
	);
}

// Role Drop Target Component
interface RoleDropTargetProps {
	role: Role | "authenticated" | "clear-roles";
	onDrop: (entityIds: string[], roleOrAccessLevel: string) => void;
}

function RoleDropTarget({ role, onDrop }: RoleDropTargetProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [dragCount, setDragCount] = useState(0);

	const isAuthenticated = role === "authenticated";
	const isClearRoles = role === "clear-roles";
	const name = isAuthenticated
		? "Authenticated"
		: isClearRoles
			? "Clear Roles"
			: role.name;
	const id = isAuthenticated
		? "authenticated"
		: isClearRoles
			? "clear-roles"
			: role.id;

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return dropTargetForElements({
			element: el,
			getData: () => ({
				type: "role-target",
				roleId: id,
				isAccessLevel: isAuthenticated,
				isClearRoles: isClearRoles,
			}),
			canDrop: ({ source }) => source.data["type"] === "entity",
			onDragEnter: ({ source }) => {
				setIsDraggedOver(true);
				setDragCount((source.data["entityCount"] as number) || 1);
			},
			onDragLeave: () => {
				setIsDraggedOver(false);
				setDragCount(0);
			},
			onDrop: ({ source }) => {
				setIsDraggedOver(false);
				setDragCount(0);
				const entityIds = source.data["entityIds"] as string[];
				onDrop(entityIds, id);
			},
		});
	}, [id, isAuthenticated, isClearRoles, onDrop]);

	return (
		<div
			ref={ref}
			className={cn(
				"flex items-center gap-2 px-4 py-4 rounded-lg border-2 border-dashed transition-all",
				isDraggedOver
					? "border-primary bg-primary/10"
					: isClearRoles
						? "border-destructive/25 hover:border-destructive/50"
						: "border-muted-foreground/25 hover:border-muted-foreground/50",
			)}
		>
			<Shield className="h-4 w-4 text-muted-foreground" />
			<span className={cn("text-sm font-medium", isClearRoles && "text-destructive")}>
				{name}
			</span>
			{isDraggedOver && dragCount > 1 && (
				<Badge variant="secondary" className="ml-auto">
					{dragCount}
				</Badge>
			)}
		</div>
	);
}

// Filter Popover Component
interface FilterPopoverProps {
	typeFilter: string;
	setTypeFilter: (v: string) => void;
	orgFilter: string;
	setOrgFilter: (v: string) => void;
	accessFilter: string;
	setAccessFilter: (v: string) => void;
	organizations: Organization[];
	activeFilterCount: number;
	onClearFilters: () => void;
}

function FilterPopover({
	typeFilter,
	setTypeFilter,
	orgFilter,
	setOrgFilter,
	accessFilter,
	setAccessFilter,
	organizations,
	activeFilterCount,
	onClearFilters,
}: FilterPopoverProps) {
	const [open, setOpen] = useState(false);

	const typeOptions = [
		{ value: "all", label: "All Types" },
		{ value: "workflow", label: "Workflows" },
		{ value: "form", label: "Forms" },
		{ value: "agent", label: "Agents" },
		{ value: "app", label: "Apps" },
	];

	const orgOptions = [
		{ value: "all", label: "All Organizations" },
		{ value: "global", label: "Global" },
		...organizations.map((org) => ({ value: org.id, label: org.name })),
	];

	const accessOptions = [
		{ value: "all", label: "All Access Levels" },
		{ value: "authenticated", label: "Authenticated" },
		{ value: "role_based", label: "Role-based" },
	];

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>
				<Button variant="outline" size="icon" className="h-9 w-9 relative">
					<Filter className="h-4 w-4" />
					{activeFilterCount > 0 && (
						<Badge
							variant="secondary"
							className="absolute -top-1 -right-1 h-4 w-4 p-0 flex items-center justify-center text-[10px]"
						>
							{activeFilterCount}
						</Badge>
					)}
				</Button>
			</PopoverTrigger>
			<PopoverContent className="w-80 p-0" align="start">
				<Command>
					<CommandInput placeholder="Search filters..." />
					<CommandList className="max-h-80">
						<CommandGroup heading="Entity Type">
							{typeOptions.map((option) => (
								<CommandItem
									key={option.value}
									value={option.label}
									onSelect={() => setTypeFilter(option.value)}
								>
									<Check
										className={cn(
											"mr-2 h-4 w-4",
											typeFilter === option.value
												? "opacity-100"
												: "opacity-0",
										)}
									/>
									{option.label}
								</CommandItem>
							))}
						</CommandGroup>
						<CommandSeparator />
						<CommandGroup heading="Organization">
							{orgOptions.map((option) => (
								<CommandItem
									key={option.value}
									value={option.label}
									onSelect={() => setOrgFilter(option.value)}
								>
									<Check
										className={cn(
											"mr-2 h-4 w-4",
											orgFilter === option.value
												? "opacity-100"
												: "opacity-0",
										)}
									/>
									{option.label}
								</CommandItem>
							))}
						</CommandGroup>
						<CommandSeparator />
						<CommandGroup heading="Access Level">
							{accessOptions.map((option) => (
								<CommandItem
									key={option.value}
									value={option.label}
									onSelect={() => setAccessFilter(option.value)}
								>
									<Check
										className={cn(
											"mr-2 h-4 w-4",
											accessFilter === option.value
												? "opacity-100"
												: "opacity-0",
										)}
									/>
									{option.label}
								</CommandItem>
							))}
						</CommandGroup>
						<CommandEmpty>No filters found.</CommandEmpty>
					</CommandList>
				</Command>
				{activeFilterCount > 0 && (
					<div className="p-2 border-t">
						<Button
							variant="ghost"
							size="sm"
							className="w-full"
							onClick={() => {
								onClearFilters();
								setOpen(false);
							}}
						>
							<X className="h-4 w-4 mr-2" />
							Clear all filters
						</Button>
					</div>
				)}
			</PopoverContent>
		</Popover>
	);
}

// Dependency Graph Dialog Component
interface DependencyGraphDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	entityName: string;
	entityType: EntityType | null;
	graphData: {
		nodes?: GraphNode[];
		edges?: GraphEdge[];
		root_id: string;
	} | null;
	isLoading: boolean;
}

function DependencyGraphDialog({
	open,
	onOpenChange,
	entityName,
	entityType,
	graphData,
	isLoading,
}: DependencyGraphDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-[90vw] h-[80vh] flex flex-col">
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<Network className="h-5 w-5" />
						Dependency Graph: {entityName}
						{entityType === "app" && (
							<span className="text-xs font-normal text-muted-foreground ml-2">
								(All Versions)
							</span>
						)}
					</DialogTitle>
				</DialogHeader>
				<div className="flex-1 min-h-0 rounded-lg border bg-background/50 overflow-hidden">
					{isLoading ? (
						<div className="h-full flex items-center justify-center">
							<div className="flex flex-col items-center gap-4">
								<Skeleton className="h-32 w-32 rounded-full" />
								<div className="text-sm text-muted-foreground">
									Loading dependency graph...
								</div>
							</div>
						</div>
					) : graphData && graphData.nodes && graphData.edges ? (
						<DependencyGraph
							nodes={graphData.nodes}
							edges={graphData.edges}
							rootId={graphData.root_id}
						/>
					) : (
						<div className="h-full flex items-center justify-center">
							<div className="text-center max-w-md">
								<Network className="h-16 w-16 text-muted-foreground/50 mx-auto mb-4" />
								<h3 className="text-lg font-semibold text-muted-foreground mb-2">
									No Dependencies Found
								</h3>
								<p className="text-sm text-muted-foreground">
									This entity has no dependencies to visualize.
								</p>
							</div>
						</div>
					)}
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function EntityManagement() {
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [searchTerm, setSearchTerm] = useState("");
	const [typeFilter, setTypeFilter] = useState<string>("all");
	const [orgFilter, setOrgFilter] = useState<string>("all");
	const [accessFilter, setAccessFilter] = useState<string>("all");
	const [sortBy, setSortBy] = useState<SortOption>("name");
	const [sortAsc, setSortAsc] = useState(true);
	const [isUpdating, setIsUpdating] = useState(false);

	// Relationship filter state
	const [relationshipFilter, setRelationshipFilter] = useState<RelationshipFilter | null>(null);
	const [isGraphDialogOpen, setIsGraphDialogOpen] = useState(false);

	// Fetch all entity types
	const {
		data: workflows,
		isLoading: loadingWorkflows,
		refetch: refetchWorkflows,
	} = useWorkflows();
	const {
		data: forms,
		isLoading: loadingForms,
		refetch: refetchForms,
	} = useForms();
	const {
		data: agents,
		isLoading: loadingAgents,
		refetch: refetchAgents,
	} = useAgents();
	const {
		data: appsResponse,
		isLoading: loadingApps,
		refetch: refetchApps,
	} = useApplications();
	const { data: organizations } = useOrganizations();
	const { data: roles } = useRoles();

	// Fetch dependency graph when relationship filter is active
	const {
		data: graphData,
		isLoading: loadingGraph,
	} = useDependencyGraph(
		relationshipFilter ? relationshipFilter.entityType as DependencyEntityType : undefined,
		relationshipFilter?.entityId,
		3, // Fixed depth of 3 for relationship filtering
	);

	// Update mutations
	const updateWorkflow = useUpdateWorkflow();
	const updateForm = useUpdateForm();
	const updateAgent = useUpdateAgent();
	const updateApplication = useUpdateApplication();

	const isLoading = loadingWorkflows || loadingForms || loadingAgents || loadingApps;

	// Normalize and combine all entities
	const allEntities = useMemo(
		() => normalizeEntities(workflows ?? [], forms ?? [], agents ?? [], appsResponse?.applications ?? []),
		[workflows, forms, agents, appsResponse],
	);

	// Extract related entity IDs from graph data
	const relatedEntityIds = useMemo(() => {
		if (!relationshipFilter || !graphData?.nodes) return null;

		const ids = new Set<string>();
		for (const node of graphData.nodes) {
			// Node IDs from the graph are prefixed with type (e.g., "workflow:uuid")
			// We need to extract just the UUID part
			const parts = node.id.split(":");
			if (parts.length === 2) {
				ids.add(parts[1]);
			} else {
				ids.add(node.id);
			}
		}
		return ids;
	}, [relationshipFilter, graphData]);

	// Apply filters
	const filteredEntities = useMemo(() => {
		let result = allEntities;

		// Apply relationship filter first (if active)
		if (relationshipFilter && relatedEntityIds) {
			result = result.filter((e) => relatedEntityIds.has(e.id));
		}

		if (typeFilter !== "all") {
			result = result.filter((e) => e.entityType === typeFilter);
		}

		if (orgFilter !== "all") {
			if (orgFilter === "global") {
				result = result.filter((e) => !e.organizationId);
			} else {
				result = result.filter((e) => e.organizationId === orgFilter);
			}
		}

		if (accessFilter !== "all") {
			result = result.filter((e) => e.accessLevel === accessFilter);
		}

		if (searchTerm) {
			const term = searchTerm.toLowerCase();
			result = result.filter((e) => e.name.toLowerCase().includes(term));
		}

		result = [...result].sort((a, b) => {
			let cmp = 0;
			switch (sortBy) {
				case "name":
					cmp = a.name.localeCompare(b.name);
					break;
				case "date":
					cmp = a.createdAt.localeCompare(b.createdAt);
					break;
				case "type":
					cmp = a.entityType.localeCompare(b.entityType);
					break;
			}
			return sortAsc ? cmp : -cmp;
		});

		return result;
	}, [
		allEntities,
		relationshipFilter,
		relatedEntityIds,
		typeFilter,
		orgFilter,
		accessFilter,
		searchTerm,
		sortBy,
		sortAsc,
	]);

	const activeFilterCount =
		(typeFilter !== "all" ? 1 : 0) +
		(orgFilter !== "all" ? 1 : 0) +
		(accessFilter !== "all" ? 1 : 0);

	const handleClearFilters = () => {
		setTypeFilter("all");
		setOrgFilter("all");
		setAccessFilter("all");
	};

	const handleRefresh = () => {
		refetchWorkflows();
		refetchForms();
		refetchAgents();
		refetchApps();
	};

	const handleSelectEntity = (entityId: string, selected: boolean) => {
		setSelectedIds((prev) => {
			const next = new Set(prev);
			if (selected) {
				next.add(entityId);
			} else {
				next.delete(entityId);
			}
			return next;
		});
	};

	const handleSelectAll = (selected: boolean) => {
		if (selected) {
			setSelectedIds(new Set(filteredEntities.map((e) => e.id)));
		} else {
			setSelectedIds(new Set());
		}
	};

	const handleShowRelationships = useCallback((entityId: string, entityType: EntityType, entityName: string) => {
		setRelationshipFilter({
			entityId,
			entityType,
			entityName,
		});
	}, []);

	const handleClearRelationshipFilter = useCallback(() => {
		setRelationshipFilter(null);
	}, []);

	const allSelected =
		filteredEntities.length > 0 &&
		filteredEntities.every((e) => selectedIds.has(e.id));
	const someSelected =
		filteredEntities.some((e) => selectedIds.has(e.id)) && !allSelected;

	const cycleSortBy = () => {
		const options: SortOption[] = ["name", "date", "type"];
		const currentIndex = options.indexOf(sortBy);
		setSortBy(options[(currentIndex + 1) % options.length]);
	};

	const handleOrgDrop = useCallback(
		async (entityIds: string[], orgId: string | null) => {
			setIsUpdating(true);
			try {
				for (const entityId of entityIds) {
					const entity = allEntities.find((e) => e.id === entityId);
					if (!entity) continue;

					try {
						if (entity.entityType === "workflow") {
							await updateWorkflow.mutateAsync(entityId, {
								organizationId: orgId,
							});
						} else if (entity.entityType === "form") {
							toast.error("Cannot change form organization", {
								description:
									"Form organization can only be set at creation time",
							});
						} else if (entity.entityType === "agent") {
							await updateAgent.mutateAsync({
								params: { path: { agent_id: entityId } },
								body: { organization_id: orgId, clear_roles: false },
							});
						} else if (entity.entityType === "app") {
							const app = entity.original as ApplicationPublic;
							await updateApplication.mutateAsync({
								params: { path: { slug: app.slug } },
								body: { scope: orgId ?? "global" },
							});
						}
					} catch (error) {
						toast.error(`Failed to update ${entity.entityType}`, {
							description:
								error instanceof Error ? error.message : "Unknown error",
						});
					}
				}
			} finally {
				setIsUpdating(false);
			}
		},
		[allEntities, updateWorkflow, updateAgent, updateApplication],
	);

	const handleRoleDrop = useCallback(
		async (entityIds: string[], roleIdOrAccessLevel: string) => {
			setIsUpdating(true);
			const isAccessLevel = roleIdOrAccessLevel === "authenticated";
			const isClearRoles = roleIdOrAccessLevel === "clear-roles";

			try {
				for (const entityId of entityIds) {
					const entity = allEntities.find((e) => e.id === entityId);
					if (!entity) continue;

					try {
						if (entity.entityType === "workflow") {
							if (isClearRoles) {
								// Set to role_based and clear all roles
								await updateWorkflow.mutateAsync(entityId, {
									accessLevel: "role_based",
									clearRoles: true,
								});
							} else {
								await updateWorkflow.mutateAsync(entityId, {
									accessLevel: isAccessLevel ? "authenticated" : "role_based",
								});
							}
						} else if (entity.entityType === "form") {
							if (isClearRoles) {
								await updateForm.mutateAsync({
									params: { path: { form_id: entityId } },
									body: {
										access_level: "role_based",
										clear_roles: true,
									},
								});
							} else {
								await updateForm.mutateAsync({
									params: { path: { form_id: entityId } },
									body: {
										access_level: isAccessLevel ? "authenticated" : "role_based",
										clear_roles: false,
									},
								});
							}
						} else if (entity.entityType === "agent") {
							if (isClearRoles) {
								await updateAgent.mutateAsync({
									params: { path: { agent_id: entityId } },
									body: {
										access_level: "role_based",
										clear_roles: true,
									},
								});
							} else {
								await updateAgent.mutateAsync({
									params: { path: { agent_id: entityId } },
									body: {
										access_level: isAccessLevel ? "authenticated" : "role_based",
										clear_roles: false,
									},
								});
							}
						} else if (entity.entityType === "app") {
							const app = entity.original as ApplicationPublic;
							if (isClearRoles) {
								await updateApplication.mutateAsync({
									params: { path: { slug: app.slug } },
									body: {
										access_level: "role_based",
										role_ids: [],
									},
								});
							} else {
								await updateApplication.mutateAsync({
									params: { path: { slug: app.slug } },
									body: {
										access_level: isAccessLevel ? "authenticated" : "role_based",
										role_ids: isAccessLevel ? [] : undefined,
									},
								});
							}
						}
					} catch (error) {
						toast.error(`Failed to update ${entity.entityType}`, {
							description:
								error instanceof Error ? error.message : "Unknown error",
						});
					}
				}
			} finally {
				setIsUpdating(false);
			}
		},
		[allEntities, updateWorkflow, updateForm, updateAgent, updateApplication],
	);

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Entity Management
					</h1>
					<p className="mt-2 text-muted-foreground">
						Manage organization and access settings for workflows, forms,
						agents, and apps
					</p>
				</div>
				<Button
					variant="outline"
					size="icon"
					onClick={handleRefresh}
					title="Refresh"
				>
					<RefreshCw className="h-4 w-4" />
				</Button>
			</div>

			{/* Main Content - Two Column Layout */}
			<div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-5 gap-6">
				{/* Left Column: Entities List */}
				<div className="lg:col-span-2 flex flex-col min-h-0">
					{/* Relationship Filter Banner */}
					{relationshipFilter && (
						<div className="flex items-center gap-2 mb-4 p-3 rounded-lg border bg-accent/50">
							<Network className="h-4 w-4 text-primary" />
							<span className="text-sm">
								Related to: <strong>{relationshipFilter.entityName}</strong>
							</span>
							<div className="flex items-center gap-1 ml-auto">
								<Button
									variant="outline"
									size="sm"
									onClick={() => setIsGraphDialogOpen(true)}
								>
									<Network className="h-4 w-4 mr-1" />
									View Graph
								</Button>
								<Button
									variant="ghost"
									size="sm"
									onClick={handleClearRelationshipFilter}
								>
									<X className="h-4 w-4 mr-1" />
									Clear
								</Button>
							</div>
						</div>
					)}

					{/* Toolbar: Select All + Search + Filters + Sort */}
					<div className="flex items-center gap-2 mb-4">
						<Checkbox
							checked={allSelected}
							onCheckedChange={handleSelectAll}
							aria-label="Select all"
							title={
								allSelected
									? "Deselect all"
									: someSelected
										? "Select all"
										: "Select all"
							}
							className={cn(
								"h-5 w-5",
								someSelected && "data-[state=checked]:bg-muted",
							)}
							ref={(el) => {
								if (el) {
									(el as HTMLButtonElement).dataset.state = someSelected
										? "indeterminate"
										: allSelected
											? "checked"
											: "unchecked";
								}
							}}
						/>
						<div className="relative flex-1">
							<Input
								placeholder="Search entities..."
								value={searchTerm}
								onChange={(e) => setSearchTerm(e.target.value)}
								className="pr-8"
							/>
							{searchTerm && (
								<Button
									variant="ghost"
									size="icon"
									className="absolute right-0 top-0 h-full w-8 hover:bg-transparent"
									onClick={() => setSearchTerm("")}
								>
									<X className="h-4 w-4" />
								</Button>
							)}
						</div>
						<FilterPopover
							typeFilter={typeFilter}
							setTypeFilter={setTypeFilter}
							orgFilter={orgFilter}
							setOrgFilter={setOrgFilter}
							accessFilter={accessFilter}
							setAccessFilter={setAccessFilter}
							organizations={organizations ?? []}
							activeFilterCount={activeFilterCount}
							onClearFilters={handleClearFilters}
						/>
						<Button
							variant="outline"
							size="sm"
							className="h-9"
							onClick={cycleSortBy}
							title={`Sort by: ${sortBy}`}
						>
							{sortAsc ? (
								<ArrowUp className="h-4 w-4 mr-2" />
							) : (
								<ArrowDown className="h-4 w-4 mr-2" />
							)}
							{sortBy === "name"
								? "Name"
								: sortBy === "date"
									? "Date"
									: "Type"}
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-9 w-9"
							onClick={() => setSortAsc((prev) => !prev)}
							title={sortAsc ? "Ascending" : "Descending"}
						>
							{sortAsc ? (
								<ArrowUp className="h-4 w-4" />
							) : (
								<ArrowDown className="h-4 w-4" />
							)}
						</Button>
					</div>

					{/* Selection info */}
					{(selectedIds.size > 0 || isUpdating) && (
						<div className="flex items-center gap-2 mb-2 text-sm text-muted-foreground">
							{isUpdating && (
								<Loader2 className="h-4 w-4 animate-spin text-primary" />
							)}
							<span>
								{isUpdating
									? "Updating..."
									: `${selectedIds.size} selected`}
							</span>
							{selectedIds.size > 0 && !isUpdating && (
								<Button
									variant="ghost"
									size="sm"
									className="h-6 px-2 text-xs"
									onClick={() => setSelectedIds(new Set())}
								>
									Clear
								</Button>
							)}
						</div>
					)}

					{/* Entity List */}
					<div className="flex-1 min-h-0 overflow-y-auto">
						{isLoading || (relationshipFilter && loadingGraph) ? (
							<div className="space-y-2">
								{[...Array(5)].map((_, i) => (
									<Skeleton key={i} className="h-16 w-full" />
								))}
							</div>
						) : filteredEntities.length > 0 ? (
							<div className="space-y-2 pr-2">
								{filteredEntities.map((entity) => (
									<EntityCard
										key={`${entity.entityType}-${entity.id}`}
										entity={entity}
										selected={selectedIds.has(entity.id)}
										onSelect={(selected) =>
											handleSelectEntity(entity.id, selected)
										}
										onShowRelationships={handleShowRelationships}
										organizations={organizations ?? []}
										selectedIds={selectedIds}
										allEntities={allEntities}
									/>
								))}
							</div>
						) : (
							<Card>
								<CardContent className="flex flex-col items-center justify-center py-12 text-center">
									<Filter className="h-12 w-12 text-muted-foreground" />
									<h3 className="mt-4 text-lg font-semibold">
										{relationshipFilter
											? "No related entities found"
											: searchTerm || activeFilterCount > 0
												? "No entities match your filters"
												: "No entities found"}
									</h3>
									<p className="mt-2 text-sm text-muted-foreground">
										{relationshipFilter
											? "This entity has no dependencies"
											: searchTerm || activeFilterCount > 0
												? "Try adjusting your filters"
												: "Create workflows, forms, or agents to manage them here"}
									</p>
								</CardContent>
							</Card>
						)}
					</div>
				</div>

				{/* Right Column: Drop Targets */}
				<div className="lg:col-span-3 flex flex-col gap-4">
					{/* Organizations Section */}
					<div className="max-h-[50%] flex flex-col">
						<div className="flex items-center gap-2 mb-3">
							<Building2 className="h-5 w-5 text-muted-foreground" />
							<h3 className="text-lg font-semibold">Organizations</h3>
						</div>
						<div className="space-y-1.5 overflow-y-auto">
							<OrgDropTarget organization={null} onDrop={handleOrgDrop} />
							{organizations?.map((org) => (
								<OrgDropTarget
									key={org.id}
									organization={org}
									onDrop={handleOrgDrop}
								/>
							))}
						</div>
					</div>

					{/* Access Levels Section */}
					<div className="max-h-[50%] flex flex-col">
						<div className="flex items-center gap-2 mb-3">
							<Shield className="h-5 w-5 text-muted-foreground" />
							<h3 className="text-lg font-semibold">Access Levels</h3>
						</div>
						<div className="space-y-1.5 overflow-y-auto">
							<RoleDropTarget role="authenticated" onDrop={handleRoleDrop} />
							<RoleDropTarget role="clear-roles" onDrop={handleRoleDrop} />
							{roles?.map((role) => (
								<RoleDropTarget
									key={role.id}
									role={role}
									onDrop={handleRoleDrop}
								/>
							))}
						</div>
					</div>
				</div>
			</div>

			{/* Dependency Graph Dialog */}
			<DependencyGraphDialog
				open={isGraphDialogOpen}
				onOpenChange={setIsGraphDialogOpen}
				entityName={relationshipFilter?.entityName ?? ""}
				entityType={relationshipFilter?.entityType ?? null}
				graphData={graphData ?? null}
				isLoading={loadingGraph}
			/>
		</div>
	);
}
