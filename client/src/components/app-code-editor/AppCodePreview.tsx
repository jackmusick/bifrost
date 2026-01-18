/**
 * App Code Preview Component
 *
 * Renders a live preview of compiled code with:
 * - Error boundary for runtime errors
 * - Loading state during compilation
 * - Iframe isolation (optional) for style isolation
 */

import React, { useEffect, useMemo, useReducer } from "react";
import { createComponent, $ } from "@/lib/app-code-runtime";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CompilationError } from "./AppCodeEditor";

interface AppCodePreviewProps {
	/** Compiled code (from app-code-compiler) */
	compiled: string | null;
	/** Compilation errors to display */
	errors?: CompilationError[];
	/** Whether compilation is in progress */
	isCompiling?: boolean;
	/** Custom components to inject into the scope */
	customComponents?: Record<string, React.ComponentType>;
	/** Additional class name for the container */
	className?: string;
	/** Whether to show a border around the preview */
	bordered?: boolean;
	/** Callback to force refresh the preview */
	onRefresh?: () => void;
}

// Reducer for preview state to avoid multiple setState calls in effects
interface PreviewState {
	renderKey: number;
	runtimeError: Error | null;
}

type PreviewAction =
	| { type: "RESET" }
	| { type: "SET_ERROR"; error: Error }
	| { type: "REFRESH" };

function previewReducer(state: PreviewState, action: PreviewAction): PreviewState {
	switch (action.type) {
		case "RESET":
			return { renderKey: state.renderKey + 1, runtimeError: null };
		case "SET_ERROR":
			return { ...state, runtimeError: action.error };
		case "REFRESH":
			return { renderKey: state.renderKey + 1, runtimeError: null };
		default:
			return state;
	}
}

/**
 * Error Boundary for catching render errors in preview
 */
class PreviewErrorBoundary extends React.Component<
	{ children: React.ReactNode; onError?: (error: Error) => void },
	{ hasError: boolean; error: Error | null }
> {
	constructor(props: { children: React.ReactNode; onError?: (error: Error) => void }) {
		super(props);
		this.state = { hasError: false, error: null };
	}

	static getDerivedStateFromError(error: Error) {
		return { hasError: true, error };
	}

	componentDidCatch(error: Error) {
		this.props.onError?.(error);
	}

	render() {
		if (this.state.hasError) {
			return (
				<div className="p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg">
					<div className="flex items-start gap-3">
						<AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
						<div className="flex-1 min-w-0">
							<h3 className="font-semibold text-red-700 dark:text-red-400">
								Runtime Error
							</h3>
							<pre className="mt-2 text-sm whitespace-pre-wrap font-mono bg-red-100 dark:bg-red-900/30 p-2 rounded overflow-auto text-red-600 dark:text-red-300">
								{this.state.error?.message || "Unknown error"}
							</pre>
						</div>
					</div>
				</div>
			);
		}

		return this.props.children;
	}
}

/**
 * Live preview component for app code
 *
 * Renders compiled code with error handling and loading states.
 *
 * @example
 * ```tsx
 * const { state } = useAppCodeEditor({ initialSource: '...' });
 *
 * <AppCodePreview
 *   compiled={state.compiled}
 *   errors={state.errors}
 *   isCompiling={state.isCompiling}
 * />
 * ```
 */
