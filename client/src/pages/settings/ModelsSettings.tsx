/**
 * Models Settings (Chat V2 / M2)
 *
 * Per-org admin view of:
 * - The platform model catalog (read-only, synced from models.json).
 * - Org allowlist + default model (multi-select + single-select).
 * - "Migrate references" button — opens the migration modal so the admin can
 *   pick replacements for currently-referenced models that are about to be
 *   removed (most commonly during a provider switch).
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
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import {
	COST_TIER_GLYPH,
	listPlatformModels,
	type CostTier,
	type PlatformModel,
} from "@/services/platformModels";
import { ModelMigrationModal } from "@/components/admin/ModelMigrationModal";

interface OrgModelSettings {
	id: string;
	allowed_chat_models: string[];
	default_chat_model: string | null;
}

export function ModelsSettings() {
	const { user } = useAuth();
	const orgId = user?.organizationId ?? null;
	const [models, setModels] = useState<PlatformModel[]>([]);
	const [org, setOrg] = useState<OrgModelSettings | null>(null);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [migrationOpen, setMigrationOpen] = useState(false);
	const [migrationCandidates, setMigrationCandidates] = useState<string[]>([]);

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
				setModels(catalog.models);
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

	// Build combobox options from the platform catalog, sorted by tier then name.
	const allowedOptions = useMemo<MultiComboboxOption[]>(() => {
		const tierRank: Record<string, number> = { fast: 0, balanced: 1, premium: 2 };
		return [...models]
			.sort((a, b) => {
				const t = (tierRank[a.cost_tier] ?? 99) - (tierRank[b.cost_tier] ?? 99);
				return t !== 0 ? t : a.display_name.localeCompare(b.display_name);
			})
			.map((m) => ({
				value: m.model_id,
				label: `${COST_TIER_GLYPH[(m.cost_tier as CostTier) ?? "balanced"]} ${m.display_name}`,
				description: m.model_id,
			}));
	}, [models]);

	const allowed = org?.allowed_chat_models ?? [];
	const hasCatalog = models.length > 0;

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
			if (
				removed.length > 0 &&
				beforeAllow.size > 0 // empty = no narrowing → nothing to lose
			) {
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
	if (loading) {
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
						{hasCatalog
							? "Pick which models your users can chat with. Empty allowlist means every model in the platform catalog is available."
							: "No platform catalog yet — type model IDs as your provider expects them. Press Enter or Tab to add each one."}
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-3">
					<Label htmlFor="org-allowed-models">Models</Label>
					{hasCatalog ? (
						<MultiCombobox
							options={allowedOptions}
							value={allowed}
							onValueChange={(values) =>
								setOrg(org ? { ...org, allowed_chat_models: values } : null)
							}
							placeholder="All models allowed (no narrowing)"
							searchPlaceholder="Search models…"
						/>
					) : (
						<TagsInput
							value={allowed}
							onChange={(values) =>
								setOrg(org ? { ...org, allowed_chat_models: values } : null)
							}
							placeholder="Type a model ID and press Enter…"
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
					{hasCatalog ? (
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
								{models
									.filter(
										(m) =>
											allowed.length === 0 || allowed.includes(m.model_id),
									)
									.map((m) => (
										<SelectItem key={m.model_id} value={m.model_id}>
											{COST_TIER_GLYPH[(m.cost_tier as CostTier) ?? "balanced"]}{" "}
											{m.display_name}
										</SelectItem>
									))}
							</SelectContent>
						</Select>
					) : (
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
					)}
					{!hasCatalog && (
						<datalist id="default-model-suggestions">
							{allowed.map((m) => (
								<option key={m} value={m} />
							))}
						</datalist>
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
