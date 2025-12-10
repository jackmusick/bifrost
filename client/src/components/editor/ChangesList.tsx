import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { FileChange } from "@/hooks/useGitHub";

interface ChangesListProps {
	changes: FileChange[];
	hasConflicts: boolean;
	onFileClick: (file: FileChange) => void;
	isLoading?: boolean;
}

export function ChangesList({
	changes,
	hasConflicts,
	onFileClick,
	isLoading = false,
}: ChangesListProps) {
	const [isOpen, setIsOpen] = useState(true);

	const getStatusIcon = (status: string) => {
		switch (status) {
			case "M":
				return <span className="text-blue-500">M</span>;
			case "A":
				return <span className="text-green-500">A</span>;
			case "D":
				return <span className="text-red-500">D</span>;
			case "U":
				return <span className="text-yellow-500">U</span>;
			case "C":
				return <span className="text-orange-500">C</span>;
			default:
				return <span className="text-gray-500">?</span>;
		}
	};

	return (
		<Collapsible
			open={isOpen}
			onOpenChange={setIsOpen}
			className="flex flex-col min-h-0"
		>
			<CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-2 hover:bg-muted/50 transition-colors border-b flex-shrink-0">
				<div className="flex items-center gap-2">
					{isOpen ? (
						<ChevronDown className="h-4 w-4" />
					) : (
						<ChevronRight className="h-4 w-4" />
					)}
					<span className="text-sm font-medium">
						Changes ({changes.length})
					</span>
				</div>
			</CollapsibleTrigger>
			<CollapsibleContent className="flex-1 min-h-0">
				<div className="h-full overflow-y-auto px-4 py-2">
					{isLoading ? (
						<div className="flex flex-col items-center justify-center py-8 text-center">
							<Loader2 className="h-6 w-6 text-muted-foreground mb-2 animate-spin" />
							<p className="text-xs text-muted-foreground">
								Loading changes...
							</p>
						</div>
					) : changes.length === 0 && !hasConflicts ? (
						<div className="flex flex-col items-center justify-center py-8 text-center">
							<Check className="h-6 w-6 text-green-500 mb-2" />
							<p className="text-xs text-muted-foreground">
								No changes
							</p>
						</div>
					) : (
						<div className="space-y-1">
							{changes.map((file) => (
								<button
									key={file.path}
									onClick={() => onFileClick(file)}
									className="flex items-center gap-2 w-full px-2 py-1 rounded text-xs hover:bg-muted/50 transition-colors"
								>
									{getStatusIcon(file.status)}
									<span className="truncate text-left flex-1">
										{file.path}
									</span>
									{file.additions !== null &&
										file.deletions !== null && (
											<span className="text-muted-foreground text-xs">
												+{file.additions} -
												{file.deletions}
											</span>
										)}
								</button>
							))}
						</div>
					)}
				</div>
			</CollapsibleContent>
		</Collapsible>
	);
}
