/**
 * AgentSelectorDialog Component
 *
 * A dialog for selecting an agent with search, org badges, and descriptions.
 * Follows the same pattern as WorkflowSelectorDialog but simplified
 * (single-select only, no role mismatch logic).
 */

import { useCallback, useMemo, useState } from "react";
import { Bot, Building2, Globe, Loader2, Search } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useAgents } from "@/hooks/useAgents";
import { useOrganizations } from "@/hooks/useOrganizations";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

type AgentSummary = components["schemas"]["AgentSummary"];

export interface AgentSelectorDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	selectedAgentId: string | null;
	onSelect: (agentId: string) => void;
	title?: string;
	description?: string;
}

export function AgentSelectorDialog({
	open,
	onOpenChange,
	selectedAgentId,
	onSelect,
	title,
	description,
}: AgentSelectorDialogProps) {
	const [localSelection, setLocalSelection] = useState<string | null>(
		selectedAgentId,
	);
	const [searchQuery, setSearchQuery] = useState("");

	// Reset local state when dialog opens
	const handleOpenChange = useCallback(
		(nextOpen: boolean) => {
			if (nextOpen) {
				setLocalSelection(selectedAgentId);
				setSearchQuery("");
			}
			onOpenChange(nextOpen);
		},
		[selectedAgentId, onOpenChange],
	);

	// Fetch agents and organizations
	const { data: agents, isLoading, error } = useAgents();
	const { data: organizations } = useOrganizations({});

	const getOrgName = useCallback(
		(orgId: string | null | undefined): string | null => {
			if (!orgId) return null;
			const org = organizations?.find(
				(o: Organization) => o.id === orgId,
			);
			return org?.name || orgId;
		},
		[organizations],
	);

	// Filter and sort
	const filteredAgents = useMemo(() => {
		let list = (agents ?? []).filter(
			(a): a is AgentSummary & { id: string } =>
				a.id != null && a.is_active,
		);

		if (searchQuery.trim()) {
			const query = searchQuery.toLowerCase();
			list = list.filter(
				(a) =>
					a.name.toLowerCase().includes(query) ||
					a.description?.toLowerCase().includes(query),
			);
		}

		// Sort: global first, then alphabetical
		return [...list].sort((a, b) => {
			const aIsGlobal = !a.organization_id;
			const bIsGlobal = !b.organization_id;
			if (aIsGlobal !== bIsGlobal) return aIsGlobal ? -1 : 1;
			return a.name.localeCompare(b.name);
		});
	}, [agents, searchQuery]);

	const handleConfirm = useCallback(() => {
		if (localSelection) {
			onSelect(localSelection);
		}
		handleOpenChange(false);
	}, [localSelection, onSelect, handleOpenChange]);

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
				<DialogHeader>
					<DialogTitle>{title || "Select Agent"}</DialogTitle>
					<DialogDescription>
						{description ||
							"Choose an agent to receive events from this source."}
					</DialogDescription>
				</DialogHeader>

				<div className="flex-1 min-h-0 flex flex-col rounded-lg ring-1 ring-foreground/5 overflow-hidden">
					{/* Search */}
					<div className="p-3 border-b bg-muted/20">
						<div className="relative">
							<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
							<Input
								placeholder="Search agents..."
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								className="pl-9"
							/>
						</div>
					</div>

					{/* Agent list */}
					<div className="flex-1 overflow-y-auto p-2">
						{isLoading ? (
							<div className="flex items-center justify-center py-8">
								<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
								<span className="ml-2 text-sm text-muted-foreground">
									Loading agents...
								</span>
							</div>
						) : error ? (
							<div className="flex items-center justify-center py-8 text-destructive">
								<span className="text-sm">
									Failed to load agents
								</span>
							</div>
						) : filteredAgents.length === 0 ? (
							<div className="flex items-center justify-center py-8 text-muted-foreground">
								<span className="text-sm">
									{searchQuery
										? "No agents match your search"
										: "No agents available"}
								</span>
							</div>
						) : (
							<div className="space-y-1">
								{filteredAgents.map((agent) => (
									<AgentListItem
										key={agent.id}
										agent={agent}
										isSelected={
											localSelection === agent.id
										}
										onToggle={() =>
											setLocalSelection(agent.id)
										}
										orgName={getOrgName(
											agent.organization_id,
										)}
									/>
								))}
							</div>
						)}
					</div>
				</div>

				<DialogFooter>
					<Button
						variant="outline"
						onClick={() => handleOpenChange(false)}
					>
						Cancel
					</Button>
					<Button
						onClick={handleConfirm}
						disabled={!localSelection}
					>
						Select
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

function AgentListItem({
	agent,
	isSelected,
	onToggle,
	orgName,
}: {
	agent: AgentSummary & { id: string };
	isSelected: boolean;
	onToggle: () => void;
	orgName: string | null;
}) {
	return (
		<button
			type="button"
			onClick={onToggle}
			className={cn(
				"w-full text-left p-3 rounded-lg border transition-colors",
				"hover:bg-accent/50",
				isSelected
					? "border-primary bg-primary/5"
					: "border-transparent bg-transparent",
			)}
		>
			<div className="flex items-start gap-3">
				{/* Radio indicator */}
				<div className="flex-shrink-0 mt-0.5">
					<div
						className={cn(
							"h-4 w-4 rounded-full border-2 flex items-center justify-center",
							isSelected
								? "border-primary bg-primary"
								: "border-muted-foreground",
						)}
					>
						{isSelected && (
							<div className="h-1.5 w-1.5 rounded-full bg-white" />
						)}
					</div>
				</div>

				{/* Agent info */}
				<div className="flex-1 min-w-0">
					<div className="flex items-center gap-2 flex-wrap">
						<Bot className="h-4 w-4 text-muted-foreground flex-shrink-0" />
						<span className="font-medium">{agent.name}</span>
						{orgName ? (
							<Badge
								variant="outline"
								className="text-xs px-1.5 py-0 h-5 text-muted-foreground"
							>
								<Building2 className="h-3 w-3 mr-1" />
								{orgName}
							</Badge>
						) : (
							<Badge
								variant="default"
								className="text-xs px-1.5 py-0 h-5"
							>
								<Globe className="h-3 w-3 mr-1" />
								Global
							</Badge>
						)}
					</div>
					<p className={cn(
						"text-sm text-muted-foreground mt-0.5 line-clamp-2",
						!agent.description && "italic",
					)}>
						{agent.description || "No description"}
					</p>
				</div>
			</div>
		</button>
	);
}
