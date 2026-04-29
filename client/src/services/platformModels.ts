/**
 * Platform model registry + admin model-migration API.
 */

import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

export type PlatformModel = components["schemas"]["PlatformModelPublic"];
export type PlatformModelListResponse =
	components["schemas"]["PlatformModelListResponse"];
export type ModelMigrationPreviewRequest =
	components["schemas"]["ModelMigrationPreviewRequest"];
export type ModelMigrationPreviewResponse =
	components["schemas"]["ModelMigrationPreviewResponse"];
export type ModelMigrationApplyRequest =
	components["schemas"]["ModelMigrationApplyRequest"];
export type ModelMigrationApplyResponse =
	components["schemas"]["ModelMigrationApplyResponse"];
export type ModelMigrationImpactItem =
	components["schemas"]["ModelMigrationImpactItem"];

export type CostTier = "fast" | "balanced" | "premium";

export const COST_TIER_GLYPH: Record<CostTier, string> = {
	fast: "⚡",
	balanced: "⚖",
	premium: "💎",
};

export const COST_TIER_LABEL: Record<CostTier, string> = {
	fast: "Fast",
	balanced: "Balanced",
	premium: "Premium",
};

export async function listPlatformModels(): Promise<PlatformModelListResponse> {
	const { data, error } = await apiClient.GET("/api/platform-models");
	if (error) throw new Error(`Failed to list platform models: ${JSON.stringify(error)}`);
	return data;
}

export async function previewModelMigration(
	request: ModelMigrationPreviewRequest,
): Promise<ModelMigrationPreviewResponse> {
	const { data, error } = await apiClient.POST(
		"/api/admin/models/preview-migration",
		{ body: request },
	);
	if (error) throw new Error(`Preview failed: ${JSON.stringify(error)}`);
	return data;
}

export async function applyModelMigration(
	request: ModelMigrationApplyRequest,
): Promise<ModelMigrationApplyResponse> {
	const { data, error } = await apiClient.POST(
		"/api/admin/models/apply-migration",
		{ body: request },
	);
	if (error) throw new Error(`Apply failed: ${JSON.stringify(error)}`);
	return data;
}
