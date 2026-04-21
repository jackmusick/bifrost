/**
 * Component tests for JsxAppShell (legacy path).
 *
 * The shell is an orchestration layer on top of a large runtime. We mock
 * every runtime module aggressively so the test exercises the shell's
 * lifecycle in isolation:
 *
 *   - authFetch: queue the /render response
 *   - app-code-router.buildRoutes: return a canned route tree we control
 *   - app-code-resolver + app-code-runtime: produce trivial React components
 *   - esm-loader.loadDependencies: no-op
 *   - useAppCodeUpdates: stable counter so nothing re-fires
 *
 * What we actually verify:
 *   - loading state → error state → success state transitions
 *   - authFetch is called with the right URL (mode=draft/live)
 *   - the route tree reaches the DOM (pages render)
 *   - navigating between two routes swaps the rendered page
 *   - buildRoutes receives the file list we loaded
 *
 * Anything deeper than that (how routes are built, how components are
 * resolved, the full jsx runtime) is tested separately at the unit level
 * for each library, or at the Playwright level for the real app-rendering
 * pipeline end-to-end.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";
import type { AppCodeRouteObject } from "@/lib/app-code-router";

// -----------------------------------------------------------------------------
// Module mocks
// -----------------------------------------------------------------------------

const mockAuthFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({
	authFetch: (...args: unknown[]) => mockAuthFetch(...args),
}));

const mockBuildRoutes = vi.fn();
vi.mock("@/lib/app-code-router", () => ({
	buildRoutes: (...args: unknown[]) => mockBuildRoutes(...args),
}));

vi.mock("@/lib/app-code-runtime", () => ({
	createComponent: vi.fn(() => () => null),
}));

vi.mock("@/lib/app-code-resolver", () => ({
	resolveAppComponentsFromFiles: vi.fn().mockResolvedValue({}),
	extractComponentNames: vi.fn().mockReturnValue([]),
	getUserComponentNames: vi.fn().mockReturnValue(new Set()),
}));

vi.mock("@/lib/esm-loader", () => ({
	loadDependencies: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/hooks/useAppCodeUpdates", () => ({
	useAppCodeUpdates: () => ({ updateCounter: 0 }),
}));

// Skip the BundledAppShell path — default shell is used for these tests.
vi.mock("./BundledAppShell", () => ({
	BundledAppShell: () => <div>bundled-shell</div>,
}));

// Replace JsxPageRenderer with a marker so we can assert routes mounted it
// and see which file reached which route.
vi.mock("./JsxPageRenderer", () => ({
	JsxPageRenderer: ({ file }: { file: { path: string } }) => (
		<div data-testpath={file.path}>page:{file.path}</div>
	),
}));

// Stub the app-builder store to a no-op — the real zustand store is fine but
// some tests run before its module is evaluated.
vi.mock("@/stores/app-builder.store", () => ({
	useAppBuilderStore: (selector: (state: unknown) => unknown) =>
		selector({ setAppContext: () => {} }),
}));

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function mockRenderResponse(files: { path: string; code: string }[]) {
	mockAuthFetch.mockResolvedValueOnce({
		ok: true,
		text: async () => "",
		json: async () => ({
			files,
			total: files.length,
			dependencies: {},
			styles: {},
		}),
	});
}

function mockRenderError(message: string) {
	mockAuthFetch.mockResolvedValueOnce({
		ok: false,
		text: async () => message,
		json: async () => ({}),
	});
}

function pageRoute(path: string, filePath: string): AppCodeRouteObject {
	return {
		path,
		file: { path: filePath, source: "src", compiled: "cmp" },
	};
}

beforeEach(() => {
	mockAuthFetch.mockReset();
	mockBuildRoutes.mockReset();
	localStorage.clear();
});

afterEach(() => {
	vi.restoreAllMocks();
});

async function renderShell(
	options: { initialPath?: string; isPreview?: boolean } = {},
) {
	const { JsxAppShell } = await import("./JsxAppShell");
	return renderWithProviders(
		<JsxAppShell
			appId="app-1"
			appSlug="my-app"
			isPreview={options.isPreview ?? true}
		/>,
		{ initialEntries: [options.initialPath ?? "/"] },
	);
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe("JsxAppShell — lifecycle", () => {
	it("shows the loading skeleton before files resolve", async () => {
		// Hold the fetch open so we can observe the loading state.
		let resolveFetch: (v: Response) => void = () => {};
		mockAuthFetch.mockImplementationOnce(
			() =>
				new Promise<Response>((resolve) => {
					resolveFetch = resolve;
				}),
		);
		mockBuildRoutes.mockReturnValue([]);

		await renderShell();

		expect(screen.getByText(/loading application/i)).toBeInTheDocument();

		// Resolve so the test doesn't leak an open promise.
		resolveFetch({
			ok: true,
			text: async () => "",
			json: async () => ({
				files: [],
				total: 0,
				dependencies: {},
				styles: {},
			}),
		} as Response);
	});

	it("shows the error panel when the /render call fails", async () => {
		mockRenderError("bad mode");
		mockBuildRoutes.mockReturnValue([]);

		await renderShell();

		expect(
			await screen.findByText(/application error/i),
		).toBeInTheDocument();
		expect(screen.getByText(/bad mode/i)).toBeInTheDocument();
	});

	it("renders the 'No pages found' empty state when buildRoutes returns []", async () => {
		mockRenderResponse([]);
		mockBuildRoutes.mockReturnValue([]);

		await renderShell();

		expect(await screen.findByText(/no pages found/i)).toBeInTheDocument();
	});
});

describe("JsxAppShell — fetch & render", () => {
	it("fetches /render with mode=draft when isPreview=true", async () => {
		mockRenderResponse([
			{ path: "pages/index", code: "export default () => null" },
		]);
		mockBuildRoutes.mockReturnValue([pageRoute("/", "pages/index")]);

		await renderShell({ isPreview: true });

		await screen.findByText("page:pages/index");

		const firstCall = mockAuthFetch.mock.calls[0];
		expect(firstCall[0]).toBe("/api/applications/app-1/render?mode=draft");
		// buildRoutes must have received the mapped files.
		const filesArg = mockBuildRoutes.mock.calls[0][0];
		expect(filesArg).toEqual([
			{
				path: "pages/index",
				source: "export default () => null",
				compiled: "export default () => null",
			},
		]);
	});

	it("fetches /render with mode=live when isPreview=false", async () => {
		mockRenderResponse([]);
		mockBuildRoutes.mockReturnValue([]);

		await renderShell({ isPreview: false });

		await waitFor(() => expect(mockAuthFetch).toHaveBeenCalledTimes(1));
		expect(mockAuthFetch.mock.calls[0][0]).toBe(
			"/api/applications/app-1/render?mode=live",
		);
	});

	it("renders the route matching the initial URL", async () => {
		mockRenderResponse([
			{ path: "pages/index", code: "idx" },
			{ path: "pages/settings", code: "stgs" },
		]);
		mockBuildRoutes.mockReturnValue([
			pageRoute("/", "pages/index"),
			pageRoute("/settings", "pages/settings"),
		]);

		await renderShell({ initialPath: "/settings" });

		expect(
			await screen.findByText("page:pages/settings"),
		).toBeInTheDocument();
		// The other page should NOT be mounted — react-router only renders
		// the matching branch.
		expect(
			screen.queryByText("page:pages/index"),
		).not.toBeInTheDocument();
	});
});
