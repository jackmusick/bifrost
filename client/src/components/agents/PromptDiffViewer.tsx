import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

import { cn } from "@/lib/utils";
import { TONE_MUTED, TYPE_MUTED } from "./design-tokens";

export interface PromptDiffViewerProps {
	before: string;
	after: string;
	className?: string;
}

/**
 * Side-by-side diff of a current prompt vs a proposed prompt.
 *
 * Thin wrapper around react-diff-viewer-continued that applies our dark-theme
 * surface tokens and renders a friendly empty state when the two sides match.
 */
export function PromptDiffViewer({
	before,
	after,
	className,
}: PromptDiffViewerProps) {
	if (before === after) {
		return (
			<div
				data-testid="prompt-diff-empty"
				className={cn(
					"rounded-md border bg-muted/30 px-3 py-4 text-center",
					TYPE_MUTED,
					TONE_MUTED,
					className,
				)}
			>
				No changes — the proposed prompt matches the current one.
			</div>
		);
	}

	return (
		<div
			data-testid="prompt-diff-viewer"
			className={cn("overflow-hidden rounded-md border", className)}
		>
			<ReactDiffViewer
				oldValue={before}
				newValue={after}
				splitView
				compareMethod={DiffMethod.WORDS}
				useDarkTheme
				styles={{
					variables: {
						dark: {
							diffViewerBackground: "hsl(var(--card))",
							diffViewerColor: "hsl(var(--foreground))",
							gutterBackground: "hsl(var(--muted))",
							gutterColor: "hsl(var(--muted-foreground))",
						},
					},
					contentText: {
						fontFamily:
							"ui-monospace, SFMono-Regular, Menlo, monospace",
						fontSize: "12px",
						lineHeight: "1.5",
					},
				}}
			/>
		</div>
	);
}
