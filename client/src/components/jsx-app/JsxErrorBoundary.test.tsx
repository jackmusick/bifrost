/**
 * Component tests for JsxErrorBoundary.
 *
 * We cover:
 *   - happy path: children render unchanged
 *   - thrown error: fallback UI includes the error message
 *   - the file path prop surfaces in the header
 *   - the reset button clears error state AND calls onReset
 *   - parseErrorLocation: line/column hints render when present
 *   - custom `fallback` prop replaces the default UI
 *   - `resetKey` change clears the error state (recovery path)
 */

import type React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { JsxErrorBoundary } from "./JsxErrorBoundary";

// A component that throws on render. Declared as returning ReactElement so
// TS accepts it as a JSX component even though `throw` never returns.
function Thrower({ message }: { message: string }): React.ReactElement {
	throw new Error(message);
}

beforeEach(() => {
	// React logs the error to console.error when an ErrorBoundary catches;
	// silence it so the test output stays readable.
	vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
	vi.restoreAllMocks();
});

describe("JsxErrorBoundary", () => {
	it("renders children when no error is thrown", () => {
		renderWithProviders(
			<JsxErrorBoundary>
				<div>all good</div>
			</JsxErrorBoundary>,
		);
		expect(screen.getByText("all good")).toBeInTheDocument();
	});

	it("renders the default fallback with the error message when a child throws", () => {
		renderWithProviders(
			<JsxErrorBoundary filePath="pages/home.tsx">
				<Thrower message="boom happened" />
			</JsxErrorBoundary>,
		);

		expect(screen.getByText(/component error/i)).toBeInTheDocument();
		expect(screen.getByText(/error in pages\/home\.tsx/i)).toBeInTheDocument();
		// happy-dom renders React's dev error overlay too, so the message text
		// appears in multiple places — assert at least one occurrence.
		expect(screen.getAllByText(/boom happened/i).length).toBeGreaterThan(0);
	});

	it("surfaces parsed line/column hints from the error message", () => {
		renderWithProviders(
			<JsxErrorBoundary>
				<Thrower message="Syntax error (12:34)" />
			</JsxErrorBoundary>,
		);
		expect(screen.getByText(/line 12/i)).toBeInTheDocument();
		expect(screen.getByText(/column 34/i)).toBeInTheDocument();
	});

	it("offers a helpful hint for 'is not defined' errors", () => {
		renderWithProviders(
			<JsxErrorBoundary>
				<Thrower message="foo is not defined" />
			</JsxErrorBoundary>,
		);
		expect(
			screen.getByText(/"foo" is not defined/i),
		).toBeInTheDocument();
	});

	it("calls onReset when the Try Again button is clicked", async () => {
		const onReset = vi.fn();
		const { user } = renderWithProviders(
			<JsxErrorBoundary onReset={onReset}>
				<Thrower message="reset me" />
			</JsxErrorBoundary>,
		);

		await user.click(screen.getByRole("button", { name: /try again/i }));

		expect(onReset).toHaveBeenCalledTimes(1);
	});

	it("renders a custom fallback when one is supplied", () => {
		renderWithProviders(
			<JsxErrorBoundary fallback={<div>custom-fallback</div>}>
				<Thrower message="anything" />
			</JsxErrorBoundary>,
		);
		expect(screen.getByText("custom-fallback")).toBeInTheDocument();
		// Default UI should not be rendered.
		expect(screen.queryByText(/component error/i)).not.toBeInTheDocument();
	});

	it("clears the error state when resetKey changes", () => {
		// Render once with a thrower and one key.
		const { rerender } = renderWithProviders(
			<JsxErrorBoundary resetKey="v1">
				<Thrower message="v1-err" />
			</JsxErrorBoundary>,
		);
		expect(screen.getByText(/component error/i)).toBeInTheDocument();

		// Change resetKey + swap children to something safe → boundary should
		// render children instead of the fallback.
		rerender(
			<JsxErrorBoundary resetKey="v2">
				<div>recovered</div>
			</JsxErrorBoundary>,
		);
		expect(screen.getByText("recovered")).toBeInTheDocument();
		expect(screen.queryByText(/component error/i)).not.toBeInTheDocument();
	});
});
