/**
 * JSX Page Renderer
 *
 * Renders a single JSX page file by:
 * 1. Extracting custom component references from source
 * 2. Resolving those components from the API
 * 3. Creating and rendering the page component
 */

import React, { useEffect, useState, useMemo } from "react";
import { createComponent } from "@/lib/jsx-runtime";
import {
	resolveAppComponents,
	extractComponentNames,
	isBuiltInComponent,
} from "@/lib/jsx-resolver";
import type { JsxFile } from "@/lib/jsx-router";
import { Skeleton } from "@/components/ui/skeleton";
import { JsxErrorBoundary } from "./JsxErrorBoundary";

interface JsxPageRendererProps {
	/** Application ID */
	appId: string;
	/** Version ID (draft or published) */
	versionId: string;
	/** The JSX file to render */
	file: JsxFile;
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
	versionId,
	file,
}: JsxPageRendererProps) {
	const [PageComponent, setPageComponent] =
		useState<React.ComponentType | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);

	// Extract the source to use (prefer compiled if available)
	const { source, useCompiled } = useMemo(() => {
		return {
			source: file.compiled || file.source,
			useCompiled: !!file.compiled,
		};
	}, [file.compiled, file.source]);

	useEffect(() => {
		let cancelled = false;

		async function loadPage() {
			setIsLoading(true);
			setError(null);

			try {
				// Extract component names from the original source (not compiled)
				// since compiled code may have different identifiers
				const componentNames = extractComponentNames(file.source);

				// Filter to only non-built-in components
				const customNames = componentNames.filter(
					(name) => !isBuiltInComponent(name),
				);

				// Resolve custom components from the API
				let customComponents: Record<string, React.ComponentType> = {};
				if (customNames.length > 0) {
					customComponents = await resolveAppComponents(
						appId,
						versionId,
						customNames,
					);
				}

				if (cancelled) return;

				// Create the page component with injected scope
				const Component = createComponent(
					source,
					customComponents,
					useCompiled,
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
	}, [appId, versionId, file.id, file.source, source, useCompiled]);

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
		<JsxErrorBoundary filePath={file.path}>
			<PageComponent />
		</JsxErrorBoundary>
	);
}