export function AppCodePreview({
	compiled,
	errors = [],
	isCompiling = false,
	customComponents = {},
	className = "",
	bordered = true,
	onRefresh,
}: AppCodePreviewProps) {
	const [state, dispatch] = useReducer(previewReducer, {
		renderKey: 0,
		runtimeError: null,
	});

	// Create the preview component from compiled code using useMemo
	// Note: This is an intentional pattern for dynamic component rendering.
	// The component is created from user-authored code at runtime.
	// useMemo ensures stability across renders with the same compiled code.
	const PreviewComponent = useMemo(() => {
		if (!compiled || errors.length > 0) {
			return null;
		}

		try {
			return createComponent(compiled, customComponents, true);
		} catch (err) {
			console.error("Failed to create preview component:", err);
			return null;
		}
	}, [compiled, errors.length, customComponents]);

	// Reset runtime error when compiled code changes
	useEffect(() => {
		dispatch({ type: "RESET" });
	}, [compiled]);

	// Handle manual refresh
	const handleRefresh = () => {
		dispatch({ type: "REFRESH" });
		onRefresh?.();
	};

	// Handle runtime errors from the error boundary
	const handleRuntimeError = (error: Error) => {
		dispatch({ type: "SET_ERROR", error });
	};

	// Compilation in progress
	if (isCompiling) {
		return (
			<div className={`h-full flex items-center justify-center ${className}`}>
				<div className="text-center">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground mx-auto mb-2" />
					<p className="text-sm text-muted-foreground">Compiling...</p>
				</div>
			</div>
		);
	}

	// Compilation errors
	if (errors.length > 0) {
		return (
			<div className={`h-full p-4 ${className}`}>
				<div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
					<div className="flex items-start gap-3">
						<AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
						<div className="flex-1 min-w-0">
							<h3 className="font-semibold text-red-700 dark:text-red-400">
								Compilation Error{errors.length > 1 ? "s" : ""}
							</h3>
							<div className="mt-2 space-y-2">
								{errors.map((error, i) => (
									<div
										key={i}
										className="text-sm font-mono bg-red-100 dark:bg-red-900/30 p-2 rounded text-red-600 dark:text-red-300"
									>
										{error.line && (
											<span className="text-red-500 dark:text-red-400">
												Line {error.line}
												{error.column ? `:${error.column}` : ""}:{" "}
											</span>
										)}
										{error.message}
									</div>
								))}
							</div>
						</div>
					</div>
				</div>
			</div>
		);
	}

	// No compiled code yet
	if (!PreviewComponent) {
		return (
			<div className={`h-full flex items-center justify-center ${className}`}>
				<div className="text-center text-muted-foreground">
					<p className="text-sm">No preview available</p>
					<p className="text-xs mt-1">Write some code to see the preview</p>
				</div>
			</div>
		);
	}

	// Render the preview
	const containerClass = `h-full ${bordered ? "border rounded-lg overflow-auto" : ""} ${className}`;

	return (
		<div className={containerClass}>
			{/* Refresh button */}
			{onRefresh && (
				<div className="absolute top-2 right-2 z-10">
					<Button
						variant="ghost"
						size="icon"
						onClick={handleRefresh}
						className="h-8 w-8"
						title="Refresh preview"
					>
						<RefreshCw className="h-4 w-4" />
					</Button>
				</div>
			)}

			{/* Preview content */}
			<div className="p-4 relative">
				<PreviewErrorBoundary
					key={state.renderKey}
					onError={handleRuntimeError}
				>
					{state.runtimeError ? (
						<div className="p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg">
							<div className="flex items-start gap-3">
								<AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
								<div className="flex-1 min-w-0">
									<h3 className="font-semibold text-red-700 dark:text-red-400">
										Runtime Error
									</h3>
									<pre className="mt-2 text-sm whitespace-pre-wrap font-mono bg-red-100 dark:bg-red-900/30 p-2 rounded overflow-auto text-red-600 dark:text-red-300">
										{state.runtimeError.message}
									</pre>
									<Button
										variant="outline"
										size="sm"
										onClick={handleRefresh}
										className="mt-3"
									>
										<RefreshCw className="h-4 w-4 mr-2" />
										Retry
									</Button>
								</div>
							</div>
						</div>
					) : (
						// eslint-disable-next-line react-hooks/static-components -- Intentional: PreviewComponent is dynamically created from user code
						<PreviewComponent />
					)}
				</PreviewErrorBoundary>
			</div>
		</div>
	);
}

/**
 * Create a sandboxed preview with custom scope
 *
 * This is useful for testing or when you want to provide
 * mock implementations of platform APIs.
 */
export function createSandboxedPreview(
	compiled: string,
	scopeOverrides: Partial<typeof $> = {},
	customComponents: Record<string, React.ComponentType> = {},
): React.ComponentType {
	const scope = {
		...$,
		...scopeOverrides,
		...customComponents,
	};

	return createComponent(compiled, scope as Record<string, React.ComponentType>, true);
}
