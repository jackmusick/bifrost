/**
 * New Version Banner
 *
 * Shows a persistent indicator when a new version has been published:
 * - "New version available" with refresh button
 * - Calls onRefresh to do a soft refresh (invalidate queries, reset store)
 */

import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface NewVersionBannerProps {
	/** Whether a new version is available */
	isVisible: boolean;
	/** Callback to refresh the app */
	onRefresh: () => void;
}

/**
 * Displays a banner when a new published version is available
 *
 * @example
 * <NewVersionBanner
 *   isVisible={newVersionAvailable}
 *   onRefresh={() => refreshApp()}
 * />
 */
export function NewVersionBanner({ isVisible, onRefresh }: NewVersionBannerProps) {
	return (
		<AnimatePresence>
			{isVisible && (
				<motion.div
					key="new-version-banner"
					initial={{ opacity: 0, scale: 0.95 }}
					animate={{ opacity: 1, scale: 1 }}
					exit={{ opacity: 0, scale: 0.95 }}
					transition={{ duration: 0.15 }}
					className="flex items-center gap-2"
				>
					<span className="text-sm text-amber-600 dark:text-amber-500 font-medium">
						New version available
					</span>
					<Button
						variant="ghost"
						size="sm"
						className="h-7 px-2 text-amber-600 hover:text-amber-700 hover:bg-amber-100 dark:text-amber-500 dark:hover:text-amber-400 dark:hover:bg-amber-900/20"
						onClick={onRefresh}
					>
						<RefreshCw className="h-3.5 w-3.5 mr-1" />
						Refresh
					</Button>
				</motion.div>
			)}
		</AnimatePresence>
	);
}

export default NewVersionBanner;
