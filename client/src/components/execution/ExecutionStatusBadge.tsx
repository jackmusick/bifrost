import { CheckCircle, XCircle, Loader2, Clock, PlayCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/v1";

// Re-export from generated types
export type ExecutionStatus = components["schemas"]["ExecutionStatus"];

interface ExecutionStatusBadgeProps {
	status: ExecutionStatus | string;
	/** Queue position for pending executions */
	queuePosition?: number;
	/** Reason for waiting (queued, memory_pressure) */
	waitReason?: string;
	/** Available memory in MB */
	availableMemoryMb?: number;
	/** Required memory in MB */
	requiredMemoryMb?: number;
	/** Optional className */
	className?: string;
}

/**
 * Renders a badge displaying execution status with appropriate styling
 */
export function ExecutionStatusBadge({
	status,
	queuePosition,
	waitReason,
	availableMemoryMb,
	requiredMemoryMb,
	className,
}: ExecutionStatusBadgeProps) {
	switch (status) {
		case "Success":
			return (
				<Badge variant="default" className={`bg-green-500 ${className ?? ""}`}>
					<CheckCircle className="mr-1 h-3 w-3" />
					Completed
				</Badge>
			);
		case "Failed":
			return (
				<Badge variant="destructive" className={className}>
					<XCircle className="mr-1 h-3 w-3" />
					Failed
				</Badge>
			);
		case "Running":
			return (
				<Badge variant="secondary" className={className}>
					<PlayCircle className="mr-1 h-3 w-3" />
					Running
				</Badge>
			);
		case "Pending": {
			if (waitReason === "queued" && queuePosition) {
				return (
					<Badge variant="outline" className={className}>
						<Clock className="mr-1 h-3 w-3" />
						Queued - Position {queuePosition}
					</Badge>
				);
			} else if (waitReason === "memory_pressure") {
				return (
					<Badge variant="outline" className={`border-orange-500 ${className ?? ""}`}>
						<Loader2 className="mr-1 h-3 w-3 animate-spin" />
						Heavy Load ({availableMemoryMb ?? "?"}MB / {requiredMemoryMb ?? "?"}MB)
					</Badge>
				);
			}
			return (
				<Badge variant="outline" className={className}>
					<Clock className="mr-1 h-3 w-3" />
					Pending
				</Badge>
			);
		}
		case "Cancelling":
			return (
				<Badge variant="secondary" className={`bg-orange-500 text-white ${className ?? ""}`}>
					<Loader2 className="mr-1 h-3 w-3 animate-spin" />
					Cancelling
				</Badge>
			);
		case "Cancelled":
			return (
				<Badge
					variant="outline"
					className={`border-gray-500 text-gray-600 dark:text-gray-400 ${className ?? ""}`}
				>
					<XCircle className="mr-1 h-3 w-3" />
					Cancelled
				</Badge>
			);
		case "CompletedWithErrors":
			return (
				<Badge variant="secondary" className={`bg-yellow-500 ${className ?? ""}`}>
					<XCircle className="mr-1 h-3 w-3" />
					Completed with Errors
				</Badge>
			);
		case "Timeout":
			return (
				<Badge variant="destructive" className={className}>
					<XCircle className="mr-1 h-3 w-3" />
					Timeout
				</Badge>
			);
		default:
			return (
				<Badge variant="outline" className={className}>
					{status}
				</Badge>
			);
	}
}

interface ExecutionStatusIconProps {
	status: ExecutionStatus | string;
	/** Icon size class, e.g., "h-12 w-12" */
	size?: string;
	/** Optional className */
	className?: string;
}

/**
 * Renders a large icon for execution status display
 */
export function ExecutionStatusIcon({
	status,
	size = "h-12 w-12",
	className,
}: ExecutionStatusIconProps) {
	const baseClasses = `${size} ${className ?? ""}`;

	switch (status) {
		case "Success":
			return <CheckCircle className={`${baseClasses} text-green-500`} />;
		case "Failed":
			return <XCircle className={`${baseClasses} text-red-500`} />;
		case "Running":
			return <Loader2 className={`${baseClasses} text-blue-500 animate-spin`} />;
		case "Pending":
			return <Clock className={`${baseClasses} text-gray-500`} />;
		case "Cancelling":
			return <Loader2 className={`${baseClasses} text-orange-500 animate-spin`} />;
		case "Cancelled":
			return <XCircle className={`${baseClasses} text-gray-500`} />;
		case "CompletedWithErrors":
			return <XCircle className={`${baseClasses} text-yellow-500`} />;
		case "Timeout":
			return <XCircle className={`${baseClasses} text-red-500`} />;
		default:
			return <Clock className={`${baseClasses} text-gray-500`} />;
	}
}

/**
 * Check if a status represents a completed execution
 */
export function isExecutionComplete(status: ExecutionStatus | string): boolean {
	return (
		status === "Success" ||
		status === "Failed" ||
		status === "CompletedWithErrors" ||
		status === "Timeout" ||
		status === "Cancelled"
	);
}

/**
 * Check if a status represents a running/in-progress execution
 */
export function isExecutionRunning(status: ExecutionStatus | string): boolean {
	return status === "Running" || status === "Pending" || status === "Cancelling";
}
