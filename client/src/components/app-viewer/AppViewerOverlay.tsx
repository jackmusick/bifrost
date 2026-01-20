// client/src/components/app-viewer/AppViewerOverlay.tsx

import { AnimatePresence } from "framer-motion";
import { WindowOverlay } from "@/components/window-management";
import { AppViewerLayout } from "./AppViewerLayout";
import { useAppViewerVisibility } from "@/hooks/useAppViewer";

/**
 * App viewer overlay component.
 * Renders the app as a fullscreen overlay when maximized.
 * Mounted at root level in App.tsx.
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
