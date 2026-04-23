import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// react-diff-viewer-continued uses CSS-in-JS that doesn't run in jsdom; mock
// it so tests focus on our component's own structure and branching logic.
vi.mock("react-diff-viewer-continued", () => ({
	default: ({
		oldValue,
		newValue,
	}: {
		oldValue: string;
		newValue: string;
	}) => (
		<div data-testid="mock-diff-viewer">
			<span data-testid="diff-old">{oldValue}</span>
			<span data-testid="diff-new">{newValue}</span>
		</div>
	),
	DiffMethod: { WORDS: "diffWords" },
}));

import { PromptDiffViewer } from "./PromptDiffViewer";

beforeEach(() => {
	vi.clearAllMocks();
});

describe("PromptDiffViewer", () => {
	it("renders before and after content", () => {
		render(
			<PromptDiffViewer
				before="You are a helpful agent."
				after="You are a helpful, concise agent."
			/>,
		);
		expect(screen.getByTestId("prompt-diff-viewer")).toBeInTheDocument();
		expect(screen.getByText(/you are a helpful agent\./i)).toBeInTheDocument();
		expect(
			screen.getByText(/you are a helpful, concise agent\./i),
		).toBeInTheDocument();
	});

	it("renders an empty-state hint when before and after are identical", () => {
		render(
			<PromptDiffViewer before="Same prompt." after="Same prompt." />,
		);
		expect(screen.getByTestId("prompt-diff-empty")).toHaveTextContent(
			/no changes/i,
		);
	});

	it("handles an empty before (fresh prompt)", () => {
		render(<PromptDiffViewer before="" after="Brand new prompt." />);
		expect(screen.getByTestId("prompt-diff-viewer")).toBeInTheDocument();
		expect(screen.getByText(/brand new prompt\./i)).toBeInTheDocument();
	});
});
