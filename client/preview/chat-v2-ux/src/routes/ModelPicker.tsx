import { useState } from "react";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
	CommandSeparator,
} from "cmdk";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { Check, ChevronsUpDown, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { MODELS, TIER_GLYPH } from "../mock";

const RESTRICTION_LABEL: Record<string, string> = {
	platform: "Not enabled on this Bifrost installation",
	org: "Restricted by your org admin",
	role: "Restricted by your role (Help Desk)",
	workspace:
		"Restricted by this workspace ('Customer Onboarding' allows only Haiku and Sonnet)",
};

export function ModelPicker() {
	const [open, setOpen] = useState(true);
	const [selected, setSelected] = useState("bifrost-balanced");

	const selectedModel = MODELS.find((m) => m.id === selected)!;
	const aliases = MODELS.filter((m) => m.is_alias);
	const available = MODELS.filter((m) => !m.is_alias && !m.restricted_by);
	const restricted = MODELS.filter((m) => !m.is_alias && m.restricted_by);

	return (
		<div className="p-8 bg-background min-h-screen max-w-3xl">
			<h1 className="text-xl font-medium mb-4">Model picker</h1>
			<p className="text-sm text-muted-foreground mb-6">
				Triggered from the chat header pill, the workspace settings, the org
				admin AI settings, and the retry-with-different-model dropdown.
				Built on <code>Popover + Command</code> (matches{" "}
				<code>MentionPicker</code>).
			</p>

			<Popover open={open} onOpenChange={setOpen}>
				<PopoverTrigger asChild>
					<Button variant="outline" className="w-80 justify-between">
						<span className="flex items-center gap-1.5">
							{TIER_GLYPH[selectedModel.tier]}
							{selectedModel.display_name}
							{selectedModel.is_alias && selectedModel.target_id && (
								<span className="text-xs text-muted-foreground ml-1">
									→ {selectedModel.target_id}
								</span>
							)}
						</span>
						<ChevronsUpDown className="size-3.5 text-muted-foreground" />
					</Button>
				</PopoverTrigger>
				<PopoverContent className="w-[28rem] p-0" align="start">
					<Command className="bg-popover text-popover-foreground">
						<div className="flex items-center border-b px-3">
							<CommandInput
								placeholder="Search models…"
								className="w-full py-2 text-sm bg-transparent outline-none placeholder:text-muted-foreground"
							/>
						</div>
						<CommandList className="max-h-96 overflow-y-auto p-1">
							<CommandEmpty className="py-4 text-center text-xs text-muted-foreground">
								No models found.
							</CommandEmpty>

							<CommandGroup
								heading="Aliases"
								className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider"
							>
								{aliases.map((m) => (
									<CommandItem
										key={m.id}
										value={m.id}
										onSelect={(v) => {
											setSelected(v);
											setOpen(false);
										}}
										className="flex items-start gap-2 px-2 py-2 rounded-md cursor-pointer aria-selected:bg-accent text-sm"
									>
										<span className="pt-0.5">{TIER_GLYPH[m.tier]}</span>
										<div className="flex-1 min-w-0">
											<div className="font-medium">
												{m.display_name}
											</div>
											<div className="text-xs text-muted-foreground">
												{TIER_GLYPH[m.tier]} {m.tier} ·{" "}
												{m.target_id}
											</div>
										</div>
										{m.id === selected && (
											<Check className="size-4 text-primary" />
										)}
									</CommandItem>
								))}
							</CommandGroup>

							<CommandSeparator className="my-1 h-px bg-border" />

							<CommandGroup
								heading="Specific models"
								className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider"
							>
								{available.map((m) => (
									<CommandItem
										key={m.id}
										value={m.id}
										onSelect={(v) => {
											setSelected(v);
											setOpen(false);
										}}
										className="flex items-start gap-2 px-2 py-2 rounded-md cursor-pointer aria-selected:bg-accent text-sm"
									>
										<span className="pt-0.5">{TIER_GLYPH[m.tier]}</span>
										<div className="flex-1 min-w-0">
											<div className="font-medium">
												{m.display_name}
											</div>
											<div className="text-xs text-muted-foreground">
												{m.provider} ·{" "}
												{(m.context_window / 1000).toFixed(0)}k context
											</div>
										</div>
										{m.id === selected && (
											<Check className="size-4 text-primary" />
										)}
									</CommandItem>
								))}
							</CommandGroup>

							{restricted.length > 0 && (
								<>
									<CommandSeparator className="my-1 h-px bg-border" />
									<CommandGroup
										heading="Restricted"
										className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider"
									>
										<TooltipProvider>
											{restricted.map((m) => (
												<Tooltip key={m.id}>
													<TooltipTrigger asChild>
														<CommandItem
															disabled
															value={m.id}
															className={cn(
																"flex items-start gap-2 px-2 py-2 rounded-md text-sm",
																"opacity-50 cursor-not-allowed",
															)}
														>
															<Lock className="size-4 text-muted-foreground mt-0.5" />
															<div className="flex-1 min-w-0">
																<div className="font-medium">
																	{m.display_name}
																</div>
																<div className="text-xs text-muted-foreground">
																	{m.provider}
																</div>
															</div>
														</CommandItem>
													</TooltipTrigger>
													<TooltipContent side="right" className="max-w-xs">
														<div className="text-xs">
															{RESTRICTION_LABEL[m.restricted_by!]}
														</div>
													</TooltipContent>
												</Tooltip>
											))}
										</TooltipProvider>
									</CommandGroup>
								</>
							)}
						</CommandList>
					</Command>
				</PopoverContent>
			</Popover>

			<div className="mt-8 space-y-2 text-sm text-muted-foreground">
				<p>
					<strong className="text-foreground">Try:</strong>
				</p>
				<ul className="list-disc pl-5 space-y-1.5">
					<li>Hover any "Restricted" model — tooltip explains who restricted it.</li>
					<li>
						Aliases at the top show their target model and tier on the
						second line — the alias is the stable handle, the underlying
						model is visible.
					</li>
					<li>
						Type in the search box — search filters across all sections,
						including restricted entries.
					</li>
				</ul>
			</div>
		</div>
	);
}
