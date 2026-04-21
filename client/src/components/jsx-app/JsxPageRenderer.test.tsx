/**
 * Component tests for JsxPageRenderer.
 *
 * This component is a thin state machine around the app-code-runtime +
 * app-code-resolver libraries. We mock both modules so the test doesn't
 * actually compile/evaluate user code — the assertions we care about are:
 *
 *   - the loading state renders before resolution settles
 *   - on success, the `createComponent()` result is rendered inside the
 *     error boundary
 *   - the right arguments are passed to `resolveAppComponentsFromFiles`
 *     and `createComponent` (compiled path vs. source path)
 *   - when the runtime throws, the error panel surfaces the message
 *   - when the rendered component itself throws, the JsxErrorBoundary
 *     fallback renders
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";
import type { AppCodeFile } from "@/lib/app-code-router";

const mockCreateComponent = vi.fn();
const mockResolve = vi.fn();
const mockExtractNames = vi.fn();

vi.mock("@/lib/app-code-runtime", () => ({
	createComponent: (...args: unknown[]) => mockCreateComponent(...args),
}));

vi.mock("@/lib/app-code-resolver", () => ({
	resolveAppComponentsFromFiles: (...args: unknown[]) =>
		mockResolve(...args),
	extractComponentNames: (src: string) => mockExtractNames(src),
}));

function makeFile(overrides: Partial<AppCodeFile> = {}): AppCodeFile {
	return {
		path: "pages/home",
		source: "export default () => <div>SRC</div>;",
		compiled: null,
		...overrides,
	};
}

beforeEach(() => {
	mockCreateComponent.mockReset();
	mockResolve.mockReset();
	mockExtractNames.mockReset();

	mockExtractNames.mockReturnValue([]);
	mockResolve.mockResolvedValue({});
	mockCreateComponent.mockImplementation(() => {
		return function RenderedPage() {
			return <div>MockedPage</div>;
		};
	});
});

afterEach(() => {
	vi.restoreAllMocks();
});

async function renderRenderer(
	file: AppCodeFile = makeFile(),
	extras: Partial<{
		userComponentNames: Set<string>;
		allFiles: AppCodeFile[];
		externalDeps: Record<string, Record<string, unknown>>;
	}> = {},
) {
	const { JsxPageRenderer } = await import("./JsxPageRenderer");
	return renderWithProviders(
		<JsxPageRenderer
			appId="app-1"
			file={file}
			userComponentNames={extras.userComponentNames ?? new Set()}
			allFiles={extras.allFiles}
			externalDeps={extras.externalDeps}
		/>,
	);
}

describe("JsxPageRenderer — success path", () => {
	it("renders the created component once the runtime resolves", async () => {
		await renderRenderer();
		expect(await screen.findByText("MockedPage")).toBeInTheDocument();
	});

	it("passes compiled code + true compiled flag when file.compiled is present", async () => {
		await renderRenderer(
			makeFile({ compiled: "COMPILED-CODE" }),
			{ externalDeps: { lodash: {} } },
		);
		await screen.findByText("MockedPage");

		expect(mockCreateComponent).toHaveBeenCalledTimes(1);
		const [codeArg, customArg, compiledFlag, depsArg] =
			mockCreateComponent.mock.calls[0];
		expect(codeArg).toBe("COMPILED-CODE");
		expect(customArg).toEqual({});
		expect(compiledFlag).toBe(true);
		expect(depsArg).toEqual({ lodash: {} });
	});

	it("falls back to source when compiled is not available", async () => {
		await renderRenderer(
			makeFile({ source: "RAW-SRC", compiled: null }),
		);
		await screen.findByText("MockedPage");

		const [codeArg, , compiledFlag] = mockCreateComponent.mock.calls[0];
		expect(codeArg).toBe("RAW-SRC");
		expect(compiledFlag).toBe(false);
	});

	it("resolves referenced components from the extracted names", async () => {
		mockExtractNames.mockReturnValue(["CustomButton"]);
		const comps = { CustomButton: () => <span>cb</span> };
		mockResolve.mockResolvedValue(comps);

		await renderRenderer(makeFile(), {
			userComponentNames: new Set(["CustomButton"]),
			allFiles: [makeFile({ path: "components/CustomButton" })],
		});
		await screen.findByText("MockedPage");

		expect(mockResolve).toHaveBeenCalledTimes(1);
		const [appId, names, userNames] = mockResolve.mock.calls[0];
		expect(appId).toBe("app-1");
		expect(names).toEqual(["CustomButton"]);
		expect(userNames).toBeInstanceOf(Set);
		expect((userNames as Set<string>).has("CustomButton")).toBe(true);

		// Those resolved components are handed to createComponent.
		expect(mockCreateComponent.mock.calls[0][1]).toBe(comps);
	});
});

describe("JsxPageRenderer — error paths", () => {
	it("renders the inline PageError panel when createComponent throws", async () => {
		mockCreateComponent.mockImplementation(() => {
			throw new Error("compile exploded");
		});

		await renderRenderer(makeFile({ path: "pages/broken" }));

		expect(await screen.findByText(/page error/i)).toBeInTheDocument();
		expect(
			screen.getByText(/failed to load pages\/broken/i),
		).toBeInTheDocument();
		expect(screen.getByText(/compile exploded/i)).toBeInTheDocument();
	});

	it("lets a throwing rendered component bubble to the JsxErrorBoundary", async () => {
		// Silence the React error log produced when the child throws.
		vi.spyOn(console, "error").mockImplementation(() => {});

		mockCreateComponent.mockImplementation(() => {
			return function ThrowingPage(): React.ReactElement {
				throw new Error("runtime boom");
			};
		});

		await renderRenderer(makeFile({ path: "pages/home" }));

		// Boundary's default fallback renders "Component Error" + the message.
		// happy-dom ALSO renders React's dev error overlay containing the same
		// text, so we just assert the message is present somewhere in the DOM.
		expect(
			await screen.findByText(/component error/i),
		).toBeInTheDocument();
		expect(screen.getAllByText(/runtime boom/i).length).toBeGreaterThan(0);
	});
});

describe("JsxPageRenderer — loading", () => {
	it("shows a skeleton before resolution completes", async () => {
		// Hold the resolver open until we manually resolve it.
		let resolveResolver: (v: Record<string, unknown>) => void = () => {};
		mockExtractNames.mockReturnValue(["A"]);
		mockResolve.mockImplementation(
			() =>
				new Promise((resolve) => {
					resolveResolver = resolve;
				}),
		);

		await renderRenderer(makeFile(), {
			userComponentNames: new Set(["A"]),
		});

		// Skeleton carries no text; check that no MockedPage is in the DOM yet
		// and that the component hasn't been created.
		expect(screen.queryByText("MockedPage")).not.toBeInTheDocument();
		expect(mockCreateComponent).not.toHaveBeenCalled();

		resolveResolver({});
		await waitFor(() =>
			expect(screen.getByText("MockedPage")).toBeInTheDocument(),
		);
	});
});
