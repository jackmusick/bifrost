import { Network } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { DependencyGraph } from "@/components/dependencies/DependencyGraph";
import type { GraphNode, GraphEdge } from "@/hooks/useDependencyGraph";
import type { EntityType } from "./types";

export interface DependencyGraphDialogProps {
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

export function DependencyGraphDialog({
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
				<div className="flex-1 min-h-0 rounded-lg ring-1 ring-foreground/5 bg-background/50 overflow-hidden">
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
