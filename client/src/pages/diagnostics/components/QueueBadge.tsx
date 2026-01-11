import { motion, AnimatePresence } from "framer-motion";
import { Clock, Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
	HoverCard,
	HoverCardContent,
	HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { QueueItem } from "@/services/workers";

interface QueueBadgeProps {
	items: QueueItem[];
	isLoading?: boolean;
}

/**
 * Format relative time from ISO date string
 */
function formatRelativeTime(dateStr: string | null | undefined): string {
	if (!dateStr) return "Unknown";
	const date = new Date(dateStr);
	const now = new Date();
	const diffMs = now.getTime() - date.getTime();
	const diffSec = Math.floor(diffMs / 1000);

	if (diffSec < 60) return `${diffSec}s ago`;
	const minutes = Math.floor(diffSec / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	return `${hours}h ago`;
}

/**
 * Compact queue indicator badge with hover popover showing queue details.
 * Shows queue count at a glance, full list on hover.
 */
export function QueueBadge({ items, isLoading }: QueueBadgeProps) {
	const count = items.length;

	return (
		<HoverCard openDelay={200} closeDelay={100}>
			<HoverCardTrigger asChild>
				<Badge
					variant={count > 0 ? "default" : "secondary"}
					className={`cursor-default ${
						count > 0
							? "bg-amber-500 hover:bg-amber-600 text-white"
							: ""
					} ${isLoading ? "animate-pulse" : ""}`}
				>
					<Inbox className="h-3 w-3 mr-1" />
					{count} queued
				</Badge>
			</HoverCardTrigger>
			<HoverCardContent align="end" className="w-80">
				<div className="space-y-2">
					<div className="flex items-center justify-between">
						<h4 className="text-sm font-semibold">Execution Queue</h4>
						<span className="text-xs text-muted-foreground">
							{count} pending
						</span>
					</div>

					{count === 0 ? (
						<div className="flex flex-col items-center justify-center py-4 text-muted-foreground">
							<Inbox className="h-6 w-6 mb-1" />
							<p className="text-xs">No jobs queued</p>
						</div>
					) : (
						<div className="divide-y max-h-64 overflow-y-auto">
							<AnimatePresence mode="popLayout">
								{items.slice(0, 10).map((item, index) => (
									<motion.div
										key={item.execution_id}
										initial={{ opacity: 0, y: -5 }}
										animate={{ opacity: 1, y: 0 }}
										exit={{ opacity: 0, x: 10 }}
										transition={{ duration: 0.15, delay: index * 0.03 }}
										layout
										className="flex items-center justify-between py-2 first:pt-0 last:pb-0"
									>
										<div className="flex items-center gap-2">
											<span className="text-muted-foreground font-mono text-xs w-5">
												#{item.position}
											</span>
											<span className="font-medium text-sm font-mono">
												{item.execution_id.substring(0, 8)}
											</span>
										</div>
										<div className="flex items-center gap-1 text-xs text-muted-foreground">
											<Clock className="h-3 w-3" />
											<span>{formatRelativeTime(item.queued_at)}</span>
										</div>
									</motion.div>
								))}
							</AnimatePresence>
							{items.length > 10 && (
								<div className="pt-2 text-center text-xs text-muted-foreground">
									+{items.length - 10} more
								</div>
							)}
						</div>
					)}
				</div>
			</HoverCardContent>
		</HoverCard>
	);
}
