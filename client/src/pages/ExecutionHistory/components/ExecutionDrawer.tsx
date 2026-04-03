import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
	SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";
import { ExecutionDetails } from "@/pages/ExecutionDetails";

interface ExecutionDrawerProps {
	executionId: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function ExecutionDrawer({
	executionId,
	open,
	onOpenChange,
}: ExecutionDrawerProps) {
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
				<div className="sticky top-0 bg-background z-10 px-6 pt-6 pb-4 border-b">
					<SheetHeader>
						<div className="flex items-center justify-between">
							<SheetTitle className="text-lg">
								Execution Details
							</SheetTitle>
							<Button
								variant="outline"
								size="sm"
								onClick={handleOpenInNewTab}
								disabled={!executionId}
							>
								<ExternalLink className="h-4 w-4 mr-2" />
								Open in new tab
							</Button>
						</div>
						<SheetDescription>
							View workflow execution details and logs
						</SheetDescription>
					</SheetHeader>
				</div>

				{executionId && (
					<ExecutionDetails
						executionId={executionId}
						embedded
					/>
				)}
			</SheetContent>
		</Sheet>
	);
}
