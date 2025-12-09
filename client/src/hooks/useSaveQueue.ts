import { useRef, useCallback } from "react";
import { fileService, FileConflictError } from "@/services/fileService";
import type { ConflictReason } from "@/stores/editorStore";

interface SaveQueueEntry {
	filePath: string;
	content: string;
	encoding: "utf-8" | "base64";
	timestamp: number;
	currentEtag?: string | undefined; // Expected etag for conflict detection
	debounceTimer?: NodeJS.Timeout | undefined;
	onComplete?: ((newEtag: string) => void) | undefined;
	onConflict?: ((reason: ConflictReason) => void) | undefined;
}

/**
 * Manages a queue of pending file saves with debouncing.
 * Ensures saves complete even when switching tabs.
 *
 * Uses 1-second debounce (Google Docs/VS Code style) and
 * processes saves sequentially to prevent conflicts.
 */
export function useSaveQueue() {
	const saveQueueRef = useRef<Map<string, SaveQueueEntry>>(new Map());
	const savingRef = useRef(false);

	/**
	 * Execute a pending save for a file
	 */
	const executeSave = useCallback(
		async (
			entry: SaveQueueEntry,
		): Promise<{ success: boolean; etag?: string }> => {
			try {
				// Pass etag for conflict detection
				const response = await fileService.writeFile(
					entry.filePath,
					entry.content,
					entry.encoding,
					entry.currentEtag,
				);
				return { success: true, etag: response.etag };
			} catch (error) {
				// Handle conflict errors specially
				if (error instanceof FileConflictError) {
					console.warn(
						`[SaveQueue] Conflict detected for ${entry.filePath}:`,
						error.conflictData.reason,
					);
					if (entry.onConflict) {
						entry.onConflict(
							error.conflictData.reason as ConflictReason,
						);
					}
					return { success: false };
				}

				console.error(
					`[SaveQueue] Failed to save ${entry.filePath}:`,
					error,
				);
				return { success: false };
			}
		},
		[],
	);

	/**
	 * Process the next item in the queue
	 */
	const processQueue = useCallback(
		async function processQueueInternal() {
			if (savingRef.current) return;

			const queue = saveQueueRef.current;
			const entries = Array.from(queue.values());

			for (const entry of entries) {
				// Skip if still debouncing
				if (entry.debounceTimer) continue;

				// Mark as saving
				savingRef.current = true;

				// Execute save
				const result = await executeSave(entry);

				// Call completion callback if provided
				if (result.success && entry.onComplete && result.etag) {
					entry.onComplete(result.etag);
				}

				// Remove from queue after processing (success or failure)
				// For failures, the onConflict callback has already been called
				// and the user will need to manually resolve the conflict
				queue.delete(entry.filePath);

				savingRef.current = false;

				// Process next item recursively
				if (queue.size > 0) {
					processQueueInternal();
				}
				break;
			}
		},
		[executeSave],
	);

	/**
	 * Enqueue a save with 1-second debounce
	 */
	const enqueueSave = useCallback(
		(
			filePath: string,
			content: string,
			encoding: "utf-8" | "base64" = "utf-8",
			currentEtag?: string,
			onComplete?: (newEtag: string) => void,
			onConflict?: (reason: ConflictReason) => void,
		) => {
			const queue = saveQueueRef.current;
			const existing = queue.get(filePath);

			// Clear existing debounce timer
			if (existing?.debounceTimer) {
				clearTimeout(existing.debounceTimer);
			}

			// Create or update queue entry
			const entry: SaveQueueEntry = {
				filePath,
				content,
				encoding,
				currentEtag,
				timestamp: Date.now(),
				onComplete,
				onConflict,
				debounceTimer: setTimeout(() => {
					// Clear timer and process queue
					const currentEntry = queue.get(filePath);
					if (currentEntry) {
						currentEntry.debounceTimer = undefined;
						processQueue();
					}
				}, 1000), // 1 second debounce (VS Code/Google Docs style)
			};

			queue.set(filePath, entry);
		},
		[processQueue],
	);

	/**
	 * Force immediate save (bypasses debounce)
	 */
	const forceSave = useCallback(
		async (
			filePath: string,
			content: string,
			encoding: "utf-8" | "base64" = "utf-8",
			currentEtag?: string,
		) => {
			const queue = saveQueueRef.current;
			const existing = queue.get(filePath);

			// Clear debounce if exists
			if (existing?.debounceTimer) {
				clearTimeout(existing.debounceTimer);
			}

			// Create entry without debounce
			const entry: SaveQueueEntry = {
				filePath,
				content,
				encoding,
				currentEtag,
				timestamp: Date.now(),
			};

			queue.set(filePath, entry);

			// Process immediately
			await processQueue();
		},
		[processQueue],
	);

	/**
	 * Check if a file has pending saves
	 */
	const hasPendingSave = useCallback((filePath: string) => {
		return saveQueueRef.current.has(filePath);
	}, []);

	/**
	 * Get pending save count
	 */
	const getPendingCount = useCallback(() => {
		return saveQueueRef.current.size;
	}, []);

	return {
		enqueueSave,
		forceSave,
		hasPendingSave,
		getPendingCount,
	};
}
