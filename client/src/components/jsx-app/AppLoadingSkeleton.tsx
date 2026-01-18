/**
 * App Loading Skeleton
 *
 * A visually rich loading state that resembles an application structure.
 * Shows a sidebar and main content area skeleton to give users immediate
 * visual feedback while the app is loading.
 */

import { Skeleton } from "@/components/ui/skeleton";

interface AppLoadingSkeletonProps {
	/** Optional message to show below the skeleton */
	message?: string;
}

/**
 * Full-page app loading skeleton
 *
 * Renders a professional-looking skeleton that mimics a typical app layout
 * with a sidebar and main content area. This provides immediate visual
 * feedback while the actual app files are being fetched and compiled.
 */
export function AppLoadingSkeleton({
	message = "Loading application...",
}: AppLoadingSkeletonProps) {
	return (
		<div className="h-full w-full flex flex-col bg-background">
			{/* Main layout with sidebar and content */}
			<div className="flex-1 flex min-h-0">
				{/* Sidebar skeleton */}
				<aside className="w-64 border-r bg-card flex flex-col shrink-0">
					{/* Logo/Brand area */}
					<div className="p-4 border-b">
						<div className="flex items-center gap-3">
							<Skeleton className="h-10 w-10 rounded-lg" />
							<div className="flex-1">
								<Skeleton className="h-4 w-24 mb-1.5" />
								<Skeleton className="h-3 w-16" />
							</div>
						</div>
					</div>

					{/* Navigation items */}
					<nav className="flex-1 p-3 space-y-1">
						{[...Array(5)].map((_, i) => (
							<div
								key={i}
								className="flex items-center gap-3 px-3 py-2.5 rounded-md"
							>
								<Skeleton className="h-4 w-4 rounded" />
								<Skeleton
									className="h-3.5"
									style={{
										width: `${60 + Math.random() * 40}px`,
									}}
								/>
							</div>
						))}
					</nav>

					{/* Bottom section */}
					<div className="p-4 border-t">
						<Skeleton className="h-16 w-full rounded-lg" />
					</div>
				</aside>

				{/* Main content skeleton */}
				<main className="flex-1 min-w-0 p-6 overflow-hidden">
					{/* Page header */}
					<div className="mb-6">
						<Skeleton className="h-8 w-48 mb-2" />
						<Skeleton className="h-4 w-72" />
					</div>

					{/* Stats row */}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
						{[...Array(3)].map((_, i) => (
							<div
								key={i}
								className="bg-card border rounded-lg p-4"
							>
								<div className="flex items-center gap-3">
									<Skeleton className="h-10 w-10 rounded-lg" />
									<div className="flex-1">
										<Skeleton className="h-6 w-16 mb-1" />
										<Skeleton className="h-3 w-20" />
									</div>
								</div>
							</div>
						))}
					</div>

					{/* Content area */}
					<div className="bg-card border rounded-lg">
						{/* Card header */}
						<div className="p-4 border-b">
							<div className="flex items-center justify-between">
								<div>
									<Skeleton className="h-5 w-24 mb-1" />
									<Skeleton className="h-3 w-16" />
								</div>
								<Skeleton className="h-9 w-24 rounded-md" />
							</div>
						</div>

						{/* List items */}
						<div className="divide-y">
							{[...Array(4)].map((_, i) => (
								<div
									key={i}
									className="p-4 flex items-center gap-4"
								>
									<Skeleton className="h-5 w-5 rounded" />
									<div className="flex-1 min-w-0">
										<Skeleton className="h-4 w-3/4 mb-1.5" />
										<Skeleton className="h-3 w-1/2" />
									</div>
									<Skeleton className="h-6 w-16 rounded-full" />
								</div>
							))}
						</div>
					</div>
				</main>
			</div>

			{/* Loading indicator overlay */}
			<div className="absolute inset-0 flex items-center justify-center pointer-events-none">
				<div className="bg-background/90 backdrop-blur-sm rounded-lg px-6 py-4 shadow-lg flex items-center gap-3">
					<div className="relative">
						<div className="h-5 w-5 rounded-full border-2 border-primary/30" />
						<div className="absolute inset-0 h-5 w-5 rounded-full border-2 border-transparent border-t-primary animate-spin" />
					</div>
					<span className="text-sm text-muted-foreground">
						{message}
					</span>
				</div>
			</div>
		</div>
	);
}
