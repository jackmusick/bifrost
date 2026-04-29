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
 * Capability lookup with multiple fallbacks. Provider-returned IDs and
 * LiteLLM keys disagree often enough that we need a chain:
 *   1. `<reseller>/<model_id>` exact (OpenRouter/Together/etc.)
 *   2. `model_id` exact (direct provider calls)
 *   3. `~`-stripped variants of both above (OpenRouter "redirect" aliases)
 *   4. Suffix-after-last-slash exact (odd routing forms)
 *   5. Endswith-match: any key whose suffix equals our suffix. Handles
 *      OpenRouter `moonshotai/kimi-k2.6` ↔ LiteLLM `moonshot/kimi-k2.6`.
 */
export function lookupModel(
	modelId: string,
	reseller: string | null,
	byId: Record<string, PlatformModel>,
): PlatformModel | null {
	const tryKey = (k: string) => byId[k] ?? null;
	const stripTilde = (s: string) => s.replace(/(^|\/)~/g, "$1");

	const cleanId = stripTilde(modelId);
	const candidates: string[] = [];
	if (reseller) {
		candidates.push(`${reseller}/${modelId}`);
		if (cleanId !== modelId) candidates.push(`${reseller}/${cleanId}`);
	}
	candidates.push(modelId);
	if (cleanId !== modelId) candidates.push(cleanId);

	for (const c of candidates) {
		const hit = tryKey(c);
		if (hit) return hit;
	}

	// Suffix exact (handles `~author/model` → `model`)
	const suffix = cleanId.includes("/")
		? cleanId.slice(cleanId.lastIndexOf("/") + 1)
		: null;
	if (suffix) {
		const hit = tryKey(suffix);
		if (hit) return hit;
		// Endswith-match: any catalog key whose own suffix is the same model.
		// Picks the first match (Object.keys order is insertion-stable in v8).
		const target = "/" + suffix;
		for (const k of Object.keys(byId)) {
			if (k === suffix || k.endsWith(target)) return byId[k];
		}
	}
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
