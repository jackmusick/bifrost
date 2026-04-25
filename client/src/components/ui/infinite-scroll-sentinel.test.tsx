/**
 * Tests for InfiniteScrollSentinel.
 *
 * jsdom does not implement IntersectionObserver, so we patch a minimal mock
 * onto the global object that exposes `trigger()` for tests. The real browser
 * runtime is exercised via the AgentRunsTab Playwright suite.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { InfiniteScrollSentinel } from "./infinite-scroll-sentinel";

type Observer = {
	callback: IntersectionObserverCallback;
	elements: Element[];
	trigger: (isIntersecting: boolean) => void;
};

let observers: Observer[] = [];

class MockIntersectionObserver implements IntersectionObserver {
	root: Element | Document | null = null;
	rootMargin = "";
	thresholds: ReadonlyArray<number> = [];
	private _observer: Observer;

	constructor(callback: IntersectionObserverCallback) {
		const observer: Observer = {
			callback,
			elements: [],
			trigger: (isIntersecting: boolean) => {
				const entries = observer.elements.map(
					(el) =>
						({
							target: el,
							isIntersecting,
							intersectionRatio: isIntersecting ? 1 : 0,
							boundingClientRect: {} as DOMRectReadOnly,
							intersectionRect: {} as DOMRectReadOnly,
							rootBounds: null,
							time: 0,
						}) as IntersectionObserverEntry,
				);
				callback(entries, this);
			},
		};
		this._observer = observer;
		observers.push(observer);
	}

	observe(target: Element): void {
		this._observer.elements.push(target);
	}
	unobserve(): void {}
	disconnect(): void {
		this._observer.elements = [];
	}
	takeRecords(): IntersectionObserverEntry[] {
		return [];
	}
}

beforeEach(() => {
	observers = [];
	(globalThis as unknown as { IntersectionObserver: typeof MockIntersectionObserver }).IntersectionObserver = MockIntersectionObserver;
});

afterEach(() => {
	cleanup();
});

describe("InfiniteScrollSentinel", () => {
	it("renders nothing when hasNext is false", () => {
		const { container } = render(
			<InfiniteScrollSentinel
				hasNext={false}
				isLoading={false}
				onLoadMore={() => {}}
			/>,
		);
		expect(container.querySelector("[data-testid]")).toBeNull();
	});

	it("calls onLoadMore when the sentinel intersects", () => {
		const onLoadMore = vi.fn();
		render(
			<InfiniteScrollSentinel
				hasNext={true}
				isLoading={false}
				onLoadMore={onLoadMore}
			/>,
		);
		expect(observers).toHaveLength(1);
		observers[0].trigger(true);
		expect(onLoadMore).toHaveBeenCalledTimes(1);
	});

	it("does not call onLoadMore while isLoading is true", () => {
		const onLoadMore = vi.fn();
		render(
			<InfiniteScrollSentinel
				hasNext={true}
				isLoading={true}
				onLoadMore={onLoadMore}
			/>,
		);
		observers[0].trigger(true);
		expect(onLoadMore).not.toHaveBeenCalled();
	});

	it("does not call onLoadMore on non-intersecting entries", () => {
		const onLoadMore = vi.fn();
		render(
			<InfiniteScrollSentinel
				hasNext={true}
				isLoading={false}
				onLoadMore={onLoadMore}
			/>,
		);
		observers[0].trigger(false);
		expect(onLoadMore).not.toHaveBeenCalled();
	});
});
