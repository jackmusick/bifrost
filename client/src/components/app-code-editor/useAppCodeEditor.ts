/**
 * App Code Editor Hook
 *
 * Manages the state for a code editor including:
 * - Source code state
 * - Auto-compilation with debouncing
 * - Unsaved changes tracking
 * - Error state
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { compileAppCode } from "@/lib/app-code-compiler";
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
	/** Initial compiled code (optional, will recompile if not provided) */
	initialCompiled?: string;
	/** Debounce delay for compilation (ms) */
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
	/** Trigger an immediate save */
	save: () => Promise<void>;
	/** Trigger an immediate compile */
	compile: () => void;
	/** Reset to initial state */
	reset: () => void;
	/** Mark as saved (clears unsaved flag) */
	markSaved: () => void;
}

/**
 * Hook for managing app code editor state
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
	compileDelay = 500,
	onSave,
	onCompile,
}: UseAppCodeEditorOptions): UseAppCodeEditorResult {
	const [state, setState] = useState<AppCodeEditorState>(() => ({
		source: initialSource,
		compiled: initialCompiled ?? null,
		errors: [],
		hasUnsavedChanges: false,
		isCompiling: false,
	}));

	const compileTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const isSavingRef = useRef(false);

	// Compile the current source
	const compile = useCallback(() => {
		setState((prev) => {
			const result = compileAppCode(prev.source);

			if (result.success && result.compiled) {
				onCompile?.(prev.source, result.compiled, []);
				return {
					...prev,
					compiled: result.compiled!,
					errors: [],
					isCompiling: false,
				};
			} else {
				const errors: CompilationError[] = result.error
					? [{ message: result.error }]
					: [{ message: "Compilation failed" }];
				onCompile?.(prev.source, null, errors);
				return {
					...prev,
					compiled: null,
					errors,
					isCompiling: false,
				};
			}
		});
	}, [onCompile]);

	// Update source code with debounced compilation
	const setSource = useCallback(
		(newSource: string) => {
			// Update source immediately
			setState((prev) => ({
				...prev,
				source: newSource,
				hasUnsavedChanges: true,
			}));

			// Clear existing timer
			if (compileTimerRef.current) {
				clearTimeout(compileTimerRef.current);
			}

			// Schedule compilation
			compileTimerRef.current = setTimeout(() => {
				// Compile with the new source (we need to do it here because
				// the state.source in the compile callback might be stale)
				const result = compileAppCode(newSource);

				if (result.success && result.compiled) {
					setState((prev) => ({
						...prev,
						compiled: result.compiled!,
						errors: [],
						isCompiling: false,
					}));
					onCompile?.(newSource, result.compiled, []);
				} else {
					const errors: CompilationError[] = result.error
						? [{ message: result.error }]
						: [{ message: "Compilation failed" }];

					setState((prev) => ({
						...prev,
						compiled: null,
						errors,
						isCompiling: false,
					}));
					onCompile?.(newSource, null, errors);
				}
			}, compileDelay);
		},
		[compileDelay, onCompile],
	);

	// Save the current state
	const save = useCallback(async () => {
		if (isSavingRef.current) return;
		if (!state.compiled || state.errors.length > 0) {
			// Can't save with errors - compile first
			compile();
			return;
		}

		isSavingRef.current = true;

		try {
			await onSave?.(state.source, state.compiled);
			setState((prev) => ({ ...prev, hasUnsavedChanges: false }));
		} finally {
			isSavingRef.current = false;
		}
	}, [state.source, state.compiled, state.errors.length, compile, onSave]);

	// Reset to initial state
	const reset = useCallback(() => {
		if (compileTimerRef.current) {
			clearTimeout(compileTimerRef.current);
		}

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

	// Initial compilation if no compiled code provided
	// We intentionally only run this on mount, so we use refs to capture values
	const initialSourceRef = useRef(initialSource);
	const initialCompiledRef = useRef(initialCompiled);

	useEffect(() => {
		if (!initialCompiledRef.current && initialSourceRef.current) {
			const result = compileAppCode(initialSourceRef.current);
			if (result.success && result.compiled) {
				setState((prev) => ({
					...prev,
					compiled: result.compiled!,
					errors: [],
				}));
			}
		}
	}, []); // Only run on mount

	// Cleanup timer on unmount
	useEffect(() => {
		return () => {
			if (compileTimerRef.current) {
				clearTimeout(compileTimerRef.current);
			}
		};
	}, []);

	return {
		state,
		setSource,
		save,
		compile,
		reset,
		markSaved,
	};
}
