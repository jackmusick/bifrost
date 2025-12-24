/**
 * Match Suggestion Badge Component
 * Displays a match suggestion with confidence score and accept/reject actions
 */

import { Check, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { MatchSuggestion } from "@/lib/matching";
import { cn } from "@/lib/utils";

interface MatchSuggestionBadgeProps {
	suggestion: MatchSuggestion;
	onAccept: () => void;
	onReject: () => void;
	disabled?: boolean;
}

export function MatchSuggestionBadge({
	suggestion,
	onAccept,
	onReject,
	disabled = false,
}: MatchSuggestionBadgeProps) {
	const isHighConfidence = suggestion.score >= 80;
	const badgeColor = isHighConfidence
		? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300 border-green-300 dark:border-green-700"
		: "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700";

	return (
		<div className="flex items-center gap-2">
			<Badge
				variant="outline"
				className={cn(
					"flex items-center gap-1.5 px-2.5 py-1 text-sm",
					badgeColor,
				)}
			>
				<span className="font-medium">{suggestion.entityName}</span>
				<span className="text-xs opacity-75">
					({suggestion.score}%)
				</span>
			</Badge>

			<div className="flex items-center gap-1">
				<Button
					size="sm"
					variant="ghost"
					className="h-7 w-7 p-0 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-950"
					onClick={onAccept}
					disabled={disabled}
					title="Accept suggestion"
				>
					<Check className="h-4 w-4" />
				</Button>
				<Button
					size="sm"
					variant="ghost"
					className="h-7 w-7 p-0 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
					onClick={onReject}
					disabled={disabled}
					title="Reject suggestion"
				>
					<X className="h-4 w-4" />
				</Button>
			</div>
		</div>
	);
}
