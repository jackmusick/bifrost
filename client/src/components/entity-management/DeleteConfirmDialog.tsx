import {
	AlertTriangle,
	Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { EntityType } from "./types";
import { ENTITY_CONFIG } from "./types";

export interface DeleteConfirmEntity {
	id: string;
	name: string;
	entityType: EntityType;
	slug?: string;
}

export interface DeleteConfirmDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	entities: DeleteConfirmEntity[];
	isDeleting: boolean;
	onConfirm: () => void;
	onCancel: () => void;
}

export function DeleteConfirmDialog({
	open,
	onOpenChange,
	entities,
	isDeleting,
	onConfirm,
	onCancel,
}: DeleteConfirmDialogProps) {
	return (
		<Dialog open={open} onOpenChange={(newOpen) => {
			if (!newOpen && !isDeleting) {
				onOpenChange(newOpen);
			}
		}}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-destructive" />
						Confirm Delete
					</DialogTitle>
					<DialogDescription>
						This action cannot be undone for workflows and apps. Forms and agents will be deactivated.
					</DialogDescription>
				</DialogHeader>
				<div className="space-y-3">
					<div className="space-y-2 max-h-60 overflow-y-auto">
						{entities.map((entity) => {
							const config = ENTITY_CONFIG[entity.entityType];
							return (
								<div
									key={entity.id}
									className="flex items-center gap-2 p-2 rounded-md bg-muted/50 ring-1 ring-foreground/5"
								>
									<Badge variant="outline" className={cn(config.color)}>
										{config.label}
									</Badge>
									<span className="text-sm truncate">{entity.name}</span>
								</div>
							);
						})}
					</div>
					{entities.some((e) => e.entityType === "app") && (
						<p className="text-sm text-destructive">
							Apps will be permanently deleted.
						</p>
					)}
					<div className="flex justify-end gap-2 pt-2">
						<Button
							variant="outline"
							onClick={onCancel}
							disabled={isDeleting}
						>
							Cancel
						</Button>
						<Button
							variant="destructive"
							onClick={onConfirm}
							disabled={isDeleting}
						>
							{isDeleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
							Delete {entities.length === 1 ? entities[0].name : `${entities.length} entities`}
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}
