import { useRef, useState } from "react";
import { Plus, Mic, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { TIER_GLYPH } from "../mock";

type Props = {
	placeholder?: string;
	model?: string;
	tier?: "fast" | "balanced" | "premium";
	onSend?: (text: string) => void;
	chips?: React.ReactNode;
	disclaimer?: string;
};

export function Composer({
	placeholder = "Reply…",
	model = "Balanced",
	tier = "balanced",
	onSend,
	chips,
	disclaimer = "Bifrost is AI and can make mistakes.",
}: Props) {
	const [text, setText] = useState("");
	const taRef = useRef<HTMLTextAreaElement>(null);

	const submit = () => {
		if (!text.trim()) return;
		onSend?.(text);
		setText("");
		if (taRef.current) {
			taRef.current.style.height = "auto";
		}
	};

	const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	};

	const onInput = () => {
		if (!taRef.current) return;
		taRef.current.style.height = "auto";
		taRef.current.style.height = `${Math.min(taRef.current.scrollHeight, 200)}px`;
	};

	return (
		<div className="px-4 pb-3 pt-2 pointer-events-none">
			<div className="max-w-3xl mx-auto pointer-events-auto">
				<div
					className={cn(
						"rounded-3xl bg-card border shadow-lg shadow-black/5 dark:shadow-black/40",
						"px-4 pt-3 pb-2",
					)}
				>
					{chips && <div className="pb-2">{chips}</div>}
					<textarea
						ref={taRef}
						value={text}
						onChange={(e) => setText(e.target.value)}
						onKeyDown={onKeyDown}
						onInput={onInput}
						rows={1}
						placeholder={placeholder}
						className={cn(
							"w-full resize-none bg-transparent text-sm",
							"focus:outline-none placeholder:text-muted-foreground",
							"min-h-[24px] max-h-[200px] overflow-y-auto",
						)}
					/>
					<div className="flex items-center justify-between pt-1.5">
						<div className="flex items-center gap-1">
							<button
								className="size-7 rounded-full hover:bg-accent flex items-center justify-center text-muted-foreground"
								aria-label="Attach"
							>
								<Plus className="size-4" />
							</button>
						</div>
						<div className="flex items-center gap-1.5">
							<button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:bg-accent rounded-md px-2 py-1">
								<span>{TIER_GLYPH[tier]}</span>
								<span>{model}</span>
								<ChevronDown className="size-3" />
							</button>
							<button
								className="size-7 rounded-full hover:bg-accent flex items-center justify-center text-muted-foreground"
								aria-label="Voice input"
							>
								<Mic className="size-4" />
							</button>
						</div>
					</div>
				</div>
				<div className="text-[10px] text-muted-foreground text-center pt-2">
					{disclaimer}
				</div>
			</div>
		</div>
	);
}
