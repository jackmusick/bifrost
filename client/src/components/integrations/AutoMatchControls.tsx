/**
 * Auto-Match Controls Component
 * Provides UI for selecting match mode and running auto-match
 */

import { useState } from "react";
import { Wand2, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	ToggleGroup,
	ToggleGroupItem,
} from "@/components/ui/toggle-group";
import type { MatchMode, MatchResult } from "@/lib/matching";

interface AutoMatchControlsProps {
	onRunAutoMatch: (mode: MatchMode) => void;
	onAcceptAll: () => void;
	onClear: () => void;
	matchStats: MatchResult["stats"] | null;
	hasSuggestions: boolean;
	isMatching: boolean;
	disabled?: boolean;
}

export function AutoMatchControls({
	onRunAutoMatch,
	onAcceptAll,
	onClear,
	matchStats,
	hasSuggestions,
	isMatching,
	disabled = false,
}: AutoMatchControlsProps) {
	const [matchMode, setMatchMode] = useState<MatchMode>("exact");

	const handleRunAutoMatch = () => {
		onRunAutoMatch(matchMode);
	};

	return (
		<div className="flex items-center gap-3">
			{/* Match Mode Selection */}
			<ToggleGroup
				type="single"
				value={matchMode}
				onValueChange={(value) => {
					if (value) setMatchMode(value as MatchMode);
				}}
				disabled={disabled || isMatching}
				size="sm"
			>
				<ToggleGroupItem value="exact">Exact</ToggleGroupItem>
				<ToggleGroupItem value="fuzzy">Fuzzy</ToggleGroupItem>
				<ToggleGroupItem value="ai" disabled>
					AI
					<Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0">
						Soon
					</Badge>
				</ToggleGroupItem>
			</ToggleGroup>

			{/* Action Buttons */}
			{hasSuggestions ? (
				<>
					<Button size="sm" variant="default" onClick={onAcceptAll} disabled={disabled}>
						<Check className="h-3.5 w-3.5 mr-1" />
						Accept All ({matchStats?.matched || 0})
					</Button>
					<Button size="sm" variant="ghost" onClick={onClear} disabled={disabled}>
						<X className="h-3.5 w-3.5" />
					</Button>
				</>
			) : (
				<Button
					size="sm"
					variant="default"
					onClick={handleRunAutoMatch}
					disabled={disabled || isMatching}
				>
					<Wand2 className="h-3.5 w-3.5 mr-1" />
					{isMatching ? "Matching..." : "Auto-Match Unmapped"}
				</Button>
			)}
		</div>
	);
}
