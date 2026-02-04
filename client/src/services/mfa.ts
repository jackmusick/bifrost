/**
 * MFA service for managing two-factor authentication
 */

import { authFetch } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types from generated schema
export type MFAStatus = components["schemas"]["MFAStatusResponse"];
export type MFASetupResponse = components["schemas"]["src__routers__mfa__MFASetupResponse"];
export type MFAVerifyResponse = components["schemas"]["MFAVerifyResponse"];
export type MFARemoveRequest = components["schemas"]["MFARemoveRequest"];
export type RecoveryCodesResponse = components["schemas"]["RecoveryCodesResponse"];
export type RecoveryCodesCountResponse = components["schemas"]["RecoveryCodesCountResponse"];

/**
 * Get MFA status for current user
 */
export async function getMFAStatus(): Promise<MFAStatus> {
	const response = await authFetch("/auth/mfa/status");
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to get MFA status");
	}
	return response.json();
}

/**
 * Start TOTP setup
 */
export async function setupTOTP(): Promise<MFASetupResponse> {
	const response = await authFetch("/auth/mfa/totp/setup", {
		method: "POST",
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to initialize TOTP setup");
	}
	return response.json();
}

/**
 * Verify TOTP setup with code
 */
export async function verifyTOTPSetup(
	code: string,
): Promise<MFAVerifyResponse> {
	const response = await authFetch("/auth/mfa/totp/verify", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ code }),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Invalid verification code");
	}
	return response.json();
}

/**
 * Remove MFA
 */
export async function removeMFA(params: MFARemoveRequest): Promise<void> {
	const response = await authFetch("/auth/mfa", {
		method: "DELETE",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(params),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to remove MFA");
	}
}

/**
 * Get recovery codes count
 */
export async function getRecoveryCodesCount(): Promise<RecoveryCodesCountResponse> {
	const response = await authFetch("/auth/mfa/recovery-codes/count");
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to get recovery codes count");
	}
	return response.json();
}

/**
 * Regenerate recovery codes
 */
export async function regenerateRecoveryCodes(
	mfaCode: string,
): Promise<RecoveryCodesResponse> {
	const response = await authFetch("/auth/mfa/recovery-codes/regenerate", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ mfa_code: mfaCode }),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to regenerate recovery codes");
	}
	return response.json();
}

export const mfaService = {
	getMFAStatus,
	setupTOTP,
	verifyTOTPSetup,
	removeMFA,
	getRecoveryCodesCount,
	regenerateRecoveryCodes,
};
