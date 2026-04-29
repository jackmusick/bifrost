/**
 * Platform-wide Model Migration Modal
 *
 * Opens when an LLM-config change is about to make some model_ids
 * unreachable for the whole installation. Shows the platform admin which
 * orgs reference those models in their allowlists, and lets them pick a
 * replacement (from the new provider's catalog) or drop the entry per old
 * model.
 *
 * Scope is intentionally narrow: only `Organization.allowed_chat_models`.
 * Defaults (org/role/workspace/user/conversation default_model) self-heal
 * via the resolver's lookup-time fallback, so they're not in this flow.
 */

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { ModelSelect, type ModelSelectModel } from "@/components/chat/ModelSelect";
import { resellerForEndpoint } from "@/services/platformModels";
import { $api } from "@/lib/api-client";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
	applyAllowlistMigration,
	listPlatformModels,
	previewAllowlistMigration,
	type OrgAllowlistImpactRow,
	type PlatformModel,
} from "@/services/platformModels";

interface ModelMigrationModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	/** Models that will become unreachable after the imminent LLM-config change. */
	unreachableModelIds: string[];
	/** Called after the apply step succeeds — typically to commit the LLM config save that triggered this. */
	onComplete?: () => void;
}

export function ModelMigrationModal({
	open,
	onOpenChange,
	unreachableModelIds,
	onComplete,
}: ModelMigrationModalProps) {
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [affected, setAffected] = useState<OrgAllowlistImpactRow[]>([]);
	const [catalogModels, setCatalogModels] = useState<PlatformModel[]>([]);
	const [replacements, setReplacements] = useState<
		Record<string, string | null>
	>({});
	const [submitting, setSubmitting] = useState(false);

	// Provider catalog (the new provider's available models)
	const llmConfigQuery = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000, enabled: open },
	);
	const reseller = resellerForEndpoint(llmConfigQuery.data?.endpoint ?? null);
	const providerModelsQuery = $api.useQuery(
		"get",
		"/api/admin/llm/models",
		undefined,
		{ retry: false, staleTime: 5 * 60 * 1000, enabled: open },
	);
	const providerModels: ModelSelectModel[] =
		providerModelsQuery.data?.models ?? [];
	const catalogById = useMemo(() => {
		const idx: Record<string, PlatformModel> = {};
		for (const m of catalogModels) idx[m.model_id] = m;
		return idx;
	}, [catalogModels]);

	useEffect(() => {
		if (!open || unreachableModelIds.length === 0) return;
		let cancelled = false;
		queueMicrotask(() => {
			if (cancelled) return;
			setLoading(true);
			setError(null);
		});
		Promise.all([
			previewAllowlistMigration({ unreachable_model_ids: unreachableModelIds }),
			listPlatformModels(),
		])
			.then(([preview, catalog]) => {
				if (cancelled) return;
				setAffected(preview.affected_orgs);
				setCatalogModels(catalog.models);
				// Initialize each unreachable id with no replacement (admin
				// chooses or leaves as "drop").
				const initial: Record<string, string | null> = {};
				for (const id of unreachableModelIds) initial[id] = null;
				setReplacements(initial);
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
	}, [open, unreachableModelIds]);

	const totalOrgs = affected.length;
	// Aggregate orphaned ids across all orgs so admin sees one input per id
	// rather than one per (org, id).
	const allOrphanedIds = useMemo(() => {
		const set = new Set<string>();
		for (const o of affected) for (const id of o.orphaned_model_ids) set.add(id);
		return [...set].sort();
	}, [affected]);

	async function handleApply() {
		setSubmitting(true);
		try {
			await applyAllowlistMigration({ replacements });
			onComplete?.();
			onOpenChange(false);
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e));
		} finally {
			setSubmitting(false);
		}
	}

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl">
				<DialogHeader>
					<DialogTitle>
						{totalOrgs > 0
							? `${totalOrgs} org${totalOrgs === 1 ? "" : "s"} reference unreachable models`
							: "Nothing to migrate"}
					</DialogTitle>
					<DialogDescription>
						These models will no longer be reachable after the configuration
						change. Pick a replacement from your new provider for each, or
						leave it blank to drop the entry from every affected allowlist.
					</DialogDescription>
				</DialogHeader>

				{loading ? (
					<div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
						<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						Scanning org allowlists…
					</div>
				) : error ? (
					<div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
						{error}
					</div>
				) : totalOrgs === 0 ? (
					<p className="text-sm text-muted-foreground">
						No org allowlists reference these models. Safe to proceed.
					</p>
				) : (
					<div className="space-y-4 max-h-[60vh] overflow-auto">
						<div className="rounded border p-3 space-y-1">
							<div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								Affected orgs
							</div>
							<ul className="text-sm space-y-0.5">
								{affected.map((o) => (
									<li key={o.organization_id}>
										<span className="font-medium">{o.organization_name}</span>
										<span className="ml-2 text-xs text-muted-foreground">
											{o.orphaned_model_ids.join(", ")}
										</span>
									</li>
								))}
							</ul>
						</div>

						{allOrphanedIds.map((oldId) => (
							<div key={oldId} className="rounded border p-3 space-y-2">
								<div>
									<code className="text-sm font-mono">{oldId}</code>
								</div>
								<div className="space-y-1.5">
									<Label className="text-xs">Replacement</Label>
									<ModelSelect
										models={providerModels}
										catalog={catalogById}
										reseller={reseller}
										value={replacements[oldId] ?? null}
										onChange={(v) =>
											setReplacements((r) => ({ ...r, [oldId]: v }))
										}
										clearable
										placeholder="(drop from every allowlist)"
									/>
								</div>
							</div>
						))}
					</div>
				)}

				<DialogFooter>
					<Button
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={submitting}
					>
						Cancel
					</Button>
					<Button onClick={handleApply} disabled={submitting || totalOrgs === 0}>
						{submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
						Apply
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
