import { AlertCircle, Download, X, RefreshCw } from "lucide-react";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ConflictReason } from "@/stores/editorStore";
import { CloudAlert } from "lucide-react";

interface FileTabConflictMenuProps {
	fileName: string;
	conflictReason: ConflictReason;
	onResolve: (
		action: "keep_mine" | "use_server" | "recreate" | "close",
	) => void;
}

/**
 * Dropdown menu for resolving file conflicts
 * Shows different options based on conflict reason:
 * - content_changed: Keep My Changes | Use Server Version
 * - path_not_found: Recreate File | Close Tab
 */
export function FileTabConflictMenu({
	fileName,
	conflictReason,
	onResolve,
}: FileTabConflictMenuProps) {
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<button
					className="flex-shrink-0 rounded-md p-0.5 hover:bg-orange-500/20 transition-colors"
					title={
						conflictReason === "content_changed"
							? "File content has changed on the server"
							: "File path no longer exists"
					}
					onClick={(e) => e.stopPropagation()}
				>
					<CloudAlert className="h-3.5 w-3.5 text-orange-500" />
				</button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="start" className="w-56 z-[100]">
				<div className="px-2 py-1.5 text-sm font-semibold text-orange-600 dark:text-orange-400 flex items-center gap-2">
					<AlertCircle className="h-4 w-4" />
					<span>File Conflict</span>
				</div>
				<div className="px-2 py-1 text-xs text-muted-foreground">
					{fileName}
				</div>
				<DropdownMenuSeparator />

				{conflictReason === "content_changed" ? (
					<>
						<DropdownMenuItem
							onClick={() => onResolve("keep_mine")}
							className="cursor-pointer"
						>
							<Download className="mr-2 h-4 w-4" />
							<div className="flex flex-col">
								<span>Keep My Changes</span>
								<span className="text-xs text-muted-foreground">
									Overwrite server version
								</span>
							</div>
						</DropdownMenuItem>
						<DropdownMenuItem
							onClick={() => onResolve("use_server")}
							className="cursor-pointer"
						>
							<RefreshCw className="mr-2 h-4 w-4" />
							<div className="flex flex-col">
								<span>Use Server Version</span>
								<span className="text-xs text-muted-foreground">
									Discard my changes
								</span>
							</div>
						</DropdownMenuItem>
					</>
				) : (
					<>
						<DropdownMenuItem
							onClick={() => onResolve("recreate")}
							className="cursor-pointer"
						>
							<Download className="mr-2 h-4 w-4" />
							<div className="flex flex-col">
								<span>Recreate File</span>
								<span className="text-xs text-muted-foreground">
									Save to server
								</span>
							</div>
						</DropdownMenuItem>
						<DropdownMenuItem
							onClick={() => onResolve("close")}
							className="cursor-pointer text-destructive focus:text-destructive"
						>
							<X className="mr-2 h-4 w-4" />
							<div className="flex flex-col">
								<span>Close Tab</span>
								<span className="text-xs text-muted-foreground">
									Discard changes
								</span>
							</div>
						</DropdownMenuItem>
					</>
				)}
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
