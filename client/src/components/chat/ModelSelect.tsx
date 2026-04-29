/**
 * ModelSelect
 *
 * Canonical "pick a model" component. Used by the chat composer (single
 * select), the org allowlist (multi select), the user/org default-model
 * picker (single), and anywhere else we need to pick from the configured
 * provider's catalog.
 *
 * Each row shows:
 *   line 1: human display name
 *   line 2: price ($/M), context window, capability icons (vision/tools/pdf/audio)
 *
 * Capability/price data comes from `platform_models` (synced from LiteLLM)
 * resolved against the provider-returned model_id via the three-step lookup
 * chain (<reseller>/<id> → <id> → suffix). Models with no catalog match
 * still appear; their second line is just the raw model_id.
 *
 * No cost-tier sections, no Uncategorized bucket — the admin reads the price
 * and decides for themselves.
 */

import { useMemo, useState } from "react";
import { Check, ChevronsUpDown, FileText, Hammer, Image, Mic, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import {
	lookupModel,
	type PlatformModel,
} from "@/services/platformModels";

export interface ModelSelectModel {
	id: string;
	display_name: string;
}

interface BaseProps {
	/** Models the configured LLM provider exposes via /v1/models. */
	models: ModelSelectModel[];
	/** Catalog rows keyed by model_id (from platform_models / LiteLLM). */
	catalog: Record<string, PlatformModel>;
	/** Reseller key (openrouter, together_ai, etc.) for catalog lookup. Null = direct. */
	reseller: string | null;
	/** Restrict choices (e.g. for default-model when an allowlist is set). */
	restrictToIds?: string[];
	placeholder?: string;
	disabled?: boolean;
	className?: string;
}

interface SingleProps extends BaseProps {
	multiple?: false;
	value: string | null;
	onChange: (value: string | null) => void;
}

interface MultiProps extends BaseProps {
	multiple: true;
	value: string[];
	onChange: (value: string[]) => void;
}

type Props = SingleProps | MultiProps;

interface RichRow {
	id: string;
	display: string;
	price: string | null;
	context: string | null;
	caps: string[]; // icon keys
	match: PlatformModel | null;
}

function fmtPrice(
	input: number | string | null | undefined,
	output: number | string | null | undefined,
): string | null {
	const ni = input == null ? null : Number(input);
	const no = output == null ? null : Number(output);
	const valid = (n: number | null): n is number => n != null && Number.isFinite(n);
	if (!valid(ni) && !valid(no)) return null;
	const fmt = (n: number) => (n < 0.01 ? n.toFixed(4) : n.toFixed(2));
	const i = valid(ni) ? `$${fmt(ni)}` : "—";
	const o = valid(no) ? `$${fmt(no)}` : "—";
	return `${i} / ${o} per M`;
}

function fmtContext(ctx: number | null | undefined): string | null {
	if (!ctx || ctx <= 0) return null;
	if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M ctx`;
	if (ctx >= 1_000) return `${Math.round(ctx / 1_000)}k ctx`;
	return `${ctx} ctx`;
}

function buildRows(props: Props): RichRow[] {
	const { models, catalog, reseller, restrictToIds } = props;
	const restrict = restrictToIds && restrictToIds.length > 0 ? new Set(restrictToIds) : null;
	const rows = models
		.filter((m) => !restrict || restrict.has(m.id))
		.map((m): RichRow => {
			const match = lookupModel(m.id, reseller, catalog);
			const caps: string[] = [];
			if (match?.capabilities?.supports_images_in) caps.push("vision");
			if (match?.capabilities?.supports_tool_use) caps.push("tools");
			if (match?.capabilities?.supports_pdf_in) caps.push("pdf");
			if (match?.capabilities?.supports_audio_in) caps.push("audio");
			return {
				id: m.id,
				display: match?.display_name?.trim() || m.display_name?.trim() || m.id,
				price: fmtPrice(
					match?.input_price_per_million ?? null,
					match?.output_price_per_million ?? null,
				),
				context: fmtContext(match?.context_window),
				caps,
				match,
			};
		})
		.sort((a, b) => a.display.localeCompare(b.display));
	return rows;
}

function CapIcon({ kind }: { kind: string }) {
	const cls = "h-3 w-3 text-muted-foreground";
	if (kind === "vision") return <Image aria-label="vision" className={cls} />;
	if (kind === "tools") return <Hammer aria-label="tool use" className={cls} />;
	if (kind === "pdf") return <FileText aria-label="pdf" className={cls} />;
	if (kind === "audio") return <Mic aria-label="audio" className={cls} />;
	return null;
}

function RowMeta({ row }: { row: RichRow }) {
	const parts: string[] = [];
	if (row.price) parts.push(row.price);
	if (row.context) parts.push(row.context);
	const text = parts.join(" · ") || row.id;
	return (
		<div className="flex items-center gap-2 text-[11px] text-muted-foreground">
			<span className="font-mono truncate">{text}</span>
			{row.caps.length > 0 && (
				<span className="flex items-center gap-1">
					{row.caps.map((c) => (
						<CapIcon key={c} kind={c} />
					))}
				</span>
			)}
		</div>
	);
}

export function ModelSelect(props: Props) {
	const { placeholder = "Choose a model…", disabled = false, className } = props;
	const [open, setOpen] = useState(false);
	const rows = useMemo(() => buildRows(props), [props]);
	const rowsById = useMemo(() => {
		const m: Record<string, RichRow> = {};
		for (const r of rows) m[r.id] = r;
		return m;
	}, [rows]);

	const isMulti = props.multiple === true;
	const selectedIds: string[] = isMulti
		? (props as MultiProps).value
		: (props as SingleProps).value
			? [(props as SingleProps).value as string]
			: [];

	function toggle(id: string) {
		if (isMulti) {
			const cur = (props as MultiProps).value;
			(props as MultiProps).onChange(
				cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
			);
		} else {
			(props as SingleProps).onChange(id);
			setOpen(false);
		}
	}

	function removeOne(id: string) {
		if (isMulti) {
			(props as MultiProps).onChange((props as MultiProps).value.filter((x) => x !== id));
		} else {
			(props as SingleProps).onChange(null);
		}
	}

	const triggerLabel = (() => {
		if (selectedIds.length === 0) return placeholder;
		if (isMulti) return `${selectedIds.length} selected`;
		const sole = selectedIds[0];
		return rowsById[sole]?.display ?? sole;
	})();

	return (
		<div className={cn("space-y-2", className)}>
			<Popover open={open} onOpenChange={setOpen}>
				<PopoverTrigger asChild>
					<Button
						variant="outline"
						role="combobox"
						disabled={disabled}
						className="w-full justify-between font-normal"
					>
						<span className={cn("truncate", selectedIds.length === 0 && "text-muted-foreground")}>
							{triggerLabel}
						</span>
						<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
					</Button>
				</PopoverTrigger>
				<PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
					<Command>
						<CommandInput placeholder="Search models…" />
						<CommandList className="max-h-72">
							<CommandEmpty>No matches.</CommandEmpty>
							<CommandGroup>
								{rows.map((row) => {
									const checked = selectedIds.includes(row.id);
									return (
										<CommandItem
											key={row.id}
											value={row.id}
											keywords={[row.display, row.id]}
											onSelect={() => toggle(row.id)}
											className="flex items-start gap-2 py-2"
										>
											{isMulti ? (
												<Check
													aria-hidden
													className={cn(
														"mt-1 h-4 w-4 shrink-0",
														checked ? "opacity-100" : "opacity-0",
													)}
												/>
											) : (
												<Check
													aria-hidden
													className={cn(
														"mt-1 h-4 w-4 shrink-0",
														checked ? "opacity-100" : "opacity-0",
													)}
												/>
											)}
											<div className="flex-1 min-w-0">
												<div className="text-sm">{row.display}</div>
												<RowMeta row={row} />
											</div>
										</CommandItem>
									);
								})}
							</CommandGroup>
						</CommandList>
					</Command>
				</PopoverContent>
			</Popover>

			{isMulti && selectedIds.length > 0 && (
				<div className="flex flex-wrap gap-1">
					{selectedIds.map((id) => {
						const row = rowsById[id];
						return (
							<Badge key={id} variant="secondary" className="gap-1.5 pr-1">
								<span>{row?.display ?? id}</span>
								<button
									type="button"
									aria-label={`Remove ${row?.display ?? id}`}
									className="rounded p-0.5 hover:bg-background/40"
									onClick={() => removeOne(id)}
								>
									<X className="h-3 w-3" />
								</button>
							</Badge>
						);
					})}
				</div>
			)}
		</div>
	);
}
