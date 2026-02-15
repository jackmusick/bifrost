/**
 * JSX Page Renderer
 *
 * Renders a single JSX page file by:
 * 1. Extracting custom component references from source
 * 2. Resolving those components from the API
 * 3. Creating and rendering the page component
 */

import React, { useEffect, useState, useMemo } from "react";
import { createComponent } from "@/lib/app-code-runtime";
import {
	resolveAppComponentsFromFiles,
	extractComponentNames,
} from "@/lib/app-code-resolver";
import type { AppCodeFile } from "@/lib/app-code-router";
import { Skeleton } from "@/components/ui/skeleton";
import { JsxErrorBoundary } from "./JsxErrorBoundary";

interface JsxPageRendererProps {
	/** Application ID */
	appId: string;
	/** The app code file to render */
	file: AppCodeFile;
	/** Set of component names that exist as user files in components/ */
	userComponentNames: Set<string>;
	/** All pre-loaded files (for resolving components without API calls) */
	allFiles?: AppCodeFile[];
}

/**
 * Loading skeleton for page content
 */
function PageSkeleton() {
	return (
		<div className="p-6 space-y-4">
			<Skeleton className="h-8 w-48" />
			<Skeleton className="h-4 w-full max-w-md" />
			<div className="space-y-2 pt-4">
				<Skeleton className="h-32 w-full" />
				<Skeleton className="h-32 w-full" />
			</div>
		</div>
	);
}

/**
 * Error display for page loading failures
 */
function PageError({
	error,
	filePath,
}: {
	error: string;
	filePath: string;
}) {
	return (
		<div className="p-6 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg m-4">
			<h2 className="text-lg font-semibold text-red-700 dark:text-red-400">
				Page Error
			</h2>
			<p className="text-red-600 dark:text-red-300 mt-1 text-sm">
				Failed to load {filePath}
			</p>
			<pre className="mt-3 p-3 bg-red-100 dark:bg-red-900/30 rounded text-sm text-red-800 dark:text-red-200 overflow-auto">
				{error}
			</pre>
		</div>
	);
}

/**
 * Renders a JSX page file
 *
 * This component:
 * 1. Extracts component names from the page source
 * 2. Filters to only custom (non-built-in) components
 * 3. Resolves custom components from the API
 * 4. Creates the page component with scope injection
 * 5. Renders the component within an error boundary
 */
export function JsxPageRenderer({
	appId,
	file,
	userComponentNames,
	allFiles,
}: JsxPageRendererProps) {
	const [PageComponent, setPageComponent] =
		useState<React.ComponentType | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	// Compilation is 100% client-side now
	const source = useMemo(() => file.source, [file.source]);

	useEffect(() => {
		let cancelled = false;

		async function loadPage() {
			setIsLoading(true);
			setError(null);

			try {
				// Extract component names from source
				const componentNames = extractComponentNames(file.source);

				// Resolve only components that exist as user files
				// (userComponentNames is the authoritative list from the files API)
				let customComponents: Record<string, React.ComponentType> = {};
				if (componentNames.length > 0) {
					customComponents = await resolveAppComponentsFromFiles(
						appId,
						componentNames,
						userComponentNames,
						allFiles,
					);
				}

				if (cancelled) return;

				// Use compiled code when available, skip client-side compilation
				const Component = createComponent(
					file.compiled || source,
					customComponents,
					!!file.compiled,
				);

				setPageComponent(() => Component);
			} catch (err) {
				if (cancelled) return;
				setError(
					err instanceof Error ? err.message : "Failed to load page",
				);
			} finally {
				if (!cancelled) {
					setIsLoading(false);
				}
			}
		}

		loadPage();

		return () => {
			cancelled = true;
		};
	}, [appId, userComponentNames, file.path, file.source, file.compiled, source]);

	if (isLoading) {
		return <PageSkeleton />;
	}

	if (error) {
		return <PageError error={error} filePath={file.path} />;
	}

	if (!PageComponent) {
		return null;
	}

	return (
		<JsxErrorBoundary filePath={file.path} resetKey={file.source}>
			<PageComponent />
		</JsxErrorBoundary>
	);
}
