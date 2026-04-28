import { Bot, Layers } from "lucide-react";
import { TIER_GLYPH } from "../mock";

const TURNS = [
	{ role: "user", body: "Walk me through last week's onboarding for ZB Labs." },
	{
		role: "assistant",
		body: "Here's a recap. We provisioned the M365 tenant on Monday, configured baselines Tuesday...",
		tokens: 1200,
	},
	{
		role: "user",
		body: "What about the Intune deployment? Did we hit the snag with the autopilot profile?",
	},
	{
		role: "assistant",
		body: "Yes — the autopilot profile took two attempts because the OOBE skip flag wasn't propagating. Fixed by re-syncing.",
		tokens: 980,
	},
];

const RECENT = [
	{
		role: "user",
		body: "Can you summarize the open items still on the ZB Labs ticket?",
	},
	{
		role: "assistant",
		body: "Three open items: (1) Autopilot profile validation pending one more device, (2) Conditional Access named locations need Acme HQ added, (3) Sharepoint default permissions audit not yet started.",
		tokens: 1400,
	},
];

export function Compaction() {
	return (
		<div className="bg-background min-h-screen p-8">
			<div className="max-w-3xl mx-auto space-y-6">
				<div>
					<h1 className="text-xl font-medium mb-2">Compaction</h1>
					<p className="text-sm text-muted-foreground">
						When auto-compaction triggers (or the user clicks the Compact
						button in the header), older turns are summarized into a
						<code className="mx-1">[Conversation history summary]</code>
						block in the model's working context. The user still sees the
						original messages in the scrollback, plus a persistent inline
						event marking when compaction happened.
					</p>
				</div>

				{/* Old turns */}
				<div className="space-y-4 opacity-60">
					{TURNS.map((t, i) => (
						<Turn key={i} {...t} />
					))}
				</div>

				{/* Compaction event */}
				<div className="relative flex items-center gap-3 py-2">
					<div className="flex-1 border-t border-border" />
					<div className="flex items-center gap-1.5 text-xs italic text-muted-foreground">
						<Layers className="size-3.5" />
						Compacted 4 earlier turns to free context space
					</div>
					<div className="flex-1 border-t border-border" />
				</div>

				{/* Recent turns */}
				<div className="space-y-4">
					{RECENT.map((t, i) => (
						<Turn key={i} {...t} />
					))}
				</div>

				<div className="text-xs text-muted-foreground border-t pt-3 space-y-2">
					<p className="font-medium text-foreground">Notes:</p>
					<ul className="list-disc pl-5 space-y-1">
						<li>
							The "Compacted N earlier turns…" event uses the same{" "}
							<code>ChatSystemEvent</code> pattern as today's agent-switch
							notifications — italic text-xs, divider lines on either side.
						</li>
						<li>
							Old turns above the divider stay readable for the user but
							the model receives a single summary block instead.
						</li>
						<li>
							Auto-compaction triggers at 85% of the current model's
							context window (per-model-aware via the resolver).
						</li>
						<li>
							The DB is the source of truth and is never modified by
							compaction. Compaction is purely a model-context construct.
						</li>
					</ul>
				</div>
			</div>
		</div>
	);
}

function Turn({
	role,
	body,
	tokens,
}: {
	role: string;
	body: string;
	tokens?: number;
}) {
	if (role === "user") {
		return (
			<div className="flex justify-end">
				<div className="bg-primary text-primary-foreground rounded-lg rounded-tr-sm px-3 py-2 text-sm max-w-md">
					{body}
				</div>
			</div>
		);
	}
	return (
		<div className="flex gap-3">
			<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
				<Bot className="size-4" />
			</div>
			<div className="flex-1">
				<div className="text-sm">{body}</div>
				{tokens && (
					<div className="text-xs text-muted-foreground mt-2">
						{TIER_GLYPH.balanced} Balanced · {tokens} tokens
					</div>
				)}
			</div>
		</div>
	);
}
