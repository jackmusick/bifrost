import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import {
	Bot,
	Folder,
	Layers,
	MoreHorizontal,
	ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { TIER_GLYPH, type Tier } from "../mock";

function CostStrip({ tiers }: { tiers: Tier[] }) {
	return (
		<TooltipProvider>
			<Tooltip>
				<TooltipTrigger asChild>
					<div className="flex items-center gap-0.5 text-xs text-muted-foreground">
						{tiers.slice(-8).map((t, i) => (
							<span key={i}>{TIER_GLYPH[t]}</span>
						))}
					</div>
				</TooltipTrigger>
				<TooltipContent side="bottom">
					<div className="text-xs">
						{tiers.length} messages this conversation
						<br />
						{tiers.filter((t) => t === "fast").length} fast,{" "}
						{tiers.filter((t) => t === "balanced").length} balanced,{" "}
						{tiers.filter((t) => t === "premium").length} premium
					</div>
				</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

export function Header() {
	const [usage, setUsage] = useState(32_000);
	const [model, setModel] = useState("Balanced");
	const max = 200_000;
	const pct = (usage / max) * 100;
	const color =
		pct < 70 ? "text-muted-foreground" : pct < 85 ? "text-primary" : "text-destructive";
	const tiers: Tier[] = [
		"fast",
		"fast",
		"balanced",
		"balanced",
		"balanced",
		"premium",
		"premium",
		"fast",
	];

	return (
		<div className="bg-background min-h-screen">
			{/* Header replica - pixel-match production height + border */}
			<div className="h-14 border-b flex items-center justify-between px-4 gap-4">
				<div className="min-w-0 flex-1">
					<h1 className="text-sm font-medium truncate">
						Acme Corp setup
					</h1>
					<div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
						<Folder className="size-3" />
						<span className="hover:text-foreground cursor-pointer">
							Customer Onboarding
						</span>
						<span>·</span>
						<Bot className="size-3" />
						<span className="hover:text-foreground cursor-pointer">
							Onboarding Assistant
						</span>
					</div>
				</div>

				{/* right side stats */}
				<div className="flex items-center gap-4 shrink-0">
					{/* model pill */}
					<button className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-accent text-xs">
						<span>{TIER_GLYPH.balanced}</span>
						<span className="font-medium">{model}</span>
						<ChevronDown className="size-3 text-muted-foreground" />
					</button>

					{/* budget bar + label */}
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="flex items-center gap-2 cursor-help">
									<Progress
										value={pct}
										className={cn("w-24 h-1.5")}
									/>
									<span className={cn("text-xs tabular-nums", color)}>
										{(usage / 1000).toFixed(0)}k /{" "}
										{(max / 1000).toFixed(0)}k
									</span>
								</div>
							</TooltipTrigger>
							<TooltipContent side="bottom">
								<div className="text-xs">
									Context budget breakdown:
									<br />
									System prompt: 3.2k
									<br />
									Knowledge: 8k
									<br />
									History: 21k
								</div>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>

					{/* cost tier strip */}
					<CostStrip tiers={tiers} />

					{/* compact button (only when budget high) */}
					{pct > 85 && (
						<Button size="sm" variant="ghost" className="h-7 text-xs">
							<Layers className="size-3.5" /> Compact
						</Button>
					)}

					{/* overflow menu */}
					<button className="p-1 rounded-md hover:bg-accent">
						<MoreHorizontal className="size-4 text-muted-foreground" />
					</button>
				</div>
			</div>

			{/* explanatory body */}
			<div className="p-8 max-w-2xl space-y-6">
				<div>
					<h2 className="text-xl font-medium mb-3">Chat header</h2>
					<p className="text-sm text-muted-foreground">
						Replaces today's admin-only stats pattern with a header visible to all
						users.
					</p>
				</div>

				<div className="space-y-4">
					<div className="border rounded-md p-4">
						<div className="text-sm font-medium mb-2">
							Try changing the budget
						</div>
						<div className="flex items-center gap-3">
							<input
								type="range"
								min={0}
								max={max}
								step={5_000}
								value={usage}
								onChange={(e) => setUsage(parseInt(e.target.value))}
								className="flex-1"
							/>
							<span className="text-xs tabular-nums w-24 text-right">
								{(usage / 1000).toFixed(0)}k tokens
							</span>
						</div>
						<div className="text-xs text-muted-foreground mt-2">
							Bar color shifts at 70% (primary teal) and 85% (destructive
							red). Past 85%, the inline "Compact" button appears next to
							the bar.
						</div>
					</div>

					<div className="border rounded-md p-4">
						<div className="text-sm font-medium mb-2">Model pill</div>
						<div className="flex gap-2">
							{(["Fast", "Balanced", "Premium"] as const).map((m) => (
								<Button
									key={m}
									variant={m === model ? "default" : "outline"}
									size="sm"
									onClick={() => setModel(m)}
								>
									{TIER_GLYPH[m.toLowerCase() as Tier]} {m}
								</Button>
							))}
						</div>
						<div className="text-xs text-muted-foreground mt-2">
							In production this opens the model picker. The pill shows
							the alias name and tier glyph.
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
