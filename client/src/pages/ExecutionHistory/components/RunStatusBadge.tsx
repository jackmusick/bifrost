/**
 * Status badge for the History feed with an explicit visual hierarchy:
 * the common case (success) renders quietly — color lives only on the
 * icon — while failures are the loudest elements on the page. This is
 * intentionally NOT the loud-green `ExecutionStatusBadge` used on detail
 * views; in a list of mostly-successful runs, success is the non-event.
 */

import {
	AlertTriangle,
	CheckCircle2,
	Clock,
	Loader2,
	XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface RunStatusBadgeProps {
	status: string;
	/** ISO datetime a Scheduled run will fire; shown via title tooltip. */
	scheduledAt?: string | null;
}

export function RunStatusBadge({ status, scheduledAt }: RunStatusBadgeProps) {
	switch (status) {
		case "Success":
			return (
				<Badge
					variant="outline"
					className="gap-1 font-normal text-muted-foreground"
				>
					<CheckCircle2 className="h-3 w-3 text-green-500" />
					Completed
				</Badge>
			);
		case "Failed":
			return (
				<Badge variant="destructive" className="gap-1">
					<XCircle className="h-3 w-3" />
					Failed
				</Badge>
			);
		case "Timeout":
			return (
				<Badge variant="destructive" className="gap-1">
					<Clock className="h-3 w-3" />
					Timed out
				</Badge>
			);
		case "CompletedWithErrors":
			return (
				<Badge
					variant="outline"
					className="gap-1 border-yellow-600/50 font-normal text-yellow-600 dark:text-yellow-500"
				>
					<AlertTriangle className="h-3 w-3" />
					Completed with errors
				</Badge>
			);
		case "Running":
			return (
				<Badge variant="secondary" className="gap-1">
					<Loader2 className="h-3 w-3 animate-spin" />
					Running
				</Badge>
			);
		case "Pending":
			return (
				<Badge
					variant="outline"
					className="gap-1 font-normal text-muted-foreground"
				>
					<Clock className="h-3 w-3" />
					Pending
				</Badge>
			);
		case "Scheduled": {
			let title: string | undefined;
			if (scheduledAt) {
				try {
					title = `Scheduled for ${new Date(scheduledAt).toLocaleString()}`;
				} catch {
					title = `Scheduled for ${scheduledAt}`;
				}
			}
			return (
				<Badge
					variant="outline"
					className="gap-1 border-sky-500/50 font-normal text-sky-700 dark:text-sky-300"
					{...(title ? { title } : {})}
				>
					<Clock className="h-3 w-3" />
					Scheduled
				</Badge>
			);
		}
		case "Cancelling":
			return (
				<Badge
					variant="outline"
					className="gap-1 border-orange-500/50 font-normal text-orange-600 dark:text-orange-400"
				>
					<Loader2 className="h-3 w-3 animate-spin" />
					Cancelling
				</Badge>
			);
		case "Cancelled":
			return (
				<Badge
					variant="outline"
					className="gap-1 font-normal text-muted-foreground"
				>
					<XCircle className="h-3 w-3" />
					Cancelled
				</Badge>
			);
		default:
			return (
				<Badge variant="outline" className="font-normal">
					{status}
				</Badge>
			);
	}
}
