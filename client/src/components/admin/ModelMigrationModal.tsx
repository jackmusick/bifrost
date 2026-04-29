/**
 * Model Migration Modal
 *
 * Opens when an admin is about to apply a change that removes access to
 * currently-referenced models. Shows the impact map + a replacement input
 * per old model (dropdown when the new provider is in `platform_models`,
 * free-text when it isn't), then calls /apply-migration on confirm.
 */

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	applyModelMigration,
	listPlatformModels,
	previewModelMigration,
	type PlatformModel,
	type ModelMigrationImpactItem,
} from "@/services/platformModels";

interface ModelMigrationModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	/** Models the admin is about to lose access to. */
	oldModelIds: string[];
	/** Called after the apply step succeeds. */
	onComplete?: () => void;
}

export function ModelMigrationModal({
	open,
	onOpenChange,
	oldModelIds,
	onComplete,
}: ModelMigrationModalProps) {
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [impacts, setImpacts] = useState<ModelMigrationImpactItem[]>([]);
	const [available, setAvailable] = useState<PlatformModel[]>([]);
	const [replacements, setReplacements] = useState<Record<string, string>>({});
	const [submitting, setSubmitting] = useState(false);

	useEffect(() => {
		if (!open || oldModelIds.length === 0) return;
		let cancelled = false;
		// Kick off load asynchronously so React doesn't see synchronous setState in the effect body.
		queueMicrotask(() => {
			if (cancelled) return;
			setLoading(true);
			setError(null);
		});
		Promise.all([
			previewModelMigration({ old_model_ids: oldModelIds }),
			listPlatformModels(),
		])
			.then(([preview, catalog]) => {
				if (cancelled) return;
				setImpacts(preview.items);
				setAvailable(catalog.models);
				const initial: Record<string, string> = {};
				for (const item of preview.items) {
					if (item.suggested_replacement) {
						initial[item.model_id] = item.suggested_replacement;
					}
				}
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
	}, [open, oldModelIds]);

	const totalRefs = impacts.reduce((acc, i) => acc + i.total, 0);
	const canSubmit =
		impacts.length > 0 &&
		impacts.every((i) => (replacements[i.model_id] ?? "").trim().length > 0);

	async function handleApply() {
		if (!canSubmit) return;
		setSubmitting(true);
		try {
			await applyModelMigration({ replacements });
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
						{totalRefs > 0
							? `Migrate ${totalRefs} model reference${totalRefs === 1 ? "" : "s"}`
							: "No migration needed"}
					</DialogTitle>
					<DialogDescription>
						These models are about to become unreachable. Pick a replacement
						for each — the suggested option matches the original cost tier when
						available. If your new provider isn't in the catalog yet, type the
						model ID it expects.
					</DialogDescription>
				</DialogHeader>

				{loading ? (
					<div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
						<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						Scanning references…
					</div>
				) : error ? (
					<div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
						{error}
					</div>
				) : impacts.length === 0 ? (
					<p className="text-sm text-muted-foreground">
						Nothing references these models. Safe to proceed.
					</p>
				) : (
					<div className="space-y-4 max-h-[60vh] overflow-auto">
						{impacts.map((item) => (
							<div
								key={item.model_id}
								className="rounded border p-3 space-y-2"
							>
								<div className="flex items-baseline justify-between gap-2">
									<code className="text-sm font-mono">{item.model_id}</code>
									<span className="text-xs text-muted-foreground">
										{item.total} reference{item.total === 1 ? "" : "s"}
									</span>
								</div>
								<div className="text-xs text-muted-foreground">
									{Object.entries(item.by_kind)
										.filter(([, n]) => n > 0)
										.map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`)
										.join(" · ") || "no references"}
								</div>
								<div>
									<Label
										htmlFor={`replacement-${item.model_id}`}
										className="text-xs"
									>
										Replacement
									</Label>
									<Input
										id={`replacement-${item.model_id}`}
										list={`available-models-${item.model_id}`}
										value={replacements[item.model_id] ?? ""}
										onChange={(e) =>
											setReplacements((r) => ({
												...r,
												[item.model_id]: e.target.value,
											}))
										}
										placeholder="model_id from your new provider"
										className="font-mono text-xs"
									/>
									<datalist id={`available-models-${item.model_id}`}>
										{available.map((m) => (
											<option
												key={m.model_id}
												value={m.model_id}
												label={`${m.display_name} · ${m.cost_tier}`}
											/>
										))}
									</datalist>
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
					<Button onClick={handleApply} disabled={!canSubmit || submitting}>
						{submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
						Apply replacements
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
