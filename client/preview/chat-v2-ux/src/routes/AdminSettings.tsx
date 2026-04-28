import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Plus, AlertTriangle } from "lucide-react";
import { TIER_GLYPH, type Tier } from "../mock";

type Row = {
	id: string;
	display: string;
	provider: string;
	tier: Tier;
	enabled: boolean;
	display_override?: string;
};

const INITIAL: Row[] = [
	{
		id: "claude-haiku-4-5",
		display: "Claude Haiku 4.5",
		provider: "Anthropic",
		tier: "fast",
		enabled: true,
	},
	{
		id: "claude-sonnet-4-6",
		display: "Claude Sonnet 4.6",
		provider: "Anthropic",
		tier: "balanced",
		enabled: true,
		display_override: "Acme Pro",
	},
	{
		id: "claude-opus-4-7",
		display: "Claude Opus 4.7",
		provider: "Anthropic",
		tier: "premium",
		enabled: true,
	},
	{
		id: "minimax-m1",
		display: "MiniMax M1",
		provider: "OpenRouter",
		tier: "fast",
		enabled: true,
	},
	{
		id: "gpt-4o",
		display: "GPT-4o",
		provider: "OpenRouter",
		tier: "balanced",
		enabled: true,
	},
];

export function AdminSettings() {
	const [rows, setRows] = useState<Row[]>(INITIAL);
	const [showOrphanDialog, setShowOrphanDialog] = useState(false);

	const toggleRow = (id: string) =>
		setRows((p) =>
			p.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)),
		);

	const onSaveProvider = () => {
		// Simulate provider switch from OpenRouter to Anthropic — would orphan minimax-m1 and gpt-4o
		setShowOrphanDialog(true);
	};

	return (
		<div className="bg-background min-h-screen p-8">
			<div className="max-w-4xl mx-auto space-y-8">
				<div>
					<h1 className="text-xl font-medium mb-2">Admin AI settings</h1>
					<p className="text-sm text-muted-foreground">
						Org admin's view of model availability for chat. Toggle which
						models are enabled. Click "Save (simulate provider switch)"
						to see the save-time orphan-reference AlertDialog.
					</p>
				</div>

				{/* Provider config (abbreviated) */}
				<section className="border rounded-md p-4 space-y-3">
					<h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
						Provider
					</h2>
					<div className="text-sm">
						Currently using <strong>OpenRouter</strong> · API key set
					</div>
					<Button onClick={onSaveProvider} size="sm" variant="outline">
						Save (simulate switch to Anthropic)
					</Button>
				</section>

				{/* Model availability table */}
				<section className="space-y-3">
					<div className="flex items-center justify-between">
						<h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
							Models available for chat
						</h2>
						<Button size="sm" variant="outline">
							<Plus className="size-4" />
							Add model
						</Button>
					</div>

					<div className="border rounded-md overflow-hidden">
						<table className="w-full text-sm">
							<thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
								<tr>
									<th className="text-left px-4 py-2 font-medium">
										Display name
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Model ID
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Provider
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Tier
									</th>
									<th className="text-right px-4 py-2 font-medium">
										Available for chat
									</th>
								</tr>
							</thead>
							<tbody>
								{rows.map((r) => (
									<tr key={r.id} className="border-t">
										<td className="px-4 py-3 font-medium">
											{r.display_override ? (
												<div>
													<div>{r.display_override}</div>
													<div className="text-xs text-muted-foreground">
														(real: {r.display})
													</div>
												</div>
											) : (
												r.display
											)}
										</td>
										<td className="px-4 py-3 text-xs font-mono text-muted-foreground">
											{r.id}
										</td>
										<td className="px-4 py-3">
											<Badge variant="secondary" className="font-normal">
												{r.provider}
											</Badge>
										</td>
										<td className="px-4 py-3">
											<span className="inline-flex items-center gap-1 text-xs">
												{TIER_GLYPH[r.tier]} {r.tier}
											</span>
										</td>
										<td className="px-4 py-3 text-right">
											<Switch
												checked={r.enabled}
												onCheckedChange={() => toggleRow(r.id)}
											/>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</section>

				{/* Aliases (abbreviated) */}
				<section className="space-y-3">
					<div className="flex items-center justify-between">
						<h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
							Aliases
						</h2>
						<Button size="sm" variant="outline">
							<Plus className="size-4" />
							Add alias
						</Button>
					</div>
					<div className="border rounded-md overflow-hidden">
						<table className="w-full text-sm">
							<thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
								<tr>
									<th className="text-left px-4 py-2 font-medium">
										Alias
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Target model
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Tier
									</th>
									<th className="text-left px-4 py-2 font-medium">
										Source
									</th>
								</tr>
							</thead>
							<tbody>
								{[
									{
										alias: "bifrost-fast",
										target: "claude-haiku-4-5",
										tier: "fast" as Tier,
										src: "platform",
									},
									{
										alias: "bifrost-balanced",
										target: "claude-sonnet-4-6",
										tier: "balanced" as Tier,
										src: "platform",
									},
									{
										alias: "bifrost-premium",
										target: "claude-opus-4-7",
										tier: "premium" as Tier,
										src: "platform",
									},
									{
										alias: "acme-default",
										target: "claude-sonnet-4-6",
										tier: "balanced" as Tier,
										src: "org-defined",
									},
								].map((a) => (
									<tr key={a.alias} className={a.src === "platform" ? "border-t opacity-60" : "border-t"}>
										<td className="px-4 py-3 font-mono text-xs">
											{a.alias}
										</td>
										<td className="px-4 py-3 font-mono text-xs text-muted-foreground">
											{a.target}
										</td>
										<td className="px-4 py-3">
											<span className="text-xs">
												{TIER_GLYPH[a.tier]} {a.tier}
											</span>
										</td>
										<td className="px-4 py-3 text-xs">
											{a.src === "platform" ? (
												<Badge variant="outline" className="font-normal text-[10px]">
													platform
												</Badge>
											) : (
												<Badge variant="secondary" className="font-normal text-[10px]">
													org-defined
												</Badge>
											)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</section>

				<AlertDialog open={showOrphanDialog} onOpenChange={setShowOrphanDialog}>
					<AlertDialogContent className="max-w-xl">
						<AlertDialogHeader>
							<AlertDialogTitle className="flex items-center gap-2">
								<AlertTriangle className="size-5 text-destructive" />
								Saving these changes will orphan model references
							</AlertDialogTitle>
							<AlertDialogDescription>
								Switching to direct Anthropic removes access to
								OpenRouter-specific models. Choose replacements before
								saving.
							</AlertDialogDescription>
						</AlertDialogHeader>

						<div className="space-y-3 py-2">
							{[
								{
									id: "minimax-m1",
									count: 3,
									where: "1 workspace, 2 conversations",
									suggested: "claude-haiku-4-5",
								},
								{
									id: "gpt-4o",
									count: 5,
									where: "1 role default, 4 conversations",
									suggested: "claude-sonnet-4-6",
								},
							].map((o) => (
								<div key={o.id} className="border rounded-md p-3 space-y-2">
									<div className="text-sm">
										<code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
											{o.id}
										</code>{" "}
										<span className="text-muted-foreground">
											referenced in {o.count} places ({o.where})
										</span>
									</div>
									<div className="flex items-center gap-2">
										<span className="text-xs text-muted-foreground shrink-0">
											Replace with:
										</span>
										<Input
											defaultValue={o.suggested}
											className="font-mono text-xs h-8 flex-1"
										/>
									</div>
								</div>
							))}
						</div>

						<AlertDialogFooter>
							<AlertDialogCancel>Cancel</AlertDialogCancel>
							<AlertDialogAction>
								Apply replacements and save
							</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>
			</div>
		</div>
	);
}
