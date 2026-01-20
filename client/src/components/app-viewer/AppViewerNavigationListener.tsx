// client/src/components/app-viewer/AppViewerNavigationListener.tsx

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppViewerStore } from "@/stores/appViewerStore";

/**
 * Listens for pending navigation requests from the app viewer overlay.
 * Must be rendered inside BrowserRouter context to access useNavigate.
 *
 * The overlay sets pendingNavigation when it needs to trigger navigation
 * (e.g., minimize, restore to windowed, close), and this component
 * handles the actual navigation since it has access to the router.
 */
export function AppViewerNavigationListener() {
	const navigate = useNavigate();
	const pendingNavigation = useAppViewerStore(
		(state) => state.pendingNavigation,
	);
	const clearPendingNavigation = useAppViewerStore(
		(state) => state.clearPendingNavigation,
	);

	useEffect(() => {
		if (pendingNavigation) {
			navigate(pendingNavigation);
			clearPendingNavigation();
		}
	}, [pendingNavigation, navigate, clearPendingNavigation]);

	return null;
}
