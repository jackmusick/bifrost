import { useState, useRef, useCallback, useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { FileTree } from "./FileTree";
import { CodeEditor } from "./CodeEditor";
import { TerminalPanel } from "./TerminalPanel";
import { RunPanel } from "./RunPanel";
import { SearchPanel } from "./SearchPanel";
import { PackagePanel } from "./PackagePanel";
import { SourceControlPanel } from "./SourceControlPanel";
import { FileTabs } from "./FileTabs";
import { useEditorSession } from "@/hooks/useEditorSession";
import { useCmdCtrlShortcut } from "@/contexts/KeyboardContext";
import { UploadProgressProvider } from "@/hooks/useUploadProgress";
import {
	X,
	Save,
	Minus,
	Maximize2,
	PanelLeftClose,
	PanelLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAutoSave } from "@/hooks/useAutoSave";

/**
 * Main editor layout container
 * Provides structure with sidebar, editor area, terminal area, and status bar
 * State is persisted, so closing and reopening restores the previous session
 */
export function EditorLayout() {
	const {
		openFile,
		unsavedChanges,
		saveState,
		sidebarPanel,
		layoutMode,
		terminalHeight,
		closeEditor,
		minimizeEditor,
		restoreEditor,
		setTerminalHeight,
		setSidebarPanel,
	} = useEditorSession();

	// Auto-save and manual save
	const { manualSave } = useAutoSave();

	const [sidebarWidth, setSidebarWidth] = useState(256); // 256px = w-64
	const [sidebarVisible, setSidebarVisible] = useState(true);
	const [isResizing, setIsResizing] = useState(false);
	const [isResizingTerminal, setIsResizingTerminal] = useState(false);
	const sidebarRef = useRef<HTMLDivElement>(null);
	const editorRef = useRef<HTMLDivElement>(null);

	// Register Cmd+B to toggle sidebar
	useCmdCtrlShortcut("toggle-sidebar", "b", () => {
		setSidebarVisible((prev) => !prev);
	});

	// Listen for run-editor-file event and trigger execution
	useEffect(() => {
		const handleRunEvent = () => {
			// Switch to Run panel and make sidebar visible
			setSidebarPanel("run");
			setSidebarVisible(true);

			// Dispatch a secondary event after a delay to trigger actual execution
			// This ensures the RunPanel has mounted and is ready
			setTimeout(() => {
				const executeEvent = new CustomEvent("execute-editor-file");
				window.dispatchEvent(executeEvent);
			}, 200);
		};

		window.addEventListener("run-editor-file", handleRunEvent);
		return () => {
			window.removeEventListener("run-editor-file", handleRunEvent);
		};
	}, [setSidebarPanel]);

	const handleMouseDown = useCallback((e: React.MouseEvent) => {
		e.preventDefault();
		setIsResizing(true);
	}, []);

	const handleMouseMove = useCallback(
		(e: MouseEvent) => {
			if (!isResizing) return;

			const newWidth = e.clientX - 48; // 48px for the left sidebar
			// Constrain between 150px and 600px
			const constrainedWidth = Math.max(150, Math.min(600, newWidth));
			setSidebarWidth(constrainedWidth);
		},
		[isResizing],
	);

	const handleMouseUp = useCallback(() => {
		setIsResizing(false);
	}, []);

	// Terminal resize handlers
	const handleTerminalMouseDown = useCallback((e: React.MouseEvent) => {
		e.preventDefault();
		setIsResizingTerminal(true);
	}, []);

	const handleTerminalMouseMove = useCallback(
		(e: MouseEvent) => {
			if (!isResizingTerminal || !editorRef.current) return;

			const editorRect = editorRef.current.getBoundingClientRect();
			const newHeight = editorRect.bottom - e.clientY;
			// Constrain between 100px and 600px
			const constrainedHeight = Math.max(100, Math.min(600, newHeight));
			setTerminalHeight(constrainedHeight);
		},
		[isResizingTerminal, setTerminalHeight],
	);

	const handleTerminalMouseUp = useCallback(() => {
		setIsResizingTerminal(false);
	}, []);

	// Add/remove event listeners for resizing
	useEffect(() => {
		if (isResizing) {
			document.addEventListener("mousemove", handleMouseMove);
			document.addEventListener("mouseup", handleMouseUp);
			return () => {
				document.removeEventListener("mousemove", handleMouseMove);
				document.removeEventListener("mouseup", handleMouseUp);
			};
		}
		return undefined;
	}, [isResizing, handleMouseMove, handleMouseUp]);

	// Add/remove event listeners for terminal resizing
	useEffect(() => {
		if (isResizingTerminal) {
			document.addEventListener("mousemove", handleTerminalMouseMove);
			document.addEventListener("mouseup", handleTerminalMouseUp);
			return () => {
				document.removeEventListener(
					"mousemove",
					handleTerminalMouseMove,
				);
				document.removeEventListener("mouseup", handleTerminalMouseUp);
			};
		}
		return undefined;
	}, [isResizingTerminal, handleTerminalMouseMove, handleTerminalMouseUp]);

	// Get label for minimized bar
	const getMinimizedLabel = () => {
		if (openFile) {
			return openFile.name;
		}
		if (sidebarPanel === "files") return "File Browser";
		if (sidebarPanel === "search") return "Search";
		if (sidebarPanel === "sourceControl") return "Source Control";
		if (sidebarPanel === "run") return "Execute";
		if (sidebarPanel === "packages") return "Packages";
		return "Editor";
	};

	// If minimized, show docked bar
	if (layoutMode === "minimized") {
		return (
			<div className="fixed bottom-4 right-4 z-50">
				<button
					onClick={restoreEditor}
					className="flex items-center gap-2 rounded-lg border bg-background px-4 py-2 shadow-lg hover:bg-muted transition-colors"
				>
					<Maximize2 className="h-4 w-4" />
					<span className="text-sm font-medium">
						{getMinimizedLabel()}
					</span>
				</button>
			</div>
		);
	}

	return (
		<UploadProgressProvider>
			<div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
				{/* Top bar with close button */}
				<div className="flex h-10 items-center justify-between border-b bg-muted/30 px-3">
					<div className="flex items-center gap-2">
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6"
							onClick={() => setSidebarVisible(!sidebarVisible)}
							title={`${
								sidebarVisible ? "Hide" : "Show"
							} Sidebar (Cmd+B)`}
						>
							{sidebarVisible ? (
								<PanelLeftClose className="h-4 w-4" />
							) : (
								<PanelLeft className="h-4 w-4" />
							)}
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6"
							onClick={manualSave}
							disabled={!unsavedChanges || saveState === "saving"}
							title="Save (Cmd+S)"
						>
							<Save className="h-4 w-4" />
						</Button>
						{openFile && (
							<span className="text-sm">{openFile.path}</span>
						)}
					</div>
					<div className="flex gap-1">
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6"
							onClick={minimizeEditor}
							title="Minimize"
						>
							<Minus className="h-3 w-3" />
						</Button>
						<Button
							variant="ghost"
							size="icon"
							className="h-6 w-6"
							onClick={() => closeEditor()}
							title="Close"
						>
							<X className="h-3 w-3" />
						</Button>
					</div>
				</div>

				{/* Main content area */}
				<div className="flex flex-1 overflow-hidden">
					{/* Left sidebar with icon navigation */}
					{sidebarVisible && <Sidebar />}

					{/* Panel content area */}
					{sidebarVisible && (
						<div
							ref={sidebarRef}
							className="flex flex-col overflow-hidden border-r relative"
							style={{ width: `${sidebarWidth}px` }}
						>
							<div className="flex-1 overflow-hidden">
								{sidebarPanel === "files" && <FileTree />}
								{sidebarPanel === "search" && <SearchPanel />}
								{sidebarPanel === "sourceControl" && (
									<SourceControlPanel />
								)}
								{sidebarPanel === "run" && <RunPanel />}
								{sidebarPanel === "packages" && (
									<PackagePanel />
								)}
							</div>

							{/* Resize handle */}
							<div
								className="absolute top-0 right-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 active:bg-primary transition-colors"
								onMouseDown={handleMouseDown}
								style={{
									cursor: isResizing
										? "col-resize"
										: "col-resize",
								}}
							/>
						</div>
					)}

					{/* Editor area with tabs and terminal */}
					<div
						className="flex flex-1 flex-col overflow-hidden"
						ref={editorRef}
					>
						{/* File tabs */}
						<FileTabs />

						{/* Editor */}
						<div className="flex-1 overflow-hidden">
							<CodeEditor />
						</div>

						{/* Terminal area (resizable, under editor only) */}
						<div
							className="border-t overflow-hidden"
							style={{ height: `${terminalHeight}px` }}
						>
							<TerminalPanel
								onResizeStart={handleTerminalMouseDown}
							/>
						</div>
					</div>
				</div>

				{/* Status bar (includes upload progress) */}
				<StatusBar />
			</div>
		</UploadProgressProvider>
	);
}
