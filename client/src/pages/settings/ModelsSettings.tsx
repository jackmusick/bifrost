/**
 * Models Settings (Chat V2 / M2)
 *
 * Per-org admin view sitting under the configured LLM provider on the AI tab.
 *
 * Data flow:
 *   - The "available models" list comes from the configured provider's
 *     /v1/models response (via /api/admin/llm/models). That's the authoritative
 *     catalog — Anthropic, OpenAI, OpenRouter, or any custom OpenAI-compat
 *     endpoint all expose it.
 *   - For each returned model_id, we look up tier + capabilities in
 *     platform_models (synced from models.json). When a model isn't in our
 *     table — most common with direct-provider Anthropic/OpenAI calls — it
 *     falls into the "Uncategorized" tier section so the admin can still
 *     allowlist it.
 *
 * Three tier sections (⚡ Fast / ⚖ Balanced / 💎 Premium / Uncategorized).
 * Each section is a multi-select bound to that tier's slice of the provider
 * list. When the provider /models call fails, every section falls back to a
 * TagsInput so the admin can still curate by typing IDs.
 */

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
	MultiCombobox,
	type MultiComboboxOption,
} from "@/components/ui/multi-combobox";
import { TagsInput } from "@/components/ui/tags-input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { apiClient, $api } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import {
	COST_TIER_GLYPH,
	COST_TIER_LABEL,
	listPlatformModels,
	lookupModel,
	resellerForEndpoint,
	type CostTier,
	type PlatformModel,
} from "@/services/platformModels";
import { ModelMigrationModal } from "@/components/admin/ModelMigrationModal";

type SectionKey = CostTier | "uncategorized";
const SECTION_ORDER: SectionKey[] = ["fast", "balanced", "premium", "uncategorized"];
const SECTION_LABEL: Record<SectionKey, string> = {
	fast: COST_TIER_LABEL.fast,
	balanced: COST_TIER_LABEL.balanced,
	premium: COST_TIER_LABEL.premium,
	uncategorized: "Uncategorized",
};
const SECTION_GLYPH: Record<SectionKey, string> = {
	fast: COST_TIER_GLYPH.fast,
	balanced: COST_TIER_GLYPH.balanced,
	premium: COST_TIER_GLYPH.premium,
	uncategorized: "·",
};
const SECTION_DESCRIPTION: Record<SectionKey, string> = {
	fast: "Cheap, fast — short tasks.",
	balanced: "General-purpose default.",
	premium: "Highest quality, most expensive.",
	uncategorized: "Models we don't have capability metadata for yet.",
};

interface OrgModelSettings {
	id: string;
	allowed_chat_models: string[];
	default_chat_model: string | null;
}

interface ProviderModel {
	id: string;
	display_name: string;
}

