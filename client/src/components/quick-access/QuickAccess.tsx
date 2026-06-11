import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileText, Workflow, FileCode, Loader2 } from "lucide-react";
import { useEditorStore } from "@/stores/editorStore";
import { useAuth } from "@/contexts/AuthContext";
import { useForms } from "@/hooks/useForms";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { fileService } from "@/services/fileService";
import {
	searchService,
	type SearchResult as ApiSearchResult,
} from "@/services/searchService";
import {
	Command,
	CommandDialog,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
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
	const { isPlatformAdmin } = useAuth();
	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const openEditor = useEditorStore((state) => state.openEditor);
	const setSidebarPanel = useEditorStore((state) => state.setSidebarPanel);

	const [query, setQuery] = useState("");
	const [results, setResults] = useState<SearchResult[]>([]);
	const [isSearching, setIsSearching] = useState(false);
	const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

	// Defer data fetching until QuickAccess is actually opened
	const { data: formsData } = useForms(undefined, { enabled: isOpen });
	// Only fetch workflows for platform admins (endpoint requires superuser)
	const { data: workflowsData } = useWorkflowsMetadata({
		enabled: isOpen && isPlatformAdmin,
	});

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
							entity_type: null,
							entity_id: null,
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

	return (
		<CommandDialog
			open={isOpen}
			onOpenChange={(open) => {
				if (!open) onClose();
			}}
			title="Quick access"
			description="Search forms, workflows, and scripts"
			className="sm:max-w-2xl"
		>
			{/* Results come server-ranked; keep their order */}
			<Command shouldFilter={false}>
				<div className="relative">
					<CommandInput
						placeholder="Search forms, workflows, and scripts..."
						value={query}
						onValueChange={setQuery}
					/>
					{isSearching && (
						<Loader2 className="absolute top-1/2 right-4 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
					)}
				</div>

				<CommandList className="max-h-[400px]">
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

					{results.length > 0 && (
						<CommandGroup>
							{results.map((result, index) => (
								<CommandItem
									key={`${result.type}-${result.name}-${index}`}
									value={`${result.type}-${result.name}-${index}`}
									onSelect={() => handleSelect(result)}
									className="items-start gap-3 px-3 py-2.5"
								>
									<div className="mt-0.5 text-muted-foreground">
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
								</CommandItem>
							))}
						</CommandGroup>
					)}
				</CommandList>

				{/* Footer hint */}
				{results.length > 0 && (
					<div className="px-4 py-2 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
						<span>↑↓ to navigate</span>
						<span>Enter to select</span>
						<span>Esc to close</span>
					</div>
				)}
			</Command>
		</CommandDialog>
	);
}
