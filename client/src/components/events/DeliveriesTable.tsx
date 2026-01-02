import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
	RefreshCw,
	CheckCircle2,
	XCircle,
	Clock,
	Loader2,
	ExternalLink,
	AlertTriangle,
	Workflow as WorkflowIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { format } from "date-fns";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import {
	useRetryDelivery,
	type EventDelivery,
	type EventDeliveryStatus,
} from "@/services/events";

interface DeliveriesTableProps {
	deliveries: EventDelivery[];
	eventId?: string;
}

function getStatusIcon(status: EventDeliveryStatus) {
	switch (status) {
		case "pending":
			return <Clock className="h-4 w-4 text-muted-foreground" />;
		case "queued":
			return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
		case "success":
			return <CheckCircle2 className="h-4 w-4 text-green-500" />;
		case "failed":
			return <XCircle className="h-4 w-4 text-destructive" />;
		case "skipped":
			return <AlertTriangle className="h-4 w-4 text-amber-500" />;
	}
}

function getStatusLabel(status: EventDeliveryStatus) {
	switch (status) {
		case "pending":
			return "Pending";
		case "queued":
			return "Queued";
		case "success":
			return "Success";
		case "failed":
			return "Failed";
		case "skipped":
			return "Skipped";
	}
}

function getStatusVariant(
	status: EventDeliveryStatus,
): "default" | "secondary" | "destructive" | "outline" {
	switch (status) {
		case "success":
			return "default";
		case "failed":
			return "destructive";
		case "queued":
		case "pending":
			return "outline";
		default:
			return "secondary";
	}
}

export function DeliveriesTable({ deliveries }: DeliveriesTableProps) {
	const { isPlatformAdmin } = useAuth();
	const queryClient = useQueryClient();
	const retryMutation = useRetryDelivery();
	const [retryingId, setRetryingId] = useState<string | null>(null);

	const handleRetry = async (deliveryId: string) => {
		setRetryingId(deliveryId);
		try {
			await retryMutation.mutateAsync({
				params: {
					path: { delivery_id: deliveryId },
				},
			});
			toast.success("Delivery retry queued");
			// Refresh deliveries
			queryClient.invalidateQueries({
				predicate: (query) =>
					query.queryKey[0] === "get" &&
					(query.queryKey[1] as string)?.includes("/deliveries"),
			});
		} catch {
			toast.error("Failed to retry delivery");
		} finally {
			setRetryingId(null);
		}
	};

	if (deliveries.length === 0) {
		return (
			<div className="text-center py-6 text-muted-foreground">
				No deliveries for this event (no active subscriptions).
			</div>
		);
	}

	const getBorderColor = (status: EventDeliveryStatus) => {
		switch (status) {
			case "success":
				return "border-l-green-500";
			case "failed":
				return "border-l-destructive";
			case "queued":
			case "pending":
				return "border-l-blue-500";
			case "skipped":
				return "border-l-amber-500";
			default:
				return "border-l-primary/60";
		}
	};

	return (
		<div className="space-y-2">
			{deliveries.map((delivery) => (
				<div
					key={delivery.id}
					className={`border rounded-lg p-3 border-l-4 bg-muted/40 ${getBorderColor(delivery.status)}`}
				>
					{/* Top row: Workflow + Status + Actions */}
					<div className="flex items-center justify-between gap-3">
						<div className="flex items-center gap-2 min-w-0 flex-1">
							<Badge
								variant="outline"
								className="font-mono text-xs shrink-0"
							>
								<WorkflowIcon className="mr-1 h-3 w-3" />
								{delivery.workflow_name || delivery.workflow_id}
							</Badge>
							{delivery.execution_id && (
								<TooltipProvider>
									<Tooltip>
										<TooltipTrigger asChild>
											<Button
												variant="ghost"
												size="icon"
												className="h-6 w-6 shrink-0"
												onClick={() => {
													window.open(
														`/history/${delivery.execution_id}`,
														"_blank",
													);
												}}
											>
												<ExternalLink className="h-3.5 w-3.5" />
											</Button>
										</TooltipTrigger>
										<TooltipContent>
											View execution
										</TooltipContent>
									</Tooltip>
								</TooltipProvider>
							)}
						</div>
						<div className="flex items-center gap-2">
							<div className="flex items-center gap-1.5">
								{getStatusIcon(delivery.status)}
								{delivery.status === "failed" &&
								delivery.error_message ? (
									<TooltipProvider>
										<Tooltip>
											<TooltipTrigger asChild>
												<Badge
													variant="destructive"
													className="cursor-pointer"
													onClick={() => {
														navigator.clipboard.writeText(
															delivery.error_message!,
														);
														toast.success(
															"Error copied to clipboard",
														);
													}}
												>
													Failed
												</Badge>
											</TooltipTrigger>
											<TooltipContent
												side="top"
												className="max-w-xs"
											>
												<p className="text-xs">
													{delivery.error_message}
												</p>
												<p className="text-xs text-muted-foreground mt-1">
													Click to copy
												</p>
											</TooltipContent>
										</Tooltip>
									</TooltipProvider>
								) : (
									<Badge
										variant={getStatusVariant(
											delivery.status,
										)}
									>
										{getStatusLabel(delivery.status)}
									</Badge>
								)}
							</div>
							{isPlatformAdmin &&
								delivery.status === "failed" && (
									<Button
										variant="outline"
										size="sm"
										onClick={() => handleRetry(delivery.id)}
										disabled={retryingId === delivery.id}
									>
										{retryingId === delivery.id ? (
											<Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
										) : (
											<RefreshCw className="h-3.5 w-3.5 mr-1" />
										)}
										Retry
									</Button>
								)}
						</div>
					</div>

					{/* Bottom row: Metadata */}
					<div className="flex items-center gap-4 mt-2 pt-2 border-t border-border/50 text-xs text-muted-foreground">
						<span>
							{delivery.attempt_count} attempt
							{delivery.attempt_count !== 1 ? "s" : ""}
						</span>
						{delivery.completed_at && (
							<span>
								Completed{" "}
								{format(
									new Date(delivery.completed_at),
									"MMM d, HH:mm:ss",
								)}
							</span>
						)}
					</div>
				</div>
			))}
		</div>
	);
}
