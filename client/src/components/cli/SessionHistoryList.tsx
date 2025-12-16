/**
 * SessionHistoryList - Shows execution history for a CLI session
 *
 * Displays a list of past executions with status, workflow name, and relative time.
 */

import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { ExecutionStatusIcon } from "@/components/execution/ExecutionStatusBadge";
import type { CLISessionExecutionSummary } from "@/services/cli";

interface SessionHistoryListProps {
	executions: CLISessionExecutionSummary[];
	currentExecutionId: string | null;
	onSelect: (executionId: string) => void;
}

export function SessionHistoryList({
	executions,
	currentExecutionId,
	onSelect,
}: SessionHistoryListProps) {
	if (executions.length === 0) {
		return (
			<div className="px-4 py-6 text-center text-sm text-muted-foreground">
				No executions yet
			</div>
		);
	}

	return (
		<div className="divide-y">
			{executions.map((execution) => {
				const isSelected = execution.id === currentExecutionId;
				const createdAt = new Date(execution.created_at);

				return (
					<button
						key={execution.id}
						onClick={() => onSelect(execution.id)}
						className={cn(
							"w-full px-4 py-2 text-left hover:bg-muted/50 transition-colors",
							"flex items-center gap-3",
							isSelected && "bg-muted",
						)}
					>
						<ExecutionStatusIcon
							status={execution.status}
							size="h-5 w-5"
						/>
						<div className="flex-1 min-w-0">
							<div className="text-sm font-medium truncate">
								{execution.workflow_name}
							</div>
							<div className="text-xs text-muted-foreground">
								{formatDistanceToNow(createdAt, {
									addSuffix: true,
								})}
								{execution.duration_ms != null && (
									<span className="ml-2">
										(
										{(execution.duration_ms / 1000).toFixed(
											1,
										)}
										s)
									</span>
								)}
							</div>
						</div>
					</button>
				);
			})}
		</div>
	);
}
