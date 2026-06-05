/**
 * Dependency Panel
 *
 * Manages npm dependencies for an app. Provides search, add, remove,
 * and version editing. Displayed in the left sidebar of the editor.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, X, Package, Loader2 } from "lucide-react";
import { useAppDependencies } from "@/hooks/useAppDependencies";
import { searchNpmPackages, type NpmPackageResult } from "@/lib/npm-search";

interface DependencyPanelProps {
	appId: string;
	/** Solution-managed app: deps are read-only (view, no add/remove). */
	readOnly?: boolean;
}

export function DependencyPanel({ appId, readOnly = false }: DependencyPanelProps) {
	const {
		dependencies,
		isLoading,
		isSaving,
		addDependency,
		removeDependency,
	} = useAppDependencies(appId);

	const [searchQuery, setSearchQuery] = useState("");
	const [searchResults, setSearchResults] = useState<NpmPackageResult[]>([]);
	const [isSearching, setIsSearching] = useState(false);
	const [showResults, setShowResults] = useState(false);
	const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const abortRef = useRef<AbortController | null>(null);
	const panelRef = useRef<HTMLDivElement>(null);

	// Debounced search
	const handleSearchChange = useCallback((value: string) => {
		setSearchQuery(value);

		if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
		if (abortRef.current) abortRef.current.abort();

		if (!value.trim()) {
			setSearchResults([]);
			setShowResults(false);
			return;
		}

		searchTimerRef.current = setTimeout(async () => {
			setIsSearching(true);
			const controller = new AbortController();
			abortRef.current = controller;

			try {
				const results = await searchNpmPackages(
					value,
					8,
					controller.signal,
				);
				setSearchResults(results);
				setShowResults(true);
			} catch {
				// Abort or network error — ignore
			} finally {
				setIsSearching(false);
			}
		}, 300);
	}, []);

	// Close dropdown when clicking outside
	useEffect(() => {
		function handleClickOutside(e: MouseEvent) {
			if (
				panelRef.current &&
				!panelRef.current.contains(e.target as Node)
			) {
				setShowResults(false);
			}
		}
		document.addEventListener("mousedown", handleClickOutside);
		return () =>
			document.removeEventListener("mousedown", handleClickOutside);
	}, []);

	// Cleanup timer on unmount
	useEffect(() => {
		return () => {
			if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
			if (abortRef.current) abortRef.current.abort();
		};
	}, []);

	const handleAdd = useCallback(
		async (pkg: NpmPackageResult) => {
			setShowResults(false);
			setSearchQuery("");
			setSearchResults([]);
			await addDependency(pkg.name, pkg.version);
		},
		[addDependency],
	);

	const depEntries = Object.entries(dependencies);

	if (isLoading) {
		return (
			<div className="p-3 space-y-3">
				<Skeleton className="h-8 w-full" />
				<Skeleton className="h-6 w-3/4" />
				<Skeleton className="h-6 w-1/2" />
			</div>
		);
	}

	return (
		<div ref={panelRef} className="h-full flex flex-col">
			{/* Search — hidden for solution-managed (read-only) apps */}
			{!readOnly && (
			<div className="p-2 border-b relative">
				<div className="relative">
					<Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
					<Input
						value={searchQuery}
						onChange={(e) => handleSearchChange(e.target.value)}
						placeholder="Search npm packages..."
						className="h-8 pl-8 pr-8 text-sm"
					/>
					{isSearching && (
						<Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
					)}
				</div>

				{/* Search results dropdown */}
				{showResults && searchResults.length > 0 && (
					<div className="absolute left-2 right-2 top-full mt-1 z-50 bg-popover border rounded-md shadow-md max-h-64 overflow-auto">
						{searchResults.map((pkg) => {
							const isInstalled = pkg.name in dependencies;
							return (
								<button
									key={pkg.name}
									className="w-full text-left px-3 py-2 hover:bg-accent text-sm border-b last:border-b-0 disabled:opacity-50"
									onClick={() => handleAdd(pkg)}
									disabled={isInstalled || isSaving}
								>
									<div className="flex items-center justify-between">
										<span className="font-medium truncate">
											{pkg.name}
										</span>
										<span className="text-xs text-muted-foreground ml-2 flex-shrink-0">
											{isInstalled
												? "installed"
												: pkg.version}
										</span>
									</div>
									{pkg.description && (
										<p className="text-xs text-muted-foreground truncate mt-0.5">
											{pkg.description}
										</p>
									)}
								</button>
							);
						})}
					</div>
				)}
			</div>
			)}

			{/* Installed packages */}
			<div className="flex-1 overflow-auto">
				{depEntries.length === 0 ? (
					<div className="p-4 text-center text-sm text-muted-foreground">
						<Package className="h-8 w-8 mx-auto mb-2 opacity-30" />
						<p>No packages installed</p>
						<p className="text-xs mt-1">
							Search above to add npm packages
						</p>
					</div>
				) : (
					<div className="py-1">
						{depEntries.map(([name, version]) => (
							<div
								key={name}
								className="flex items-center justify-between px-3 py-1.5 hover:bg-accent/50 group"
							>
								<div className="min-w-0">
									<div className="text-sm font-medium truncate">
										{name}
									</div>
									<div className="text-xs text-muted-foreground">
										{version}
									</div>
								</div>
								{!readOnly && (
									<Button
										variant="ghost"
										size="icon"
										className="h-6 w-6 opacity-0 group-hover:opacity-100 flex-shrink-0"
										onClick={() => removeDependency(name)}
										disabled={isSaving}
										title={`Remove ${name}`}
									>
										<X className="h-3.5 w-3.5" />
									</Button>
								)}
							</div>
						))}
					</div>
				)}
			</div>

			{/* Footer with count */}
			{depEntries.length > 0 && (
				<div className="px-3 py-1.5 border-t text-xs text-muted-foreground">
					{depEntries.length}/20 packages
					{isSaving && (
						<Loader2 className="inline-block h-3 w-3 animate-spin ml-2" />
					)}
				</div>
			)}
		</div>
	);
}
