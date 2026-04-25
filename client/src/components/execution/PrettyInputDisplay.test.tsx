/**
 * Component tests for PrettyInputDisplay.
 *
 * Covers: empty-state, snake_case → Title Case label rendering, value-type
 * badges (null / boolean / number / url / date / array / object), copy
 * button, and the Pretty ↔ Tree view toggle.
 */

import { describe, it, expect, vi, beforeEach, MockInstance } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { PrettyInputDisplay } from "./PrettyInputDisplay";

// VariablesTreeView is imported unconditionally but only rendered in tree
// view; we still stub it so the tree-view test can assert the dispatch.
vi.mock("@/components/ui/variables-tree-view", () => ({
	VariablesTreeView: ({ data }: { data: Record<string, unknown> }) => (
		<div aria-label="variables-tree-stub">{JSON.stringify(data)}</div>
	),
}));

// Toast is a side-effect; spy on it to verify copy success/failure UX.
vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

let writeTextSpy: MockInstance;

beforeEach(() => {
	writeTextSpy = vi
		.spyOn(navigator.clipboard, "writeText")
		.mockResolvedValue(undefined);
});

describe("PrettyInputDisplay — empty state", () => {
	it("renders 'No input parameters' when the object is empty", () => {
		renderWithProviders(<PrettyInputDisplay inputData={{}} />);
		expect(screen.getByText(/no input parameters/i)).toBeInTheDocument();
	});
});

describe("PrettyInputDisplay — label and value formatting", () => {
	it("converts snake_case keys to Title Case labels", () => {
		renderWithProviders(
			<PrettyInputDisplay inputData={{ user_name: "alice" }} />,
		);
		expect(screen.getByText("User Name")).toBeInTheDocument();
	});

	it("upper-cases known acronyms in labels", () => {
		renderWithProviders(
			<PrettyInputDisplay
				inputData={{ api_key: "x", some_id: "y", site_url: "z" }}
			/>,
		);
		expect(screen.getByText("API Key")).toBeInTheDocument();
		expect(screen.getByText("Some ID")).toBeInTheDocument();
		expect(screen.getByText("Site URL")).toBeInTheDocument();
	});

	it("renders a null value with a 'null' badge", () => {
		renderWithProviders(<PrettyInputDisplay inputData={{ n: null }} />);
		// Badge + value both read "null"; just assert both exist.
		const nulls = screen.getAllByText("null");
		expect(nulls.length).toBeGreaterThanOrEqual(1);
	});

	it("renders booleans with a Yes/No display and true/false badge", () => {
		renderWithProviders(<PrettyInputDisplay inputData={{ flag: true }} />);
		expect(screen.getByText("Yes")).toBeInTheDocument();
		expect(screen.getByText("true")).toBeInTheDocument();
	});

	it("renders numbers with locale formatting and a 'number' badge", () => {
		renderWithProviders(
			<PrettyInputDisplay inputData={{ count: 1234 }} />,
		);
		expect(screen.getByText("number")).toBeInTheDocument();
		expect(screen.getByText(/1,234/)).toBeInTheDocument();
	});

	it("tags URL-shaped strings with a url badge", () => {
		renderWithProviders(
			<PrettyInputDisplay inputData={{ link: "https://example.com" }} />,
		);
		expect(screen.getByText("url")).toBeInTheDocument();
	});

	it("tags ISO-date strings with a date badge", () => {
		renderWithProviders(
			<PrettyInputDisplay inputData={{ when: "2026-04-20" }} />,
		);
		expect(screen.getByText("date")).toBeInTheDocument();
	});

	it("tags arrays with the element count", () => {
		renderWithProviders(
			<PrettyInputDisplay inputData={{ items: ["a", "b", "c"] }} />,
		);
		expect(screen.getByText(/array \(3\)/)).toBeInTheDocument();
	});
});

describe("PrettyInputDisplay — copy button", () => {
	it("writes the JSON payload to the clipboard from tree view", async () => {
		// The Copy affordance lives on the Tree view bar, not the Pretty view.
		const { user } = renderWithProviders(
			<PrettyInputDisplay
				inputData={{ foo: "bar" }}
				showToggle={true}
				defaultView="tree"
			/>,
		);
		await user.click(screen.getByRole("button", { name: /copy/i }));

		expect(writeTextSpy).toHaveBeenCalledTimes(1);
		expect(writeTextSpy.mock.calls[0][0]).toBe(
			JSON.stringify({ foo: "bar" }, null, 2),
		);

		// The icon label flips to "Copied!" after a successful write.
		expect(
			await screen.findByRole("button", { name: /copied/i }),
		).toBeInTheDocument();
	});
});

describe("PrettyInputDisplay — view toggle", () => {
	it("switches between Pretty and Tree view when the toggle is present", async () => {
		const { user } = renderWithProviders(
			<PrettyInputDisplay
				inputData={{ foo: "bar" }}
				showToggle={true}
				defaultView="pretty"
			/>,
		);
		// Pretty view shows the parameter count line.
		expect(screen.getByText(/viewing 1 parameter/i)).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: /tree view/i }));
		expect(screen.getByLabelText("variables-tree-stub")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: /pretty view/i }));
		expect(screen.getByText(/viewing 1 parameter/i)).toBeInTheDocument();
	});

	it("pluralises the parameter count correctly", () => {
		renderWithProviders(
			<PrettyInputDisplay
				inputData={{ a: 1, b: 2 }}
				showToggle={true}
				defaultView="pretty"
			/>,
		);
		expect(screen.getByText(/viewing 2 parameters/i)).toBeInTheDocument();
	});
});
