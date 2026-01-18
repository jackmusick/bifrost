/**
 * App Code Editor Component
 *
 * A Monaco-based code editor for editing code files in the App Builder.
 * Features:
 * - Syntax highlighting for JSX/TypeScript
 * - Auto-compilation with debouncing
 * - Error markers from compilation
 * - Save with Cmd/Ctrl+S
 */

import { useRef, useCallback, useEffect } from "react";
import Editor, { type OnMount, type BeforeMount } from "@monaco-editor/react";
import { useTheme } from "@/contexts/ThemeContext";
import { initializeMonaco } from "@/lib/monaco-setup";
import { Loader2 } from "lucide-react";
import type * as Monaco from "monaco-editor";

export interface CompilationError {
	message: string;
	line?: number;
	column?: number;
}

export interface AppCodeEditorProps {
	/** Current source code value */
	value: string;
	/** Called when source code changes */
	onChange: (value: string) => void;
	/** Called when user saves (Cmd/Ctrl+S) */
	onSave?: () => void;
	/** Compilation errors to display as markers */
	errors?: CompilationError[];
	/** Whether the editor is read-only */
	readOnly?: boolean;
	/** Height of the editor (default: 100%) */
	height?: string | number;
	/** File path - used by Monaco to determine language and file type */
	path?: string;
	/** Additional class name for the container */
	className?: string;
}

/**
 * App Code Editor
 *
 * A Monaco editor configured for JSX editing with compilation error support.
 */
export function AppCodeEditor({
	value,
	onChange,
	onSave,
	errors = [],
	readOnly = false,
	height = "100%",
	path,
	className = "",
}: AppCodeEditorProps) {
	const { theme } = useTheme();
	const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
	const monacoRef = useRef<typeof Monaco | null>(null);
	const monacoInitializedRef = useRef<boolean>(false);

	// Determine Monaco theme based on app theme
	const monacoTheme = theme === "light" ? "vs" : "vs-dark";

	// Ensure path has .tsx extension for Monaco to recognize TypeScript+JSX
	const monacoPath = path
		? path.endsWith(".tsx")
			? path
			: `${path}.tsx`
		: "file.tsx";

	// Configure Monaco BEFORE it mounts
	const handleEditorWillMount: BeforeMount = async (monaco) => {
		if (!monacoInitializedRef.current) {
			monacoInitializedRef.current = true;
			await initializeMonaco(monaco);
		}
	};

	// Handle editor mount
	const handleEditorMount: OnMount = (editor, monaco) => {
		editorRef.current = editor;
		monacoRef.current = monaco;

		// Register Cmd/Ctrl+S for save
		editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
			onSave?.();
		});

		// Focus the editor
		editor.focus();
	};

	// Handle value changes
	const handleChange = useCallback(
		(newValue: string | undefined) => {
			if (newValue !== undefined) {
				onChange(newValue);
			}
		},
		[onChange],
	);

	// Apply error markers when errors change
	useEffect(() => {
		const editor = editorRef.current;
		const monaco = monacoRef.current;

		if (!editor || !monaco) return;

		const model = editor.getModel();
		if (!model) return;

		// Clear previous markers
		monaco.editor.setModelMarkers(model, "app-code-compiler", []);

		// Apply new error markers
		if (errors.length > 0) {
			const markers: Monaco.editor.IMarkerData[] = errors.map((err) => ({
				severity: monaco.MarkerSeverity.Error,
				message: err.message,
				startLineNumber: err.line ?? 1,
				startColumn: err.column ?? 1,
				endLineNumber: err.line ?? 1,
				endColumn: 1000, // Highlight to end of line
				source: "App Code Compiler",
			}));

			monaco.editor.setModelMarkers(model, "app-code-compiler", markers);
		}
	}, [errors]);

	return (
		<div className={`h-full w-full ${className}`}>
			<Editor
				height={height}
				path={monacoPath}
				defaultLanguage="typescript"
				value={value}
				onChange={handleChange}
				beforeMount={handleEditorWillMount}
				onMount={handleEditorMount}
				theme={monacoTheme}
				options={{
					// Display
					minimap: { enabled: true },
					scrollBeyondLastLine: false,
					fontSize: 14,
					wordWrap: "on",
					automaticLayout: true,
					renderWhitespace: "selection",
					cursorBlinking: "smooth",
					smoothScrolling: true,

					// Indentation
					tabSize: 2,
					insertSpaces: true,

					// Formatting
					formatOnPaste: true,
					formatOnType: true,

					// Context menu
					contextmenu: true,

					// Auto-closing
					autoClosingBrackets: "always",
					autoClosingQuotes: "always",
					autoSurround: "languageDefined",

					// Bracket colorization
					bracketPairColorization: {
						enabled: true,
					},

					// Code folding
					showFoldingControls: "always",
					foldingStrategy: "auto",

					// IntelliSense
					quickSuggestions: {
						other: true,
						comments: false,
						strings: true,
					},
					suggestOnTriggerCharacters: true,

					// Multi-cursor
					multiCursorModifier: "ctrlCmd",

					// Read-only mode
					readOnly,

					// Line numbers
					lineNumbers: "on",
					renderLineHighlight: "all",
				}}
				loading={
					<div className="flex h-full items-center justify-center">
						<div className="text-center">
							<Loader2 className="h-8 w-8 animate-spin text-muted-foreground mx-auto mb-2" />
							<p className="text-sm text-muted-foreground">
								Loading editor...
							</p>
						</div>
					</div>
				}
			/>
		</div>
	);
}
