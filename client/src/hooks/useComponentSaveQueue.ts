/**
 * Component Save Queue Hook
 *
 * Manages a queue of pending component CRUD operations and page updates with debouncing.
 * Property updates are debounced (500ms), structural changes (create/delete/move) are immediate.
 *
 * Uses the granular component API endpoints:
 * - POST /api/applications/{app_id}/pages/{page_id}/components
 * - PATCH /api/applications/{app_id}/pages/{page_id}/components/{component_id}
 * - DELETE /api/applications/{app_id}/pages/{page_id}/components/{component_id}
 * - POST /api/applications/{app_id}/pages/{page_id}/components/{component_id}/move
 *
 * And page metadata endpoint:
 * - PATCH /api/applications/{app_id}/pages/{page_id}
 */

import { useRef, useCallback, useState, useEffect } from "react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { useAppBuilderEditorStore } from "@/stores/app-builder-editor.store";
import type { components } from "@/lib/v1";

type AppComponentCreate = components["schemas"]["AppComponentCreate"];
type AppComponentUpdate = components["schemas"]["AppComponentUpdate"];
type AppComponentMove = components["schemas"]["AppComponentMove"];
type AppComponentResponse = components["schemas"]["AppComponentResponse"];
type AppPageUpdate = components["schemas"]["AppPageUpdate"];

/**
 * Operation types for the save queue
 */
type OperationType = "create" | "update" | "delete" | "move";

interface QueuedOperation {
	type: OperationType;
	componentId: string;
	data?: AppComponentCreate | AppComponentUpdate | AppComponentMove;
	timestamp: number;
	debounceTimer?: ReturnType<typeof setTimeout>;
	retryCount?: number;
}

interface UseComponentSaveQueueOptions {
	/** App ID (required) */
	appId: string;
	/** Page ID (required) */
	pageId: string;
	/** Debounce time in ms for property updates (default: 500) */
	debounceMs?: number;
	/** Max retries on failure (default: 2) */
	maxRetries?: number;
	/** Callback when save succeeds */
	onSaveSuccess?: (
		componentId: string,
		operation: OperationType,
		response?: AppComponentResponse,
	) => void;
	/** Callback when save fails */
	onSaveError?: (
		componentId: string,
		operation: OperationType,
		error: Error,
	) => void;
}

interface UseComponentSaveQueueReturn {
	/** Enqueue a create operation (immediate) */
	enqueueCreate: (componentId: string, data: AppComponentCreate) => void;
	/** Enqueue an update operation (debounced) */
	enqueueUpdate: (componentId: string, data: AppComponentUpdate) => void;
	/** Enqueue a delete operation (immediate) */
	enqueueDelete: (componentId: string) => void;
	/** Enqueue a move operation (immediate) */
	enqueueMove: (componentId: string, data: AppComponentMove) => void;
	/** Enqueue a page update operation (debounced) */
	enqueuePageUpdate: (pageId: string, data: Partial<AppPageUpdate>) => void;
	/** Force all pending operations to execute immediately */
	flushAll: () => Promise<void>;
	/** Cancel a pending operation for a component */
	cancel: (componentId: string) => void;
	/** Cancel all pending operations */
	cancelAll: () => void;
	/** Whether any save is currently in progress */
	isSaving: boolean;
	/** Count of pending operations */
	pendingCount: number;
	/** Whether there are any pending or in-progress operations */
	hasPendingOperations: boolean;
}

/**
 * Hook for managing component save operations with debouncing
 */
