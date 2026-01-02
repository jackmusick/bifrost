import { useState } from "react";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import {
	Clock,
	CheckCircle2,
	XCircle,
	Loader2,
	Copy,
	Check,
	Globe,
} from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import {
	useEvent,
	useDeliveries,
	type Event,
	type EventStatus,
} from "@/services/events";
import { DeliveriesTable } from "./DeliveriesTable";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";

interface EventDetailDialogProps {
	event: Event | null;
	onClose: () => void;
}

function getStatusIcon(status: EventStatus) {
	switch (status) {
		case "received":
			return <Clock className="h-4 w-4 text-muted-foreground" />;
		case "processing":
			return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
		case "completed":
			return <CheckCircle2 className="h-4 w-4 text-green-500" />;
		case "failed":
			return <XCircle className="h-4 w-4 text-destructive" />;
	}
}

function getStatusLabel(status: EventStatus) {
	switch (status) {
		case "received":
			return "Received";
		case "processing":
			return "Processing";
		case "completed":
			return "Completed";
		case "failed":
			return "Failed";
	}
}

function getStatusVariant(
	status: EventStatus,
): "default" | "secondary" | "destructive" | "outline" {
	switch (status) {
		case "completed":
			return "default";
		case "failed":
			return "destructive";
		case "processing":
			return "outline";
		default:
			return "secondary";
	}
}

function TextViewer({ data, label }: { data: unknown; label: string }) {
	const [copied, setCopied] = useState(false);

	const displayText =
		typeof data === "string" ? data : JSON.stringify(data, null, 2);

	const handleCopy = async () => {
		try {
			await navigator.clipboard.writeText(displayText);
			setCopied(true);
			toast.success(`${label} copied to clipboard`);
			setTimeout(() => setCopied(false), 2000);
		} catch {
			toast.error("Failed to copy");
		}
	};

	return (
		<div className="relative">
			<Button
				variant="ghost"
				size="icon"
				className="absolute top-2 right-2 h-6 w-6"
				onClick={handleCopy}
			>
				{copied ? (
					<Check className="h-3 w-3 text-green-500" />
				) : (
					<Copy className="h-3 w-3" />
				)}
			</Button>
			<pre className="bg-muted p-4 rounded-lg overflow-auto max-h-80 text-sm font-mono whitespace-pre-wrap">
				{displayText}
			</pre>
		</div>
	);
}

function EventDetailContent({ eventId }: { eventId: string }) {
	const { data: event, isLoading: eventLoading } = useEvent(eventId);
	const { data: deliveriesData, isLoading: deliveriesLoading } =
		useDeliveries(eventId);

	if (eventLoading) {
		return (
			<div className="space-y-4">
				<Skeleton className="h-24 w-full" />
				<Skeleton className="h-48 w-full" />
			</div>
		);
	}

	if (!event) {
		return (
			<div className="flex flex-col items-center justify-center py-8">
				<XCircle className="h-12 w-12 text-muted-foreground mb-4" />
				<p className="text-muted-foreground">Event not found</p>
			</div>
		);
	}

	return (
		<div className="space-y-6 max-h-[70vh] overflow-y-auto pr-2">
			{/* Metadata Card */}
			<Card>
				<CardHeader className="pb-3">
					<CardTitle className="text-base">Event Details</CardTitle>
				</CardHeader>
				<CardContent className="space-y-3">
					<div className="grid grid-cols-2 gap-4">
						<div>
							<span className="text-sm text-muted-foreground">
								Event Type
							</span>
							<div className="mt-1">
								{event.event_type ? (
									<Badge variant="outline">
										{event.event_type}
									</Badge>
								) : (
									<span className="text-muted-foreground">
										—
									</span>
								)}
							</div>
						</div>
						<div>
							<span className="text-sm text-muted-foreground">
								Status
							</span>
							<div className="mt-1 flex items-center gap-1.5">
								{getStatusIcon(event.status)}
								<Badge variant={getStatusVariant(event.status)}>
									{getStatusLabel(event.status)}
								</Badge>
							</div>
						</div>
						<div>
							<span className="text-sm text-muted-foreground">
								Received At
							</span>
							<div className="mt-1 font-medium">
								{format(new Date(event.received_at), "PPpp")}
							</div>
						</div>
						<div>
							<span className="text-sm text-muted-foreground">
								Source IP
							</span>
							<div className="mt-1 font-mono text-sm flex items-center gap-1.5">
								<Globe className="h-3.5 w-3.5 text-muted-foreground" />
								{event.source_ip || "Unknown"}
							</div>
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Headers Accordion */}
			{event.headers && Object.keys(event.headers).length > 0 && (
				<Accordion type="single" collapsible>
					<AccordionItem value="headers">
						<AccordionTrigger className="text-base font-semibold">
							Request Headers ({Object.keys(event.headers).length}
							)
						</AccordionTrigger>
						<AccordionContent>
							<VariablesTreeView
								data={event.headers as Record<string, unknown>}
							/>
						</AccordionContent>
					</AccordionItem>
				</Accordion>
			)}

			{/* Payload */}
			<div>
				<h4 className="text-base font-semibold mb-3">Event Payload</h4>
				{event.data !== null &&
				typeof event.data === "object" &&
				!Array.isArray(event.data) ? (
					<VariablesTreeView
						data={event.data as Record<string, unknown>}
					/>
				) : (
					<TextViewer data={event.data} label="Payload" />
				)}
			</div>

			{/* Deliveries */}
			<div>
				<h4 className="text-base font-semibold mb-3">
					Deliveries ({deliveriesData?.total || 0})
				</h4>
				{deliveriesLoading ? (
					<Skeleton className="h-32 w-full" />
				) : (
					<DeliveriesTable
						deliveries={deliveriesData?.items || []}
						eventId={eventId}
					/>
				)}
			</div>
		</div>
	);
}

export function EventDetailDialog({ event, onClose }: EventDetailDialogProps) {
	return (
		<Dialog open={!!event} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="sm:max-w-[700px]">
				<DialogHeader>
					<DialogTitle>Event Details</DialogTitle>
				</DialogHeader>
				{event && <EventDetailContent eventId={event.id} />}
			</DialogContent>
		</Dialog>
	);
}
