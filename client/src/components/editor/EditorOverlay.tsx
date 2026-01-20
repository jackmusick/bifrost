// client/src/components/editor/EditorOverlay.tsx

import { AnimatePresence } from "framer-motion";
import { useEditorStore } from "@/stores/editorStore";
import { useAuth } from "@/contexts/AuthContext";
import { EditorLayout } from "./EditorLayout";
import { WindowOverlay } from "@/components/window-management";

/**
 * Editor overlay component
 * Renders the editor as a fullscreen overlay on top of the current page
 * Only visible when isOpen is true and user is a platform admin
 * When minimized, returns null - the unified dock handles the minimized state
 */
export function EditorOverlay() {
	const isOpen = useEditorStore((state) => state.isOpen);
	const layoutMode = useEditorStore((state) => state.layoutMode);
	const { isPlatformAdmin } = useAuth();

	if (!isOpen || !isPlatformAdmin) {
		return null;
	}

	// If minimized, don't render - unified dock handles this
	if (layoutMode === "minimized") {
		return null;
	}

	return (
		<AnimatePresence>
			{layoutMode === "fullscreen" && (
				<WindowOverlay>
					<EditorLayout />
				</WindowOverlay>
			)}
		</AnimatePresence>
	);
}
