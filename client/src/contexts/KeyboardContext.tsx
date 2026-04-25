import { createContext, useContext, useEffect, useRef, ReactNode } from "react";

/**
 * Keyboard shortcut handler function
 */
type KeyboardHandler = (event: KeyboardEvent) => void | boolean;

/**
 * Keyboard shortcut definition
 */
interface KeyboardShortcut {
	key: string;
	ctrl?: boolean;
	meta?: boolean;
	shift?: boolean;
	alt?: boolean;
	handler: KeyboardHandler;
}

/**
 * Context for managing global keyboard shortcuts
 */
interface KeyboardContextType {
	registerShortcut: (id: string, shortcut: KeyboardShortcut) => void;
	unregisterShortcut: (id: string) => void;
}

const KeyboardContext = createContext<KeyboardContextType | undefined>(
	undefined,
);

/**
 * Provider component for global keyboard shortcuts
 * Manages a registry of keyboard shortcuts and dispatches events to registered handlers
 */
export function KeyboardProvider({ children }: { children: ReactNode }) {
	const shortcutsRef = useRef<Map<string, KeyboardShortcut>>(new Map());

	const registerShortcut = (id: string, shortcut: KeyboardShortcut) => {
		shortcutsRef.current.set(id, shortcut);
	};

	const unregisterShortcut = (id: string) => {
		shortcutsRef.current.delete(id);
	};

	useEffect(() => {
		const handleKeyDown = (event: KeyboardEvent) => {
			// Check each registered shortcut
			for (const shortcut of shortcutsRef.current.values()) {
				const keyMatches =
					event.key.toLowerCase() === shortcut.key.toLowerCase();

				// Special handling for Cmd/Ctrl shortcuts
				const isCmdCtrlShortcut = shortcut.ctrl && shortcut.meta;

				let modifiersMatch: boolean;
				if (isCmdCtrlShortcut) {
					// For Cmd/Ctrl shortcuts, accept either
					const cmdCtrlPressed = event.ctrlKey || event.metaKey;
					const shiftMatches =
						shortcut.shift === undefined ||
						event.shiftKey === shortcut.shift;
					const altMatches =
						shortcut.alt === undefined ||
						event.altKey === shortcut.alt;
					modifiersMatch =
						cmdCtrlPressed && shiftMatches && altMatches;
				} else {
					// Regular modifier matching
					const ctrlMatches =
						shortcut.ctrl === undefined ||
						event.ctrlKey === shortcut.ctrl;
					const metaMatches =
						shortcut.meta === undefined ||
						event.metaKey === shortcut.meta;
					const shiftMatches =
						shortcut.shift === undefined ||
						event.shiftKey === shortcut.shift;
					const altMatches =
						shortcut.alt === undefined ||
						event.altKey === shortcut.alt;
					modifiersMatch =
						ctrlMatches &&
						metaMatches &&
						shiftMatches &&
						altMatches;
				}

				if (keyMatches && modifiersMatch) {
					const result = shortcut.handler(event);
					// If handler returns false, don't prevent default
					if (result !== false) {
						event.preventDefault();
						event.stopPropagation();
					}
					break; // Only trigger first matching shortcut
				}
			}
		};

		window.addEventListener("keydown", handleKeyDown, true); // Use capture phase
		return () => window.removeEventListener("keydown", handleKeyDown, true);
	}, []);

	return (
		<KeyboardContext.Provider
			value={{ registerShortcut, unregisterShortcut }}
		>
			{children}
		</KeyboardContext.Provider>
	);
}

/**
 * Hook to register a keyboard shortcut
 * Automatically cleans up when component unmounts
 *
 * @example
 * useKeyboardShortcut("save", {
 *   key: "s",
 *   ctrl: true,
 *   meta: true,
 *   handler: (e) => {
 *
 *   }
 * });
 */
export function useKeyboardShortcut(id: string, shortcut: KeyboardShortcut) {
	const context = useContext(KeyboardContext);

	if (!context) {
		throw new Error(
			"useKeyboardShortcut must be used within a KeyboardProvider",
		);
	}

	const { registerShortcut, unregisterShortcut } = context;

	useEffect(() => {
		registerShortcut(id, shortcut);
		return () => unregisterShortcut(id);
	}, [id, shortcut, registerShortcut, unregisterShortcut]);
}

/**
 * Hook for common Cmd/Ctrl+Key shortcuts
 * Handles both Ctrl (Windows/Linux) and Cmd (Mac) automatically
 *
 * @example
 * useCmdCtrlShortcut("save", "s", () => {
 *
 * });
 */
export function useCmdCtrlShortcut(
	id: string,
	key: string,
	handler: KeyboardHandler,
) {
	useKeyboardShortcut(id, {
		key,
		ctrl: true,
		meta: true,
		handler,
	});
}
