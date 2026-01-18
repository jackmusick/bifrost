/**
 * Platform hook: useAppState
 *
 * Zustand-backed cross-page state for app code.
 * State persists across page navigations within the same app session.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { useCallback } from "react";

/**
 * Internal store for app state
 * Manages cross-page state that persists during the session
 */
interface AppCodeStateStore {
	/** App-level state values keyed by name */
	state: Record<string, unknown>;

	/** Set a single state value */
	setState: (key: string, value: unknown) => void;

	/** Get a state value */
	getState: (key: string) => unknown;

	/** Reset all state (called when app changes) */
	reset: () => void;
}

/**
 * Zustand store for app state
 * Uses subscribeWithSelector for granular re-renders
 */
export const appCodeStateStore = create<AppCodeStateStore>()(
	subscribeWithSelector((set, get) => ({
		state: {},

		setState: (key, value) =>
			set((prev) => ({
				state: { ...prev.state, [key]: value },
			})),

		getState: (key) => get().state[key],

		reset: () => set({ state: {} }),
	})),
);

/**
 * App-level state that persists across page navigations
 *
 * @param key - Unique key for the state value
 * @param initialValue - Initial value if state is not set
 * @returns Tuple of [value, setValue] similar to useState
 *
 * @example
 * ```jsx
 * // In any page or component
 * const [selectedClientId, setSelectedClientId] = useAppState('selectedClient', null);
 *
 * // Value persists when navigating to other pages
 * <Button onClick={() => {
 *   setSelectedClientId(client.id);
 *   navigate('/client-details');
 * }}>
 *   View Details
 * </Button>
 * ```
 *
 * @example
 * ```jsx
 * // Sharing state across pages
 * // Page 1: Set the state
 * const [cart, setCart] = useAppState('cart', []);
 * setCart([...cart, newItem]);
 *
 * // Page 2: Read the same state
 * const [cart] = useAppState('cart', []);
 * // cart contains items added from Page 1
 * ```
 */
export function useAppState<T>(
	key: string,
	initialValue: T,
): [T, (value: T) => void] {
	// Subscribe to changes for this specific key
	const storedValue = appCodeStateStore((state) => state.state[key]);
	const setStateAction = appCodeStateStore((state) => state.setState);

	// Return initialValue if no stored value exists
	const value = (storedValue !== undefined ? storedValue : initialValue) as T;

	// Memoize the setter to maintain stable reference
	const setValue = useCallback(
		(newValue: T) => {
			setStateAction(key, newValue);
		},
		[key, setStateAction],
	);

	return [value, setValue];
}

/**
 * Reset all app state
 * Called when switching between apps or on app unmount
 * @internal
 */
export function resetAppCodeState(): void {
	appCodeStateStore.getState().reset();
}
