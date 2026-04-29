/**
 * Models Settings (Chat V2 / M2)
 *
 * Sits under <LLMConfig /> on the AI tab. Two cards: allowed models, default
 * model. Both autosave on change (debounced 500ms) — no Save button. Status
 * indicators in each card header show idle / saving / saved / error.
 *
 * The migration modal still intercepts allowlist-narrowing. On cancel, local
 * state reverts to the last-saved snapshot so the picker stops showing
 * removed models.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";

import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { TagsInput } from "@/components/ui/tags-input";
import { apiClient, $api } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import {
	resellerForEndpoint,
	type PlatformModel,
} from "@/services/platformModels";
import { ModelSelect, type ModelSelectModel } from "@/components/chat/ModelSelect";
import { listPlatformModels } from "@/services/platformModels";

interface OrgModelSettings {
	id: string;
	allowed_chat_models: string[];
	default_chat_model: string | null;
}

type SaveStatus = "idle" | "saving" | "saved" | "error";

function StatusBadge({ status, errorMessage }: { status: SaveStatus; errorMessage?: string }) {
	if (status === "saving") {
		return (
			<span className="flex items-center gap-1.5 text-xs text-muted-foreground">
				<Loader2 className="h-3 w-3 animate-spin" />
				Saving…
			</span>
		);
	}
	if (status === "saved") {
		return (
			<span className="flex items-center gap-1.5 text-xs text-muted-foreground">
				<Check className="h-3 w-3" />
				Saved
			</span>
		);
	}
	if (status === "error") {
		return (
			<span className="text-xs text-destructive" title={errorMessage}>
				Couldn't save
			</span>
		);
	}
	return null;
}

export function ModelsSettings() {
	const { user } = useAuth();
	const orgId = user?.organizationId ?? null;

	const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
	const [org, setOrg] = useState<OrgModelSettings | null>(null);
	const [loading, setLoading] = useState(true);
	const [allowedStatus, setAllowedStatus] = useState<SaveStatus>("idle");
	const [defaultStatus, setDefaultStatus] = useState<SaveStatus>("idle");
	const [error, setError] = useState<string | null>(null);

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
					const initial = {
						id: orgRes.data.id,
						allowed_chat_models: orgRes.data.allowed_chat_models ?? [],
						default_chat_model: orgRes.data.default_chat_model ?? null,
					};
					setOrg(initial);
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

	// --- autosave plumbing ---------------------------------------------------
	// Per-section debounced PATCH. The status badge in each card header reflects
	// idle/saving/saved/error.
	const allowedTimer = useRef<number | null>(null);
	const defaultTimer = useRef<number | null>(null);
	const allowedSavedTimer = useRef<number | null>(null);
	const defaultSavedTimer = useRef<number | null>(null);

	async function persist(
		next: OrgModelSettings,
		setStatus: (s: SaveStatus) => void,
		savedTimerRef: React.MutableRefObject<number | null>,
	) {
		setStatus("saving");
		setError(null);
		try {
			await apiClient.PATCH("/api/organizations/{org_id}", {
				params: { path: { org_id: next.id } },
				body: {
					allowed_chat_models: next.allowed_chat_models,
					default_chat_model: next.default_chat_model,
				},
			});
			setStatus("saved");
			if (savedTimerRef.current) window.clearTimeout(savedTimerRef.current);
			savedTimerRef.current = window.setTimeout(() => setStatus("idle"), 2000);
		} catch (e) {
			setStatus("error");
			setError(e instanceof Error ? e.message : String(e));
		}
	}

	function setAllowed(next: string[]) {
		if (!org) return;
		const updated = { ...org, allowed_chat_models: next };
		setOrg(updated);
		if (allowedTimer.current) window.clearTimeout(allowedTimer.current);
		allowedTimer.current = window.setTimeout(async () => {
			// Narrowing your own org's allowlist is a non-event for migration:
			// the chat picker just won't pick those models anymore, which is
			// the intent. The migration flow runs at the platform level (when
			// LLMConfig changes make models unreachable across the install)
			// and lives in the LLMConfig save flow, not here.
			await persist(updated, setAllowedStatus, allowedSavedTimer);
		}, 500);
	}

	function setDefault(next: string | null) {
		if (!org) return;
		const updated = { ...org, default_chat_model: next };
		setOrg(updated);
		if (defaultTimer.current) window.clearTimeout(defaultTimer.current);
		defaultTimer.current = window.setTimeout(async () => {
			await persist(updated, setDefaultStatus, defaultSavedTimer);
		}, 500);
	}

	useEffect(() => {
		return () => {
			if (allowedTimer.current) window.clearTimeout(allowedTimer.current);
			if (defaultTimer.current) window.clearTimeout(defaultTimer.current);
			if (allowedSavedTimer.current) window.clearTimeout(allowedSavedTimer.current);
			if (defaultSavedTimer.current) window.clearTimeout(defaultSavedTimer.current);
		};
	}, []);

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
	const allowed = org?.allowed_chat_models ?? [];

	return (
		<div className="space-y-6">
			<Card>
				<CardHeader>
					<div className="flex items-start justify-between gap-4">
						<div className="space-y-1.5">
							<CardTitle>Allowed models</CardTitle>
							<CardDescription>
								Pick the models from your provider that your users can chat
								with. Empty allowlist means every model your provider exposes
								is available.
							</CardDescription>
						</div>
						<StatusBadge
							status={allowedStatus}
							errorMessage={error ?? undefined}
						/>
					</div>
				</CardHeader>
				<CardContent>
					{usingFreetext ? (
						<TagsInput
							value={allowed}
							onChange={setAllowed}
							placeholder="Type a model_id and press Enter…"
						/>
					) : (
						<ModelSelect
							multiple
							models={providerModels ?? []}
							catalog={platformByModelId}
							reseller={reseller}
							value={allowed}
							onChange={setAllowed}
							placeholder="All models allowed (no narrowing)"
						/>
					)}
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<div className="flex items-start justify-between gap-4">
						<div className="space-y-1.5">
							<CardTitle>Default model</CardTitle>
							<CardDescription>
								Used when a user, role, workspace, or conversation hasn't
								picked something more specific.
							</CardDescription>
						</div>
						<StatusBadge
							status={defaultStatus}
							errorMessage={error ?? undefined}
						/>
					</div>
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
							onChange={setDefault}
							placeholder="(no default — uses platform floor)"
						/>
					) : (
						<>
							<input
								id="org-default-model"
								type="text"
								list="default-model-suggestions"
								value={org?.default_chat_model ?? ""}
								onChange={(e) => setDefault(e.target.value || null)}
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

			{error && allowedStatus !== "error" && defaultStatus !== "error" && (
				<div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
					{error}
				</div>
			)}
		</div>
	);
}
