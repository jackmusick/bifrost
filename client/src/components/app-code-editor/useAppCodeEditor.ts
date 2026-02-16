/**
 * App Code Editor Hook
 *
 * Manages the state for a code editor including:
 * - Source code state
 * - Unsaved changes tracking
 * - Error state
 *
 * Compilation happens server-side on save.
 */

import { useState, useCallback, useRef } from "react";
import type { CompilationError } from "./AppCodeEditor";

export interface AppCodeEditorState {
	/** Current source code */
	source: string;
	/** Compiled output (if successful) */
	compiled: string | null;
	/** Compilation errors */
	errors: CompilationError[];
	/** Whether there are unsaved changes */
	hasUnsavedChanges: boolean;
	/** Whether compilation is in progress */
	isCompiling: boolean;
}

export interface UseAppCodeEditorOptions {
	/** Initial source code */
	initialSource: string;
	/** Initial compiled code (optional) */
	initialCompiled?: string;
	/** Debounce delay for compilation (ms) — kept for API compat but unused */
	compileDelay?: number;
	/** Callback when save is triggered */
	onSave?: (source: string, compiled: string) => void | Promise<void>;
	/** Callback when compilation completes */
	onCompile?: (source: string, compiled: string | null, errors: CompilationError[]) => void;
}

export interface UseAppCodeEditorResult {
	/** Current editor state */
	state: AppCodeEditorState;
	/** Update the source code */
	setSource: (source: string) => void;
	/** Update the compiled output (e.g. after server-side compilation) */
	setCompiled: (compiled: string | null) => void;
	/** Trigger an immediate save */
	save: () => Promise<void>;
	/** Trigger an immediate compile (no-op, kept for API compat) */
	compile: () => void;
	/** Reset to initial state */
	reset: () => void;
	/** Mark as saved (clears unsaved flag) */
	markSaved: () => void;
}

/**
 * Hook for managing app code editor state
 *
 * Compilation now happens server-side on save. The editor only tracks
 * source changes and sends them to the server when saved.
 *
 * @example
 * ```tsx
 * const { state, setSource, save } = useAppCodeEditor({
 *   initialSource: 'return <div>Hello</div>;',
 *   onSave: async (source, compiled) => {
 *     await api.saveFile(fileId, source, compiled);
 *   }
 * });
 * ```
 */
export function useAppCodeEditor({
	initialSource,
	initialCompiled,
	compileDelay: _compileDelay = 500,
	onSave,
	onCompile: _onCompile,
}: UseAppCodeEditorOptions): UseAppCodeEditorResult {
	const [state, setState] = useState<AppCodeEditorState>(() => ({
		source: initialSource,
		compiled: initialCompiled ?? null,
		errors: [],
		hasUnsavedChanges: false,
		isCompiling: false,
	}));

	const isSavingRef = useRef(false);

	// compile() is now a no-op — compilation happens server-side on save
	const compile = useCallback(() => {
		// Server-side compilation happens via the save flow.
		// This is kept for API compatibility but does nothing.
	}, []);

	// Update source code — just track changes, no compilation
	const setSource = useCallback((newSource: string) => {
		setState((prev) => ({
			...prev,
			source: newSource,
			hasUnsavedChanges: true,
		}));
	}, []);

	// Update compiled output (e.g. after server returns compiled code)
	const setCompiled = useCallback((compiled: string | null) => {
		setState((prev) => ({ ...prev, compiled }));
	}, []);

	// Save: send source to server (compilation happens server-side)
	const save = useCallback(async () => {
		if (isSavingRef.current) return;
		isSavingRef.current = true;

		setState((prev) => ({ ...prev, isCompiling: true }));

		try {
			await onSave?.(state.source, state.compiled ?? state.source);
			setState((prev) => ({
				...prev,
				hasUnsavedChanges: false,
				isCompiling: false,
			}));
		} catch (error) {
			setState((prev) => ({
				...prev,
				isCompiling: false,
				errors: [{
					message: error instanceof Error ? error.message : "Save failed",
				}],
			}));
		} finally {
			isSavingRef.current = false;
		}
	}, [state.source, state.compiled, onSave]);

	// Reset to initial state
	const reset = useCallback(() => {
		setState({
			source: initialSource,
			compiled: initialCompiled ?? null,
			errors: [],
			hasUnsavedChanges: false,
			isCompiling: false,
		});
	}, [initialSource, initialCompiled]);

	// Mark as saved
	const markSaved = useCallback(() => {
		setState((prev) => ({ ...prev, hasUnsavedChanges: false }));
	}, []);

	return {
		state,
		setSource,
		setCompiled,
		save,
		compile,
		reset,
		markSaved,
	};
}
