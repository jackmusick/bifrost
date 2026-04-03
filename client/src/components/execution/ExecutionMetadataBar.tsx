import { User, Building2, Clock, Timer } from "lucide-react";
import { ExecutionStatusBadge } from "./ExecutionStatusBadge";
import { formatDate } from "@/lib/utils";
import type { components } from "@/lib/v1";

type ExecutionStatus =
	| components["schemas"]["ExecutionStatus"]
	| "Cancelling"
	| "Cancelled";

interface ExecutionMetadataBarProps {
	workflowName: string;
	status: ExecutionStatus;
	executedByName?: string | null;
	orgName?: string | null;
	startedAt?: string | null;
	durationMs?: number | null;
	queuePosition?: number;
	waitReason?: string;
	availableMemoryMb?: number;
	requiredMemoryMb?: number;
}

function formatDuration(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	const minutes = Math.floor(ms / 60000);
	const seconds = ((ms % 60000) / 1000).toFixed(0);
	return `${minutes}m ${seconds}s`;
}

export function ExecutionMetadataBar({
	workflowName,
	status,
	executedByName,
	orgName,
	startedAt,
	durationMs,
	queuePosition,
	waitReason,
	availableMemoryMb,
	requiredMemoryMb,
}: ExecutionMetadataBarProps) {
	return (
		<div className="space-y-3">
			{/* Workflow name + status */}
			<div className="flex items-center justify-between gap-3 flex-wrap">
				<h3 className="text-lg font-semibold truncate">
					{workflowName}
				</h3>
				<ExecutionStatusBadge
					status={status}
					queuePosition={queuePosition}
					waitReason={waitReason}
					availableMemoryMb={availableMemoryMb}
					requiredMemoryMb={requiredMemoryMb}
				/>
			</div>
			{/* Compact metadata grid */}
			<div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<User className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">{executedByName || "Unknown"}</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Building2 className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">{orgName || "Global"}</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Clock className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">
						{startedAt ? formatDate(startedAt) : "Not started"}
					</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Timer className="h-3.5 w-3.5 flex-shrink-0" />
					<span>
						{durationMs != null
							? formatDuration(durationMs)
							: "In progress..."}
					</span>
				</div>
			</div>
		</div>
	);
}
