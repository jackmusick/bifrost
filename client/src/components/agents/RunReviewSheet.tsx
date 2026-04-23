/**
 * Slide-over sheet that wraps a run's review and tuning experience.
 *
 * Mounts the shared RunReviewPanel under the Review tab and the
 * FlagConversation under the Tune tab. The parent controls open state,
 * the run, and all state for verdict / note / conversation — this
 * component is purely presentational.
 */

import { Sparkles } from "lucide-react";

import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import {
	Tabs,
	TabsContent,
	TabsList,
	TabsTrigger,
} from "@/components/ui/tabs";
import type { components } from "@/lib/v1";

import { FlagConversation } from "./FlagConversation";
import { RunReviewPanel, type Verdict } from "./RunReviewPanel";

type AgentRunDetail = components["schemas"]["AgentRunDetailResponse"];
type FlagConversationResponse = components["schemas"]["FlagConversationResponse"];

export interface RunReviewSheetProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	run: AgentRunDetail | null;
	verdict: Verdict;
	note: string;
	onVerdict: (v: Verdict) => void;
	onNote: (n: string) => void;
	conversation: FlagConversationResponse | null;
	onSendChat: (text: string) => void;
	chatPending?: boolean;
	onTestAgainstRun?: () => void;
	defaultTab?: "review" | "tune";
}

export function RunReviewSheet({
	open,
	onOpenChange,
	run,
	verdict,
	note,
	onVerdict,
	onNote,
	conversation,
	onSendChat,
	chatPending,
	onTestAgainstRun,
	defaultTab = "review",
}: RunReviewSheetProps) {
	if (!run) return null;
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				aria-label="Run review"
				className="flex w-full flex-col gap-0 p-0 sm:max-w-2xl"
			>
				<SheetHeader className="border-b px-6 py-4">
					<SheetTitle className="truncate">
						{run.did || run.asked || "Run review"}
					</SheetTitle>
				</SheetHeader>
				<Tabs
					defaultValue={defaultTab}
					className="flex min-h-0 flex-1 flex-col gap-0"
				>
					<TabsList className="mx-6 mt-3 self-start">
						<TabsTrigger value="review">Review</TabsTrigger>
						<TabsTrigger value="tune">
							<Sparkles size={12} /> Tune
						</TabsTrigger>
					</TabsList>
					<TabsContent
						value="review"
						className="flex-1 overflow-y-auto"
					>
						<RunReviewPanel
							run={run}
							verdict={verdict}
							note={note}
							onVerdict={onVerdict}
							onNote={onNote}
							variant="drawer"
						/>
					</TabsContent>
					<TabsContent
						value="tune"
						className="flex min-h-0 flex-1 flex-col"
					>
						<FlagConversation
							conversation={conversation}
							onSend={onSendChat}
							pending={chatPending}
							onTestAgainstRun={onTestAgainstRun}
						/>
					</TabsContent>
				</Tabs>
			</SheetContent>
		</Sheet>
	);
}
