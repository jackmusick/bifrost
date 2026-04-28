import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
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
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Pencil, RotateCcw, ChevronDown, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { TIER_GLYPH } from "../mock";

const SAMPLE_USER = "Draft a follow-up to Acme about the VPN issue.";
const SAMPLE_ASSISTANT =
	"Sure — here's a polished draft. I checked the ticket history and the issue was last updated Tuesday afternoon...";

export function EditRetry() {
	const [editing, setEditing] = useState(false);
	const [userMsg, setUserMsg] = useState(SAMPLE_USER);
	const [draft, setDraft] = useState(userMsg);
	const [confirm, setConfirm] = useState(false);
	const [retryOpen, setRetryOpen] = useState(false);
	const [model, setModel] = useState("Balanced");

	const submitEdit = () => {
		setUserMsg(draft);
		setEditing(false);
		setConfirm(false);
	};

	return (
		<div className="bg-background min-h-screen p-8">
			<div className="max-w-2xl mx-auto space-y-8">
				<div>
					<h1 className="text-xl font-medium mb-2">Edit + retry</h1>
					<p className="text-sm text-muted-foreground">
						Hover a user message to reveal the pencil. Hover an assistant
						message to reveal the retry icon (with split caret for
						"retry with…"). Edit triggers a destructive AlertDialog
						because subsequent messages will be deleted.
					</p>
				</div>

				{/* User message */}
				<div className="group relative flex justify-end">
					{editing ? (
						<div className="w-full max-w-md space-y-2">
							<Textarea
								value={draft}
								onChange={(e) => setDraft(e.target.value)}
								className="min-h-[80px]"
							/>
							<div className="flex gap-2 justify-end">
								<Button
									variant="ghost"
									size="sm"
									onClick={() => {
										setEditing(false);
										setDraft(userMsg);
									}}
								>
									Cancel
								</Button>
								<Button size="sm" onClick={() => setConfirm(true)}>
									Send
								</Button>
							</div>
						</div>
					) : (
						<div className="bg-primary text-primary-foreground rounded-lg rounded-tr-sm px-3 py-2 text-sm max-w-md relative">
							{userMsg}
							<button
								onClick={() => {
									setDraft(userMsg);
									setEditing(true);
								}}
								className="absolute -top-3 right-1 opacity-0 group-hover:opacity-100 bg-background border rounded-md p-1 hover:bg-accent"
								aria-label="Edit message"
							>
								<Pencil className="size-3 text-foreground" />
							</button>
						</div>
					)}
				</div>

				{/* Assistant message */}
				<div className="group relative flex gap-3">
					<div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
						<Bot className="size-4" />
					</div>
					<div className="flex-1">
						<div className="text-sm">{SAMPLE_ASSISTANT}</div>
						<div className="text-xs text-muted-foreground mt-2 flex items-center gap-2">
							<span>{TIER_GLYPH.balanced} Balanced</span>
							<span>·</span>
							<span>892 tokens</span>
						</div>
					</div>
					<div className="absolute right-0 -top-3 opacity-0 group-hover:opacity-100 flex">
						<Button
							variant="outline"
							size="sm"
							className="h-7 rounded-r-none border-r-0"
						>
							<RotateCcw className="size-3" /> Retry
						</Button>
						<Popover open={retryOpen} onOpenChange={setRetryOpen}>
							<PopoverTrigger asChild>
								<Button
									variant="outline"
									size="sm"
									className="h-7 rounded-l-none px-1.5"
								>
									<ChevronDown className="size-3" />
								</Button>
							</PopoverTrigger>
							<PopoverContent align="end" className="w-56 p-1">
								<div className="text-xs px-2 py-1.5 text-muted-foreground font-medium">
									Retry with…
								</div>
								{(["Fast", "Balanced", "Premium"] as const).map((m) => (
									<button
										key={m}
										onClick={() => {
											setModel(m);
											setRetryOpen(false);
										}}
										className={cn(
											"w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm hover:bg-accent",
											model === m && "bg-accent",
										)}
									>
										<span>
											{TIER_GLYPH[m.toLowerCase() as "fast"]}
										</span>
										<span>{m}</span>
									</button>
								))}
							</PopoverContent>
						</Popover>
					</div>
				</div>

				<AlertDialog open={confirm} onOpenChange={setConfirm}>
					<AlertDialogContent>
						<AlertDialogHeader>
							<AlertDialogTitle>Replace this message?</AlertDialogTitle>
							<AlertDialogDescription>
								This will discard the assistant's response and any
								subsequent messages. This cannot be undone.
							</AlertDialogDescription>
						</AlertDialogHeader>
						<AlertDialogFooter>
							<AlertDialogCancel>Cancel</AlertDialogCancel>
							<AlertDialogAction onClick={submitEdit}>
								Replace and re-run
							</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>

				<div className="text-xs text-muted-foreground border-t pt-3">
					Spec flags this AlertDialog as a usability concern worth
					user-testing — the destructive action is irreversible without DB
					restore. Could be replaced with a non-blocking undo toast if
					testing reveals friction.
				</div>
			</div>
		</div>
	);
}