export function ModelsSettings() {
	const { user } = useAuth();
	const orgId = user?.organizationId ?? null;

	const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
	const [org, setOrg] = useState<OrgModelSettings | null>(null);

	// Endpoint comes from LLMConfig — used to derive the reseller key for the
	// three-step capability lookup chain. Same query LLMConfig.tsx uses, so
	// react-query dedupes.
	const llmConfigQuery = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000 },
	);
	const reseller = resellerForEndpoint(llmConfigQuery.data?.endpoint ?? null);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [migrationOpen, setMigrationOpen] = useState(false);
	const [migrationCandidates, setMigrationCandidates] = useState<string[]>([]);

	// Provider models — reuse the same endpoint LLMConfig already polls.
	const providerModelsQuery = $api.useQuery(
		"get",
		"/api/admin/llm/models",
		undefined,
		{ retry: false, staleTime: 5 * 60 * 1000 },
	);
	const providerModels: ProviderModel[] | null = useMemo(() => {
		if (providerModelsQuery.data) return providerModelsQuery.data.models;
		if (providerModelsQuery.error) return [];
		return null;
	}, [providerModelsQuery.data, providerModelsQuery.error]);
	const providerError = providerModelsQuery.error
		? "Provider /v1/models unavailable; using freeform input."
		: null;

	useEffect(() => {
		if (!orgId) return;
		let cancelled = false;
		Promise.all([
			listPlatformModels(),
			apiClient.GET("/api/organizations/{org_id}", {
				params: { path: { org_id: orgId } },
			}),
		])
			.then(([catalog, orgRes]) => {
				if (cancelled) return;
				setPlatformModels(catalog.models);
				if (orgRes.data) {
					setOrg({
						id: orgRes.data.id,
						allowed_chat_models: orgRes.data.allowed_chat_models ?? [],
						default_chat_model: orgRes.data.default_chat_model ?? null,
					});
				}
			})
			.catch((e: unknown) => {
				if (!cancelled) setError(e instanceof Error ? e.message : String(e));
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, [orgId]);

	// Resolve each provider-returned model_id to its catalog row using the
	// three-step fallback chain (prefixed → bare → suffix). The result is the
	// authoritative source for tier, display name, etc.
	const platformByModelId = useMemo(() => {
		const idx: Record<string, PlatformModel> = {};
		for (const m of platformModels) idx[m.model_id] = m;
		return idx;
	}, [platformModels]);

	const matchByProviderId = useMemo(() => {
		const idx: Record<string, PlatformModel | null> = {};
		for (const p of providerModels ?? []) {
			idx[p.id] = lookupModel(p.id, reseller, platformByModelId);
		}
		return idx;
	}, [providerModels, reseller, platformByModelId]);

	function tierFor(modelId: string): SectionKey {
		const match = matchByProviderId[modelId];
		if (!match) return "uncategorized";
		return (match.cost_tier as CostTier) ?? "balanced";
	}

	function displayFor(modelId: string): string {
		const match = matchByProviderId[modelId];
		if (match?.display_name) return match.display_name;
		const fromProvider = providerModels?.find((p) => p.id === modelId);
		return fromProvider?.display_name || modelId;
	}

	// Group the provider's catalog by tier (uncategorized for unknown).
	const providerOptionsBySection = useMemo(() => {
		const out: Record<SectionKey, MultiComboboxOption[]> = {
			fast: [],
			balanced: [],
			premium: [],
			uncategorized: [],
		};
		for (const p of providerModels ?? []) {
			const tier = tierFor(p.id);
			out[tier].push({
				value: p.id,
				label: displayFor(p.id),
				description: p.id,
			});
		}
		for (const k of SECTION_ORDER) {
			out[k].sort((a, b) => a.label.localeCompare(b.label));
		}
		return out;
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [providerModels, matchByProviderId]);

	// Slice the org allowlist by section so each input shows only its own.
	const allowed = useMemo(
		() => org?.allowed_chat_models ?? [],
		[org?.allowed_chat_models],
	);
	const allowedBySection = useMemo(() => {
		const out: Record<SectionKey, string[]> = {
			fast: [],
			balanced: [],
			premium: [],
			uncategorized: [],
		};
		for (const id of allowed) {
			out[tierFor(id)].push(id);
		}
		return out;
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [allowed, matchByProviderId]);

	function setAllowedForSection(section: SectionKey, ids: string[]) {
		if (!org) return;
		// Replace this section's slice; keep other sections' selections intact.
		const others = allowed.filter((id) => tierFor(id) !== section);
		setOrg({ ...org, allowed_chat_models: [...others, ...ids] });
	}

	const usingFreetext = providerModels !== null && providerModels.length === 0;

	async function save() {
		if (!org) return;
		setSaving(true);
		setError(null);
		try {
			// If save would remove models that are currently in use, surface
			// the migration modal first.
			const previous = await apiClient.GET("/api/organizations/{org_id}", {
				params: { path: { org_id: org.id } },
			});
			const beforeAllow = new Set(previous.data?.allowed_chat_models ?? []);
			const afterAllow = new Set(org.allowed_chat_models);
			const removed = [...beforeAllow].filter((m) => !afterAllow.has(m));
			if (removed.length > 0 && beforeAllow.size > 0) {
				setMigrationCandidates(removed);
				setMigrationOpen(true);
				setSaving(false);
				return;
			}
			await apiClient.PATCH("/api/organizations/{org_id}", {
				params: { path: { org_id: org.id } },
				body: {
					allowed_chat_models: org.allowed_chat_models,
					default_chat_model: org.default_chat_model,
				},
			});
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e));
		} finally {
			setSaving(false);
		}
	}

	async function commitAfterMigration() {
		if (!org) return;
		setSaving(true);
		try {
			await apiClient.PATCH("/api/organizations/{org_id}", {
				params: { path: { org_id: org.id } },
				body: {
					allowed_chat_models: org.allowed_chat_models,
					default_chat_model: org.default_chat_model,
				},
			});
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e));
		} finally {
			setSaving(false);
		}
	}

	if (!orgId) {
		return (
			<div className="text-sm text-muted-foreground">
				Your account is not associated with an organization.
			</div>
		);
	}
	if (loading || providerModelsQuery.isLoading) {
		return (
			<div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
				<Loader2 className="mr-2 h-4 w-4 animate-spin" />
				Loading models…
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle>Allowed models</CardTitle>
					<CardDescription>
						Pick which models from your provider your users can chat with.
						{providerError ? ` ${providerError}` : ""} Empty allowlist means
						every model your provider exposes is available.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-6">
					{SECTION_ORDER.map((section) => {
						const opts = providerOptionsBySection[section];
						const selected = allowedBySection[section];
						// Skip uncategorized when there's nothing in it AND no items to add.
						if (
							section === "uncategorized" &&
							opts.length === 0 &&
							selected.length === 0 &&
							!usingFreetext
						) {
							return null;
						}
						return (
							<div key={section} className="space-y-2">
								<div>
									<Label className="text-sm font-semibold flex items-center gap-2">
										<span aria-hidden>{SECTION_GLYPH[section]}</span>
										{SECTION_LABEL[section]}
									</Label>
									<p className="text-xs text-muted-foreground">
										{SECTION_DESCRIPTION[section]}
									</p>
								</div>
								{usingFreetext ? (
									<TagsInput
										value={selected}
										onChange={(values) =>
											setAllowedForSection(section, values)
										}
										placeholder="Type a model_id and press Enter…"
									/>
								) : (
									<MultiCombobox
										options={opts}
										value={selected}
										onValueChange={(values) =>
											setAllowedForSection(section, values)
										}
										placeholder={
											opts.length === 0
												? "(no models from provider in this tier)"
												: "Choose models…"
										}
										searchPlaceholder="Search…"
										disabled={opts.length === 0}
									/>
								)}
							</div>
						);
					})}
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Default model</CardTitle>
					<CardDescription>
						Used when a user, role, workspace, or conversation hasn't picked
						something more specific.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Label htmlFor="org-default-model">Default</Label>
					{!usingFreetext ? (
						<Select
							value={org?.default_chat_model ?? ""}
							onValueChange={(v) =>
								setOrg(org ? { ...org, default_chat_model: v || null } : null)
							}
						>
							<SelectTrigger id="org-default-model" className="mt-1">
								<SelectValue placeholder="(no default — uses platform floor)" />
							</SelectTrigger>
							<SelectContent>
								{(providerModels ?? [])
									.filter(
										(m) => allowed.length === 0 || allowed.includes(m.id),
									)
									.map((m) => (
										<SelectItem key={m.id} value={m.id}>
											{displayFor(m.id)}
										</SelectItem>
									))}
							</SelectContent>
						</Select>
					) : (
						<>
							<input
								id="org-default-model"
								type="text"
								list="default-model-suggestions"
								value={org?.default_chat_model ?? ""}
								onChange={(e) =>
									setOrg(
										org
											? {
													...org,
													default_chat_model: e.target.value || null,
												}
											: null,
									)
								}
								placeholder="model_id (or leave blank for platform floor)"
								className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
							/>
							<datalist id="default-model-suggestions">
								{allowed.map((m) => (
									<option key={m} value={m} />
								))}
							</datalist>
						</>
					)}
				</CardContent>
			</Card>

			{error && (
				<div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
					{error}
				</div>
			)}

			<div className="flex justify-end gap-2">
				<Button onClick={save} disabled={saving || !org}>
					{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
					Save
				</Button>
			</div>

			<ModelMigrationModal
				open={migrationOpen}
				onOpenChange={setMigrationOpen}
				oldModelIds={migrationCandidates}
				onComplete={() => {
					setMigrationCandidates([]);
					void commitAfterMigration();
				}}
			/>
		</div>
	);
}
