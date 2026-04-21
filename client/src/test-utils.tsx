/**
 * Shared test utilities for component tests.
 *
 * The point of this file is to keep per-test boilerplate minimal:
 *   - renderWithProviders wraps in MemoryRouter + a fresh QueryClient
 *   - makeQueryClient is exposed for tests that need to pre-seed cache
 *   - mockAuthFetch gives a typed vi.fn() suitable for stubbing authFetch
 *
 * Usage:
 *   import { renderWithProviders, screen } from "@/test-utils";
 *
 *   const { user } = renderWithProviders(<MyComponent />);
 *   await user.click(screen.getByRole("button", { name: /save/i }));
 *
 * Mocking $api in a sibling test file:
 *   vi.mock("@/lib/api-client", () => ({
 *     $api: {
 *       useQuery: vi.fn(() => ({ data: ..., isLoading: false })),
 *       useMutation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
 *     },
 *     authFetch: vi.fn(),
 *   }));
 */

import { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, RenderOptions, RenderResult } from "@testing-library/react";
import userEvent, { UserEvent } from "@testing-library/user-event";
import { vi } from "vitest";

/**
 * Build a QueryClient tuned for tests: no retries, no background refetch,
 * failures bubble immediately so assertions surface the real error.
 *
 * Exposed separately so individual tests can seed cache with
 * `client.setQueryData(...)` before rendering.
 */
export function makeQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, gcTime: 0, staleTime: 0 },
			mutations: { retry: false },
		},
	});
}

export interface RenderWithProvidersOptions
	extends Omit<RenderOptions, "wrapper"> {
	/** Initial URL entries for MemoryRouter. Defaults to ["/"]. */
	initialEntries?: string[];
	/** Pre-built QueryClient (e.g. with seeded cache). Defaults to makeQueryClient(). */
	queryClient?: QueryClient;
}

export interface RenderWithProvidersResult extends RenderResult {
	/** userEvent instance bound to the rendered document. */
	user: UserEvent;
	/** The QueryClient used for this render, in case tests want to seed cache. */
	queryClient: QueryClient;
}

/**
 * Render a component with the router + react-query providers every Bifrost
 * component expects in production. Returns a `user` from userEvent.setup()
 * so tests don't have to remember to create one.
 */
export function renderWithProviders(
	ui: ReactElement,
	options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
	const {
		initialEntries = ["/"],
		queryClient = makeQueryClient(),
		...rest
	} = options;

	function Wrapper({ children }: { children: ReactNode }) {
		return (
			<QueryClientProvider client={queryClient}>
				<MemoryRouter initialEntries={initialEntries}>
					{children}
				</MemoryRouter>
			</QueryClientProvider>
		);
	}

	const result = render(ui, { wrapper: Wrapper, ...rest });
	return { ...result, user: userEvent.setup(), queryClient };
}

/**
 * Minimal fetch-shaped mock for `authFetch`. Defaults to `{ ok: true, json: () => ({}) }`
 * so components that only check `res.ok` don't blow up. Tests override per-call:
 *
 *   const fetchMock = mockAuthFetch();
 *   fetchMock.mockResolvedValueOnce({
 *     ok: true,
 *     status: 200,
 *     json: async () => ({ data: [...] }),
 *   } as Response);
 *
 * The return value is `vi.fn()`-compatible so `.mockResolvedValueOnce`,
 * `.mockRejectedValueOnce`, `.mockImplementation`, etc. all work.
 */
export function mockAuthFetch() {
	const fn = vi.fn(async (..._args: unknown[]) => ({
		ok: true,
		status: 200,
		headers: new Headers(),
		json: async () => ({}),
		text: async () => "",
	}));
	return fn;
}

// Re-export the testing-library surface so tests only need one import.
export {
	screen,
	within,
	waitFor,
	waitForElementToBeRemoved,
	fireEvent,
	act,
	cleanup,
} from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
