import { useState, useCallback } from "react";
import {
	Search,
	Loader2,
	X,
	CaseSensitive,
	Regex as RegexIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	searchService,
	type SearchResponse,
	type SearchResult,
} from "@/services/searchService";
import { fileService } from "@/services/fileService";
import { toast } from "sonner";
import { useEditorStore } from "@/stores/editorStore";
import { cn } from "@/lib/utils";

/**
 * Search Panel Component
 * VS Code-style file content search with results list
 */
export function SearchPanel() {
	const [query, setQuery] = useState("");
	const [caseSensitive, setCaseSensitive] = useState(false);
	const [useRegex, setUseRegex] = useState(false);
	const [isSearching, setIsSearching] = useState(false);
	const [searchResults, setSearchResults] = useState<SearchResponse | null>(
		null,
	);

	const { setOpenFile, setLoadingFile } = useEditorStore();

	const handleSearch = useCallback(async () => {
		if (!query.trim()) {
			toast.error("Please enter a search query");
			return;
		}

		setIsSearching(true);
		try {
			const response = await searchService.searchFiles({
				query: query.trim(),
				case_sensitive: caseSensitive,
				is_regex: useRegex,
				include_pattern: "**/*",
				max_results: 1000,
			});

			setSearchResults(response);

			if (response.total_matches === 0) {
				toast.info("No matches found");
			} else {
				toast.success(
					`Found ${response.total_matches} match${
						response.total_matches === 1 ? "" : "es"
					} in ${response.files_searched} file${
						response.files_searched === 1 ? "" : "s"
					}`,
				);
			}
		} catch (err) {
			toast.error(
				err instanceof Error ? err.message : "Failed to search files",
			);
		} finally {
			setIsSearching(false);
		}
	}, [query, caseSensitive, useRegex]);

	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "Enter" && !isSearching) {
				handleSearch();
			}
		},
		[handleSearch, isSearching],
	);

	const handleResultClick = useCallback(
		async (result: SearchResult) => {
			// Open file in editor (same as FileTree does it)
			try {
				setLoadingFile(true);
				const response = await fileService.readFile(result.file_path);
				setOpenFile(
					{
						path: result.file_path,
						name:
							result.file_path.split("/").pop() ||
							result.file_path,
						type: "file" as const,
						size: response.size,
						extension: result.file_path.includes(".")
							? result.file_path.substring(
									result.file_path.lastIndexOf("."),
								)
							: null,
						modified: response.modified,
						is_workflow: false,
						is_data_provider: false,
					},
					response.content,
					response.encoding as "utf-8" | "base64",
				);
			} catch {
				toast.error("Failed to open file");
				setLoadingFile(false);
			}
		},
		[setOpenFile, setLoadingFile],
	);

	const handleClear = useCallback(() => {
		setQuery("");
		setSearchResults(null);
	}, []);

	return (
		<div className="flex h-full flex-col">
			{/* Search input and options */}
			<div className="border-b p-3 space-y-2">
				<div className="relative">
					<Input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						onKeyDown={handleKeyDown}
						placeholder="Search..."
						className="pr-20"
						disabled={isSearching}
					/>
					<div className="absolute right-1 top-1 flex gap-1">
						{query && (
							<Button
								variant="ghost"
								size="icon"
								className="h-7 w-7"
								onClick={handleClear}
								title="Clear"
							>
								<X className="h-3 w-3" />
							</Button>
						)}
						<Button
							variant="ghost"
							size="icon"
							className="h-7 w-7"
							onClick={handleSearch}
							disabled={isSearching || !query.trim()}
							title="Search"
						>
							{isSearching ? (
								<Loader2 className="h-3 w-3 animate-spin" />
							) : (
								<Search className="h-3 w-3" />
							)}
						</Button>
					</div>
				</div>

				{/* Search options */}
				<div className="flex gap-1">
					<Button
						variant={caseSensitive ? "secondary" : "ghost"}
						size="sm"
						className={cn("h-7", caseSensitive && "bg-primary/20")}
						onClick={() => setCaseSensitive(!caseSensitive)}
						title="Match Case"
					>
						<CaseSensitive className="h-3 w-3 mr-1" />
						Aa
					</Button>
					<Button
						variant={useRegex ? "secondary" : "ghost"}
						size="sm"
						className={cn("h-7", useRegex && "bg-primary/20")}
						onClick={() => setUseRegex(!useRegex)}
						title="Use Regular Expression"
					>
						<RegexIcon className="h-3 w-3 mr-1" />
						.*
					</Button>
				</div>

				{/* Search stats */}
				{searchResults && (
					<div className="text-xs text-muted-foreground">
						{searchResults.total_matches}{" "}
						{searchResults.total_matches === 1
							? "result"
							: "results"}{" "}
						in {searchResults.files_searched}{" "}
						{searchResults.files_searched === 1 ? "file" : "files"}
						{searchResults.truncated && " (truncated)"}
					</div>
				)}
			</div>

			{/* Results list */}
			<div className="flex-1 overflow-y-auto">
				{searchResults && searchResults.results.length > 0 ? (
					<div className="divide-y">
						{searchResults.results.map(
							(result: SearchResult, index: number) => (
								<SearchResultItem
									key={`${result.file_path}-${result.line}-${index}`}
									result={result}
									query={query}
									onClick={() => handleResultClick(result)}
								/>
							),
						)}
					</div>
				) : searchResults && searchResults.results.length === 0 ? (
					<div className="flex h-full items-center justify-center p-4 text-sm text-muted-foreground">
						No matches found for "{query}"
					</div>
				) : (
					<div className="flex h-full items-center justify-center p-4 text-sm text-muted-foreground">
						Enter a query to search files
					</div>
				)}
			</div>
		</div>
	);
}

/**
 * Individual search result item
 */
function SearchResultItem({
	result,
	query,
	onClick,
}: {
	result: SearchResult;
	query: string;
	onClick: () => void;
}) {
	// Highlight the matched text
	const highlightMatch = (text: string) => {
		if (!query) return text;

		const parts = text.split(new RegExp(`(${query})`, "gi"));
		return (
			<span>
				{parts.map((part, i) =>
					part.toLowerCase() === query.toLowerCase() ? (
						<mark
							key={i}
							className="bg-yellow-200/50 dark:bg-yellow-900/50"
						>
							{part}
						</mark>
					) : (
						<span key={i}>{part}</span>
					),
				)}
			</span>
		);
	};

	return (
		<button
			onClick={onClick}
			className="w-full text-left p-2 hover:bg-muted/50 transition-colors focus:bg-muted/70 focus:outline-none"
		>
			<div className="text-xs text-muted-foreground truncate mb-1">
				{result.file_path}:{result.line}
			</div>
			<div className="text-sm font-mono truncate">
				{highlightMatch(result.match_text)}
			</div>
		</button>
	);
}
