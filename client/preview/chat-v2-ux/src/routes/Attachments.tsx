import { useState } from "react";
import { Progress } from "@/components/ui/progress";
import { X, FileText, FileSpreadsheet, FileImage, Upload, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ATTACHMENTS_DEMO, type Attachment } from "../mock";
import { Composer } from "../components/Composer";

const ICON_FOR: Record<Attachment["type"], typeof FileText> = {
	image: FileImage,
	pdf: FileText,
	csv: FileSpreadsheet,
	text: FileText,
};

export function Attachments() {
	const [chips, setChips] = useState<Attachment[]>(ATTACHMENTS_DEMO);
	const [dragOver, setDragOver] = useState(false);

	const remove = (id: string) =>
		setChips((p) => p.filter((c) => c.id !== id));

	return (
		<div
			className="bg-background min-h-screen relative"
			onDragOver={(e) => {
				e.preventDefault();
				setDragOver(true);
			}}
			onDragLeave={() => setDragOver(false)}
			onDrop={(e) => {
				e.preventDefault();
				setDragOver(false);
				const newChip: Attachment = {
					id: `dropped-${Date.now()}`,
					filename: "dropped-file.png",
					size: "1.7 MB",
					type: "image",
					progress: 30,
				};
				setChips((p) => [...p, newChip]);
			}}
		>
			<div className="max-w-3xl mx-auto p-8 space-y-6 pb-48">
				<div>
					<h1 className="text-xl font-medium mb-2">Attachments</h1>
					<p className="text-sm text-muted-foreground">
						Drag any file from your desktop onto this page to see the
						overlay. Chips appear at the top of the floating composer with
						progress, file type icon, size, and PDF token estimate.
					</p>
				</div>

				<div className="text-xs text-muted-foreground space-y-1.5 pt-3 border-t">
					<p className="font-medium text-foreground">Notes for the spec:</p>
					<ul className="list-disc pl-5 space-y-1">
						<li>
							PDF chip shows{" "}
							<code>"1.2 MB · 3 pages, ~2.1k tokens"</code> — token
							estimate communicates cost contribution before the user
							sends.
						</li>
						<li>
							Failed upload chip ("broken-upload.png") gets a destructive
							border + error link.
						</li>
						<li>
							In-flight chip ("uploading-now.txt") shows mini Progress bar
							instead of size text.
						</li>
						<li>
							Drop zone is the whole window — drag any file in to see.
						</li>
						<li>
							Paste an image (Cmd+V) into the textarea would auto-name as{" "}
							<code>screenshot-YYYY-MM-DD-HHmm.png</code> in production.
						</li>
					</ul>
				</div>
			</div>

			{/* Drag overlay */}
			{dragOver && (
				<div className="fixed inset-0 z-50 bg-primary/10 backdrop-blur-sm flex items-center justify-center pointer-events-none">
					<div className="bg-popover border-2 border-dashed border-primary rounded-lg px-12 py-10 text-center">
						<Upload className="size-12 text-primary mx-auto mb-3" />
						<div className="font-medium text-foreground">
							Drop files to attach
						</div>
						<div className="text-xs text-muted-foreground mt-1">
							Images, PDFs, CSVs, and text files supported
						</div>
					</div>
				</div>
			)}

			{/* Floating composer w/ chips */}
			<div className="fixed inset-x-0 bottom-0">
				<Composer
					placeholder="Ask anything…"
					chips={
						chips.length > 0 ? (
							<div className="flex flex-wrap gap-1.5">
								{chips.map((c) => {
									const Icon = ICON_FOR[c.type];
									return (
										<div
											key={c.id}
											className={cn(
												"group flex items-center gap-2 rounded-2xl border bg-background pl-2 pr-1.5 py-1 text-xs max-w-xs",
												c.error && "border-destructive/40 bg-destructive/5",
											)}
										>
											<Icon
												className={cn(
													"size-3.5 shrink-0",
													c.error
														? "text-destructive"
														: "text-muted-foreground",
												)}
											/>
											<div className="min-w-0">
												<div className="font-medium truncate text-[11px]">
													{c.filename}
												</div>
												<div className="text-[10px] text-muted-foreground flex items-center gap-1.5">
													{c.error ? (
														<span className="text-destructive flex items-center gap-1">
															<AlertCircle className="size-2.5" />
															{c.error}
														</span>
													) : c.progress !== undefined ? (
														<>
															<Progress
																value={c.progress}
																className="h-0.5 w-10"
															/>
															<span>{c.progress}%</span>
														</>
													) : (
														<span>
															{c.size}
															{c.tokens
																? ` · ${c.pages} pgs, ~${(c.tokens / 1000).toFixed(1)}k`
																: ""}
														</span>
													)}
												</div>
											</div>
											<button
												onClick={() => remove(c.id)}
												className="opacity-50 hover:opacity-100 ml-1 hover:bg-accent rounded-full size-4 flex items-center justify-center"
											>
												<X className="size-3" />
											</button>
										</div>
									);
								})}
							</div>
						) : null
					}
				/>
			</div>
		</div>
	);
}
