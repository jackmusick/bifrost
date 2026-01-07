/**
 * Workflow Sidebar Component
 *
 * Collapsible sidebar for filtering workflows by category and entity usage.
 * Shows categories and entities (forms, apps, agents) with workflow counts.
 */

import { useState } from "react";
import {
	ChevronDown,
	ChevronRight,
	FileText,
	AppWindow,
	Bot,
	X,
	Tag,
	PanelLeftClose,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

type EntityUsage = components["schemas"]["EntityUsage"];

/** Category with workflow count */
export interface CategoryCount {
	name: string;
	count: number;
}

interface CategorySectionProps {
	categories: CategoryCount[];
	selectedCategory: string | null;
	onSelect: (category: string | null) => void;
	isLoading: boolean;
}

function CategorySection({
	categories,
	selectedCategory,
	onSelect,
	isLoading,
}: CategorySectionProps) {
	const [isExpanded, setIsExpanded] = useState(true);

	return (
		<div className="border-b">
			<button
				onClick={() => setIsExpanded(!isExpanded)}
				className="flex items-center justify-between w-full py-3 pl-3 pr-6 hover:bg-muted/50 transition-colors text-left"
			>
				<div className="flex items-center gap-2">
					{isExpanded ? (
						<ChevronDown className="h-4 w-4 text-muted-foreground" />
					) : (
						<ChevronRight className="h-4 w-4 text-muted-foreground" />
					)}
					<Tag className="h-4 w-4 text-muted-foreground" />
					<span className="font-medium text-sm">Categories</span>
				</div>
				<Badge variant="secondary" className="text-xs">
					{isLoading ? "..." : categories.length}
				</Badge>
			</button>

			{isExpanded && (
				<div className="pb-2">
					{isLoading ? (
						<div className="px-3 space-y-2">
							{[...Array(3)].map((_, i) => (
								<Skeleton key={i} className="h-8 w-full" />
							))}
						</div>
					) : categories.length === 0 ? (
						<div className="px-6 py-2 text-xs text-muted-foreground italic">
							No categories found
						</div>
					) : (
						<div className="space-y-0.5">
							{categories.map((cat) => (
								<button
									key={cat.name}
									onClick={() =>
										onSelect(
											selectedCategory === cat.name
												? null
												: cat.name,
										)
									}
									className={cn(
										"flex items-center w-full px-6 py-1.5 text-sm transition-colors",
										selectedCategory === cat.name
											? "bg-primary/10 text-primary font-medium"
											: "hover:bg-muted/50 text-foreground",
									)}
								>
									<span className="truncate flex-1 text-left min-w-0">
										{cat.name}
									</span>
									<Badge
										variant="secondary"
										className="text-xs ml-auto shrink-0"
									>
										{cat.count}
									</Badge>
								</button>
							))}
						</div>
					)}
				</div>
			)}
		</div>
	);
}

interface EntitySectionProps {
	title: string;
	icon: React.ReactNode;
	entities: EntityUsage[];
	selectedId: string | null;
	onSelect: (id: string | null) => void;
	isLoading: boolean;
}

function EntitySection({
	title,
	icon,
	entities,
	selectedId,
	onSelect,
	isLoading,
}: EntitySectionProps) {
	const [isExpanded, setIsExpanded] = useState(true);

	return (
		<div className="border-b last:border-b-0">
			<button
				onClick={() => setIsExpanded(!isExpanded)}
				className="flex items-center justify-between w-full py-3 pl-3 pr-6 hover:bg-muted/50 transition-colors text-left"
			>
				<div className="flex items-center gap-2">
					{isExpanded ? (
						<ChevronDown className="h-4 w-4 text-muted-foreground" />
					) : (
						<ChevronRight className="h-4 w-4 text-muted-foreground" />
					)}
					{icon}
					<span className="font-medium text-sm">{title}</span>
				</div>
				<Badge variant="secondary" className="text-xs">
					{isLoading ? "..." : entities.length}
				</Badge>
			</button>

			{isExpanded && (
				<div className="pb-2">
					{isLoading ? (
						<div className="px-3 space-y-2">
							{[...Array(3)].map((_, i) => (
								<Skeleton key={i} className="h-8 w-full" />
							))}
						</div>
					) : entities.length === 0 ? (
						<div className="px-6 py-2 text-xs text-muted-foreground italic">
							No {title.toLowerCase()} found
						</div>
					) : (
						<div className="space-y-0.5">
							{entities.map((entity) => (
								<button
									key={entity.id}
									onClick={() =>
										onSelect(
											selectedId === entity.id
												? null
												: entity.id,
										)
									}
									className={cn(
										"flex items-center w-full px-6 py-1.5 text-sm transition-colors",
										selectedId === entity.id
											? "bg-primary/10 text-primary font-medium"
											: "hover:bg-muted/50 text-foreground",
									)}
								>
									<span className="truncate flex-1 text-left min-w-0">
										{entity.name}
									</span>
									<Badge
										variant={
											entity.workflow_count === 0
												? "outline"
												: "secondary"
										}
										className={cn(
											"text-xs ml-auto shrink-0",
											entity.workflow_count === 0 &&
												"text-muted-foreground",
										)}
									>
										{entity.workflow_count}
									</Badge>
								</button>
							))}
						</div>
					)}
				</div>
			)}
		</div>
	);
}

export interface WorkflowSidebarProps {
	/** Categories with workflow counts */
	categories: CategoryCount[];
	/** Whether categories are loading */
	categoriesLoading?: boolean;
	/** Selected category filter */
	selectedCategory: string | null;
	/** Callback when category filter changes */
	onCategorySelect: (category: string | null) => void;
	/** Selected form ID filter */
	selectedFormId: string | null;
	/** Selected app ID filter */
	selectedAppId: string | null;
	/** Selected agent ID filter */
	selectedAgentId: string | null;
	/** Callback when form filter changes */
	onFormSelect: (formId: string | null) => void;
	/** Callback when app filter changes */
	onAppSelect: (appId: string | null) => void;
	/** Callback when agent filter changes */
	onAgentSelect: (agentId: string | null) => void;
	/** Organization scope for filtering */
	scope?: string;
	/** Callback to close/collapse the sidebar */
	onClose?: () => void;
	/** Additional CSS classes */
	className?: string;
}

/**
 * Workflow Sidebar
 *
 * Shows categories and entities (forms, apps, agents) with workflow counts.
 * Click a category or entity to filter the workflow list.
 */
export function WorkflowSidebar({
	categories,
	categoriesLoading = false,
	selectedCategory,
	onCategorySelect,
	selectedFormId,
	selectedAppId,
	selectedAgentId,
	onFormSelect,
	onAppSelect,
	onAgentSelect,
	scope,
	onClose,
	className,
}: WorkflowSidebarProps) {
	const { data, isLoading } = $api.useQuery(
		"get",
		"/api/workflows/usage-stats",
		{
			params: {
				query: {
					scope,
				},
			},
		},
	);

	const hasActiveFilter =
		selectedCategory !== null ||
		selectedFormId !== null ||
		selectedAppId !== null ||
		selectedAgentId !== null;

	const clearFilters = () => {
		onCategorySelect(null);
		onFormSelect(null);
		onAppSelect(null);
		onAgentSelect(null);
	};

	// Find selected filter name for display
	const getSelectedFilterName = (): string | null => {
		if (selectedCategory) {
			return selectedCategory;
		}
		if (selectedFormId && data?.forms) {
			return data.forms.find((f) => f.id === selectedFormId)?.name ?? null;
		}
		if (selectedAppId && data?.apps) {
			return data.apps.find((a) => a.id === selectedAppId)?.name ?? null;
		}
		if (selectedAgentId && data?.agents) {
			return (
				data.agents.find((a) => a.id === selectedAgentId)?.name ?? null
			);
		}
		return null;
	};

	const selectedFilterName = getSelectedFilterName();

	return (
		<div
			className={cn(
				"flex flex-col border rounded-lg bg-card h-full",
				className,
			)}
		>
			{/* Header */}
			<div className="flex items-center justify-between p-3 border-b">
				<span className="font-semibold text-sm">Filters</span>
				<div className="flex items-center gap-1">
					{hasActiveFilter && (
						<Button
							variant="ghost"
							size="sm"
							onClick={clearFilters}
							className="h-6 px-2 text-xs"
						>
							<X className="h-3 w-3 mr-1" />
							Clear
						</Button>
					)}
					{onClose && (
						<Button
							variant="ghost"
							size="icon"
							onClick={onClose}
							className="h-6 w-6"
							title="Hide filters"
						>
							<PanelLeftClose className="h-4 w-4" />
						</Button>
					)}
				</div>
			</div>

			{/* Active Filter Display */}
			{hasActiveFilter && selectedFilterName && (
				<div className="px-3 py-2 bg-primary/5 border-b">
					<div className="text-xs text-muted-foreground">
						Filtering by:
					</div>
					<div className="text-sm font-medium text-primary truncate">
						{selectedFilterName}
					</div>
				</div>
			)}

			{/* Filter Sections */}
			<div className="flex-1 overflow-auto">
				{/* By Category */}
				<div className="px-3 pt-3 pb-1">
					<span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
						By Category
					</span>
				</div>
				<CategorySection
					categories={categories}
					selectedCategory={selectedCategory}
					onSelect={onCategorySelect}
					isLoading={categoriesLoading}
				/>

				{/* By Usage */}
				<div className="px-3 pt-3 pb-1">
					<span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
						By Usage
					</span>
				</div>
				<EntitySection
					title="Forms"
					icon={<FileText className="h-4 w-4 text-muted-foreground" />}
					entities={data?.forms ?? []}
					selectedId={selectedFormId}
					onSelect={(id) => {
						onFormSelect(id);
						if (id) {
							onAppSelect(null);
							onAgentSelect(null);
						}
					}}
					isLoading={isLoading}
				/>
				<EntitySection
					title="Apps"
					icon={
						<AppWindow className="h-4 w-4 text-muted-foreground" />
					}
					entities={data?.apps ?? []}
					selectedId={selectedAppId}
					onSelect={(id) => {
						onAppSelect(id);
						if (id) {
							onFormSelect(null);
							onAgentSelect(null);
						}
					}}
					isLoading={isLoading}
				/>
				<EntitySection
					title="Agents"
					icon={<Bot className="h-4 w-4 text-muted-foreground" />}
					entities={data?.agents ?? []}
					selectedId={selectedAgentId}
					onSelect={(id) => {
						onAgentSelect(id);
						if (id) {
							onFormSelect(null);
							onAppSelect(null);
						}
					}}
					isLoading={isLoading}
				/>
			</div>
		</div>
	);
}

export default WorkflowSidebar;
