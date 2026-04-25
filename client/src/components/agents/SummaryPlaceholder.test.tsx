/**
 * SummaryPlaceholder needs to prefer the run-level lifecycle state over
 * summary_status because the summarizer silently short-circuits on
 * non-completed runs — showing "Summary pending…" for a failed or running
 * run is misleading (the summarizer will never get there).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SummaryPlaceholder } from "./SummaryPlaceholder";

describe("SummaryPlaceholder", () => {
	it("shows 'Summary pending…' when summary_status is pending and run is completed", () => {
		render(<SummaryPlaceholder status="pending" runStatus="completed" />);
		expect(screen.getByText(/summary pending/i)).toBeInTheDocument();
	});

	it("shows 'Summary failed' when summary_status='failed' and run is completed", () => {
		render(<SummaryPlaceholder status="failed" runStatus="completed" />);
		expect(screen.getByText(/summary failed/i)).toBeInTheDocument();
	});

	it("shows 'Summarizing…' when summary_status='generating' and run is completed", () => {
		render(<SummaryPlaceholder status="generating" runStatus="completed" />);
		expect(screen.getByText(/summarizing/i)).toBeInTheDocument();
	});

	it("shows 'Run in progress…' when run is still running, regardless of summary_status", () => {
		render(<SummaryPlaceholder status="pending" runStatus="running" />);
		expect(screen.getByText(/run in progress/i)).toBeInTheDocument();
	});

	it("shows 'Run in progress…' when run is queued", () => {
		render(<SummaryPlaceholder status="pending" runStatus="queued" />);
		expect(screen.getByText(/run in progress/i)).toBeInTheDocument();
	});

	it("shows 'Run failed' when the run itself failed", () => {
		render(<SummaryPlaceholder status="pending" runStatus="failed" />);
		expect(screen.getByText(/run failed/i)).toBeInTheDocument();
	});

	it("shows 'Budget exceeded' for budget_exceeded runs", () => {
		render(<SummaryPlaceholder status="pending" runStatus="budget_exceeded" />);
		expect(screen.getByText(/budget exceeded/i)).toBeInTheDocument();
	});

	it("shows 'Run cancelled' for cancelled runs", () => {
		render(<SummaryPlaceholder status="pending" runStatus="cancelled" />);
		expect(screen.getByText(/run cancelled/i)).toBeInTheDocument();
	});

	it("shows '—' when summary is completed", () => {
		render(<SummaryPlaceholder status="completed" runStatus="completed" />);
		expect(screen.getByText("—")).toBeInTheDocument();
	});

	it("falls back to 'Summary pending…' when runStatus is not provided", () => {
		// Backwards-compat check: callers that haven't been updated still get
		// the old behavior.
		render(<SummaryPlaceholder status="pending" />);
		expect(screen.getByText(/summary pending/i)).toBeInTheDocument();
	});
});
