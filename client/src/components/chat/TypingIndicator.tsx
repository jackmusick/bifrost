/**
 * TypingIndicator — three pulsing dots shown while the assistant is generating
 * a response but hasn't streamed any content yet. Avoids the "where did my
 * message go?" silence between user-send and first-token.
 */

import { Bot } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
	className?: string;
	label?: string;
}

export function TypingIndicator({ className, label = "Thinking" }: Props) {
	return (
		<div
			className={cn(
				"flex items-center gap-3 px-4 py-3 text-muted-foreground",
				className,
			)}
			aria-live="polite"
			aria-label={`${label}…`}
		>
			<div className="size-7 rounded-full bg-muted flex items-center justify-center shrink-0">
				<Bot className="h-3.5 w-3.5" />
			</div>
			<div className="flex items-center gap-1.5">
				<span className="text-sm">{label}</span>
				<span className="flex gap-1">
					<Dot delay="0ms" />
					<Dot delay="150ms" />
					<Dot delay="300ms" />
				</span>
			</div>
		</div>
	);
}

function Dot({ delay }: { delay: string }) {
	return (
		<span
			className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce"
			style={{ animationDelay: delay }}
		/>
	);
}
