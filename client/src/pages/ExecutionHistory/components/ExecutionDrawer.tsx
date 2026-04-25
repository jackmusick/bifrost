import { useState } from "react";
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ExternalLink, Copy } from "lucide-react";
import { toast } from "sonner";
import { ExecutionDetails } from "@/pages/ExecutionDetails";

interface ExecutionDrawerProps {
	executionId: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onExecutionChange?: (newExecutionId: string) => void;
}

export function ExecutionDrawer({
	executionId,
	open,
	onOpenChange,
	onExecutionChange,
}: ExecutionDrawerProps) {
	const [actionsContainer, setActionsContainer] =
		useState<HTMLDivElement | null>(null);

	const handleOpenInNewTab = () => {
		if (executionId) {
			window.open(`/history/${executionId}`, "_blank");
		}
	};

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				className="w-full sm:max-w-xl md:max-w-2xl overflow-y-auto p-0"
			>
				<div className="sticky top-0 bg-background z-10 px-4 py-2 border-b">
					<SheetHeader>
						<div className="flex items-center justify-between">
							<SheetTitle className="text-sm font-medium text-muted-foreground">
								Execution Details
							</SheetTitle>
							<div className="flex items-center gap-1">
								<div
									ref={setActionsContainer}
									className="flex items-center gap-1"
								/>
								<Button
									variant="ghost"
									size="icon"
									className="h-7 w-7"
									onClick={() => {
										if (executionId) {
											navigator.clipboard.writeText(executionId);
											toast.success("Execution ID copied");
										}
									}}
									disabled={!executionId}
									title="Copy execution ID"
								>
									<Copy className="h-3.5 w-3.5" />
								</Button>
								<Button
									variant="ghost"
									size="icon"
									className="h-7 w-7"
									onClick={handleOpenInNewTab}
									disabled={!executionId}
								>
									<ExternalLink className="h-3.5 w-3.5" />
								</Button>
							</div>
						</div>
					</SheetHeader>
				</div>

				{executionId && (
					<ExecutionDetails
						executionId={executionId}
						embedded
						actionsContainer={actionsContainer}
						onExecutionChange={onExecutionChange}
					/>
				)}
			</SheetContent>
		</Sheet>
	);
}
