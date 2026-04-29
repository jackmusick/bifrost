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

/**
 * Mirror of the backend's RESELLER_BY_HOST table. Returns null when the
 * endpoint is the model maker's own API (no prefix needed for lookup) or
 * unrecognized.
 */
const RESELLER_BY_HOST: Record<string, string> = {
	"openrouter.ai": "openrouter",
	"api.together.xyz": "together_ai",
	"api.fireworks.ai": "fireworks_ai",
	"api.deepinfra.com": "deepinfra",
	"api.groq.com": "groq",
	"integrate.api.nvidia.com": "nvidia_nim",
	"api.cerebras.ai": "cerebras",
	"inference.baseten.co": "baseten",
	"api.sambanova.ai": "sambanova",
	"api.ai21.com": "ai21_chat",
	"api.perplexity.ai": "perplexity",
	"api.mistral.ai": "mistral",
	"api.deepseek.com": "deepseek",
	"api.friendli.ai": "friendliai",
	"api.lambdalabs.com": "lambda_ai",
	"api.novita.ai": "novita",
	"api.hyperbolic.xyz": "hyperbolic",
	"api.replicate.com": "replicate",
	"ollama.com": "ollama",
	"api.z.ai": "z_ai",
};

export function resellerForEndpoint(endpoint: string | null | undefined): string | null {
	if (!endpoint) return null;
	try {
		const host = new URL(endpoint).hostname;
		return RESELLER_BY_HOST[host] ?? null;
	} catch {
		return null;
	}
}

/**
 * Three-step capability lookup mirroring the backend's lookup_capabilities():
 *   1. `<reseller>/<model_id>` exact match (handles OpenRouter/Together/etc.)
 *   2. `model_id` exact match (handles direct provider calls)
 *   3. Suffix-after-last-slash exact match (handles odd routing forms)
 */
export function lookupModel(
	modelId: string,
	reseller: string | null,
	byId: Record<string, PlatformModel>,
): PlatformModel | null {
	if (reseller) {
		const prefixed = `${reseller}/${modelId}`;
		if (byId[prefixed]) return byId[prefixed];
	}
	if (byId[modelId]) return byId[modelId];
	const suffix = modelId.includes("/")
		? modelId.slice(modelId.lastIndexOf("/") + 1)
		: null;
	if (suffix && byId[suffix]) return byId[suffix];
	return null;
}

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
