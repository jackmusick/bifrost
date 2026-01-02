/**
 * Hook for real-time event streaming via WebSocket
 *
 * Subscribes to event source updates and automatically updates
 * React Query cache with new events.
 */

import { useEffect, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { webSocketService, type EventSourceUpdate } from "@/services/websocket";

interface UseEventStreamOptions {
	enabled?: boolean;
}

export function useEventStream(
	sourceId: string | undefined,
	options: UseEventStreamOptions = {},
) {
	const { enabled = true } = options;
	const queryClient = useQueryClient();
	const [isConnected, setIsConnected] = useState(false);

	const handleUpdate = useCallback(
		(update: EventSourceUpdate) => {
			if (!sourceId) return;

			// Invalidate events queries to trigger refetch
			// Using partial key match so it works regardless of filter params
			if (
				update.type === "event_created" ||
				update.type === "event_updated"
			) {
				// Invalidate events list
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/events/sources/{source_id}/events"],
				});

				// Also invalidate individual event queries so detail dialogs update
				queryClient.invalidateQueries({
					predicate: (query) =>
						query.queryKey[0] === "get" &&
						query.queryKey[1] === "/api/events/{event_id}",
				});

				// Invalidate deliveries queries so delivery status updates in dialog
				queryClient.invalidateQueries({
					predicate: (query) =>
						query.queryKey[0] === "get" &&
						query.queryKey[1] ===
							"/api/events/{event_id}/deliveries",
				});
			}
		},
		[sourceId, queryClient],
	);

	// Manage WebSocket connection
	useEffect(() => {
		// Skip if not enabled or no sourceId
		if (!sourceId || !enabled) {
			return;
		}

		const channel = `event-source:${sourceId}`;

		// Connect to WebSocket with the event source channel
		webSocketService.connect([channel]).then(() => {
			setIsConnected(true);
		});

		// Subscribe to updates
		const unsubscribe = webSocketService.onEventSourceUpdate(
			sourceId,
			handleUpdate,
		);

		return () => {
			unsubscribe();
			// Unsubscribe from channel
			webSocketService.unsubscribe(channel);
			setIsConnected(false);
		};
	}, [sourceId, enabled, handleUpdate]);

	// If not enabled or no sourceId, connection is always false
	const effectiveIsConnected = sourceId && enabled ? isConnected : false;

	return {
		isConnected: effectiveIsConnected,
	};
}
