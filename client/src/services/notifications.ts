/**
 * Notifications API Service
 *
 * Provides REST API methods for notification management.
 * Real-time updates come via WebSocket (notification:{user_id} channel).
 */

import { authFetch } from "@/lib/api-client";
import type { Notification } from "@/stores/notificationStore";

// API response types (before we have generated types)
interface NotificationListResponse {
	notifications: Array<{
		id: string;
		category: string;
		title: string;
		description: string | null;
		status: string;
		percent: number | null;
		error: string | null;
		result: Record<string, unknown> | null;
		metadata: Record<string, unknown> | null;
		created_at: string;
		updated_at: string;
		user_id: string;
	}>;
}

interface UploadLockInfo {
	locked: boolean;
	owner_user_id?: string;
	owner_email?: string;
	operation?: string;
	locked_at?: string;
	expires_at?: string;
}

/**
 * Convert API response to frontend notification format
 */
function toNotification(
	data: NotificationListResponse["notifications"][0],
): Notification {
	return {
		id: data.id,
		category: data.category as Notification["category"],
		title: data.title,
		description: data.description,
		status: data.status as Notification["status"],
		percent: data.percent,
		error: data.error,
		result: data.result,
		metadata: data.metadata,
		createdAt: data.created_at,
		updatedAt: data.updated_at,
		userId: data.user_id,
	};
}

/**
 * Get all notifications for the current user
 */
export async function getNotifications(): Promise<Notification[]> {
	const response = await authFetch("/api/notifications");
	if (!response.ok) {
		throw new Error(`Failed to fetch notifications: ${response.status}`);
	}
	const data: NotificationListResponse = await response.json();
	return data.notifications.map(toNotification);
}

/**
 * Dismiss (delete) a notification
 */
export async function dismissNotification(
	notificationId: string,
): Promise<void> {
	const response = await authFetch(`/api/notifications/${notificationId}`, {
		method: "DELETE",
	});
	if (!response.ok && response.status !== 404) {
		throw new Error(`Failed to dismiss notification: ${response.status}`);
	}
}

/**
 * Get upload lock status
 */
export async function getUploadLockStatus(): Promise<{
	locked: boolean;
	ownerUserId?: string;
	ownerEmail?: string;
	operation?: string;
	lockedAt?: string;
	expiresAt?: string;
}> {
	const response = await authFetch("/api/notifications/locks/upload");
	if (!response.ok) {
		throw new Error(`Failed to get upload lock status: ${response.status}`);
	}
	const data: UploadLockInfo = await response.json();
	return {
		locked: data.locked,
		ownerUserId: data.owner_user_id,
		ownerEmail: data.owner_email,
		operation: data.operation,
		lockedAt: data.locked_at,
		expiresAt: data.expires_at,
	};
}

/**
 * Force release upload lock (admin only)
 */
export async function forceReleaseUploadLock(): Promise<void> {
	const response = await authFetch("/api/notifications/locks/upload", {
		method: "DELETE",
	});
	if (!response.ok) {
		throw new Error(`Failed to release upload lock: ${response.status}`);
	}
}
