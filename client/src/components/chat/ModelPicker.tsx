/**
 * Model Picker
 *
 * Lets the user pick a model for the current conversation. Shows the full
 * platform catalog; models outside the org allowlist are visible-but-disabled
 * with a provenance tooltip ("restricted by your org admin"). Cost tier
 * glyphs (⚡ / ⚖ / 💎) sit next to each name.
 *
 * Spec: docs/superpowers/specs/2026-04-27-chat-ux-design.md §16.6.
 */

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Check, Lock } from "lucide-react";

import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
	type CostTier,
	COST_TIER_GLYPH,
	COST_TIER_LABEL,
	type PlatformModel,
	listPlatformModels,
} from "@/services/platformModels";

interface ModelPickerProps {
	/** Current selection. May be undefined while the conversation has no override. */
	value: string | null | undefined;
	/** Org allowlist; if empty/undefined, every platform model is allowed. */
	allowedModelIds?: string[];
	/** Called when the user picks a model. */
	onChange: (modelId: string) => void;
	/** Disable the trigger entirely. */
	disabled?: boolean;
	/** Compact mode hides the model name in the trigger, showing only the glyph. */
	compact?: boolean;
}

const TIER_ORDER: CostTier[] = ["fast", "balanced", "premium"];

export function ModelPicker({
	value,
	allowedModelIds,
	onChange,
	disabled = false,
	compact = false,
}: ModelPickerProps) {
	const [models, setModels] = useState<PlatformModel[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;
		listPlatformModels()
			.then((res) => {
				if (cancelled) return;
				setModels(res.models);
				setError(null);
			})
			.catch((e: unknown) => {
				if (cancelled) return;
				setError(e instanceof Error ? e.message : "Failed to load models");
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const allowed = useMemo(() => {
		const set = allowedModelIds && allowedModelIds.length > 0 ? new Set(allowedModelIds) : null;
		return set;
	}, [allowedModelIds]);

	const selected = models.find((m) => m.model_id === value);
	const grouped = useMemo(() => {
		const out: Record<CostTier, PlatformModel[]> = {
			fast: [],
			balanced: [],
			premium: [],
		};
		for (const m of models) {
			const tier = (m.cost_tier as CostTier) ?? "balanced";
			(out[tier] ?? out.balanced).push(m);
		}
		for (const tier of TIER_ORDER) {
			out[tier].sort((a, b) => a.display_name.localeCompare(b.display_name));
		}
		return out;
	}, [models]);

	const triggerLabel = (() => {
		if (loading) return "Loading models…";
		if (error) return "Models unavailable";
		if (!selected) return "Select a model";
		const glyph = COST_TIER_GLYPH[(selected.cost_tier as CostTier) ?? "balanced"];
		return compact ? glyph : `${glyph} ${selected.display_name}`;
	})();

	return (
		<TooltipProvider delayDuration={200}>
			<DropdownMenu>
				<DropdownMenuTrigger asChild>
					<Button
						variant="ghost"
						size="sm"
						disabled={disabled || loading || !!error}
						className={cn("gap-1.5 text-xs font-normal", compact && "px-2")}
					>
						<span className="truncate">{triggerLabel}</span>
						<ChevronDown className="h-3 w-3 opacity-60" />
					</Button>
				</DropdownMenuTrigger>
				<DropdownMenuContent align="start" className="w-72">
					{TIER_ORDER.map((tier) => {
						const items = grouped[tier];
						if (items.length === 0) return null;
						return (
							<div key={tier}>
								<DropdownMenuLabel className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
									<span aria-hidden>{COST_TIER_GLYPH[tier]}</span>
									{COST_TIER_LABEL[tier]}
								</DropdownMenuLabel>
								{items.map((m) => {
									const isAllowed = !allowed || allowed.has(m.model_id);
									const isSelected = m.model_id === value;
									const item = (
										<DropdownMenuItem
											key={m.model_id}
											disabled={!isAllowed}
											className={cn(
												"flex items-start gap-2",
												!isAllowed && "opacity-60",
											)}
											onSelect={(e) => {
												if (!isAllowed) {
													e.preventDefault();
													return;
												}
												onChange(m.model_id);
											}}
										>
											<div className="flex-1 min-w-0">
												<div className="flex items-center gap-1.5">
													<span className="text-sm">{m.display_name}</span>
													{!isAllowed && (
														<Lock className="h-3 w-3 text-muted-foreground" />
													)}
												</div>
												<div className="text-[11px] text-muted-foreground truncate">
													{m.model_id}
												</div>
											</div>
											{isSelected && <Check className="h-4 w-4 mt-0.5" />}
										</DropdownMenuItem>
									);
									if (isAllowed) return item;
									return (
										<Tooltip key={m.model_id}>
											<TooltipTrigger asChild>
												<div>{item}</div>
											</TooltipTrigger>
											<TooltipContent side="right">
												Restricted by your org admin
											</TooltipContent>
										</Tooltip>
									);
								})}
								<DropdownMenuSeparator />
							</div>
						);
					})}
					{models.length === 0 && (
						<div className="px-3 py-2 text-xs text-muted-foreground">
							No models available. Ask your platform admin to run the model
							registry sync.
						</div>
					)}
				</DropdownMenuContent>
			</DropdownMenu>
		</TooltipProvider>
	);
}
