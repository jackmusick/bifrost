import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * App Viewer state store using Zustand with persistence.
 * Manages the app viewer overlay state for minimize/maximize/restore.
 */

export type AppViewerLayoutMode = "maximized" | "minimized" | null;

interface AppViewerState {
	// App identity
	appId: string | null;
	appSlug: string | null;
	appName: string | null;
	versionId: string | null;
	isPreview: boolean;

	// Display mode (null = windowed/not in overlay mode)
	layoutMode: AppViewerLayoutMode;

	// Navigation memory
	returnToPath: string | null;

	// Internal app route (e.g., "/dashboard")
	internalRoute: string;

	// Pending navigation - set by overlay, consumed by main app
	pendingNavigation: string | null;

	// Actions
	openApp: (params: {
		appId: string;
		appSlug: string;
		appName: string;
		versionId: string;
		isPreview: boolean;
	}) => void;
	maximize: (currentPath: string) => void;
	minimize: () => void;
	restoreToWindowed: () => string; // Returns the app route to navigate to
	closeApp: () => string | null; // Returns returnToPath if was in overlay
	setInternalRoute: (route: string) => void;
	hydrateFromRoute: (params: {
		appId: string;
		appSlug: string;
		appName: string;
		versionId: string;
		isPreview: boolean;
	}) => void;
	clearPendingNavigation: () => void;
}

export const useAppViewerStore = create<AppViewerState>()(
	persist(
		(set, get) => ({
			// Initial state
			appId: null,
			appSlug: null,
			appName: null,
			versionId: null,
			isPreview: false,
			layoutMode: null,
			returnToPath: null,
			internalRoute: "/",
			pendingNavigation: null,

			// Open an app (called when navigating to app route)
			openApp: ({ appId, appSlug, appName, versionId, isPreview }) =>
				set({
					appId,
					appSlug,
					appName,
					versionId,
					isPreview,
					layoutMode: null, // Start in windowed mode
					returnToPath: null,
					internalRoute: "/",
				}),

			// Maximize the app (overlay mode)
			maximize: (currentPath) =>
				set({
					layoutMode: "maximized",
					returnToPath: currentPath,
				}),

			// Minimize to dock
			minimize: () =>
				set({
					layoutMode: "minimized",
				}),

			// Restore to windowed mode (navigate to app route)
			restoreToWindowed: () => {
				const { appSlug, isPreview } = get();
				set({
					layoutMode: null,
					returnToPath: null,
				});
				return isPreview ? `/apps/${appSlug}/preview` : `/apps/${appSlug}`;
			},

			// Close the app entirely
			closeApp: () => {
				const { returnToPath, layoutMode } = get();
				const pathToReturn = layoutMode ? returnToPath : null;
				set({
					appId: null,
					appSlug: null,
					appName: null,
					versionId: null,
					isPreview: false,
					layoutMode: null,
					returnToPath: null,
					internalRoute: "/",
				});
				return pathToReturn;
			},

			// Update internal route (for display in header)
			setInternalRoute: (route) =>
				set({
					internalRoute: route,
				}),

			// Hydrate store when landing directly on app route
			hydrateFromRoute: ({ appId, appSlug, appName, versionId, isPreview }) => {
				const state = get();
				// Only hydrate if not already tracking this app
				if (state.appId !== appId) {
					set({
						appId,
						appSlug,
						appName,
						versionId,
						isPreview,
						layoutMode: null,
						returnToPath: null,
						internalRoute: "/",
					});
				}
			},

			// Clear pending navigation after it's been handled
			clearPendingNavigation: () =>
				set({
					pendingNavigation: null,
				}),
		}),
		{
			name: "app-viewer-storage",
			partialize: (state) => ({
				appId: state.appId,
				appSlug: state.appSlug,
				appName: state.appName,
				versionId: state.versionId,
				isPreview: state.isPreview,
				layoutMode: state.layoutMode,
				returnToPath: state.returnToPath,
				internalRoute: state.internalRoute,
			}),
		},
	),
);
