import { useEffect, useRef } from "react";

export interface InfiniteScrollSentinelProps {
	/** Whether another page is available. When false, the sentinel is inert. */
	hasNext: boolean;
	/** True while the next page request is in flight — stops re-triggering. */
	isLoading: boolean;
	/** Called when the sentinel intersects the viewport and `hasNext` is true. */
	onLoadMore: () => void;
	/**
	 * Extra pixels of slack around the viewport before triggering. Positive
	 * values fetch the next page earlier (smoother scroll). Default 200px.
	 */
	rootMargin?: string;
}

/**
 * Invisible sentinel that calls `onLoadMore` when it scrolls into view.
 *
 * Drop at the end of a scrollable list. Using an `IntersectionObserver`
 * is cheaper and less bug-prone than listening to scroll events and
 * recalculating offsets — the observer reports intersections asynchronously
 * and batches them with layout.
 */
export function InfiniteScrollSentinel({
	hasNext,
	isLoading,
	onLoadMore,
	rootMargin = "200px",
}: InfiniteScrollSentinelProps) {
	const ref = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		if (!hasNext) return;
		const el = ref.current;
		if (!el) return;
		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting && !isLoading) {
						onLoadMore();
					}
				}
			},
			{ rootMargin },
		);
		observer.observe(el);
		return () => observer.disconnect();
	}, [hasNext, isLoading, onLoadMore, rootMargin]);

	if (!hasNext) return null;
	return (
		<div
			ref={ref}
			aria-hidden
			data-testid="infinite-scroll-sentinel"
			className="h-px w-full"
		/>
	);
}
