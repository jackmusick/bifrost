import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface OrgScope {
	type: "global" | "organization";
	orgId: string | null;
	orgName: string | null;
}

interface ScopeState {
	scope: OrgScope;
	isGlobalScope: boolean;
	_hasHydrated: boolean;
	setScope: (scope: OrgScope) => void;
	setHasHydrated: (hydrated: boolean) => void;
}

/**
 * Store for tracking the current organization scope selection.
 *
 * This is used for UI purposes (org switcher display, query cache keys)
 * but does NOT affect API requests - organization filtering is done
 * via query parameters on each endpoint.
 */
export const useScopeStore = create<ScopeState>()(
	persist(
		(set) => ({
			scope: { type: "global", orgId: null, orgName: null },
			isGlobalScope: true,
			_hasHydrated: false,
			setScope: (scope) => {
				set({
					scope,
					isGlobalScope: scope.type === "global",
				});
			},
			setHasHydrated: (hydrated) => {
				set({ _hasHydrated: hydrated });
			},
		}),
		{
			name: "msp-automation-org-scope",
			storage: createJSONStorage(() => localStorage),
			onRehydrateStorage: () => () => {
				// Mark as hydrated when localStorage state is loaded
				useScopeStore.setState({ _hasHydrated: true });
			},
		},
	),
);
