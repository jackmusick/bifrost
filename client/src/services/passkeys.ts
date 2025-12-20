/**
 * Passkeys Service
 *
 * API methods for WebAuthn passkey operations.
 * Provides passwordless authentication via biometrics (Face ID, Touch ID, etc.)
 */

import {
	startRegistration,
	startAuthentication,
	browserSupportsWebAuthn,
	browserSupportsWebAuthnAutofill,
} from "@simplewebauthn/browser";
import type {
	PublicKeyCredentialCreationOptionsJSON,
	PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { authFetch } from "@/lib/api-client";

// =============================================================================
// Types
// =============================================================================

export interface PasskeyPublic {
	id: string;
	name: string;
	device_type: string;
	backed_up: boolean;
	created_at: string;
	last_used_at: string | null;
}

export interface PasskeyListResponse {
	passkeys: PasskeyPublic[];
	count: number;
}

export interface PasskeyRegistrationResult {
	verified: boolean;
	passkey_id: string;
	name: string;
}

export interface LoginTokens {
	access_token: string;
	refresh_token: string;
}

// =============================================================================
// Feature Detection
// =============================================================================

/**
 * Check if the browser supports WebAuthn passkeys
 */
export function supportsPasskeys(): boolean {
	return browserSupportsWebAuthn();
}

/**
 * Check if the browser supports passkey autofill (conditional UI)
 */
export async function supportsPasskeyAutofill(): Promise<boolean> {
	return browserSupportsWebAuthnAutofill();
}

// =============================================================================
// Registration (for authenticated users adding passkeys)
// =============================================================================

/**
 * Register a new passkey for the current user.
 * Triggers the browser's passkey creation flow (Face ID, Touch ID, etc.)
 *
 * @param deviceName - Optional friendly name for the passkey (e.g., "MacBook Pro")
 * @returns Registration result with passkey ID
 */
export async function registerPasskey(
	deviceName?: string,
): Promise<PasskeyRegistrationResult> {
	// Step 1: Get registration options from server
	const optionsRes = await authFetch("/auth/passkeys/register/options", {
		method: "POST",
		body: JSON.stringify({ device_name: deviceName }),
	});

	if (!optionsRes.ok) {
		const error = await optionsRes.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to get registration options");
	}

	const { options } = await optionsRes.json();

	// Step 2: Trigger browser passkey creation
	let credential;
	try {
		credential = await startRegistration({
			optionsJSON: options as PublicKeyCredentialCreationOptionsJSON,
		});
	} catch (error) {
		// Handle specific WebAuthn errors
		if (error instanceof Error) {
			if (error.name === "NotAllowedError") {
				throw new Error(
					"Passkey registration was cancelled or not allowed",
				);
			}
			if (error.name === "InvalidStateError") {
				throw new Error(
					"This passkey is already registered on this device",
				);
			}
		}
		throw error;
	}

	// Step 3: Send credential to server for verification
	const verifyRes = await authFetch("/auth/passkeys/register/verify", {
		method: "POST",
		body: JSON.stringify({
			credential,
			device_name: deviceName,
		}),
	});

	if (!verifyRes.ok) {
		const error = await verifyRes.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to verify passkey registration");
	}

	return verifyRes.json();
}

// =============================================================================
// Authentication (passwordless login)
// =============================================================================

/**
 * Authenticate with a passkey (passwordless login).
 * Triggers the browser's passkey selection flow.
 *
 * @param email - Optional email to target specific user's credentials
 * @returns JWT tokens on successful authentication
 */
export async function authenticateWithPasskey(
	email?: string,
): Promise<LoginTokens> {
	// Step 1: Get authentication options from server
	const optionsRes = await fetch("/auth/passkeys/authenticate/options", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ email }),
	});

	if (!optionsRes.ok) {
		const error = await optionsRes.json().catch(() => ({}));
		throw new Error(
			error.detail || "Failed to get authentication options",
		);
	}

	const { challenge_id, options } = await optionsRes.json();

	// Step 2: Trigger browser passkey authentication
	let credential;
	try {
		credential = await startAuthentication({
			optionsJSON: options as PublicKeyCredentialRequestOptionsJSON,
		});
	} catch (error) {
		if (error instanceof Error) {
			if (error.name === "NotAllowedError") {
				throw new Error(
					"Passkey authentication was cancelled or not allowed",
				);
			}
			if (error.name === "AbortError") {
				throw new Error("Passkey authentication was cancelled");
			}
		}
		throw error;
	}

	// Step 3: Send credential to server for verification
	const verifyRes = await fetch("/auth/passkeys/authenticate/verify", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		credentials: "same-origin",
		body: JSON.stringify({
			challenge_id,
			credential,
		}),
	});

	if (!verifyRes.ok) {
		const error = await verifyRes.json().catch(() => ({}));
		throw new Error(
			error.detail || "Failed to verify passkey authentication",
		);
	}

	return verifyRes.json();
}

// =============================================================================
// Passkey Management
// =============================================================================

/**
 * Get list of user's registered passkeys
 */
export async function getPasskeys(): Promise<PasskeyListResponse> {
	const res = await authFetch("/auth/passkeys");
	if (!res.ok) {
		const error = await res.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to get passkeys");
	}
	return res.json();
}

/**
 * Delete a passkey by ID
 */
export async function deletePasskey(
	passkeyId: string,
): Promise<{ deleted: boolean }> {
	const res = await authFetch(`/auth/passkeys/${passkeyId}`, {
		method: "DELETE",
	});
	if (!res.ok) {
		const error = await res.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to delete passkey");
	}
	return res.json();
}
