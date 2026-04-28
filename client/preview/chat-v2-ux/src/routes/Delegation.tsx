import { useState } from "react";
import { Bot, Check, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { TIER_GLYPH, MESSAGES } from "../mock";

export function Delegation() {
	const [expanded, setExpanded] = useState(true);
	const lastMsg = MESSAGES[MESSAGES.length - 1];

	return (
		<div className="bg-background min-h-screen p-8">
			<div className="max-w-2xl mx-auto space-y-6">
				<div>
					<h1 className="text-xl font-medium mb-2">
						Multi-agent delegation
					</h1>
					<p className="text-sm text-muted-foreground">
						When the active agent calls into a delegated agent during a
						turn, the user sees a single response from the active agent,
						with an inline Card showing what the delegated agent
						contributed. The active agent's identity stays consistent —
						the user keeps talking to the same agent.
					</p>
				</div>

				{/* preceding user message */}
				<div className="flex justify-end">
					<div className="bg-primary text-primary-foreground rounded-lg rounded-tr-sm px-3 py-2 text-sm max-w-md">
						Could you also tag in the network specialist agent for
						confirmation? I'd feel better having them double-check the
						firewall theory.
					</div>
				</div>

				{/* assistant message with delegation card */}
				<div className="flex gap-3">
					<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
						<Bot className="size-4" />
					</div>
					<div className="flex-1 space-y-3">
						{/* Delegation card embedded inline */}
						{lastMsg.delegated && (
							<div className="rounded-md border bg-card border-l-2 border-l-primary">
								<button
									onClick={() => setExpanded(!expanded)}
									className="w-full flex items-center gap-2 p-3 text-left"
								>
									<Check className="size-4 text-primary shrink-0" />
									<div className="flex-1 min-w-0">
										<div className="text-xs font-medium">
											Consulted{" "}
											<span className="text-primary">
												{lastMsg.delegated.agent_name}
											</span>
										</div>
										<div className="text-[11px] text-muted-foreground">
											{lastMsg.delegated.description}
										</div>
									</div>
									<ChevronRight
										className={cn(
											"size-4 text-muted-foreground transition-transform",
											expanded && "rotate-90",
										)}
									/>
								</button>
								{expanded && (
									<div className="px-3 pb-3 pt-1 text-sm text-muted-foreground border-t bg-muted/30">
										{lastMsg.delegated.body}
									</div>
								)}
							</div>
						)}

						{/* Primary agent's response, in full */}
						<div className="text-sm">{lastMsg.content}</div>

						<div className="text-xs text-muted-foreground flex items-center gap-2">
							<span>{TIER_GLYPH.balanced} Balanced</span>
							<span>·</span>
							<span>892 tokens</span>
						</div>
					</div>
				</div>

				<div className="text-xs text-muted-foreground border-t pt-3 space-y-1.5">
					<p className="font-medium text-foreground">Notes:</p>
					<ul className="list-disc pl-5 space-y-1">
						<li>
							Click the card header to expand/collapse the delegated
							agent's contribution.
						</li>
						<li>
							The card renders <em>inline within</em> the primary
							agent's response — not as a separate message in the
							thread.
						</li>
						<li>
							Subtle left-border in the primary teal distinguishes the
							delegation visually without making it loud.
						</li>
						<li>
							Conversation's active agent stays the primary. @-mention
							switches the agent (different mechanism).
						</li>
					</ul>
				</div>
			</div>
		</div>
	);
}
