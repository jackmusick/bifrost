/**
 * Profile service for user profile management
 */

import { authFetch } from "@/lib/api-client";

export interface ProfileResponse {
	id: string;
	email: string;
	name: string | null;
	has_avatar: boolean;
	has_password: boolean;
	organization_id: string | null;
	is_superuser: boolean;
}

export interface ProfileUpdate {
	name?: string | null;
}

export interface PasswordChange {
	current_password?: string | null;
	new_password: string;
}

/**
 * Get the current user's profile
 */
export async function getProfile(): Promise<ProfileResponse> {
	const response = await authFetch("/api/profile");
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to get profile: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Update the current user's profile
 */
export async function updateProfile(
	data: ProfileUpdate,
): Promise<ProfileResponse> {
	const response = await authFetch("/api/profile", {
		method: "PATCH",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(data),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to update profile: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Upload avatar image
 */
export async function uploadAvatar(file: File): Promise<ProfileResponse> {
	const formData = new FormData();
	formData.append("file", file);

	const response = await authFetch("/api/profile/avatar", {
		method: "POST",
		body: formData,
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to upload avatar: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Delete avatar
 */
export async function deleteAvatar(): Promise<ProfileResponse> {
	const response = await authFetch("/api/profile/avatar", {
		method: "DELETE",
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to delete avatar: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Get avatar URL for the current user
 */
export function getAvatarUrl(): string {
	return "/api/profile/avatar";
}

/**
 * Change or set password
 * @param currentPassword - Required if user already has a password, null/undefined otherwise
 * @param newPassword - The new password to set
 */
export async function changePassword(
	currentPassword: string | null | undefined,
	newPassword: string,
): Promise<void> {
	const body: PasswordChange = { new_password: newPassword };
	if (currentPassword) {
		body.current_password = currentPassword;
	}

	const response = await authFetch("/api/profile/password", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to change password: ${response.statusText}`,
		);
	}
}

export const profileService = {
	getProfile,
	updateProfile,
	uploadAvatar,
	deleteAvatar,
	getAvatarUrl,
	changePassword,
};
