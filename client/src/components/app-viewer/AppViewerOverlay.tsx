// client/src/components/app-viewer/AppViewerOverlay.tsx

import { AnimatePresence } from "framer-motion";
import { WindowOverlay } from "@/components/window-management";
import { AppViewerLayout } from "./AppViewerLayout";
import { useAppViewerVisibility } from "@/hooks/useAppViewer";

/**
 * App viewer overlay component.
 * Renders the app as a fullscreen overlay when maximized.
 *
 * The app uses MemoryRouter internally for isolated routing context,
 * allowing it to be rendered globally without conflicting with the
 * browser's URL-based routing.
 */
export function AppViewerOverlay() {
	const { appId, layoutMode } = useAppViewerVisibility();

	// Not active - no app loaded
	if (!appId) {
		return null;
	}

	// If minimized, don't render the overlay - dock handles minimized state
	// The app will remount when restored (MemoryRouter resets to initial route)
	if (layoutMode === "minimized") {
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
