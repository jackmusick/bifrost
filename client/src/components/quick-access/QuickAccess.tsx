import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileText, Workflow, FileCode, Loader2 } from "lucide-react";
import { useEditorStore } from "@/stores/editorStore";
import { useForms } from "@/hooks/useForms";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { fileService } from "@/services/fileService";
import {
	searchService,
	type SearchResult as ApiSearchResult,
} from "@/services/searchService";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

interface SearchResult {
	type: "form" | "workflow" | "script";
	name: string;
	description: string;
	path?: string;
	id?: string;
}

interface QuickAccessProps {
	isOpen: boolean;
	onClose: () => void;
}

/**
 * Quick access command palette (Cmd+K)
 * Search and navigate to forms, workflows, and scripts
 */
export function QuickAccess({ isOpen, onClose }: QuickAccessProps) {
	const navigate = useNavigate();
	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const openEditor = useEditorStore((state) => state.openEditor);
	const setSidebarPanel = useEditorStore((state) => state.setSidebarPanel);

	const [query, setQuery] = useState("");
	const [selectedIndex, setSelectedIndex] = useState(0);
	const [results, setResults] = useState<SearchResult[]>([]);
	const [isSearching, setIsSearching] = useState(false);
	const inputRef = useRef<HTMLInputElement>(null);
	const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
	const resultsRef = useRef<(HTMLButtonElement | null)[]>([]);

	const { data: formsData } = useForms();
	const { data: workflowsData } = useWorkflowsMetadata();

	// Focus input when opened
	useEffect(() => {
		if (isOpen && inputRef.current) {
			inputRef.current.focus();
		}
	}, [isOpen]);

	// Search function
	const performSearch = useCallback(
		async (searchQuery: string) => {
			if (!searchQuery.trim()) {
				setResults([]);
				return;
			}

			setIsSearching(true);
			const queryLower = searchQuery.toLowerCase();
			const allResults: SearchResult[] = [];

			// Search forms by name - formsData is the array directly, not wrapped in an object
			if (formsData && Array.isArray(formsData)) {
				const formResults = formsData
					.filter(
						(form) =>
							form.name?.toLowerCase().includes(queryLower) ||
							form.description
								?.toLowerCase()
								.includes(queryLower),
					)
					.map((form) => ({
						type: "form" as const,
						name: form.name || "Untitled Form",
						description: form.description || "",
						id: form.id,
					}));
				allResults.push(...formResults);
			}

			// Search workflows by name
			if (workflowsData?.workflows) {
				const workflowResults = workflowsData.workflows
					.filter(
						(workflow: WorkflowMetadata) =>
							workflow.name?.toLowerCase().includes(queryLower) ||
							workflow.description
								?.toLowerCase()
								.includes(queryLower),
					)
					.map((workflow: WorkflowMetadata) => ({
						type: "workflow" as const,
						name: workflow.name || "Untitled Workflow",
						description: workflow.description || "",
					}));
				allResults.push(...workflowResults);
			}

			// Search scripts by filename and content
			try {
				const scriptsResponse = await searchService.searchFiles({
					query: searchQuery,
					case_sensitive: false,
					is_regex: false,
					include_pattern: "**/*",
					max_results: 50,
				});

				const scriptResults = scriptsResponse.results.map(
					(result: ApiSearchResult) => ({
						type: "script" as const,
						name:
							result.file_path.split("/").pop() ||
							result.file_path,
						description: result.match_text
							? `Line ${result.line}: ${result.match_text.trim()}`
							: "",
						path: result.file_path,
					}),
				);
				allResults.push(...scriptResults);
			} catch {
				// Silently handle file search error
			}

			setResults(allResults);
			setSelectedIndex(0);
			setIsSearching(false);
		},
		[formsData, workflowsData],
	);

	// Debounced search
	useEffect(() => {
		if (searchTimeoutRef.current) {
			clearTimeout(searchTimeoutRef.current);
		}

		searchTimeoutRef.current = setTimeout(() => {
			performSearch(query);
		}, 300); // 300ms debounce

		return () => {
			if (searchTimeoutRef.current) {
				clearTimeout(searchTimeoutRef.current);
			}
		};
	}, [query, performSearch]);

	// Handle selection
	const handleSelect = useCallback(
		async (result: SearchResult) => {
			onClose();
			setQuery("");
			setResults([]);

			if (result.type === "form") {
				navigate(`/execute/${result.id}`);
			} else if (result.type === "workflow") {
				navigate(`/workflows/${result.name}/execute`);
			} else if (result.type === "script" && result.path) {
				// Open script in editor
				try {
					const fileResponse = await fileService.readFile(
						result.path,
					);
					const fileName =
						result.path.split("/").pop() || result.path;
					openEditor();
					openFileInTab(
						{
							name: fileName,
							path: result.path,
							type: "file",
							size: fileResponse.content.length,
							extension: fileName.includes(".")
								? fileName.split(".").pop() || null
								: null,
							modified: new Date().toISOString(),
							isReadOnly: false,
						},
						fileResponse.content,
						fileResponse.encoding as "utf-8" | "base64",
					);
					// Switch to Run panel if it's a Python file
					if (fileName.endsWith(".py")) {
						setSidebarPanel("run");
					}
				} catch {
					// Silently handle file open error
				}
			}
		},
		[navigate, onClose, openEditor, openFileInTab, setSidebarPanel],
	);

	// Scroll selected item into view
	useEffect(() => {
		if (resultsRef.current[selectedIndex]) {
			resultsRef.current[selectedIndex]?.scrollIntoView({
				block: "nearest",
				behavior: "smooth",
			});
		}
	}, [selectedIndex]);

	// Keyboard navigation
	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "ArrowDown") {
				e.preventDefault();
				setSelectedIndex((prev) =>
					Math.min(prev + 1, results.length - 1),
				);
			} else if (e.key === "ArrowUp") {
				e.preventDefault();
				setSelectedIndex((prev) => Math.max(prev - 1, 0));
			} else if (e.key === "Enter" && results[selectedIndex]) {
				e.preventDefault();
				handleSelect(results[selectedIndex]);
			} else if (e.key === "Escape") {
				e.preventDefault();
				onClose();
			}
		},
		[results, selectedIndex, handleSelect, onClose],
	);

	// Get icon for result type
	const getIcon = (type: SearchResult["type"]) => {
		switch (type) {
			case "form":
				return <FileText className="h-4 w-4" />;
			case "workflow":
				return <Workflow className="h-4 w-4" />;
			case "script":
				return <FileCode className="h-4 w-4" />;
		}
	};

	if (!isOpen) return null;

	return (
		<>
			{/* Backdrop */}
			<div
				className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] animate-in fade-in duration-200"
				onClick={onClose}
			/>

			{/* Modal */}
			<div className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-2xl z-[60] animate-in fade-in zoom-in-95 duration-200">
				<div className="bg-background border shadow-2xl rounded-lg overflow-hidden">
					{/* Search input */}
					<div className="flex items-center gap-3 px-4 py-3 border-b">
						<Search className="h-5 w-5 text-muted-foreground" />
						<input
							ref={inputRef}
							type="text"
							placeholder="Search forms, workflows, and scripts..."
							value={query}
							onChange={(e) => setQuery(e.target.value)}
							onKeyDown={handleKeyDown}
							className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
						/>
						{isSearching && (
							<Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
						)}
					</div>

					{/* Results */}
					<div className="max-h-[400px] overflow-auto">
						{results.length === 0 &&
							query.trim() !== "" &&
							!isSearching && (
								<div className="px-4 py-8 text-center text-sm text-muted-foreground">
									No results found
								</div>
							)}

						{results.length === 0 && query.trim() === "" && (
							<div className="px-4 py-8 text-center">
								<Search className="h-12 w-12 mx-auto mb-3 text-muted-foreground/50" />
								<p className="text-sm text-muted-foreground">
									Search for forms, workflows, and scripts
								</p>
								<p className="text-xs text-muted-foreground mt-2">
									Use ↑↓ to navigate, Enter to select, Esc to
									close
								</p>
							</div>
						)}

						{results.map((result, index) => (
							<button
								key={`${result.type}-${result.name}-${index}`}
								ref={(el) => {
									resultsRef.current[index] = el;
								}}
								onClick={() => handleSelect(result)}
								className={`w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors ${
									index === selectedIndex ? "bg-muted" : ""
								}`}
							>
								<div className="mt-0.5">
									{getIcon(result.type)}
								</div>
								<div className="flex-1 min-w-0">
									<div className="flex items-center gap-2">
										<span className="font-medium text-sm">
											{result.name}
										</span>
										<span className="text-xs text-muted-foreground capitalize">
											{result.type}
										</span>
									</div>
									{result.description && (
										<p className="text-xs text-muted-foreground mt-1 truncate">
											{result.description}
										</p>
									)}
								</div>
							</button>
						))}
					</div>

					{/* Footer hint */}
					{results.length > 0 && (
						<div className="px-4 py-2 border-t bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
							<span>↑↓ to navigate</span>
							<span>Enter to select</span>
							<span>Esc to close</span>
						</div>
					)}
				</div>
			</div>
		</>
	);
}