export function useComponentSaveQueue({
	appId,
	pageId,
	debounceMs = 500,
	maxRetries = 2,
	onSaveSuccess,
	onSaveError,
}: UseComponentSaveQueueOptions): UseComponentSaveQueueReturn {
	// Queue of pending component operations
	const queueRef = useRef<Map<string, QueuedOperation>>(new Map());

	// Queue of pending page updates (pageId -> merged update data)
	const pageQueueRef = useRef<Map<string, Partial<AppPageUpdate>>>(
		new Map(),
	);
	const pageDebounceTimerRef = useRef<
		Map<string, ReturnType<typeof setTimeout>>
	>(new Map());

	// Processing state
	const [isSaving, setIsSaving] = useState(false);
	const [pendingCount, setPendingCount] = useState(0);
	const processingRef = useRef(false);
	const processingPagesRef = useRef(false);

	// Get editor store actions
	const editorStore = useAppBuilderEditorStore();

	// Update pending count when queues change
	const updatePendingCount = useCallback(() => {
		setPendingCount(queueRef.current.size + pageQueueRef.current.size);
	}, []);

	/**
	 * Execute a single operation
	 */
	const executeOperation = useCallback(
		async (
			operation: QueuedOperation,
		): Promise<{ success: boolean; response?: AppComponentResponse }> => {
			const { type, componentId, data } = operation;

			try {
				switch (type) {
					case "create": {
						const { data: responseData, error } =
							await apiClient.POST(
								"/api/applications/{app_id}/pages/{page_id}/components",
								{
									params: {
										path: {
											app_id: appId,
											page_id: pageId,
										},
									},
									body: data as AppComponentCreate,
								},
							);
						if (error)
							throw new Error(
								(error as { detail?: string }).detail ??
									"Failed to create component",
							);

						// Store the UUID mapping
						if (responseData?.id) {
							editorStore.setUUID(componentId, responseData.id);
						}

						return { success: true, response: responseData };
					}

					case "update": {
						const { data: responseData, error } =
							await apiClient.PATCH(
								"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
								{
									params: {
										path: {
											app_id: appId,
											page_id: pageId,
											component_id: componentId,
										},
									},
									body: data as AppComponentUpdate,
								},
							);
						if (error)
							throw new Error(
								(error as { detail?: string }).detail ??
									"Failed to update component",
							);
						return { success: true, response: responseData };
					}

					case "delete": {
						const { error } = await apiClient.DELETE(
							"/api/applications/{app_id}/pages/{page_id}/components/{component_id}",
							{
								params: {
									path: {
										app_id: appId,
										page_id: pageId,
										component_id: componentId,
									},
								},
							},
						);
						if (error)
							throw new Error(
								(error as { detail?: string }).detail ??
									"Failed to delete component",
							);
						return { success: true };
					}

					case "move": {
						const { data: responseData, error } =
							await apiClient.POST(
								"/api/applications/{app_id}/pages/{page_id}/components/{component_id}/move",
								{
									params: {
										path: {
											app_id: appId,
											page_id: pageId,
											component_id: componentId,
										},
									},
									body: data as AppComponentMove,
								},
							);
						if (error)
							throw new Error(
								(error as { detail?: string }).detail ??
									"Failed to move component",
							);
						return { success: true, response: responseData };
					}

					default:
						throw new Error(`Unknown operation type: ${type}`);
				}
			} catch (error) {
				console.error(
					`[ComponentSaveQueue] Failed to ${type} component ${componentId}:`,
					error,
				);
				return { success: false };
			}
		},
		[appId, pageId, editorStore],
	);

	/**
	 * Process page updates
	 */
	const processPageQueue = useCallback(async () => {
		if (processingPagesRef.current) return;

		const pageQueue = pageQueueRef.current;
		if (pageQueue.size === 0) return;

		processingPagesRef.current = true;
		const hasComponentOps = queueRef.current.size > 0;
		setIsSaving(true);
		editorStore.setSaving(true);

		for (const [pageIdToUpdate, updates] of Array.from(
			pageQueue.entries(),
		)) {
			try {
				const { error } = await apiClient.PATCH(
					"/api/applications/{app_id}/pages/{page_id}",
					{
						params: {
							path: {
								app_id: appId,
								page_id: pageIdToUpdate,
							},
						},
						body: updates as AppPageUpdate,
					},
				);

				if (error) {
					throw new Error(
						(error as { detail?: string }).detail ??
							"Failed to update page",
					);
				}

				// Mark page as clean in editor store
				editorStore.markPageClean(pageIdToUpdate);

				// Remove from queue
				pageQueue.delete(pageIdToUpdate);
			} catch (error) {
				console.error(
					`[ComponentSaveQueue] Failed to update page ${pageIdToUpdate}:`,
					error,
				);

				// Show toast
				toast.error(`Failed to save page`, {
					description: `Could not update page metadata. Changes may be lost.`,
				});

				// Remove from queue even on error to avoid infinite retry
				pageQueue.delete(pageIdToUpdate);
			}
		}

		processingPagesRef.current = false;
		setIsSaving(hasComponentOps || pageQueue.size > 0);
		editorStore.setSaving(hasComponentOps || pageQueue.size > 0);
		updatePendingCount();
	}, [appId, editorStore, updatePendingCount]);

	/**
	 * Process the component queue
	 */
	const processQueue = useCallback(async () => {
		if (processingRef.current) return;

		const queue = queueRef.current;
		const readyOperations = Array.from(queue.entries()).filter(
			([, op]) => !op.debounceTimer,
		);

		if (readyOperations.length === 0) return;

		processingRef.current = true;
		const hasPageOps = pageQueueRef.current.size > 0;
		setIsSaving(true);
		editorStore.setSaving(true);

		for (const [componentId, operation] of readyOperations) {
			const result = await executeOperation(operation);

			if (result.success) {
				// Mark component as clean in editor store
				editorStore.markClean(componentId);

				// Remove from queue
				queue.delete(componentId);

				// Call success callback
				onSaveSuccess?.(componentId, operation.type, result.response);
			} else {
				// Retry logic
				const retryCount = (operation.retryCount ?? 0) + 1;

				if (retryCount <= maxRetries) {
					// Update retry count and try again later
					operation.retryCount = retryCount;
					operation.debounceTimer = setTimeout(() => {
						const op = queue.get(componentId);
						if (op) {
							op.debounceTimer = undefined;
							processQueue();
						}
					}, 1000 * retryCount); // Exponential backoff
				} else {
					// Max retries exceeded - remove from queue and notify
					queue.delete(componentId);

					const error = new Error(
						`Failed to ${operation.type} component after ${maxRetries} retries`,
					);
					onSaveError?.(componentId, operation.type, error);

					// Show toast
					toast.error(`Failed to save component`, {
						description: `Could not ${operation.type} component. Changes may be lost.`,
					});
				}
			}
		}

		processingRef.current = false;
		setIsSaving(hasPageOps || queue.size > 0);
		editorStore.setSaving(hasPageOps || queue.size > 0);
		updatePendingCount();

		// Process any remaining items
		if (queue.size > 0) {
			processQueue();
		}
	}, [
		executeOperation,
		editorStore,
		maxRetries,
		onSaveSuccess,
		onSaveError,
		updatePendingCount,
	]);

	/**
	 * Enqueue an operation
	 */
	const enqueue = useCallback(
		(
			componentId: string,
			type: OperationType,
			data?: AppComponentCreate | AppComponentUpdate | AppComponentMove,
			immediate = false,
		) => {
			const queue = queueRef.current;
			const existing = queue.get(componentId);

			// Clear existing debounce timer
			if (existing?.debounceTimer) {
				clearTimeout(existing.debounceTimer);
			}

			// For updates, merge with existing update data
			let mergedData = data;
			if (
				type === "update" &&
				existing?.type === "update" &&
				existing.data &&
				data
			) {
				mergedData = {
					...(existing.data as AppComponentUpdate),
					...(data as AppComponentUpdate),
					props: {
						...((existing.data as AppComponentUpdate).props ?? {}),
						...((data as AppComponentUpdate).props ?? {}),
					},
				};
			}

			const operation: QueuedOperation = {
				type,
				componentId,
				data: mergedData,
				timestamp: Date.now(),
				retryCount: 0,
			};

			if (immediate) {
				// Execute immediately (creates, deletes, moves)
				queue.set(componentId, operation);
				updatePendingCount();
				processQueue();
			} else {
				// Debounce (updates)
				operation.debounceTimer = setTimeout(() => {
					const op = queue.get(componentId);
					if (op) {
						op.debounceTimer = undefined;
						processQueue();
					}
				}, debounceMs);
				queue.set(componentId, operation);
				updatePendingCount();
			}
		},
		[debounceMs, processQueue, updatePendingCount],
	);

	/**
	 * Enqueue a create operation (immediate)
	 */
	const enqueueCreate = useCallback(
		(componentId: string, data: AppComponentCreate) => {
			editorStore.markNew(componentId);
			enqueue(componentId, "create", data, true);
		},
		[enqueue, editorStore],
	);

	/**
	 * Enqueue an update operation (debounced)
	 */
	const enqueueUpdate = useCallback(
		(componentId: string, data: AppComponentUpdate) => {
			editorStore.markModified(componentId);
			enqueue(componentId, "update", data, false);
		},
		[enqueue, editorStore],
	);

	/**
	 * Enqueue a delete operation (immediate)
	 */
	const enqueueDelete = useCallback(
		(componentId: string) => {
			editorStore.markDeleted(componentId);
			enqueue(componentId, "delete", undefined, true);
		},
		[enqueue, editorStore],
	);

	/**
	 * Enqueue a move operation (immediate)
	 */
	const enqueueMove = useCallback(
		(componentId: string, data: AppComponentMove) => {
			enqueue(componentId, "move", data, true);
		},
		[enqueue],
	);

	/**
	 * Enqueue a page update operation (debounced)
	 */
	const enqueuePageUpdate = useCallback(
		(pageIdToUpdate: string, updates: Partial<AppPageUpdate>) => {
			const pageQueue = pageQueueRef.current;
			const timers = pageDebounceTimerRef.current;

			// Clear existing debounce timer
			const existingTimer = timers.get(pageIdToUpdate);
			if (existingTimer) {
				clearTimeout(existingTimer);
			}

			// Merge with existing updates
			const existing = pageQueue.get(pageIdToUpdate) || {};
			const merged = { ...existing, ...updates };
			pageQueue.set(pageIdToUpdate, merged);

			// Mark page as dirty
			editorStore.markPageDirty(pageIdToUpdate);

			// Set new debounce timer
			const timer = setTimeout(() => {
				timers.delete(pageIdToUpdate);
				processPageQueue();
			}, debounceMs);

			timers.set(pageIdToUpdate, timer);
			updatePendingCount();
		},
		[debounceMs, editorStore, processPageQueue, updatePendingCount],
	);

	/**
	 * Force all pending operations to execute immediately
	 */
	const flushAll = useCallback(async () => {
		const queue = queueRef.current;
		const pageQueue = pageQueueRef.current;
		const pageTimers = pageDebounceTimerRef.current;

		// Clear all component debounce timers
		for (const [, operation] of queue) {
			if (operation.debounceTimer) {
				clearTimeout(operation.debounceTimer);
				operation.debounceTimer = undefined;
			}
		}

		// Clear all page debounce timers
		for (const [, timer] of pageTimers) {
			clearTimeout(timer);
		}
		pageTimers.clear();

		// Wait for processing to complete
		await Promise.all([processQueue(), processPageQueue()]);

		// Poll until both queues are empty
		const maxWait = 10000;
		const startTime = Date.now();
		while (
			(queue.size > 0 ||
				pageQueue.size > 0 ||
				processingRef.current ||
				processingPagesRef.current) &&
			Date.now() - startTime < maxWait
		) {
			await new Promise((resolve) => setTimeout(resolve, 50));
		}
	}, [processQueue, processPageQueue]);

	/**
	 * Cancel a pending operation
	 */
	const cancel = useCallback((componentId: string) => {
		const queue = queueRef.current;
		const operation = queue.get(componentId);

		if (operation?.debounceTimer) {
			clearTimeout(operation.debounceTimer);
		}

		queue.delete(componentId);
		setPendingCount(queue.size);
	}, []);

	/**
	 * Cancel all pending operations
	 */
	const cancelAll = useCallback(() => {
		const queue = queueRef.current;
		const pageQueue = pageQueueRef.current;
		const pageTimers = pageDebounceTimerRef.current;

		// Cancel component operations
		for (const [, operation] of queue) {
			if (operation.debounceTimer) {
				clearTimeout(operation.debounceTimer);
			}
		}
		queue.clear();

		// Cancel page operations
		for (const [, timer] of pageTimers) {
			clearTimeout(timer);
		}
		pageTimers.clear();
		pageQueue.clear();

		setPendingCount(0);
	}, []);

	// Cleanup on unmount
	useEffect(() => {
		// Capture ref values for cleanup
		const queue = queueRef.current;
		const pageTimers = pageDebounceTimerRef.current;

		return () => {
			// Clear all component timers
			for (const [, operation] of queue) {
				if (operation.debounceTimer) {
					clearTimeout(operation.debounceTimer);
				}
			}

			// Clear all page timers
			for (const [, timer] of pageTimers) {
				clearTimeout(timer);
			}
		};
	}, []);

	return {
		enqueueCreate,
		enqueueUpdate,
		enqueueDelete,
		enqueueMove,
		enqueuePageUpdate,
		flushAll,
		cancel,
		cancelAll,
		isSaving,
		pendingCount,
		hasPendingOperations: pendingCount > 0 || isSaving,
	};
}
