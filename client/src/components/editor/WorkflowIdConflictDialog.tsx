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
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { AlertTriangle } from "lucide-react";
import type { components } from "@/lib/v1";

type WorkflowIdConflict = components["schemas"]["WorkflowIdConflict"];

interface WorkflowIdConflictDialogProps {
	conflicts: WorkflowIdConflict[];
	open: boolean;
	onUseExisting: () => void;
	onGenerateNew: () => void;
	onCancel: () => void;
}

/**
 * Dialog shown when uploading/saving a workflow file that would overwrite
 * existing workflows and lose their IDs.
 *
 * Gives the user the choice to:
 * 1. Use the existing IDs from the database (preserves workflow continuity)
 * 2. Generate new IDs (creates new workflow entries, orphans old ones)
 * 3. Cancel the operation
 */
export function WorkflowIdConflictDialog({
	conflicts,
	open,
	onUseExisting,
	onGenerateNew,
	onCancel,
}: WorkflowIdConflictDialogProps) {
	return (
		<Dialog open={open} onOpenChange={(open) => !open && onCancel()}>
			<DialogContent className="sm:max-w-[600px]">
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-yellow-500" />
						Workflow ID Conflict
					</DialogTitle>
					<DialogDescription>
						{conflicts.length === 1
							? "This file contains a workflow that already exists in the database but the file doesn't have an ID in the decorator."
							: `This file contains ${conflicts.length} workflows that already exist in the database but don't have IDs in their decorators.`}
					</DialogDescription>
				</DialogHeader>

				<div className="max-h-[300px] overflow-y-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Workflow Name</TableHead>
								<TableHead>Function</TableHead>
								<TableHead>Existing ID</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{conflicts.map((conflict) => (
								<TableRow key={conflict.function_name}>
									<TableCell className="font-medium">
										{conflict.name}
									</TableCell>
									<TableCell className="font-mono text-sm text-muted-foreground">
										{conflict.function_name}
									</TableCell>
									<TableCell className="font-mono text-xs text-muted-foreground">
										{conflict.existing_id.substring(0, 8)}
										...
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				</div>

				<div className="text-sm text-muted-foreground space-y-2 border-t pt-4">
					<p>
						<strong>Use Existing IDs:</strong> The existing workflow
						IDs will be injected into the file. This preserves
						execution history, schedules, and any references to
						these workflows.
					</p>
					<p>
						<strong>Generate New IDs:</strong> New UUIDs will be
						created. The old workflow entries will become orphaned
						and their history may be lost.
					</p>
				</div>

				<DialogFooter className="flex gap-2">
					<Button variant="outline" onClick={onCancel}>
						Cancel
					</Button>
					<Button variant="destructive" onClick={onGenerateNew}>
						Generate New IDs
					</Button>
					<Button onClick={onUseExisting}>Use Existing IDs</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
