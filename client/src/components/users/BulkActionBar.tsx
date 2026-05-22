import { Building2, Power, PowerOff, Shield, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface BulkActionBarProps {
	/** Count of selected items. The bar is hidden when this is 0. */
	count: number;
	/** Mix of active/inactive in the selection — controls which power buttons appear. */
	activeMix: "all_active" | "all_inactive" | "mixed";
	/** Clear-selection callback. */
	onClear: () => void;
	onMoveOrg: () => void;
	onReplaceRoles: () => void;
	onDisable: () => void;
	onEnable: () => void;
	className?: string;
}

/**
 * Sticky bottom action bar that appears when one or more users are selected.
 *
 * Active-mix logic:
 *  - all_active: show only "Disable"
 *  - all_inactive: show only "Enable"
 *  - mixed: show both
 */
export function BulkActionBar({
	count,
	activeMix,
	onClear,
	onMoveOrg,
	onReplaceRoles,
	onDisable,
	onEnable,
	className,
}: BulkActionBarProps) {
	if (count === 0) return null;

	const showDisable = activeMix !== "all_inactive";
	const showEnable = activeMix !== "all_active";

	return (
		<div
			role="region"
			aria-label="Bulk user actions"
			className={cn(
				"sticky bottom-4 left-0 right-0 mx-auto flex items-center gap-3 rounded-lg border bg-popover px-4 py-2 shadow-lg",
				"w-full max-w-3xl z-20",
				className,
			)}
		>
			<span className="text-sm font-medium">
				{count} selected
			</span>
			<Separator orientation="vertical" className="h-6" />

			<Button variant="ghost" size="sm" onClick={onMoveOrg}>
				<Building2 className="h-4 w-4 mr-1.5" />
				Move to org
			</Button>
			<Button variant="ghost" size="sm" onClick={onReplaceRoles}>
				<Shield className="h-4 w-4 mr-1.5" />
				Replace roles
			</Button>
			{showDisable && (
				<Button variant="ghost" size="sm" onClick={onDisable}>
					<PowerOff className="h-4 w-4 mr-1.5" />
					Disable
				</Button>
			)}
			{showEnable && (
				<Button variant="ghost" size="sm" onClick={onEnable}>
					<Power className="h-4 w-4 mr-1.5" />
					Enable
				</Button>
			)}

			<div className="ml-auto">
				<Button
					variant="ghost"
					size="sm"
					onClick={onClear}
					aria-label="Clear selection"
				>
					<X className="h-4 w-4" />
				</Button>
			</div>
		</div>
	);
}
