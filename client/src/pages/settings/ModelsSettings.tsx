/**
 * Models Settings (Chat V2 / M2)
 *
 * Per-org admin view sitting under the configured LLM provider on the AI tab.
 * Uses the canonical <ModelSelect /> for both allowed-models (multi) and the
 * default-model (single). No tier sections, no Uncategorized bucket — every
 * row shows price/context/capability info and the admin reads it directly.
 *
 * Save flow opens the migration modal when narrowing the allowlist would
 * orphan currently-referenced models.
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
import { TagsInput } from "@/components/ui/tags-input";
import { apiClient, $api } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import {
	listPlatformModels,
	resellerForEndpoint,
	type PlatformModel,
} from "@/services/platformModels";
import { ModelSelect, type ModelSelectModel } from "@/components/chat/ModelSelect";
import { ModelMigrationModal } from "@/components/admin/ModelMigrationModal";

interface OrgModelSettings {
	id: string;
	allowed_chat_models: string[];
	default_chat_model: string | null;
}

export function ModelsSettings() {
	const { user } = useAuth();
	const orgId = user?.organizationId ?? null;

	const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
	const [org, setOrg] = useState<OrgModelSettings | null>(null);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [migrationOpen, setMigrationOpen] = useState(false);
	const [migrationCandidates, setMigrationCandidates] = useState<string[]>([]);

	const llmConfigQuery = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000 },
	);
	const reseller = resellerForEndpoint(llmConfigQuery.data?.endpoint ?? null);

	const providerModelsQuery = $api.useQuery(
		"get",
		"/api/admin/llm/models",
		undefined,
		{ retry: false, staleTime: 5 * 60 * 1000 },
	);
	const providerModels: ModelSelectModel[] | null = useMemo(() => {
		if (providerModelsQuery.data) return providerModelsQuery.data.models;
		if (providerModelsQuery.error) return [];
		return null;
	}, [providerModelsQuery.data, providerModelsQuery.error]);

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

	const platformByModelId = useMemo(() => {
		const idx: Record<string, PlatformModel> = {};
		for (const m of platformModels) idx[m.model_id] = m;
		return idx;
	}, [platformModels]);

	const allowed = org?.allowed_chat_models ?? [];

	async function save() {
		if (!org) return;
		setSaving(true);
		setError(null);
		try {
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

	const usingFreetext = providerModels !== null && providerModels.length === 0;

	return (
		<div className="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle>Allowed models</CardTitle>
					<CardDescription>
						Pick the models from your provider that your users can chat with.
						Empty allowlist means every model your provider exposes is
						available.
					</CardDescription>
				</CardHeader>
				<CardContent>
					{usingFreetext ? (
						<TagsInput
							value={allowed}
							onChange={(values) =>
								setOrg(org ? { ...org, allowed_chat_models: values } : null)
							}
							placeholder="Type a model_id and press Enter…"
						/>
					) : (
						<ModelSelect
							multiple
							models={providerModels ?? []}
							catalog={platformByModelId}
							reseller={reseller}
							value={allowed}
							onChange={(values) =>
								setOrg(org ? { ...org, allowed_chat_models: values } : null)
							}
							placeholder="All models allowed (no narrowing)"
						/>
					)}
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
						<ModelSelect
							models={providerModels ?? []}
							catalog={platformByModelId}
							reseller={reseller}
							restrictToIds={allowed}
							value={org?.default_chat_model ?? null}
							onChange={(v) =>
								setOrg(org ? { ...org, default_chat_model: v } : null)
							}
							placeholder="(no default — uses platform floor)"
						/>
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
