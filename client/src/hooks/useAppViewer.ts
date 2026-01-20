import { useShallow } from "zustand/react/shallow";
import { useNavigate, useLocation } from "react-router-dom";
import { useCallback } from "react";
import { useAppViewerStore } from "@/stores/appViewerStore";

/**
 * Hook for accessing app viewer state with navigation actions.
 * Wraps store actions with router navigation.
 */
export function useAppViewer() {
	const navigate = useNavigate();
	const location = useLocation();

	const store = useAppViewerStore(
		useShallow((state) => ({
			appId: state.appId,
			appSlug: state.appSlug,
			appName: state.appName,
			versionId: state.versionId,
			isPreview: state.isPreview,
			layoutMode: state.layoutMode,
			returnToPath: state.returnToPath,
			internalRoute: state.internalRoute,
			openApp: state.openApp,
			maximize: state.maximize,
			minimize: state.minimize,
			restoreToWindowed: state.restoreToWindowed,
			closeApp: state.closeApp,
			setInternalRoute: state.setInternalRoute,
			hydrateFromRoute: state.hydrateFromRoute,
		})),
	);

	// Maximize to overlay mode (no navigation - overlay appears on top)
	const handleMaximize = useCallback(() => {
		store.maximize(location.pathname);
	}, [store, location.pathname]);

	// Minimize to dock - navigate back to returnToPath if available
	const handleMinimize = useCallback(() => {
		const { returnToPath } = useAppViewerStore.getState();
		store.minimize();
		// If we have a return path (user was somewhere else before maximizing),
		// navigate back there
		if (returnToPath) {
			navigate(returnToPath);
		}
		// If no returnToPath, we stay on the app route and AppRouter shows minimized placeholder
	}, [store, navigate]);

	// Restore to windowed with navigation
	const handleRestoreToWindowed = useCallback(() => {
		const appRoute = store.restoreToWindowed();
		navigate(appRoute);
	}, [store, navigate]);

	// Close with navigation
	const handleClose = useCallback(() => {
		const returnPath = store.closeApp();
		if (returnPath) {
			navigate(returnPath);
		}
	}, [store, navigate]);

	// Restore from minimized (go to maximized)
	const handleRestoreFromDock = useCallback(() => {
		useAppViewerStore.setState({ layoutMode: "maximized" });
	}, []);

	return {
		// State
		appId: store.appId,
		appSlug: store.appSlug,
		appName: store.appName,
		versionId: store.versionId,
		isPreview: store.isPreview,
		layoutMode: store.layoutMode,
		returnToPath: store.returnToPath,
		internalRoute: store.internalRoute,

		// Actions
		openApp: store.openApp,
		maximize: handleMaximize,
		minimize: handleMinimize,
		restoreToWindowed: handleRestoreToWindowed,
		restoreFromDock: handleRestoreFromDock,
		closeApp: handleClose,
		setInternalRoute: store.setInternalRoute,
		hydrateFromRoute: store.hydrateFromRoute,
	};
}

/**
 * Lightweight hook for components that only need visibility state.
 */
export function useAppViewerVisibility() {
	return useAppViewerStore(
		useShallow((state) => ({
			appId: state.appId,
			appName: state.appName,
			layoutMode: state.layoutMode,
			isPreview: state.isPreview,
		})),
	);
}

/**
 * Hook for app viewer overlay that doesn't require router context.
 * Navigation actions set pendingNavigation in store - main app listens and navigates.
 */
export function useAppViewerOverlay() {
	const store = useAppViewerStore(
		useShallow((state) => ({
			appId: state.appId,
			appSlug: state.appSlug,
			appName: state.appName,
			versionId: state.versionId,
			isPreview: state.isPreview,
			layoutMode: state.layoutMode,
			returnToPath: state.returnToPath,
			internalRoute: state.internalRoute,
		})),
	);

	// Minimize to dock - set pending navigation for main app to handle
	const handleMinimize = useCallback(() => {
		const { returnToPath } = useAppViewerStore.getState();
		useAppViewerStore.getState().minimize();
		// Set pending navigation for the main app (inside BrowserRouter) to handle
		if (returnToPath) {
			useAppViewerStore.setState({ pendingNavigation: returnToPath });
		}
	}, []);

	// Restore to windowed - set pending navigation
	const handleRestoreToWindowed = useCallback(() => {
		const { appSlug, isPreview } = useAppViewerStore.getState();
		useAppViewerStore.getState().restoreToWindowed();
		// Navigate to the app route
		const appRoute = isPreview
			? `/apps/${appSlug}/preview`
			: `/apps/${appSlug}`;
		useAppViewerStore.setState({ pendingNavigation: appRoute });
	}, []);

	// Close - set pending navigation
	const handleClose = useCallback(() => {
		const returnPath = useAppViewerStore.getState().closeApp();
		if (returnPath) {
			useAppViewerStore.setState({ pendingNavigation: returnPath });
		}
	}, []);

	return {
		// State
		appId: store.appId,
		appSlug: store.appSlug,
		appName: store.appName,
		versionId: store.versionId,
		isPreview: store.isPreview,
		layoutMode: store.layoutMode,
		returnToPath: store.returnToPath,
		internalRoute: store.internalRoute,

		// Actions (navigation-free)
		minimize: handleMinimize,
		restoreToWindowed: handleRestoreToWindowed,
		closeApp: handleClose,
	};
}
