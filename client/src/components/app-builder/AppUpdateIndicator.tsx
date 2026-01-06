/**
 * App Update Indicator
 *
 * Shows brief attribution when someone else updates the app:
 * - "[avatar] {name} updated" message (2-3 seconds, then fades)
 * - Uses same AnimatePresence pattern as WorkflowStatusIndicator
 */

import { motion, AnimatePresence } from "framer-motion";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface AppUpdateIndicatorProps {
	/** Info about the last update (who and when) */
	lastUpdate?: {
		userName: string;
		timestamp: Date;
	} | null;
}

/**
 * Displays brief attribution when an app is updated by another user
 *
 * @example
 * <AppUpdateIndicator
 *   lastUpdate={{ userName: "John Doe", timestamp: new Date() }}
 * />
 */
export function AppUpdateIndicator({ lastUpdate }: AppUpdateIndicatorProps) {
	// Get initials for avatar
	const initials = lastUpdate
		? lastUpdate.userName
				.split(" ")
				.map((n) => n[0])
				.join("")
				.toUpperCase()
				.slice(0, 2) || "?"
		: "";

	return (
		<AnimatePresence>
			{lastUpdate && (
				<motion.div
					key="update-indicator"
					initial={{ opacity: 0, x: 10 }}
					animate={{ opacity: 1, x: 0 }}
					exit={{ opacity: 0, x: -10 }}
					transition={{ duration: 0.15 }}
					className="flex items-center gap-2 text-sm text-muted-foreground"
				>
					<Avatar className="h-5 w-5">
						<AvatarFallback className="text-xs bg-primary/10 text-primary">
							{initials}
						</AvatarFallback>
					</Avatar>
					<span>{lastUpdate.userName} updated</span>
				</motion.div>
			)}
		</AnimatePresence>
	);
}

export default AppUpdateIndicator;
