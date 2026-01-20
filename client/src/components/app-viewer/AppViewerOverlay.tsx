// client/src/components/app-viewer/AppViewerOverlay.tsx

import { AnimatePresence } from "framer-motion";
import { WindowOverlay } from "@/components/window-management";
import { AppViewerLayout } from "./AppViewerLayout";
import { useAppViewerVisibility } from "@/hooks/useAppViewer";

/**
 * App viewer overlay component.
 * Renders the app as a fullscreen overlay when maximized.
 *
 * NOTE: This component is currently not used as the overlay is
 * rendered inside AppRouter to maintain correct React Router context.
 * Kept for reference or future use where routing context isn't needed.
 */
export function AppViewerOverlay() {
	const { appId, layoutMode } = useAppViewerVisibility();

	// Not active or minimized (dock handles minimized state)
	if (!appId || !layoutMode || layoutMode === "minimized") {
		return null;
	}

	return (
		<AnimatePresence>
			{layoutMode === "maximized" && (
				<WindowOverlay>
					<AppViewerLayout />
				</WindowOverlay>
			)}
		</AnimatePresence>
	);
}
